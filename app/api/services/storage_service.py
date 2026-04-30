"""app/api/services/storage_service.py — GCS file storage (replaces BYTEA)."""
import logging
import os
import uuid
from datetime import date

log = logging.getLogger(__name__)

_BUCKET_NAME: str | None = None


def _gcs_available() -> bool:
    """Return True only if GCS bucket name and credentials are configured."""
    return bool(os.environ.get("GCS_BUCKET_NAME", ""))


def _bucket():
    global _BUCKET_NAME
    if _BUCKET_NAME is None:
        _BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "")
        if not _BUCKET_NAME:
            raise RuntimeError("GCS_BUCKET_NAME env var not set")
    from google.cloud import storage
    client = storage.Client()
    return client.bucket(_BUCKET_NAME)


def upload_file(file_bytes: bytes, file_name: str, mime_type: str, tenant_id: str) -> str | None:
    """Upload bytes to GCS. Returns gcs_path, or None if GCS is not configured (fallback to DB)."""
    if not _gcs_available():
        log.info("action=gcs_skip_no_bucket file=%s — will store in DB", file_name)
        return None
    try:
        today = date.today().isoformat()
        safe_name = file_name.replace("/", "_").replace("\\", "_")
        gcs_path = f"{tenant_id}/{today}/{uuid.uuid4().hex}_{safe_name}"
        bucket = _bucket()
        blob = bucket.blob(gcs_path)
        blob.upload_from_string(file_bytes, content_type=mime_type or "application/octet-stream")
        log.info("action=gcs_upload path=%s size=%d", gcs_path, len(file_bytes))
        return gcs_path
    except Exception as e:
        log.warning("action=gcs_upload_failed error=%s — falling back to DB storage", e)
        return None


def download_file(gcs_path: str) -> bytes:
    """Download bytes from GCS by path. Raises on failure (caller should fallback to DB)."""
    bucket = _bucket()
    blob = bucket.blob(gcs_path)
    data = blob.download_as_bytes()
    log.info("action=gcs_download path=%s size=%d", gcs_path, len(data))
    return data


def safe_download(gcs_path: str | None, db_fallback: bytes | None = None) -> bytes | None:
    """Try GCS download; if it fails or gcs_path is None, return db_fallback bytes."""
    if gcs_path:
        try:
            return download_file(gcs_path)
        except Exception as e:
            log.warning("action=gcs_download_failed path=%s fallback=%s err=%s",
                        gcs_path, "db" if db_fallback else "none", e)
    return bytes(db_fallback) if db_fallback else None


def delete_file(gcs_path: str) -> None:
    """Delete a GCS object. Silently ignores not-found."""
    try:
        bucket = _bucket()
        bucket.blob(gcs_path).delete()
        log.info("action=gcs_delete path=%s", gcs_path)
    except Exception as e:
        log.warning("gcs_delete failed (non-fatal): %s — %s", gcs_path, e)


def generate_signed_url(gcs_path: str, expires_in: int = 900) -> str | None:
    """Generate a temporary signed URL for direct browser access (default 15 min).
    Returns None if GCS is unavailable or signing fails."""
    if not _gcs_available():
        return None
    try:
        import datetime
        from google.oauth2 import service_account
        bucket = _bucket()
        blob = bucket.blob(gcs_path)
        # Try with service account credentials (required for signing)
        creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        if creds_path and os.path.exists(creds_path):
            creds = service_account.Credentials.from_service_account_file(creds_path)
            url = blob.generate_signed_url(
                expiration=datetime.timedelta(seconds=expires_in),
                method="GET",
                credentials=creds,
                version="v4",
            )
        else:
            # Fallback: unsigned public URL pattern (works only for public buckets)
            url = blob.generate_signed_url(
                expiration=datetime.timedelta(seconds=expires_in),
                method="GET",
                version="v4",
            )
        log.info("action=gcs_signed_url path=%s expires=%ds", gcs_path, expires_in)
        return url
    except Exception as e:
        log.warning("generate_signed_url failed path=%s: %s", gcs_path, e)
        return None

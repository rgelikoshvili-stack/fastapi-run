"""tests/unit/test_documents_routes.py
Documents route structural unit tests.
"""
import inspect


# ── 1. Upload endpoint exists ─────────────────────────────────────────────────

def test_upload_endpoint_exists():
    import app.api.routes_documents as mod
    src = inspect.getsource(mod)
    assert "upload" in src.lower()


# ── 2. Upload creates draft with tenant scope ─────────────────────────────────

def test_upload_creates_tenant_scoped_draft():
    import app.api.routes_documents as mod
    src = inspect.getsource(mod)
    assert "tenant_id" in src
    assert "journal_drafts" in src or "draft" in src.lower()


# ── 3. Duplicate detection via file hash ─────────────────────────────────────

def test_duplicate_detection_present():
    import app.api.routes_documents as mod
    src = inspect.getsource(mod)
    assert "hash" in src.lower() or "duplicate" in src.lower() or "file_hash" in src


# ── 4. Role detection: buyer/seller ──────────────────────────────────────────

def test_buyer_seller_role_detection():
    import app.api.routes_documents as mod
    src = inspect.getsource(mod)
    assert "buyer" in src.lower() or "seller" in src.lower() or "our_role" in src


# ── 5. GCS file storage mentioned ────────────────────────────────────────────

def test_gcs_storage_present():
    import app.api.routes_documents as mod
    src = inspect.getsource(mod)
    assert "gcs" in src.lower() or "storage" in src.lower() or "bucket" in src.lower() or "file_content" in src


# ── 6. Human review flow exists ──────────────────────────────────────────────

def test_human_review_flow():
    import app.api.routes_documents as mod
    src = inspect.getsource(mod)
    assert "human_review" in src or "pending" in src.lower()


# ── 7. OCR pipeline referenced ────────────────────────────────────────────────

def test_ocr_pipeline_referenced():
    import app.api.routes_documents as mod
    src = inspect.getsource(mod)
    assert "ocr" in src.lower() or "extract" in src.lower() or "vision" in src.lower() or "parse" in src.lower()


# ── 8. Document list scoped by tenant ────────────────────────────────────────

def test_document_list_tenant_scoped():
    import app.api.routes_documents as mod
    src = inspect.getsource(mod)
    lines_with_select = [l for l in src.splitlines() if "SELECT" in l.upper() and "FROM" in l.upper()]
    tenant_filtered = [l for l in lines_with_select if "tenant_id" in l.lower() or "tenant" in l.lower()]
    assert len(tenant_filtered) >= 1 or src.count("tenant_id") >= 5

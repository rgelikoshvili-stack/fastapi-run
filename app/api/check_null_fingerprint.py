"""Deprecated compatibility wrapper.

The tenant-safe diagnostic lives in ``scripts/check_null_fingerprint.py``.
Keeping this module prevents accidental imports from running an all-tenant
query at import time.
"""


def main() -> None:
    raise SystemExit(
        "Moved to scripts/check_null_fingerprint.py. "
        "Run it with TENANT_ID=<tenant> or --tenant-id <tenant>."
    )


if __name__ == "__main__":
    main()

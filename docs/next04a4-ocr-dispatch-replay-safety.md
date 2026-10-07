# NEXT-04A4 OCR dispatch and callback replay safety

Bridge Hub dispatches eligible persisted PDF documents from the authenticated
document-upload flow only. Dispatch is disabled unless
`OCR_WORKER_DISPATCH_ENABLED=1` and the worker URL/HMAC configuration are
present. `OCR_CALLBACK_BASE_URL` is an explicit server configuration value;
the application never derives it from a request `Host` header. HTTPS is
required outside `TEST_MODE` (which is intended only for local tests).

For each dispatch, Bridge Hub creates the job ID and short-lived signed
callback token, registers the job in the tenant-scoped `ocr_callback_receipts`
table, then sends `callback_url`, `callback_token`, document/job identifiers,
and the GCS object path to the worker. The token binds tenant, document, job,
job type, callback purpose/audience, issue time, and expiry. The token is
sensitive and must not be logged. The worker request is separately HMAC-signed.

The callback must return the signed token and matching document/job/type
identifiers, and must have a valid worker HMAC. Only then does Bridge Hub enter
the signed tenant's transaction-local DB context. The receipt row serializes
first acceptance and concurrent retries. It stores a SHA-256 fingerprint of
canonical result fields: exact duplicates are acknowledged without repeating
the initial document write, while conflicting results receive a generic 409
and increment a durable conflict counter. Pipeline work is tied to the accepted
receipt and retries are guarded against creating a second source-document
draft. Migration `014_ocr_callback_receipts.sql` is forward-only and must be
applied only through an explicitly approved migration process; this change
does not apply it to any production database.

## External contract status

The Hetzner worker implementation is not present in this repository. Therefore
its acceptance and unchanged return of `callback_url`, `callback_token`,
`job_id`, and callback identifiers, and its callback HMAC behavior, have not
been verified end-to-end. The Bridge Hub dispatch test is a strict mocked
contract test, not proof of external worker compatibility. Do not enable
production dispatch or treat OCR as rollout-ready until the external worker
contract is independently verified.

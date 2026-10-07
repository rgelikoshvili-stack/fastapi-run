# NEXT-04A3 OCR worker callback contract

## Bridge Hub source behavior

`app/api/services/worker_client.py::dispatch_job` is the only dispatcher
implementation found in this repository. It creates a collision-resistant
`job_id`, creates a short-lived HS256 job claim from the current server-side
tenant context, and sends the `callback_token`, job type, tenant hint, document
IDs, and job ID in the authenticated `POST {HETZNER_WORKER_URL}/job` payload.
The token is purpose-bound to `ocr_callback`, includes tenant/document/job
identity, issued/expiry times, and an explicit Bridge Hub callback audience.
The dispatch request is HMAC-signed with `X-Worker-Signature`.

No call site for `dispatch_job()` exists in this repository. It also does not
send a `callback_url`; callback URL configuration must therefore be supplied
by the worker deployment/contract, not inferred from this source. There is no
worker implementation or contract document in this repository to verify that
the token is retained and echoed.

The callback endpoint requires the worker HMAC first, then the Bridge Hub job
token. The signed tenant/document/type/job ID/audience are authoritative; body
tenant, document, type, and job ID are required to match. Only after validation
does the route enter `tenant_db_context` and update tenant-scoped document data.
Legacy HMAC-only callbacks are rejected.

## Required worker behavior (not yet verified externally)

The worker implementation must:

1. Verify the request HMAC over the exact raw request bytes.
2. Persist and treat `callback_token`, `job_id`, `callback_doc_id`, and
   `job_type` as opaque immutable callback metadata for that job.
3. POST to the deployment-configured Bridge Hub `/worker/result` URL with the
   exact unchanged callback token and matching `job_id`, `doc_id`, and
   `job_type`, plus result fields and a valid `X-Worker-Signature` over the
   exact raw response bytes.
4. Never reconstruct/replace the callback token or derive tenant authority
   from document contents or callback JSON.

The token is bearer-like sensitive operational data: it must not be logged.
The HMAC shared secret must not be included in payloads or logs.

## Remaining compatibility and replay gaps

Repository evidence cannot prove that the external worker accepts or echoes
this contract: **EXTERNAL_OCR_WORKER_COMPATIBILITY = CANNOT_VERIFY**.

There is no durable OCR job/callback receipt or idempotency key in the current
schema/route. A valid repeated callback currently repeats document updates and
can retrigger processing; a conflicting callback for the same signed job is
not durably detected. This change does not claim replay safety. Before
end-to-end rollout, define and test a durable per-job completion/replay rule
under tenant RLS, including how identical retries are acknowledged and
conflicting results are rejected without overwriting trusted data.

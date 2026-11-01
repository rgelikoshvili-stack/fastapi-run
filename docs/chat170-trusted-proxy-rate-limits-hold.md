# Bridge Hub — Chat170: trusted proxy and rate-limit identity

**Date:** 2026-10-27. **Release state: HOLD.** Draft PR #154 only.
**Last CI-verified CODE SHA:** `2b21f243699d06de7442d7667e4f2872e3838381`.
No Production, Cloud SQL, public configuration, main, or original Windows Git changed.

## Confirmed vulnerability and correction

Prior code trusted the leftmost HTTP `X-Forwarded-For` value as the client IP in BOTH:
- `app/api/security.py::_real_ip` used by SlowAPI route decorators.
- `app/api/middleware/rate_limit_middleware.py::_get_client_ip` used by the category limiter for unauthenticated/non-user-specific keys.

An external caller could rotate an untrusted XFF value and evade per-IP quotas on some request paths. Authentication had separately used the socket peer in the category limiter, but SlowAPI's independent limiter still accepted the attacker-selected XFF.

**Draft correction:** both limiters now use a single `app/api/client_ip.py::client_ip_for_rate_limit` identity source:
1. No configured allowlist: **always use the immediate ASGI socket peer**, ignoring XFF.
2. `RATE_LIMIT_TRUSTED_PROXY_CIDRS`: optional, explicit comma-separated trusted ingress peer CIDRs. It is intentionally **unset by default**.
3. Use a forwarded chain only if the **immediate peer** is a valid IP in the allowlist; resolve right-to-left, skipping trusted hops and choosing the first untrusted hop.
4. Invalid CIDRs, internet-wide `/0`, malformed/duplicate XFF, unknown hop, oversized header, excessive chain length, or all-proxy chain: fall back to the socket peer.
5. Dockerfile and Procfile use `uvicorn ... --no-proxy-headers`. This is essential: ASGI `request.client.host` must remain the real socket peer before our check runs. Review other startup paths if adopted.

## Independently verified CI evidence

- [Synthetic PostgreSQL 15/16 workflow](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40537626720): **137 passed PostgreSQL 15**, **137 passed PostgreSQL 16**.
- [Backend/frontend workflow](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40537627040): backend **7,998 passed, 3 skipped**, additional integration smoke **1 passed**, frontend PASS; deploy **SKIPPED**.
- [NEXT-01 tenant membership](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40537627120): PASS.
- [NEXT-04A fail-closed RLS](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40537626988): PASS.
- New `tests/unit/test_chat170_trusted_proxy_rate_limits.py` covers no-trust spoofing, malicious header rotation still producing 429 at the documented AUTH/POSTING thresholds, explicit trusted peers, right-to-left IPv4/IPv6 chains, duplicate/malformed/overlong XFF, invalid/broad allowlists, and both Uvicorn startup entrypoints.
- These are synthetic CI proofs only. **No real Cloud Run forwarding path or external load balancer was tested.**

## Mandatory isolated staging preflight before any configuration

1. Deploy on a fully **isolated**, approved staging service only. Retain `RATE_LIMIT_TRUSTED_PROXY_CIDRS` unset and `--no-proxy-headers`; verify the socket peer as seen by ASGI using synthetic test requests without logging production personal IP addresses.
2. Confirm the **actual immediate proxy's IP addresses/networks** via infrastructure configuration and controlled experiments. Do **not** guess Google Cloud/Cloud Run address ranges or allowlist the entire internet/private address space.
3. Prove that the trusted proxy **overwrites or reliably appends verified prior-hop IPs** to XFF. Confirm attacker-supplied leftmost XFF cannot select the key; test IPv4, IPv6, multiple CDN/LB hops, duplicate headers, malformed inputs and direct bypass routes.
4. Only after these proofs, consider setting exact `RATE_LIMIT_TRUSTED_PROXY_CIDRS` on isolated staging. With an empty allowlist, all clients behind the same ingress may share a quota and produce false 429s. This is a safe but potentially disruptive default.
5. Test legitimate login, OAuth callback, password reset, frontend and HTTPS redirect behavior because disabling Uvicorn's implicit proxy rewrites can change request scheme/URL behavior.
6. Verify BOTH limiter backends use a **durable shared quota store** across at least two replicas; confirm load balancing cannot amplify allowed requests and Redis failures follow an approved fail-closed or edge-enforced security policy. Neither global multi-replica proof nor edge gate is completed.
7. Verify `X-Forwarded-Proto` in `main.py::https_redirect`: it is still consumed without this allowlist and requires a separate host/scheme trust audit. Canonical HTTPS origin must not be derived from untrusted Host data.
8. Maintain PR #154 as OPEN/DRAFT. Do not merge PR #153/#154 or change main/Cloud Run/Cloud SQL without explicit owner approval.

## Outstanding release blockers

- **Critical:** quota storage currently supports in-memory fallback. SlowAPI uses in-memory by default without Redis, and the category Redis backend can downgrade to per-instance memory when Redis fails. Production Cloud Run scales to multiple replicas; this is **not proven secure** against cross-instance circumvention.
- Actual Cloud Run/proxy socket peer and XFF semantics, IP allowlist values, HTTPS redirect trust and source-deployed startup flags require isolated verification.
- Migrations 014/015/016, real tenant RLS/runtime grants, JWT revocation rollback, SMTP/OAuth/financial E2E, Cloud SQL backups/PITR/restore drill and Windows repository integrity remain HOLD.

**Decision: security patch and disposable tests PASS; staging and Production release gates remain HOLD.**

# Bridge Hub — H39 Local Docker Availability / Evidence Capture Plan

## 1. Purpose

This document defines the H39 plan for capturing Docker availability evidence safely before any Docker provisioning execution is authorized. It establishes what evidence is needed, how it must be captured, redaction rules, local-only proof requirements, the Docker evidence packet shape, no-go blockers, and decision outputs.

**H39 is docs/tests only.**

- H39 does NOT execute Docker.
- H39 does NOT run `docker version`.
- H39 does NOT run `docker pull`.
- H39 does NOT run `docker run`.
- H39 does NOT create a Docker container.
- H39 does NOT create a Docker volume.
- H39 does NOT create a DB.
- H39 does NOT connect to a DB.
- H39 does NOT run psql.
- H39 does NOT run createdb / dropdb / pg_isready.
- H39 does NOT execute SQL.
- H39 does NOT run migrations.
- H39 does NOT load fixture data.
- H39 does NOT call runtime report APIs.
- H39 does NOT enable `POSTED_LEDGER_REPORTS_ENABLED`.
- H39 does NOT mutate Cloud Run env vars.
- H39 does NOT change production behavior.

All rules in this document describe future evidence planning only. Nothing is executed or provisioned in H39.

---

## 2. H37-H38 Context

The combined H37-H38 bundle was live verified (PR #76, SHA abcd14f2f027c5c207fc6ced593695a2e257dfe0):

| Item | Status |
|---|---|
| H37 decision | `BLOCKED_DOCKER_NOT_EXECUTED` |
| H38 decision | `BLOCKED_MISSING_H37_EVIDENCE` |
| Docker evidence available | No — not captured |
| DB provisioned | No |
| Docker executed | No |
| H37 evidence packet | Not produced |
| H38 `ready_for_h38` | `false` |

**H39 therefore defines how to capture the Docker availability evidence that H37 requires before any provisioning execution can proceed.**

The production flag `POSTED_LEDGER_REPORTS_ENABLED` **remains OFF** throughout H39.

---

## 3. Evidence Capture Scope

The following evidence items must be captured before Docker provisioning execution is authorized:

| # | Evidence Item | Description |
|---|---|---|
| EV1 | Docker installed proof | Confirmation that Docker is installed on the local machine |
| EV2 | Docker daemon available proof | Confirmation that Docker daemon is running and responsive |
| EV3 | Docker version proof | `docker version` output captured and redacted if needed |
| EV4 | Local-only host proof | Docker context confirmed as local (not remote/cloud/production) |
| EV5 | User permission proof | Current user can execute Docker commands without sudo error |
| EV6 | No production network proof | Docker context does not route to production network |
| EV7 | No Cloud Run mutation proof | Cloud Run service env vars were not modified |
| EV8 | No production DB connection proof | No connection attempted to production DB |
| EV9 | No Balance.ge activation proof | Balance.ge connector remains demo_mode / unconfigured |
| EV10 | No feature flag enablement proof | `POSTED_LEDGER_REPORTS_ENABLED` remains OFF/absent |

All 10 evidence items must be captured and recorded before `ready_for_preflight` can be set to `true`.

---

## 4. Future Evidence Commands

**[FUTURE — NOT EXECUTED IN H39]**

The commands below are documentation only. They describe what must be run at evidence capture time by a human operator on their local machine. They are forbidden in H39.

```
[FUTURE] Check Docker installation (NOT EXECUTED IN H39)
  docker --version

[FUTURE] Confirm Docker daemon running (NOT EXECUTED IN H39)
  docker version

[FUTURE] Inspect Docker info (NOT EXECUTED IN H39)
  docker info

[FUTURE] List Docker contexts (NOT EXECUTED IN H39)
  docker context ls

[FUTURE] List running containers (NOT EXECUTED IN H39)
  docker ps

[FUTURE] List volumes (NOT EXECUTED IN H39)
  docker volume ls

[FUTURE] List networks (NOT EXECUTED IN H39)
  docker network ls
```

These commands must be run only by the engineering owner at evidence capture time, with outputs reviewed and redacted before recording.

---

## 5. Evidence Redaction Rules

All evidence collected by future Docker availability commands must follow these redaction rules before being recorded:

| # | Rule |
|---|---|
| R1 | No raw secrets in any captured output |
| R2 | No API tokens or access keys |
| R3 | No passwords — replace with `***` |
| R4 | No full connection strings with password |
| R5 | No production hostnames — replace with `[redacted]` |
| R6 | No API keys in any captured output |
| R7 | Screenshots and log snippets must be reviewed before inclusion in evidence packet |
| R8 | Evidence may include only non-sensitive local Docker metadata (version, context name, status) |
| R9 | Any line containing a secret-like pattern blocks evidence acceptance |
| R10 | Evidence reviewer must sign off that redaction is complete |

---

## 6. Local-Only Proof Requirements

Docker evidence is only acceptable if the following local-only constraints are met:

| # | Requirement | Acceptable | Forbidden |
|---|---|---|---|
| L1 | Docker context | `default` / local Desktop context | Remote context, cloud context |
| L2 | Docker host | `localhost` / `unix:///var/run/docker.sock` / `npipe:////./pipe/docker_engine` | Remote TCP host |
| L3 | Production cluster | Not connected | Any Kubernetes / GKE / Cloud Run cluster |
| L4 | Production DB host | Not in evidence | Any host containing production markers |
| L5 | Cloud Run mutation | Not triggered | Any `gcloud run services update` |
| L6 | Production network | Not routed | Any production VPC / subnet |

Any violation of L1–L6 triggers `BLOCKED_REMOTE_CONTEXT` or `BLOCKED_PRODUCTION_RISK`.

---

## 7. Docker Evidence Packet

At evidence capture time, the following packet must be produced and recorded. This packet is **NOT produced in H39**.

```json
{
  "docker_evidence_id": "string — unique ID, e.g. DOCKER-EV-2026-001",
  "docker_installed": false,
  "docker_daemon_available": false,
  "docker_version": "string — from docker version output",
  "docker_context": "string — from docker context ls",
  "host_classification": "local_only | unknown | remote | production_risk",
  "version_proof_reference": "string — file/artifact path of captured docker version output",
  "context_proof_reference": "string — file/artifact path of captured docker context ls output",
  "permission_proof_reference": "string — confirmation user can run docker",
  "no_production_network_proof": "string — confirmation of local-only network",
  "no_cloud_run_mutation_proof": "string — confirmation Cloud Run not modified",
  "no_production_db_connection_proof": "string — confirmation no production DB touched",
  "no_balance_ge_activation_proof": "string — balance connector remains demo_mode",
  "no_feature_flag_enablement_proof": "string — POSTED_LEDGER_REPORTS_ENABLED remains OFF",
  "redaction_checked": false,
  "production_risk": false,
  "ready_for_preflight": false,
  "created_at": "ISO 8601 UTC — filled at evidence capture time",
  "created_by": "Bridge Hub"
}
```

### Required Fields

All 19 fields are required. A packet missing any field is incomplete and cannot authorize H40 preflight gate evaluation.

### `ready_for_preflight` Rules

| Condition | `ready_for_preflight` |
|---|---|
| All EV1–EV10 captured; redaction confirmed; host_classification = local_only | `true` |
| Any EV item missing | `false` |
| Docker unavailable | `false` |
| Remote or production context detected | `false` |
| Raw secret in evidence | `false` |
| Redaction not confirmed | `false` |

---

## 8. H39 No-Go Blockers

Any of the following blocks H39 evidence from being accepted:

| # | Blocker | Severity |
|---|---|---|
| HB1 | Docker not installed | HIGH |
| HB2 | Docker daemon unavailable | HIGH |
| HB3 | Remote Docker context active | CRITICAL |
| HB4 | Production or cloud Docker context active | CRITICAL |
| HB5 | Raw secret detected in evidence | CRITICAL |
| HB6 | Production hostname in evidence | CRITICAL |
| HB7 | Owner approval missing | HIGH |
| HB8 | Cleanup policy missing | HIGH |
| HB9 | Host classification unclear or unknown | HIGH |

---

## 9. H39 Decision Outputs

| Decision Output | Meaning | Condition |
|---|---|---|
| `READY_FOR_H40_PREFLIGHT` | All EV1–EV10 captured; redaction confirmed; local-only; packet complete | All evidence confirmed; `ready_for_preflight: true` |
| `BLOCKED_DOCKER_EVIDENCE_NOT_CAPTURED` | H39 is docs/tests only; no evidence captured | Current H39 status |
| `BLOCKED_DOCKER_UNAVAILABLE` | Docker not installed or not running | EV1 or EV2 missing |
| `BLOCKED_DOCKER_DAEMON_UNAVAILABLE` | Docker daemon not responsive | EV2 missing |
| `BLOCKED_REMOTE_CONTEXT` | Remote or cloud Docker context active | L1 or L2 violated |
| `BLOCKED_PRODUCTION_RISK` | Production hostname or network detected in evidence | HB6 triggered |
| `BLOCKED_RAW_SECRET_RISK` | Raw secret in captured evidence | HB5 triggered |
| `BLOCKED_MISSING_OWNER_APPROVAL` | Owner approval not yet issued | HB7 triggered |

**Current H39 decision: `BLOCKED_DOCKER_EVIDENCE_NOT_CAPTURED`**

Reason: H39 is docs/tests only. No Docker commands were executed. No evidence was captured. No Docker evidence packet produced.

---

## 10. Safety Rules

These rules are non-negotiable for H39:

- H39 executes no Docker commands.
- H39 creates no DB.
- H39 connects to no DB.
- H39 runs no SQL.
- H39 runs no migration.
- H39 loads no fixture data.
- H39 calls no runtime APIs.
- H39 enables no feature flags.
- H39 mutates no Cloud Run environment variables.
- H39 activates no Balance.ge connector.
- H39 uses no production data.
- H39 uses no real credentials.
- H39 makes no infrastructure changes.
- H39 makes no UI/static file changes.
- H39 does not modify any runtime code in `app/`.
- H39 does not modify any migration file.
- H39 does not modify fixture JSON files.

---

## 11. Next Task Link

H40 — Local Docker Provisioning Dry-Run Preflight Approval Packet is included in this combined PR as docs/tests only. See `docs/local-docker-provisioning-dry-run-preflight-approval-packet.md`.

Only after PR merge, deploy, and live verification of the H39-H40 bundle:

**If Docker evidence is available (EV1–EV10 complete, local-only confirmed):**

H41 — Local Docker PostgreSQL Provisioning Dry-Run Execution

**If Docker evidence is not available (current status):**

H41 — Docker Evidence Capture Execution

H41 must not be started before H39-H40 bundle is live verified.

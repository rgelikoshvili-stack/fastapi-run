# Bridge Hub - H45 Docker Install Blocker Resolution Plan

## 1. Title

H45 Docker Install Blocker Resolution Plan

## 2. Purpose

Docker is unavailable on the local Windows development machine. H45 plans how the owner resolves the install blocker before any local Docker PostgreSQL provisioning execution can begin.

H45 is planning only. It does not install Docker, run Docker, create containers, create volumes, create a DB, connect to a DB, run SQL, execute migrations, load fixtures, call runtime APIs, mutate Cloud Run, enable feature flags, activate Balance.ge, or use production data.

Expected current decision: `BLOCKED_INSTALL_REQUIRED`.

## 3. H41-H44 Context

H41 captured Docker availability evidence and documented `BLOCKED_DOCKER_UNAVAILABLE`.
H42 sanitized the evidence and documented `EVIDENCE_SANITIZED`.
H43 prepared the owner approval packet and documented `APPROVAL_PACKET_READY_PENDING_SIGNATURE`.
H44 evaluated G1-G15 and documented final decision `BLOCKED_DOCKER_UNAVAILABLE`.

The primary blocker is Docker not installed. Secondary blockers are unsigned owner approval, fixture hash not captured, and migration 011 review/hash not captured.

## 4. Non-action Statement

H45 does not install Docker.
H45 does not run Docker.
H45 does not run Docker evidence commands.
H45 does not create a container.
H45 does not create a volume.
H45 does not create or connect to a DB.
H45 does not execute SQL or migrations.
H45 does not load fixtures.
H45 does not call runtime APIs.

## 5. Supported Install Options

Supported install options for a future owner-executed setup:
- Docker Desktop for Windows 11.
- WSL2 backend.
- Docker Engine alternative only if explicitly approved by the engineering owner.

No Docker Hub login is required for evidence capture unless a future image pull requires it.

## 6. Required User Actions

Future manual owner actions:
- Download and install Docker Desktop manually from the official Docker source.
- Enable WSL2 backend if required.
- Reboot Windows if required by the installer.
- Open Docker Desktop and wait for the daemon to be ready.
- Confirm `docker --version` after install in a future task.
- Do not connect to production, cloud, or remote Docker context.

## 7. Safety Rules

Safety rules:
- no production context
- no cloud context
- no Docker Hub login required for evidence
- no DB/container yet
- no fixture load
- no migration execution
- no Cloud Run mutation
- no feature flag change
- no Balance.ge activation
- no credentials committed

## 8. Evidence Needed After Install

Future H49 evidence must capture:
- `docker --version`
- `docker version`
- `docker context ls`
- `docker info`

These commands are not executed in H45. They are future evidence commands after manual install.

## 9. No-Go Blockers

No-go blockers:
- install unavailable
- daemon unavailable
- remote/cloud context
- raw secrets
- production indicators
- Docker context cannot be classified local-only

## 10. Decision Outputs

Allowed decision outputs:
- `READY_FOR_DOCKER_RECHECK`
- `BLOCKED_INSTALL_REQUIRED`
- `BLOCKED_REBOOT_REQUIRED`
- `BLOCKED_DAEMON_UNAVAILABLE`
- `BLOCKED_REMOTE_CONTEXT`

Current H45 decision: `BLOCKED_INSTALL_REQUIRED`.

## 11. Next Task

H49 - Docker Recheck Evidence Capture

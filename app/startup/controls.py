"""Strict, fail-closed controls for application startup side effects.

``BRIDGEHUB_STARTUP_WORK_ENABLED`` accepts ``true``/``1`` or ``false``/``0``
(case-insensitive, surrounding whitespace ignored); when missing it defaults
to ``true`` to preserve existing startup behavior. Set it explicitly to
``false`` to skip process-started background loops, startup maintenance, and
startup migrations. This is not a request-level maintenance mode and does not
stop already-running instances or provide cross-instance coordination.

``BRIDGEHUB_STARTUP_MAINTENANCE_ENABLED`` accepts the same values and defaults
to ``true``. It controls startup maintenance only (including the central
migration runner); it does not suppress background loops. The master switch
still takes precedence. Thus ``WORK=true, MAINTENANCE=false,
SKIP_MIGRATIONS=true`` registers background loops but schedules neither startup
maintenance nor migrations. Existing defaults preserve all prior behavior.

| WORK | MAINTENANCE | SKIP_MIGRATIONS | Effect |
| --- | --- | --- | --- |
| false | any/unparsed | any/unparsed | No startup loops, maintenance, or startup migrations. |
| true | false | true | Register background loops; skip pool initialization, startup maintenance, and startup migrations. |
| true | false | false | Register background loops; skip startup maintenance and startup migrations. |
| true | true | true | Register loops and startup maintenance except database migrations. |
| true | true | false | Preserve the existing loops, startup maintenance, and migration behavior. |

Maintenance includes pool initialization, email and Balance table bootstrap,
knowledge/inventory initialization, and the one-shot NBG sync. When maintenance
is disabled, any schema/data these processes need must already exist; this
switch neither initializes it elsewhere nor proves production readiness.

``SKIP_MIGRATIONS`` uses the same accepted values and defaults to ``false``.
It suppresses migrations only; it does not suppress other startup work.
An invalid master, maintenance, or applicable migration value fails
application startup before workers are scheduled. Direct migration entrypoints
continue to skip migration work on invalid master/migration controls. With
startup work disabled, subordinate controls are not consulted because all
startup work is already off.
"""

import os


def read_bool_env(name: str, *, default: bool) -> bool:
    """Read an explicit boolean; reject ambiguous values instead of guessing."""
    raw = os.environ.get(name)
    if raw is None:
        return default

    value = raw.strip().lower()
    if value in {"true", "1"}:
        return True
    if value in {"false", "0"}:
        return False
    raise ValueError(f"{name} must be true, false, 1, or 0")


def startup_work_enabled() -> bool:
    """Whether startup migrations, maintenance, and background loops may run."""
    return read_bool_env("BRIDGEHUB_STARTUP_WORK_ENABLED", default=True)


def startup_maintenance_enabled() -> bool:
    """Whether startup maintenance (including startup migrations) may run."""
    if not startup_work_enabled():
        return False
    return read_bool_env("BRIDGEHUB_STARTUP_MAINTENANCE_ENABLED", default=True)


def migrations_enabled() -> bool:
    """Whether the startup migration runner may run."""
    if not startup_work_enabled():
        return False
    return not read_bool_env("SKIP_MIGRATIONS", default=False)

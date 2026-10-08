# NEXT-04A12 Learning Decay Tenant Scope

## Existing path

`main.py::_create_background_tasks` registers `app.startup.background.decay_loop` once
per application process. The loop wakes hourly and previously submitted
`learning_service.run_decay_service()` to a thread without an argument or tenant context.
That service defaults its argument to `default` and calls the synchronous
`pattern_engine.decay_old_patterns`, whose sole business write is a parameterized
`UPDATE learning_patterns ... WHERE tenant_id = %s`. `learning_patterns` has tenant
ownership data; no global update/delete occurs in this decay function.

The database helper's ContextVar is copied into threads by
`run_in_tenant_executor`. The previous raw `run_in_executor` call did not use that helper.

## New caller boundary

Each hourly tick gets active IDs from the existing server-side `tenants` registry via
`_get_active_tenant_ids`, the same enumeration used by autopilot. That helper filters
inactive/suspended identities and validates each ID through canonical `tenant_db_context`.
The loop invokes the immutable service once per accepted identity through
`run_decay_tenant_work`, which delegates to `run_in_tenant_executor(tenant_id, work,
tenant_id)`. The trusted ID therefore scopes both the ContextVar and the service's explicit
tenant parameter. Context cleanup happens in the shared helper's `finally` and executor
context restoration, including when work raises.

An empty registry yields no decay work. Invalid IDs, including missing, empty, malformed,
and `default`, fail validation and never reach the decay service. A tenant failure is
counted and the next tenant can proceed after context cleanup. There is no request input,
learning-pattern enumeration, generated tenant ID, or default fallback.

## Emergency switch

`LEARNING_DECAY_ENABLED` controls only the scheduled decay loop. An unset value defaults to
enabled, preserving existing production scheduling while using the corrected tenant scope.
Only explicit truthy values (`1`, `true`, `yes`, `on`, case-insensitive) enable the loop;
other values disable it. The switch value is not logged. It does not affect HTTP learning,
classification, or other background workers. No production environment value was changed.

## Data and migration impact

The immutable service and engine are unchanged. The SQL predicate continues to name one
specific `tenant_id`; `learning_patterns` already has that column. Existing rows do not
need a data migration. Rows assigned to `default` are intentionally not processed by the
scheduled worker and are not reassigned. Any cleanup requires a separately reviewed data
operation. The loop can be paused with the switch during migration 013 while preserving
other learning behavior.

"""
app/api/metrics.py
Bridge Hub — centralized Prometheus metrics definitions.
Import from here everywhere; avoids duplicate registration errors.
"""
try:
    from prometheus_client import Counter, Histogram, Gauge

    # ── Approval actions ────────────────────────────────────────────────────
    APPROVAL_ACTIONS = Counter(
        "bridgehub_approval_actions_total",
        "Approval queue actions",
        ["action", "tenant"],          # action: approve | reject | correct
    )

    APPROVAL_DURATION = Histogram(
        "bridgehub_approval_duration_seconds",
        "Time to process an approval action",
        ["action"],
        buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    )

    # ── AI / classification ─────────────────────────────────────────────────
    AI_CLASSIFICATION_TOTAL = Counter(
        "bridgehub_ai_classification_total",
        "AI classification attempts",
        ["tenant", "result"],           # result: success | failure | fallback
    )

    AI_CLASSIFICATION_DURATION = Histogram(
        "bridgehub_ai_classification_duration_seconds",
        "Time for AI classification call",
        ["model"],
        buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
    )

    # ── File / document ─────────────────────────────────────────────────────
    FILE_PREVIEW_DURATION = Histogram(
        "bridgehub_file_preview_duration_seconds",
        "Time to generate a file signed URL or stream",
        ["method"],                     # method: signed_url | stream | db
        buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
    )

    FILE_UPLOAD_TOTAL = Counter(
        "bridgehub_file_upload_total",
        "File uploads",
        ["tenant", "result"],           # result: gcs | db | error
    )

    # ── Workers / background jobs ───────────────────────────────────────────
    WORKER_ERRORS = Counter(
        "bridgehub_worker_errors_total",
        "Background worker failures",
        ["worker"],                     # worker: autopilot | decay | email_poller
    )

    METRICS_OK = True

except ImportError:
    METRICS_OK = False

    class _Noop:
        def labels(self, **_): return self
        def inc(self, *_): pass
        def observe(self, *_): pass
        def dec(self, *_): pass
        def set(self, *_): pass

    _noop = _Noop()
    APPROVAL_ACTIONS       = _noop
    APPROVAL_DURATION      = _noop
    AI_CLASSIFICATION_TOTAL    = _noop
    AI_CLASSIFICATION_DURATION = _noop
    FILE_PREVIEW_DURATION  = _noop
    FILE_UPLOAD_TOTAL      = _noop
    WORKER_ERRORS          = _noop

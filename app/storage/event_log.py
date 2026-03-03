from datetime import datetime, timezone

AUDIT_LOG: list = []

def write(
    object_id: str,
    object_type: str,
    from_state: str,
    to_state: str,
    actor: str,
    reason: str = '',
    metadata: dict = {},
) -> dict:
    entry = {
        'object_id':   object_id,
        'object_type': object_type,
        'from_state':  from_state,
        'to_state':    to_state,
        'actor':       actor,
        'reason':      reason,
        'metadata':    metadata,
        'ts':          datetime.now(timezone.utc).isoformat(),
    }
    AUDIT_LOG.append(entry)
    return entry

def get_log(object_id: str = '', object_type: str = '') -> list:
    result = AUDIT_LOG
    if object_id:
        result = [e for e in result if e['object_id'] == object_id]
    if object_type:
        result = [e for e in result if e['object_type'] == object_type]
    return result

def get_stats() -> dict:
    return {
        'total_events': len(AUDIT_LOG),
        'by_type': {},
    }

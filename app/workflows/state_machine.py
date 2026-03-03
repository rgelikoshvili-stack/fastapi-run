from enum import Enum
from datetime import datetime, timezone

class TxState(str, Enum):
    RECEIVED     = 'received'
    PARSED       = 'parsed'
    NORMALIZED   = 'normalized'
    VALIDATED    = 'validated'
    NEEDS_REVIEW = 'needs_review'
    APPROVED     = 'approved'
    POSTED       = 'posted'
    RECONCILED   = 'reconciled'
    REPORTED     = 'reported'
    CLOSED       = 'closed'
    REJECTED     = 'rejected'

TRANSITIONS: dict[TxState, list[TxState]] = {
    TxState.RECEIVED:     [TxState.PARSED,       TxState.REJECTED],
    TxState.PARSED:       [TxState.NORMALIZED,   TxState.REJECTED],
    TxState.NORMALIZED:   [TxState.VALIDATED,    TxState.REJECTED],
    TxState.VALIDATED:    [TxState.APPROVED,     TxState.NEEDS_REVIEW, TxState.REJECTED],
    TxState.NEEDS_REVIEW: [TxState.APPROVED,     TxState.REJECTED],
    TxState.APPROVED:     [TxState.POSTED],
    TxState.POSTED:       [TxState.RECONCILED],
    TxState.RECONCILED:   [TxState.REPORTED],
    TxState.REPORTED:     [TxState.CLOSED],
}

AUDIT_LOG = []

def transition(obj: dict, new_state: TxState, actor: str, reason: str = '') -> dict:
    allowed = TRANSITIONS.get(TxState(obj['state']), [])
    if new_state not in allowed:
        raise ValueError(f"Illegal transition: {obj['state']} → {new_state}")
    old_state = obj['state']
    obj['state'] = new_state.value
    AUDIT_LOG.append({
        'object_id':   obj.get('id', ''),
        'object_type': obj.get('_type', 'transaction'),
        'from_state':  old_state,
        'to_state':    new_state.value,
        'actor':       actor,
        'reason':      reason,
        'ts':          datetime.now(timezone.utc).isoformat(),
    })
    return obj

def get_audit_log(object_id: str = '') -> list:
    if object_id:
        return [e for e in AUDIT_LOG if e['object_id'] == object_id]
    return AUDIT_LOG

CONFIDENCE_THRESHOLDS = {
    'AUTO_APPROVE':       0.90,
    'REVIEW_RECOMMENDED': 0.70,
    'MANUAL_MANDATORY':   0.00,
}

def route_by_confidence(score: float) -> str:
    if score >= CONFIDENCE_THRESHOLDS['AUTO_APPROVE']:
        return 'auto_approve_queue'
    elif score >= CONFIDENCE_THRESHOLDS['REVIEW_RECOMMENDED']:
        return 'review_queue'
    else:
        return 'manual_review_queue'

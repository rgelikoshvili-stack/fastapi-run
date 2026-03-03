from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import date
from decimal import Decimal
import uuid

class CanonicalBankTransaction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    date: date
    description: str
    amount: Decimal
    currency: str = 'GEL'
    direction: Literal['IN', 'OUT']
    counterparty: Optional[str] = None
    counterparty_normalized: Optional[str] = None
    source_file: Optional[str] = None
    source_file_type: Optional[str] = None
    raw_reference: Optional[str] = None
    confidence: float = 1.0
    duplicate_hash: Optional[str] = None
    state: str = 'received'

class JournalLine(BaseModel):
    account_code: str
    account_name: str
    debit: Optional[Decimal] = None
    credit: Optional[Decimal] = None
    cost_center: Optional[str] = None

class CanonicalJournalDraft(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    transaction_id: str
    document_id: Optional[str] = None
    lines: list[JournalLine]
    tax_hint: Optional[str] = None
    tax_amount: Optional[Decimal] = None
    confidence: float
    requires_approval: bool = True
    reasoning: str
    state: Literal['draft','pending','approved','posted','rejected'] = 'draft'

    @property
    def is_balanced(self) -> bool:
        total_debit  = sum(l.debit  or 0 for l in self.lines)
        total_credit = sum(l.credit or 0 for l in self.lines)
        return abs(total_debit - total_credit) < Decimal('0.01')

class CanonicalDocument(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    doc_type: Literal['invoice','waybill','receipt','contract','payroll','tax_doc','bank_statement','unknown']
    filename: str
    extracted_text: Optional[str] = None
    structured_fields: dict = {}
    source: str
    confidence: float
    validation_status: Literal['valid','invalid','partial'] = 'partial'
    linked_transaction_ids: list[str] = []

class ControlIssue(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    issue_type: Literal['duplicate','anomaly','policy_violation','missing_document','threshold_breach','reconciliation_gap','suspicious_pattern']
    severity: Literal['CRITICAL','HIGH','MEDIUM','LOW','INFO']
    message: str
    linked_object_id: str
    linked_object_type: str
    suggested_action: Optional[str] = None
    status: Literal['open','in_review','resolved','false_positive'] = 'open'
    created_at: str = Field(default_factory=lambda: __import__('datetime').datetime.utcnow().isoformat())

class ForecastScenario(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    horizon_days: int
    assumptions: dict
    revenue_projection: Decimal
    expense_projection: Decimal
    cash_projection: Decimal
    risk_flags: list[str] = []

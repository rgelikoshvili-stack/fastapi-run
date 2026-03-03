from sqlalchemy import Column, String, Numeric, DateTime, Boolean, Text, Integer, JSON
from sqlalchemy.sql import func
from app.storage.database import Base

class JournalEntry(Base):
    __tablename__ = "journal_entries"
    id           = Column(String, primary_key=True)
    tx_id        = Column(String, index=True)
    doc_date     = Column(String)
    description  = Column(Text)
    counterparty = Column(String)
    amount       = Column(Numeric(18,2))
    direction    = Column(String(4))
    debit_code   = Column(String(10))
    debit_name   = Column(Text)
    credit_code  = Column(String(10))
    credit_name  = Column(Text)
    vat_class    = Column(String(30))
    tax_amount   = Column(Numeric(18,2))
    rule_id      = Column(String(50))
    confidence   = Column(Numeric(4,2))
    queue        = Column(String(20))
    is_balanced  = Column(Boolean, default=True)
    status       = Column(String(20), default="draft")
    gaas_version = Column(String(10), default="v5.2")
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    lines_json   = Column(JSON)

class AuditLog(Base):
    __tablename__ = "audit_log"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    entry_id     = Column(String, index=True)
    action       = Column(String(50))
    from_state   = Column(String(20))
    to_state     = Column(String(20))
    actor        = Column(String(50))
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

class ControlIssue(Base):
    __tablename__ = "control_issues"
    id           = Column(String, primary_key=True)
    rule_id      = Column(String(50))
    severity     = Column(String(10))
    issue_type   = Column(String(30))
    message      = Column(Text)
    suggested_action = Column(Text)
    tx_id        = Column(String, index=True)
    status       = Column(String(10), default="open")
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

class VATReturn(Base):
    __tablename__ = "vat_returns"
    id            = Column(String, primary_key=True)
    company_id    = Column(String(50))
    period_year   = Column(Integer)
    period_month  = Column(Integer)
    vat_out       = Column(Numeric(18,2))
    vat_in        = Column(Numeric(18,2))
    vat_payable   = Column(Numeric(18,2))
    status        = Column(String(20), default="draft")
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

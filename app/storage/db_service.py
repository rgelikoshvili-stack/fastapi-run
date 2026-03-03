from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.storage.database import SessionLocal
from app.storage import models
import uuid
from datetime import datetime, timezone

def save_journal_entry(entry: dict):
    db: Session = SessionLocal()
    try:
        obj = models.JournalEntry(
            id=entry.get("id", str(uuid.uuid4())),
            tx_id=entry.get("tx_id",""),
            doc_date=entry.get("date",""),
            description=entry.get("description",""),
            counterparty=entry.get("counterparty",""),
            amount=entry.get("amount","0"),
            direction=entry.get("direction","OUT"),
            debit_code=entry.get("debit","9999"),
            debit_name=entry.get("debit_name",""),
            credit_code=entry.get("credit","1120"),
            credit_name=entry.get("credit_name",""),
            vat_class=entry.get("vat_class","NON_VAT"),
            tax_amount=entry.get("tax_amount","0") or "0",
            rule_id=entry.get("rule_id",""),
            confidence=entry.get("confidence",0),
            queue=entry.get("queue","MANUAL"),
            is_balanced=entry.get("is_balanced", True),
            status=entry.get("status","draft"),
            gaas_version=entry.get("gaas_version","v5.2"),
            lines_json=entry.get("lines",[]),
        )
        db.merge(obj)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"DB save error: {e}")
        return False
    finally:
        db.close()

def get_journal_entries(limit=100):
    db: Session = SessionLocal()
    try:
        rows = db.query(models.JournalEntry).order_by(
            desc(models.JournalEntry.created_at)).limit(limit).all()
        return [{"id":r.id,"tx_id":r.tx_id,"date":r.doc_date,
                 "description":r.description,"amount":str(r.amount),
                 "debit":r.debit_code,"debit_name":r.debit_name,
                 "credit":r.credit_code,"credit_name":r.credit_name,
                 "vat_class":r.vat_class,"tax_amount":str(r.tax_amount),
                 "rule_id":r.rule_id,"confidence":float(r.confidence or 0),
                 "queue":r.queue,"is_balanced":r.is_balanced,
                 "status":r.status,"gaas_version":r.gaas_version,
                 "created_at":str(r.created_at)} for r in rows]
    finally:
        db.close()

def save_audit_log(entry_id: str, action: str, from_state: str, to_state: str, actor: str):
    db: Session = SessionLocal()
    try:
        obj = models.AuditLog(
            entry_id=entry_id, action=action,
            from_state=from_state, to_state=to_state, actor=actor)
        db.add(obj)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        return False
    finally:
        db.close()

def get_audit_log(limit=200):
    db: Session = SessionLocal()
    try:
        rows = db.query(models.AuditLog).order_by(
            desc(models.AuditLog.created_at)).limit(limit).all()
        return [{"id":r.id,"entry_id":r.entry_id,"action":r.action,
                 "from_state":r.from_state,"to_state":r.to_state,
                 "actor":r.actor,"created_at":str(r.created_at)} for r in rows]
    finally:
        db.close()

def save_vat_return(company_id: str, period: dict, totals: dict):
    db: Session = SessionLocal()
    try:
        obj = models.VATReturn(
            id=str(uuid.uuid4()),
            company_id=company_id,
            period_year=period.get("year",2026),
            period_month=period.get("month",3),
            vat_out=totals.get("vat_out_total",0),
            vat_in=totals.get("vat_in_deductible_total",0),
            vat_payable=totals.get("vat_payable",0),
            status="submitted",
        )
        db.add(obj)
        db.commit()
        return obj.id
    except Exception as e:
        db.rollback()
        print(f"VAT return save error: {e}")
        return None
    finally:
        db.close()

def get_db_stats():
    db: Session = SessionLocal()
    try:
        from sqlalchemy import func
        je = db.query(func.count(models.JournalEntry.id)).scalar()
        al = db.query(func.count(models.AuditLog.id)).scalar()
        ci = db.query(func.count(models.ControlIssue.id)).scalar()
        vr = db.query(func.count(models.VATReturn.id)).scalar()
        return {"journal_entries":je,"audit_log":al,
                "control_issues":ci,"vat_returns":vr}
    finally:
        db.close()

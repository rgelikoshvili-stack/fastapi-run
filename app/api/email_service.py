import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from app.config.secrets import get_email_secret

log = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@bridgehub.ge")
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://fastapi-run-226875230147.us-central1.run.app")

def send_email(to: str, subject: str, body_html: str, body_text: str = "") -> dict:
    smtp_pass = get_email_secret("SMTP_PASS")
    if os.environ.get("TEST_MODE") == "1":
        return {
            "sent": False,
            "configured": bool(SMTP_USER and smtp_pass),
            "status": "degraded",
            "reason": "SMTP delivery disabled in TEST_MODE",
        }
    if not SMTP_USER or not smtp_pass:
        return {"sent": False, "configured": False, "status": "degraded", "reason": "SMTP not configured"}
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = FROM_EMAIL
        msg["To"] = to
        if body_text:
            msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, smtp_pass)
            server.sendmail(FROM_EMAIL, to, msg.as_string())
        return {"sent": True, "configured": True}
    except Exception:
        log.warning("SMTP delivery failed; configured=true")
        return {"sent": False, "configured": True, "status": "degraded", "reason": "SMTP delivery failed"}

def notify_draft_approved(to: str, draft: dict) -> dict:
    subject = f"[Bridge Hub] Journal Draft #{draft.get('id')} Approved"
    html = f"""
    <h2 style="color:#22c55e">✅ Journal Draft Approved</h2>
    <table style="border-collapse:collapse;font-family:Arial">
      <tr><td><b>ID:</b></td><td>{draft.get('id')}</td></tr>
      <tr><td><b>Date:</b></td><td>{draft.get('date')}</td></tr>
      <tr><td><b>Description:</b></td><td>{draft.get('description')}</td></tr>
      <tr><td><b>Amount:</b></td><td>{draft.get('amount')} GEL</td></tr>
      <tr><td><b>Dr:</b></td><td>{draft.get('debit_account')}</td></tr>
      <tr><td><b>Cr:</b></td><td>{draft.get('credit_account')}</td></tr>
    </table>
    <p style="color:#666;font-size:12px">Bridge Hub v1.0.0</p>
    """
    return send_email(to, subject, html)

def notify_review_required(to: str, count: int) -> dict:
    subject = f"[Bridge Hub] {count} Drafts Require Review"
    html = f"""
    <h2 style="color:#f59e0b">⚠️ Review Required</h2>
    <p><b>{count}</b> journal draft(s) are waiting for your approval.</p>
    <a href="{APP_BASE_URL}/ui/dashboard"
       style="background:#3b82f6;color:white;padding:10px 20px;border-radius:8px;text-decoration:none">
       Open Dashboard
    </a>
    <p style="color:#666;font-size:12px">Bridge Hub v1.0.0</p>
    """
    return send_email(to, subject, html)

def notify_reconciliation(to: str, result: dict) -> dict:
    status_color = "#22c55e" if result.get("status") == "balanced" else "#ef4444"
    subject = f"[Bridge Hub] Reconciliation Report — {result.get('status','').upper()}"
    html = f"""
    <h2 style="color:{status_color}">📊 Reconciliation Report</h2>
    <table style="border-collapse:collapse;font-family:Arial">
      <tr><td><b>Period:</b></td><td>{result.get('period',{}).get('from')} — {result.get('period',{}).get('to')}</td></tr>
      <tr><td><b>Total Transactions:</b></td><td>{result.get('total_transactions')}</td></tr>
      <tr><td><b>Total Income:</b></td><td>{result.get('total_income')} GEL</td></tr>
      <tr><td><b>Total Expense:</b></td><td>{result.get('total_expense')} GEL</td></tr>
      <tr><td><b>Balance:</b></td><td>{result.get('balance')} GEL</td></tr>
      <tr><td><b>Status:</b></td><td style="color:{status_color}"><b>{result.get('status','').upper()}</b></td></tr>
      <tr><td><b>Duplicates:</b></td><td>{result.get('duplicate_count')}</td></tr>
    </table>
    <p style="color:#666;font-size:12px">Bridge Hub v1.0.0</p>
    """
    return send_email(to, subject, html)

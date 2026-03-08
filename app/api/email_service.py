import smtplib, os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@bridgehub.ge")

def send_email(to: str, subject: str, body_html: str, body_text: str = "") -> dict:
    if not SMTP_USER or not SMTP_PASS:
        return {"sent": False, "reason": "SMTP not configured"}
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
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, to, msg.as_string())
        return {"sent": True}
    except Exception as e:
        return {"sent": False, "reason": str(e)}

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
    <a href="https://fastapi-run-226875230147.us-central1.run.app/ui/dashboard"
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

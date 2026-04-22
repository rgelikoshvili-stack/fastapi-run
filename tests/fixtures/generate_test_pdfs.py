"""Generate synthetic test PDFs for document intelligence tests.
Uses ASCII/English text only — Helvetica cannot render Georgian in pdfplumber.
"""
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from pathlib import Path
import io

FIXTURES = Path(__file__).parent

def _make_pdf(text_lines: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 780
    for line in text_lines:
        c.setFont("Helvetica", 11)
        c.drawString(50, y, line)
        y -= 18
    c.save()
    return buf.getvalue()

# 1. Tax invoice — we are buyer (IT services)
(FIXTURES / "invoice_buyer_it_services.pdf").write_bytes(_make_pdf([
    "TAX INVOICE",
    "Series: AF  Number: 00123456  Date: 2026-03-15",
    "Seller: Tech Services LLC   INN: 205123456",
    "Buyer: Alte University      INN: 202192643",
    "N   Description             Unit  Qty   Price",
    "1   IT services             hr    10    150.00",
    "Subtotal: 1500.00",
    "VAT (18%): 270.00",
    "Total: 1770.00 GEL",
]))

# 2. Tax invoice — we are seller
(FIXTURES / "invoice_seller_education.pdf").write_bytes(_make_pdf([
    "TAX INVOICE",
    "Series: AG  Number: 00456789  Date: 2026-02-20",
    "Seller: Alte University     INN: 202192643",
    "Buyer: Beta LLC             INN: 205999888",
    "1   Education service       unit  1     5000.00",
    "VAT (0%): 0.00",
    "Total: 5000.00 GEL",
]))

# 3. Utility bill — buyer
(FIXTURES / "utility_electricity.pdf").write_bytes(_make_pdf([
    "PAYMENT RECEIPT",
    "Date: 2026-03-31",
    "Provider: Energo Corp       INN: 211234567",
    "Customer: Alte University   INN: 202192643",
    "Service: electricity utility bill",
    "Period: 2026-03",
    "Total: 324.00 GEL",
]))

# 4. Office rent receipt — buyer
(FIXTURES / "office_rent_receipt.pdf").write_bytes(_make_pdf([
    "RENT RECEIPT",
    "Date: 2026-03-01",
    "Landlord: GEO Real Estate   INN: 212345678",
    "Tenant: Alte University     INN: 202192643",
    "Property: Office, Tbilisi",
    "Monthly office rent: 2500.00 GEL",
    "Total: 2500.00 GEL",
]))

# 5. Foreign document (neither party is us)
(FIXTURES / "invoice_foreign.pdf").write_bytes(_make_pdf([
    "INVOICE",
    "Date: 2026-01-10",
    "Seller: XYZ Corp            INN: 211111111",
    "Buyer: ABC LLC              INN: 222222222",
    "Services: Consulting",
    "Total: 8000.00 USD",
]))

# 6. Advance payment — buyer
(FIXTURES / "advance_payment.pdf").write_bytes(_make_pdf([
    "TAX INVOICE",
    "Series: AH  Number: 00099001  Date: 2026-03-10",
    "Seller: Ad Agency Ltd       INN: 213456789",
    "Buyer: Alte University      INN: 202192643",
    "1   Advance payment for marketing campaign  3000.00",
    "Total: 3000.00 GEL",
]))

# 7. IT SaaS subscription — buyer
(FIXTURES / "saas_subscription.pdf").write_bytes(_make_pdf([
    "INVOICE",
    "Date: 2026-03-15",
    "Seller: Cloud Services Ltd  INN: 214567890",
    "Buyer: Alte University      INN: 202192643",
    "Service: Annual cloud subscription",
    "Qty: 1   Price: 1200.00 USD",
    "Total: 1200.00 USD",
]))

print("Generated 7 test PDF fixtures:")
for p in sorted(FIXTURES.glob("*.pdf")):
    print(f"  {p.name} ({p.stat().st_size} bytes)")

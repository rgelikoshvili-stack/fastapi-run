"""Unit tests for multi-currency FX helpers (no DB required)."""
import os
from decimal import Decimal
from unittest.mock import patch, MagicMock

os.environ.setdefault("TEST_MODE", "1")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("JWT_SECRET", "test-secret-for-ci")


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_db_no_rates():
    """DB returns no rows — should fall back to DEFAULT_RATES."""
    conn = MagicMock()
    cur  = MagicMock()
    cur.fetchone.return_value = None
    conn.cursor.return_value  = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__  = MagicMock(return_value=False)
    return conn


# ── 1. GEL → GEL always 1.0 ──────────────────────────────────────────────────

def test_gel_to_gel_rate():
    from app.api.services.currency_service import get_rate
    assert get_rate("GEL", "GEL") == Decimal("1.0")


# ── 2. USD → GEL uses DEFAULT_RATES fallback ──────────────────────────────────

def test_usd_to_gel_fallback():
    from app.api.services.currency_service import get_rate, _DEFAULT_RATES
    with patch("app.api.services.currency_service.get_db", return_value=_mock_db_no_rates()):
        rate = get_rate("USD", "GEL")
    expected = Decimal(str(_DEFAULT_RATES["USD"]))
    assert rate == expected, f"Expected {expected}, got {rate}"


# ── 3. GEL → USD is 1/USD_rate ───────────────────────────────────────────────

def test_gel_to_usd_is_inverse():
    from app.api.services.currency_service import get_rate, _DEFAULT_RATES
    with patch("app.api.services.currency_service.get_db", return_value=_mock_db_no_rates()):
        rate = get_rate("GEL", "USD")
    expected = round(1 / _DEFAULT_RATES["USD"], 6)
    assert abs(float(rate) - expected) < 0.00001


# ── 4. Cross currency EUR → USD via GEL ──────────────────────────────────────

def test_cross_currency_eur_to_usd():
    from app.api.services.currency_service import get_rate, _DEFAULT_RATES
    with patch("app.api.services.currency_service.get_db", return_value=_mock_db_no_rates()):
        rate = get_rate("EUR", "USD")
    # EUR→GEL / USD→GEL
    expected = _DEFAULT_RATES["EUR"] / _DEFAULT_RATES["USD"]
    assert abs(float(rate) - expected) < 0.001


# ── 5. convert() returns correct structure ────────────────────────────────────

def test_convert_returns_structure():
    from app.api.services.currency_service import convert
    with patch("app.api.services.currency_service.get_db", return_value=_mock_db_no_rates()):
        result = convert(Decimal("100"), "USD", "GEL")
    assert "original" in result
    assert "converted" in result
    assert "rate" in result
    assert result["original"]["currency"] == "USD"
    assert result["converted"]["currency"] == "GEL"


# ── 6. convert() USD 100 → GEL correct amount ────────────────────────────────

def test_convert_usd_100_to_gel():
    from app.api.services.currency_service import convert, _DEFAULT_RATES
    with patch("app.api.services.currency_service.get_db", return_value=_mock_db_no_rates()):
        result = convert(Decimal("100"), "USD", "GEL")
    expected_gel = round(100 * _DEFAULT_RATES["USD"], 2)
    assert abs(result["converted"]["amount"] - expected_gel) < 0.01


# ── 7. apply_fx_to_entry — GEL passthrough ───────────────────────────────────

def test_apply_fx_gel_entry():
    from app.api.services.currency_service import apply_fx_to_entry
    entry = {"amount": 500.0, "currency": "GEL"}
    result = apply_fx_to_entry(entry)
    assert result["amount_gel"]    == 500.0
    assert result["exchange_rate"] == 1.0


# ── 8. apply_fx_to_entry — USD converted ─────────────────────────────────────

def test_apply_fx_usd_entry():
    from app.api.services.currency_service import apply_fx_to_entry, _DEFAULT_RATES
    with patch("app.api.services.currency_service.get_db", return_value=_mock_db_no_rates()):
        entry  = {"amount": 200.0, "currency": "USD"}
        result = apply_fx_to_entry(entry)
    expected_gel = round(200 * _DEFAULT_RATES["USD"], 2)
    assert abs(result["amount_gel"] - expected_gel) < 0.01
    assert result["exchange_rate"] == _DEFAULT_RATES["USD"]


# ── 9. NBG fetch_nbg_rates returns dict ──────────────────────────────────────

def test_nbg_fetch_returns_dict():
    from app.integrations.nbg_api import fetch_nbg_rates
    import urllib.request
    mock_data = [{"currencies": [
        {"code": "USD", "rate": 2.72, "quantity": 1},
        {"code": "EUR", "rate": 2.95, "quantity": 1},
    ]}]
    import json
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_data).encode()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__  = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        rates = fetch_nbg_rates()
    assert "USD" in rates
    assert "EUR" in rates
    assert rates["USD"] == 2.72
    assert rates["GEL"] == 1.0


# ── 10. NBG sync_rates_to_db writes correct SQL ──────────────────────────────

def test_nbg_sync_to_db():
    from app.integrations.nbg_api import sync_rates_to_db
    conn = MagicMock()
    cur  = MagicMock()
    conn.cursor.return_value = cur
    import urllib.request, json
    mock_data = [{"currencies": [
        {"code": "USD", "rate": 2.72, "quantity": 1},
    ]}]
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_data).encode()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__  = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        n = sync_rates_to_db(conn)
    assert n == 1
    assert conn.commit.called

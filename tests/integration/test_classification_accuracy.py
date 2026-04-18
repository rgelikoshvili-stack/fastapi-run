"""
tests/integration/test_classification_accuracy.py
Verifies that the knowledge base classifies known transactions correctly.
No DB required — runs fully in-process.
"""
import pytest
from app.knowledge import classify_transaction


CASES = [
    # (description, expected_account, label)
    ("tbc bank commission 2024-01", "7510", "TBC bank fee"),
    ("bog საკომ. 12.5₾", "7510", "BOG commission"),
    ("amazon aws s3 storage", "7810", "AWS cloud"),
    ("ხელფასი იანვარი", "7210", "Salary GEO"),
    ("salary march 2024", "7210", "Salary EN"),
    ("office rent payment", "7310", "Rent"),
    ("wolt delivery", "7720", "Wolt entertainment"),
    ("facebook advertising", "7710", "FB ads"),
    ("bolt taxi ride", "7730", "Bolt transport"),
    ("დივიდენდი", "3370", "Dividend GEO"),
    ("invoice sale revenue", "6110", "Revenue"),
    ("pit საშემოსავლო", "3320", "PIT"),
    ("cit profit tax", "3340", "CIT"),
]


@pytest.mark.parametrize("desc,expected_account,label", CASES)
def test_classification(desc, expected_account, label):
    result = classify_transaction(desc)
    assert result["account"] == expected_account, (
        f"[{label}] '{desc}': expected account {expected_account}, "
        f"got {result['account']} (matched_on={result['matched_on']!r}, source={result['source']!r})"
    )


def test_vat_inclusive_calculation():
    from app.knowledge import calculate_vat
    result = calculate_vat(5900, inclusive=True)
    assert result["net"] == pytest.approx(5000.0, abs=1.0)
    assert result["vat"] == pytest.approx(900.0, abs=1.0)
    assert result["gross"] == 5900


def test_vat_exclusive_calculation():
    from app.knowledge import calculate_vat
    result = calculate_vat(1000, inclusive=False)
    assert result["net"] == 1000
    assert result["vat"] == pytest.approx(180.0, abs=0.01)
    assert result["gross"] == pytest.approx(1180.0, abs=0.01)


def test_payroll_calculation():
    from app.knowledge import calculate_payroll
    result = calculate_payroll(3000)
    assert result["pit"] == pytest.approx(600.0, abs=0.01)
    assert result["payg_employee"] == pytest.approx(60.0, abs=0.01)
    assert result["net"] == pytest.approx(2340.0, abs=0.01)


def test_cit_calculation():
    from app.knowledge import calculate_cit
    result = calculate_cit(10000)
    assert result["tax_base"] == pytest.approx(11764.71, abs=0.1)
    assert result["cit"] == pytest.approx(1764.71, abs=0.1)
    assert result["net_dividend"] == pytest.approx(8235.29, abs=0.1)

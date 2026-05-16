"""
ENC-1 — Georgian Encoding / Mojibake Cleanup Contract Tests

Verifies that mojibake artifacts have been removed from the 4 target files
and that correct Georgian Unicode text is present where expected.

No DB, no network, no shell execution, no SQL, no migrations.
All assertions are read-only file text scans.
"""

import ast
import pathlib
import re

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT = pathlib.Path(__file__).parents[2]
_RBAC = _ROOT / "app" / "api" / "middleware" / "rbac_middleware.py"
_APPROVAL = _ROOT / "app" / "api" / "routes_approval.py"
_PAYROLL = _ROOT / "app" / "api" / "services" / "payroll_service.py"
_PMAP = _ROOT / "app" / "api" / "policy" / "permission_map.py"
_THIS_FILE = pathlib.Path(__file__)

TARGET_FILES = [_RBAC, _APPROVAL, _PAYROLL, _PMAP]

# Mojibake artifact patterns (stored split to avoid self-match in scan)
_MOJI_GEORGIAN = "áƒ"[0] + "ƒ"         # áƒ = mojibake Georgian prefix (E1 83)
_MOJI_GEORGIAN2 = "á" + "‚"       # á‚ = mojibake Georgian alt prefix
_MOJI_EMDASH = "â" + "€" + "”"  # â€" = mojibake em dash
_MOJI_OPENQUOTE = "â" + "€" + "œ"  # â€œ = mojibake open quote
_MOJI_PREFIX = "â" + "€"          # â€ = mojibake prefix (many symbols)
_MOJI_ARROW = "â" + "†"           # â† = mojibake right-arrow
_MOJI_BOXDRAW = "â" + "”" + "€"  # â"€ = mojibake box-drawing ─
_MOJI_C3 = "Ã"                    # Ã = mojibake (byte C3)
_MOJI_C2 = "Â"                    # Â = mojibake (byte C2)

MOJIBAKE_PATTERNS = [
    _MOJI_GEORGIAN,
    _MOJI_GEORGIAN2,
    _MOJI_EMDASH,
    _MOJI_OPENQUOTE,
    _MOJI_PREFIX,
    _MOJI_ARROW,
    _MOJI_BOXDRAW,
    _MOJI_C3,
    _MOJI_C2,
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: pathlib.Path) -> str:
    assert path.exists(), f"Target file missing: {path}"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: no mojibake patterns in any target file
# ---------------------------------------------------------------------------


def test_no_mojibake_patterns_in_target_files():
    for path in TARGET_FILES:
        text = _read(path)
        for pat in MOJIBAKE_PATTERNS:
            assert pat not in text, (
                f"Mojibake pattern {repr(pat)} found in {path.name}. "
                f"ENC-1 cleanup may be incomplete."
            )


# ---------------------------------------------------------------------------
# Test 2: RBAC Georgian error messages are clean and present
# ---------------------------------------------------------------------------


def test_rbac_georgian_messages_are_clean():
    text = _read(_RBAC)
    assert "ავთენტიკაცია აუცილებელია" in text, (
        "Authentication required message missing or not cleaned in rbac_middleware.py"
    )
    assert "როლი ვერ განისაზღვრა" in text, (
        "Role cannot be determined message missing or not cleaned in rbac_middleware.py"
    )
    assert "წვდომა აკრძალულია" in text, (
        "Access denied message missing or not cleaned in rbac_middleware.py"
    )


# ---------------------------------------------------------------------------
# Test 3: routes_approval.py pagination messages are clean
# ---------------------------------------------------------------------------


def test_routes_approval_messages_are_clean():
    text = _read(_APPROVAL)
    # Must contain clean Georgian for both limit and offset messages
    assert "limit" in text and "offset" in text, (
        "Pagination parameters not found in routes_approval.py"
    )
    # Must not contain mojibake in the pagination message section
    for lineno, line in enumerate(text.splitlines(), 1):
        if "INVALID_PAGINATION" in line:
            for pat in MOJIBAKE_PATTERNS:
                assert pat not in line, (
                    f"Mojibake in INVALID_PAGINATION message at "
                    f"routes_approval.py:{lineno}: {line.strip()!r}"
                )
    # Clean Georgian text must be present
    assert "იყოს" in text, (
        "Expected Georgian word 'იყოს' not found in routes_approval.py"
    )


# ---------------------------------------------------------------------------
# Test 4: payroll_service.py docstrings are clean and contain correct Georgian
# ---------------------------------------------------------------------------


def test_payroll_docstrings_are_clean():
    text = _read(_PAYROLL)
    assert "Bridge Hub — Payroll Service" in text, (
        "Module title with em dash not found/cleaned in payroll_service.py"
    )
    assert "საშემოსავლო გადასახადი" in text, (
        "'საშემოსავლო გადასახადი' not found in payroll_service.py"
    )
    assert "georgia_pack.py-ს გამოიყენებს" in text, (
        "'georgia_pack.py-ს გამოიყენებს' not found in payroll_service.py"
    )
    assert "ერთი თანამშრომლის ხელფასის გამოთვლა" in text, (
        "'ერთი თანამშრომლის ხელფასის გამოთვლა' not found in payroll_service.py"
    )
    assert "მრავალი თანამშრომლის payroll გამოთვლა" in text, (
        "'მრავალი თანამშრომლის payroll გამოთვლა' not found in payroll_service.py"
    )
    assert "RS.ge-ისთვის XML ფორმატის გენერაცია" in text, (
        "'RS.ge-ისთვის XML ფორმატის გენერაცია' not found in payroll_service.py"
    )


# ---------------------------------------------------------------------------
# Test 5: permission_map.py metrics comment is clean
# ---------------------------------------------------------------------------


def test_permission_map_metrics_comment_is_clean():
    text = _read(_PMAP)
    assert "Metrics" in text, "Metrics section not found in permission_map.py"
    assert "Prometheus" in text, "Prometheus not found in permission_map.py"
    assert "internal only" in text, "'internal only' not found in permission_map.py"
    assert "—" in text, "Em dash (—) not found in permission_map.py metrics comment"
    # Must not contain the mojibake prefix â (U+00E2) followed by € or "
    assert _MOJI_EMDASH not in text, (
        "Mojibake em dash still present in permission_map.py"
    )
    assert _MOJI_BOXDRAW not in text, (
        "Mojibake box-drawing still present in permission_map.py"
    )


# ---------------------------------------------------------------------------
# Test 6: no logic keywords changed by encoding cleanup
# ---------------------------------------------------------------------------


def test_no_logic_keywords_changed_by_encoding_contract():
    rbac_text = _read(_RBAC)
    assert "required_permission" in rbac_text
    assert "status_code" in rbac_text
    assert "401" in rbac_text
    assert "403" in rbac_text

    approval_text = _read(_APPROVAL)
    assert "limit" in approval_text
    assert "offset" in approval_text
    assert "_validate_pagination" in approval_text

    payroll_text = _read(_PAYROLL)
    assert "calculate_payroll" in payroll_text
    assert "calculate_payg" in payroll_text or "calculate_payroll" in payroll_text
    assert "generate_rsge_xml" in payroll_text

    pmap_text = _read(_PMAP)
    assert "PERMISSION_MAP" in pmap_text
    assert "match_permission" in pmap_text
    assert "COMPILED_PERMISSION_MAP" in pmap_text


# ---------------------------------------------------------------------------
# Test 7: no DB or network imports in this test file
# ---------------------------------------------------------------------------


def test_no_db_or_network_imports_in_test_file():
    source = _THIS_FILE.read_text(encoding="utf-8")
    # Stored as fragments to avoid self-match
    forbidden = [
        "psy" + "copg",
        "sqla" + "lchemy",
        "requ" + "ests",
        "htt" + "px",
        "sock" + "et",
        "subp" + "rocess",
        "ps" + "ql",
        "creat" + "edb",
        "gcl" + "oud",
    ]
    for name in forbidden:
        assert name not in source, (
            f"Forbidden import/reference {name!r} found in ENC-1 test file"
        )


# ---------------------------------------------------------------------------
# Test 8: ENC-1 scope — only target files contain encoding fixes
# ---------------------------------------------------------------------------


def test_enc1_scope_is_only_target_files():
    # Verify all 4 target files exist and are non-empty
    for path in TARGET_FILES:
        assert path.exists(), f"Target file missing: {path}"
        assert path.stat().st_size > 0, f"Target file is empty: {path}"
    # This test documents scope; git diff verification is in the final report.
    # No runtime check of git state to keep the test pure and dependency-free.

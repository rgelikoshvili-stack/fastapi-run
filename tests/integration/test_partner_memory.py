def test_partner_memory_hook_exists():
    from app.api.transaction_classifier import check_partner_memory
    assert callable(check_partner_memory)
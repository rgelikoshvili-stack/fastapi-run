from app.api.middleware.rbac_middleware import check_permission


def test_rbac_block():
    # viewer — write permission არ აქვს → RBAC block
    assert check_permission("viewer", "write") is False

    # viewer — read permission აქვს
    assert check_permission("viewer", "read") is True

    # admin — ყველაფერი შეუძლია
    assert check_permission("admin", "write") is True

    # operator — write შეუძლია
    assert check_permission("operator", "write") is True
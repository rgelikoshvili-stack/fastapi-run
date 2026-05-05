"""Permission map behavior/performance tests."""


def test_compiled_permission_map_matches_linear_reference_for_sampled_routes():
    from app.api.policy.permission_map import match_permission, linear_match_permission

    samples = [
        ("GET", "/reports/monthly"),
        ("POST", "/reports/export"),
        ("GET", "/metrics"),
        ("POST", "/approval/approve/1"),
        ("GET", "/approval/queue"),
        ("DELETE", "/dashboard/widget/1"),
        ("PATCH", "/posting/123"),
        ("POST", "/webhooks/test"),
        ("GET", "/unknown/path"),
    ]
    for method, path in samples:
        assert match_permission(method, path) == linear_match_permission(method, path)


def test_compiled_permission_map_matches_linear_reference_for_all_entries():
    from app.api.policy.permission_map import PERMISSION_MAP, match_permission, linear_match_permission

    methods = {method for method, _, _ in PERMISSION_MAP if method != "*"} | {"GET", "POST", "PATCH", "DELETE", "PUT"}
    for method in methods:
        for _, prefix, _ in PERMISSION_MAP:
            path = prefix.rstrip("/") + "/sample"
            assert match_permission(method, path) == linear_match_permission(method, path)


def test_metrics_still_requires_dashboard_admin():
    from app.api.policy.permission_map import match_permission

    assert match_permission("GET", "/metrics") == "dashboard:admin"


def test_permission_map_is_compiled_by_method():
    from app.api.policy.permission_map import COMPILED_PERMISSION_MAP, PERMISSION_MAP

    assert isinstance(COMPILED_PERMISSION_MAP, dict)
    assert "GET" in COMPILED_PERMISSION_MAP
    assert len(COMPILED_PERMISSION_MAP["GET"]) < len(PERMISSION_MAP)


def test_rbac_uses_compiled_matcher_not_local_linear_scan():
    import inspect
    import app.api.middleware.rbac_middleware as mod

    src = inspect.getsource(mod)
    assert "from app.api.policy.permission_map import match_permission" in src
    assert "for allowed_method, prefix, permission in PERMISSION_MAP" not in src

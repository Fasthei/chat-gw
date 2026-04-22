from app.sensitive import scan_sensitive_fields


def test_flat_sensitive_keys():
    hits = scan_sensitive_fields({"query": "hi", "api_key": "sk-1", "password": "x"})
    assert set(hits) == {"api_key", "password"}


def test_nested_and_mixed_keys():
    data = {
        "auth": {"token": "t", "user": "u"},
        "payload": {"body": {"api-key": "x"}},
        "misc": {"safe": 1},
    }
    hits = scan_sensitive_fields(data)
    assert "auth.token" in hits
    assert "payload.body.api-key" in hits
    assert "misc.safe" not in hits


def test_list_of_dicts():
    data = {"items": [{"token": "t1"}, {"name": "n"}, {"password": "p"}]}
    hits = scan_sensitive_fields(data)
    assert "items[0].token" in hits
    assert "items[2].password" in hits


def test_case_insensitive():
    data = {"API_KEY": "x", "Password": "y", "Authorization": "z"}
    hits = scan_sensitive_fields(data)
    assert set(hits) == {"API_KEY", "Password", "Authorization"}


def test_empty_and_non_dict():
    assert scan_sensitive_fields({}) == []
    assert scan_sensitive_fields("just-a-string") == []
    assert scan_sensitive_fields(None) == []

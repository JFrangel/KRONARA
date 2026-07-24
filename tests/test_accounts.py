import json

from kronara.accounts import account_status, accounts_for_content_kind, load_accounts


def _write(tmp_path, accounts):
    path = tmp_path / "accounts.v1.json"
    path.write_text(json.dumps({"schema_version": 1, "accounts": accounts}), encoding="utf-8")
    return str(path)


def test_load_shipped_accounts_have_env_references_not_tokens():
    accounts = load_accounts()
    assert accounts  # the shipped config is present
    # Nothing here may look like a secret value -- only env-var NAMES.
    for account in accounts:
        assert account.token_env.startswith("KRONARA_")
        assert account.platform
        assert account.content_kinds


def test_account_status_never_leaks_the_token_value(tmp_path):
    path = _write(tmp_path, [
        {"id": "a", "platform": "facebook", "label": "A", "token_env": "TOK",
         "id_env": "PAGE", "content_kinds": ["narrative_story"], "enabled": True},
    ])
    load_accounts.cache_clear()
    account = load_accounts(path)[0]
    env = {"TOK": "super-secret-value", "PAGE": "12345"}
    status = account_status(account, env)
    assert status["token_present"] is True
    assert status["id_present"] is True
    assert status["configured"] is True
    # The secret VALUE must never appear anywhere in the safe view.
    assert "super-secret-value" not in json.dumps(status)


def test_account_not_configured_when_token_missing_or_disabled(tmp_path):
    path = _write(tmp_path, [
        {"id": "a", "platform": "youtube", "label": "A", "token_env": "TOK",
         "id_env": "", "content_kinds": ["reflection"], "enabled": True},
        {"id": "b", "platform": "tiktok", "label": "B", "token_env": "TOK2",
         "id_env": "", "content_kinds": ["quote"], "enabled": False},
    ])
    load_accounts.cache_clear()
    a, b = load_accounts(path)
    assert account_status(a, {})["configured"] is False  # enabled but no token
    assert account_status(b, {"TOK2": "x"})["configured"] is False  # token but disabled


def test_accounts_for_content_kind_returns_only_configured(tmp_path):
    path = _write(tmp_path, [
        {"id": "yt", "platform": "youtube", "label": "YT", "token_env": "TOK",
         "id_env": "", "content_kinds": ["reflection", "scripture"], "enabled": True},
        {"id": "tt", "platform": "tiktok", "label": "TT", "token_env": "TOK2",
         "id_env": "", "content_kinds": ["reflection"], "enabled": True},
    ])
    load_accounts.cache_clear()
    env = {"TOK": "present"}  # TOK2 missing
    matched = accounts_for_content_kind("reflection", env, path)
    assert [m["id"] for m in matched] == ["yt"]
    assert accounts_for_content_kind("quote", env, path) == []

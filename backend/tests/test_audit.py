from app.audit.logger import redact


def test_redacts_known_secret_fields():
    out = redact({"password": "hunter2", "title": "buy milk", "api_key": "sk-abc123"})
    assert out["password"] == "***REDACTED***"
    assert out["api_key"] == "***REDACTED***"
    assert out["title"] == "buy milk"


def test_redact_handles_empty_and_none():
    assert redact({}) == {}
    assert redact(None) == {}


def test_redact_is_case_insensitive():
    out = redact({"Password": "x", "API_KEY": "y"})
    assert out["Password"] == "***REDACTED***"
    assert out["API_KEY"] == "***REDACTED***"

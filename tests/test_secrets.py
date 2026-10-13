"""Tests for recursive secret redaction."""

import importlib
import importlib.util
import json

import pytest


def test_recursive_redaction_removes_nested_credentials():
    """Nested mappings, sequences and credential text use one redaction policy."""
    module_spec = importlib.util.find_spec("src.utils.secrets")
    assert module_spec is not None, "secret redaction module must exist"
    secrets = importlib.import_module("src.utils.secrets")
    secret = "issue4-fixed-secret-value"
    value = {
        "llm_config": {"api_key": secret, "model": "fake-model"},
        "nested": [
            {"access_token": secret},
            {"token": secret, "id_token": secret, "auth_token": secret},
            f"Authorization: Bearer {secret}",
            f"request failed with api_key={secret}",
        ],
    }

    redacted = secrets.redact_sensitive_data(value)
    serialized = json.dumps(redacted)

    assert secret not in serialized
    assert redacted["llm_config"]["api_key"] == "[REDACTED]"
    assert redacted["llm_config"]["model"] == "fake-model"


def test_webhook_endpoints_are_redacted_as_credentials():
    secrets = importlib.import_module("src.utils.secrets")
    value = secrets.redact_sensitive_data({"webhook_url": "https://example.test/private-token"})
    assert value["webhook_url"] == "[REDACTED]"


def test_text_redaction_handles_quoted_keys_and_authorization_schemes():
    """JSON-like key text and complete authorization values are removed."""
    secrets = importlib.import_module("src.utils.secrets")
    secret = "issue4-quoted-secret"
    text = (
        f'{{"api_key":"{secret}"}} '
        f"{{'client_secret': '{secret}'}} "
        f"Authorization: Basic {secret}"
    )

    redacted = secrets.redact_sensitive_text(text)

    assert secret not in redacted
    assert redacted.count("[REDACTED]") >= 3


def test_sensitive_key_matching_preserves_metrics_and_similar_words():
    """Credential fields are redacted without corrupting ordinary result metrics."""
    secrets = importlib.import_module("src.utils.secrets")
    secret = "issue4-token-secret"
    value = {
        "token": secret,
        "session_token": secret,
        "total_tokens": 30,
        "prompt_tokens": 10,
        "secretary": "person",
        "passwordless": True,
        "credentials_count": 2,
    }

    redacted = secrets.redact_sensitive_data(value)

    assert redacted["token"] == "[REDACTED]"
    assert redacted["session_token"] == "[REDACTED]"
    assert redacted["total_tokens"] == 30
    assert redacted["prompt_tokens"] == 10
    assert redacted["secretary"] == "person"
    assert redacted["passwordless"] is True
    assert redacted["credentials_count"] == 2


def test_text_redaction_is_idempotent_and_hides_digest_authorization():
    """Complete authorization values are removed and repeated cleanup is stable."""
    secrets = importlib.import_module("src.utils.secrets")
    secret = "issue4-digest-response-secret"
    text = f'Authorization: Digest username="demo", response="{secret}"'

    redacted_once = secrets.redact_sensitive_text(text)
    redacted_twice = secrets.redact_sensitive_text(redacted_once)

    assert secret not in redacted_once
    assert redacted_once == redacted_twice
    assert secrets.redact_sensitive_text("api_key=[REDACTED]") == "api_key=[REDACTED]"


def test_text_redaction_handles_escaped_quotes_in_json_authorization():
    """Escaped quotes cannot end a JSON credential value early."""
    secrets = importlib.import_module("src.utils.secrets")
    secret = "issue4-escaped-digest-secret"
    text = '{"Authorization":"Digest username=\\"demo\\", response=\\"' + secret + '\\""}'

    redacted = secrets.redact_sensitive_text(text)

    assert secret not in redacted
    assert "[REDACTED]" in redacted


@pytest.mark.parametrize("known_secret", ["password", "api_key", "Authorization", "Bearer", "="])
def test_known_secrets_cannot_disable_credential_syntax_redaction(known_secret):
    secrets = importlib.import_module("src.utils.secrets")
    text = "password=private-password api_key=private-key\nAuthorization: Bearer private-token"
    redacted = secrets.redact_sensitive_text(text, (known_secret,))
    for value in ("private-password", "private-key", "private-token"):
        assert value not in redacted
    assert secrets.redact_sensitive_text(redacted, (known_secret,)) == redacted


def test_overlapping_known_secrets_redact_longest_value_first():
    secrets = importlib.import_module("src.utils.secrets")
    assert (
        secrets.redact_sensitive_text("failed: abcdefgh", ("abc", "abcdefgh"))
        == "failed: [REDACTED]"
    )


def test_known_secret_containing_placeholder_is_redacted_as_one_value():
    secrets = importlib.import_module("src.utils.secrets")
    key = "prefix[REDACTED]suffix"
    redacted = secrets.redact_sensitive_text(f"provider returned {key}", ("prefix", key, "["))
    assert redacted == "provider returned [REDACTED]"
    assert secrets.redact_sensitive_text(redacted, ("prefix", key, "[")) == redacted

"""Helpers for keeping credentials out of logs and exported data."""

import re
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import SecretStr

REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "access_token",
        "refresh_token",
        "id_token",
        "auth_token",
        "token",
        "password",
        "passwd",
        "secret",
        "credential",
        "credentials",
        "webhook_url",
        "slack_webhook_url",
    }
)
_SENSITIVE_SUFFIXES = tuple(f"_{key}" for key in _SENSITIVE_KEYS)
_DOUBLE_QUOTED_VALUE = r'"(?:\\.|[^"\\])*"'
_SINGLE_QUOTED_VALUE = r"'(?:\\.|[^'\\])*'"
_QUOTED_VALUE = f"(?:{_DOUBLE_QUOTED_VALUE}|{_SINGLE_QUOTED_VALUE})"
_BEARER_VALUE = re.compile(r"(?i)(\bbearer\s+)[^\s,;]+")
_AUTHORIZATION_VALUE = re.compile(
    r"(?i)(?P<prefix>(?:\"|')?authorization(?:\"|')?\s*[:=]\s*)"
    rf"(?P<value>{_QUOTED_VALUE}|[^\r\n}}]+)"
)
_KEY_VALUE = re.compile(
    r"(?P<prefix>(?P<quote>[\"']?)(?P<key>[A-Za-z_][A-Za-z0-9_-]*)(?P=quote)\s*[:=]\s*)"
    rf"(?P<value>{_QUOTED_VALUE}|[^\s,;&}}]+)"
)


def is_sensitive_key(key: object) -> bool:
    """Return whether a mapping key conventionally contains a credential."""
    if not isinstance(key, str):
        return False
    normalized = key.casefold().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith(_SENSITIVE_SUFFIXES)


def _redacted_assignment(match: re.Match) -> str:
    """Preserve assignment punctuation while replacing its value."""
    value = match.group("value")
    quoted = len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}
    unquoted = value[1:-1] if quoted else value
    if unquoted == REDACTED:
        return str(match.group(0))
    if quoted:
        replacement = f"{value[0]}{REDACTED}{value[-1]}"
    else:
        replacement = REDACTED
    return f"{match.group('prefix')}{replacement}"


def _redact_key_value(match: re.Match) -> str:
    """Redact only assignments whose key is credential-bearing."""
    if not is_sensitive_key(match.group("key")):
        return str(match.group(0))
    return _redacted_assignment(match)


def _redact_mapping_value(key: object, value: Any, known_secrets: tuple[str, ...]) -> Any:
    """Redact non-empty credential fields without inventing a secret value."""
    if not is_sensitive_key(key):
        return redact_sensitive_data(value, known_secrets)
    if value is None or value == "":
        return value
    if isinstance(value, SecretStr) and not value.get_secret_value():
        return ""
    return REDACTED


def redact_sensitive_text(text: str, known_secrets: Iterable[str] = ()) -> str:
    """Remove credential-shaped text and explicitly known secret values."""
    # Known values can themselves be syntax such as "password" or "=".
    # Recognize credential fields before substitutions can alter their labels.
    redacted = _AUTHORIZATION_VALUE.sub(_redacted_assignment, text)
    redacted = _BEARER_VALUE.sub(lambda match: f"{match.group(1)}{REDACTED}", redacted)
    redacted = _KEY_VALUE.sub(_redact_key_value, redacted)
    values = {value for value in known_secrets if value and value != REDACTED}
    if values:
        # Match complete keys (including keys containing a literal placeholder)
        # and existing placeholders in one pass, longest alternatives first.
        # This also prevents short keys from modifying replacement markers.
        values.add(REDACTED)
        pattern = re.compile(
            "|".join(re.escape(value) for value in sorted(values, key=len, reverse=True))
        )
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


def redact_sensitive_data(value: Any, known_secrets: Iterable[str] = ()) -> Any:
    """Recursively redact credentials while preserving ordinary data."""
    secrets = tuple(secret for secret in known_secrets if secret)

    if isinstance(value, SecretStr):
        return REDACTED
    if isinstance(value, Mapping):
        return {key: _redact_mapping_value(key, item, secrets) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item, secrets) for item in value)
    if isinstance(value, list):
        return [redact_sensitive_data(item, secrets) for item in value]
    if isinstance(value, set):
        return {redact_sensitive_data(item, secrets) for item in value}
    if isinstance(value, str):
        return redact_sensitive_text(value, secrets)
    return value

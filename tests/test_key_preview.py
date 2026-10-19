"""Unit tests for API key list masked previews."""

from api.auth.key_preview import masked_preview_from_secret


def test_masked_preview_uses_seven_char_prefix_and_fixed_length():
    secret = "sk-private-unique-test-value"
    preview = masked_preview_from_secret(secret)
    assert preview.startswith(secret[:7])
    assert len(preview) == 35
    assert preview.endswith("*")
    assert secret not in preview


def test_short_secret_still_fixed_length():
    preview = masked_preview_from_secret("ab")
    assert preview == "ab" + "*" * 33

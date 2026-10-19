"""Fixed-format API key previews for list metadata (prefix + asterisks)."""

MASKED_PREVIEW_LEN = 35
MAX_VISIBLE_PREFIX = 7


def masked_preview_from_secret(secret: str) -> str:
    prefix = secret[: min(MAX_VISIBLE_PREFIX, len(secret))]
    pad = MASKED_PREVIEW_LEN - len(prefix)
    return prefix + ("*" * pad if pad > 0 else "")

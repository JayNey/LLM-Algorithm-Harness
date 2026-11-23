"""Deployment-owned authorization for user-controlled Web HTTP alert rules."""

import ipaddress
import re
from urllib.parse import urlsplit

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError

_REJECTED = "Web alert target is not an allowed HTTPS delivery URL"
_DNS_NAME = re.compile(
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)*\.?\Z"
)


class WebAlertTargetSettings(BaseSettings):
    """Only deployment configuration can authorize full webhook destinations."""

    model_config = SettingsConfigDict(
        env_prefix="COST_ALERT_",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )
    allowed_webhook_urls: list[SecretStr] = Field(default_factory=list)


def _valid_https_url(target: str) -> bool:
    # Reject syntax that parsers may discard or interpret differently. Do not
    # resolve user input: DNS authority belongs to the trusted deployment list.
    if (
        not target.startswith("https://")
        or "\\" in target
        or "#" in target
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in target)
    ):
        return False
    try:
        parsed = urlsplit(target)
        host = parsed.hostname
        if not host or parsed.username is not None or parsed.password is not None:
            return False
        if parsed.port is not None and parsed.port == 0:
            return False
        if ":" in host:
            if re.fullmatch(r"\[[^\]]+\](?::[0-9]+)?", parsed.netloc) is None:
                return False
            ipaddress.IPv6Address(host)
            return "%" not in host
        return (
            re.fullmatch(r"[^:]+(?::[0-9]+)?", parsed.netloc) is not None
            and _DNS_NAME.fullmatch(host) is not None
        )
    except ValueError:
        return False


def authorized_alert_target(channel: str, target: str) -> str:
    """Return the deployment's exact authorized URL, or a secret-free error.

    SMTP recipients and local log rules do not authorize HTTP destinations.
    No network lookup is performed for either accepted or rejected input.
    """
    if channel not in {"slack", "webhook"}:
        return target
    if not _valid_https_url(target):
        raise ValueError(_REJECTED)
    try:
        settings = WebAlertTargetSettings()
    except (ValueError, SettingsError):
        raise ValueError(_REJECTED) from None
    for allowed in settings.allowed_webhook_urls:
        configured = allowed.get_secret_value()
        if target == configured:
            return configured
    raise ValueError(_REJECTED)

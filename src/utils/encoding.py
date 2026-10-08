"""Explicit UTF-8 contract for Python child process standard streams."""

from __future__ import annotations

import os
from collections.abc import Mapping


def utf8_subprocess_env(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy the intended environment and make Python pipe output match UTF-8 decoding."""
    return {**(os.environ if environment is None else environment), "PYTHONIOENCODING": "utf-8"}

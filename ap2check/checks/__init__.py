"""All checks, in report order. Each is a plain deterministic function CheckInput -> result."""

from __future__ import annotations

from collections.abc import Callable

from ap2check.checks import agent_card, profile, signature
from ap2check.models import CheckInput, CheckResult

ALL_CHECKS: list[Callable[[CheckInput], CheckResult]] = [
    *profile.CHECKS,
    *agent_card.CHECKS,
    *signature.CHECKS,
]

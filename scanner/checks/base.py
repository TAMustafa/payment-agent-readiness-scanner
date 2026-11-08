"""Helpers shared by check implementations."""

from __future__ import annotations

from scanner.checks.copy import get_guidance
from scanner.models import CheckResult, CheckStatus, Evidence, ScanContext


def result(
    check_id: str,
    ctx: ScanContext,
    status: CheckStatus,
    score_fraction: float,
    evidence: list[Evidence],
) -> CheckResult:
    """Build a CheckResult with metadata from the registry and guidance from copy/."""
    # Imported at call time: the registry imports every check module, so a module-level
    # import here would be circular whichever module is imported first.
    from scanner.checks.registry import REGISTRY

    spec = REGISTRY[check_id]
    return CheckResult(
        id=spec.id,
        category=spec.category,
        label=spec.label,
        status=status,
        weight=spec.weight,
        score_fraction=round(max(0.0, min(1.0, score_fraction)), 4),
        evidence=evidence,
        guidance="" if status == "pass" else get_guidance(spec.id, ctx.options.lang),
        effort=spec.effort,
    )

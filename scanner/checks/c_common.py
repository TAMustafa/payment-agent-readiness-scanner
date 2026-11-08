"""Shared handling of a probe that did not run or stopped early (C1-C4)."""

from __future__ import annotations

from scanner.checks.base import result
from scanner.models import CheckoutProbe, CheckResult, Evidence, ScanContext

NOT_LIVE_NOTE = (
    "Agent checkout is not live for Dutch merchants yet; this measures readiness of the "
    "normal web checkout for browser-based agents."
)


def probe_steps(probe: CheckoutProbe) -> list[Evidence]:
    return [
        Evidence(url=s.url, detail=f"{s.name}: {s.outcome} - {s.detail}", snippet=s.screenshot)
        for s in probe.steps
    ]


def not_run(check_id: str, ctx: ScanContext) -> CheckResult | None:
    """Result for a probe that was skipped/disabled before reaching this check's step."""
    p = ctx.checkout
    if p.skipped_kind == "disabled":
        return result(
            check_id,
            ctx,
            "not_applicable",
            0.0,
            [Evidence(detail=f"Not tested: {p.skipped_reason or 'checkout probe disabled'}")],
        )
    if p.skipped_kind == "robots":
        return result(
            check_id,
            ctx,
            "not_applicable",
            0.0,
            [
                Evidence(
                    detail=f"Not tested: {p.skipped_reason}. Run with merchant consent "
                    "(--checkout-consent) to test it."
                ),
                *probe_steps(p),
            ],
        )
    return None


def technical_error(check_id: str, ctx: ScanContext, why: str) -> CheckResult:
    p = ctx.checkout
    reason = p.skipped_reason or why
    return result(
        check_id,
        ctx,
        "error",
        0.0,
        [Evidence(detail=f"Probe could not reach this step: {reason}"), *probe_steps(p)],
    )

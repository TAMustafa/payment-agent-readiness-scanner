"""D5.merchant_center — Google Merchant Center feed active and healthy.

Manual input only (no Merchant Center API access in v1, SPEC §2): never guessed.
not_applicable without input. Thresholds are an initial choice, to confirm:
active and <= 5% disapproved -> pass; <= 20% -> warn; more, or inactive -> fail.
"""

from __future__ import annotations

from scanner.checks.base import result
from scanner.models import CheckResult, CheckStatus, Evidence, ScanContext

CHECK_ID = "D5.merchant_center"
PASS_MAX_PCT = 5.0
WARN_MAX_PCT = 20.0


async def check(ctx: ScanContext) -> CheckResult:
    o = ctx.options
    if o.merchant_center_active is None:
        return result(
            CHECK_ID,
            ctx,
            "not_applicable",
            0.0,
            [Evidence(detail="No Merchant Center input provided (manual input; never guessed)")],
        )
    if not o.merchant_center_active:
        return result(
            CHECK_ID,
            ctx,
            "fail",
            0.0,
            [Evidence(detail="Operator input: no active Google Merchant Center feed")],
        )
    pct = o.merchant_center_disapproved_pct
    if pct is None:
        return result(
            CHECK_ID,
            ctx,
            "warn",
            0.5,
            [Evidence(detail="Operator input: feed active; disapproval % not provided")],
        )
    detail = f"Operator input: feed active, {pct:g}% of products disapproved"
    if pct <= PASS_MAX_PCT:
        return result(CHECK_ID, ctx, "pass", 1.0, [Evidence(detail=detail)])
    fraction = max(0.0, 1 - pct / 100)
    status: CheckStatus = "warn" if pct <= WARN_MAX_PCT else "fail"
    return result(CHECK_ID, ctx, status, fraction, [Evidence(detail=detail)])

"""C2.guest_checkout — checkout reachable without forced account creation."""

from __future__ import annotations

from scanner.checks.base import result
from scanner.checks.c_common import not_run, probe_steps, technical_error
from scanner.models import CheckResult, Evidence, ScanContext

CHECK_ID = "C2.guest_checkout"


async def check(ctx: ScanContext) -> CheckResult:
    p = ctx.checkout
    if not p.checkout_reached:
        return not_run(CHECK_ID, ctx) or technical_error(CHECK_ID, ctx, "checkout not reached")
    steps = probe_steps(p)
    if p.guest_option:
        return result(
            CHECK_ID,
            ctx,
            "pass",
            1.0,
            [Evidence(url=p.checkout_url, detail="Checkout can be done as a guest"), *steps],
        )
    if p.login_wall:
        return result(
            CHECK_ID,
            ctx,
            "fail",
            0.0,
            [
                Evidence(
                    url=p.checkout_url,
                    detail="Checkout requires logging in or creating an "
                    "account (password field, no guest option)",
                ),
                *steps,
            ],
        )
    return result(
        CHECK_ID,
        ctx,
        "warn",
        0.5,
        [
            Evidence(
                url=p.checkout_url,
                detail="Checkout reached, but no clear guest option or "
                "login wall detected; verify manually",
            ),
            *steps,
        ],
    )

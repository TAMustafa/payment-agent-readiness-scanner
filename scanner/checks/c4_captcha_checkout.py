"""C4.captcha_checkout — no captcha on checkout entry (reCAPTCHA, hCaptcha, Turnstile, ...)."""

from __future__ import annotations

from scanner.checks.base import result
from scanner.checks.c_common import not_run, probe_steps, technical_error
from scanner.models import CheckResult, Evidence, ScanContext

CHECK_ID = "C4.captcha_checkout"


async def check(ctx: ScanContext) -> CheckResult:
    p = ctx.checkout
    if not p.checkout_reached:
        return not_run(CHECK_ID, ctx) or technical_error(CHECK_ID, ctx, "checkout not reached")
    if p.captcha_markers:
        return result(
            CHECK_ID,
            ctx,
            "fail",
            0.0,
            [
                Evidence(
                    url=p.checkout_url,
                    detail=f"Captcha on checkout entry: {', '.join(p.captcha_markers)}",
                ),
                *probe_steps(p),
            ],
        )
    return result(
        CHECK_ID,
        ctx,
        "pass",
        1.0,
        [
            Evidence(url=p.checkout_url, detail="No captcha markers on checkout entry"),
            *probe_steps(p),
        ],
    )

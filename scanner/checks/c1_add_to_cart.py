"""C1.add_to_cart — add-to-cart works headless without captcha or bot challenge.

Fail on a challenge; warn on more than 2 interstitials (the cookie banner counts once);
error when the probe could not run or confirm for a technical reason (SPEC §4 C).
"""

from __future__ import annotations

from scanner.checks.base import result
from scanner.checks.c_common import probe_steps, technical_error
from scanner.models import CheckResult, Evidence, ScanContext

CHECK_ID = "C1.add_to_cart"


async def check(ctx: ScanContext) -> CheckResult:
    p = ctx.checkout
    steps = probe_steps(p)
    if p.skipped_kind == "disabled":
        return result(
            CHECK_ID,
            ctx,
            "not_applicable",
            0.0,
            [Evidence(detail=f"Not tested: {p.skipped_reason or 'checkout probe disabled'}")],
        )
    if p.challenge and not p.added_to_cart:
        return result(
            CHECK_ID,
            ctx,
            "fail",
            0.0,
            [
                Evidence(url=p.product_url, detail=f"Bot challenge before the cart: {p.challenge}"),
                *steps,
            ],
        )
    if p.added_to_cart:
        cookie = 1 if "cookie banner" in p.interstitials else 0
        others = sum(1 for i in p.interstitials if i != "cookie banner")
        total = cookie + others
        detail = f"Product added to cart headless; {total} interstitial(s)"
        if total > 2:
            return result(
                CHECK_ID,
                ctx,
                "warn",
                0.7,
                [Evidence(url=p.product_url, detail=detail + " (more than 2)"), *steps],
            )
        return result(
            CHECK_ID, ctx, "pass", 1.0, [Evidence(url=p.product_url, detail=detail), *steps]
        )
    if p.skipped_kind == "robots":
        return result(
            CHECK_ID,
            ctx,
            "not_applicable",
            0.0,
            [
                Evidence(
                    detail=f"Not tested: {p.skipped_reason}. Run with merchant consent "
                    "(--checkout-consent) to test it."
                ),
                *steps,
            ],
        )
    return technical_error(CHECK_ID, ctx, "add-to-cart not confirmed")

"""C3.payment_methods — iDEAL / Wero offered; note cards, PayPal, Klarna, Apple/Google Pay.

Sources: the checkout page (probe), the home page and policy pages (payment logos and text).
Privacy pages are excluded: they list data processors (e.g. Klarna), not payment methods.
Pass if iDEAL or Wero is present. Fail only when the probe saw the checkout itself without
them; when only home/policy pages were seen, missing logos are a warn (not proof).
"""

from __future__ import annotations

from scanner.checkout.markers import payment_haystack, payment_methods_in
from scanner.checks.base import result
from scanner.models import CheckResult, Evidence, ScanContext

CHECK_ID = "C3.payment_methods"
REQUIRED = ("iDEAL", "Wero")


async def check(ctx: ScanContext) -> CheckResult:
    found: dict[str, str] = dict(ctx.checkout.payment_methods)
    pages = [ctx.basics.home] + [p for k, p in ctx.pages.policies.items() if k != "privacy"]
    for page in pages:
        if page is None or not page.ok:
            continue
        for m in payment_methods_in(payment_haystack(page.body or "")):
            found.setdefault(m, page.final_url or page.url)
    if not found:
        return result(
            CHECK_ID,
            ctx,
            "warn",
            0.0,
            [
                Evidence(
                    detail="No payment method information found on checkout, home or policy pages"
                )
            ],
        )
    evidence = [Evidence(url=url, detail=f"{m} shown") for m, url in sorted(found.items())]
    have = [m for m in REQUIRED if m in found]
    if have:
        evidence.insert(
            0,
            Evidence(
                detail=f"{' and '.join(have)} offered; also: "
                + ", ".join(m for m in sorted(found) if m not in have)
            ),
        )
        return result(CHECK_ID, ctx, "pass", 1.0, evidence)
    if ctx.checkout.checkout_reached:
        evidence.insert(
            0,
            Evidence(
                url=ctx.checkout.checkout_url,
                detail="Neither iDEAL nor Wero offered on the checkout page",
            ),
        )
        return result(CHECK_ID, ctx, "fail", 0.0, evidence)
    evidence.insert(
        0,
        Evidence(
            detail="iDEAL / Wero not listed on the home or policy pages "
            "(checkout not inspected, so not proof they are missing)"
        ),
    )
    return result(CHECK_ID, ctx, "warn", 0.3, evidence)

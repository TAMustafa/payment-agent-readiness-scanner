"""C3.payment_methods — cards (for agent payments) and iDEAL / Wero (for Dutch customers).

Changed 2026-11-10 (Tarek: "only if agent documentation requires cards"; it does):
- OpenAI ACP Delegated Payment Spec: payment method is a card ("fpan" or "network_token")
  https://developers.openai.com/commerce/specs/payment
- Google UCP: Google Pay payment handler (card credentials); the merchant's PSP must process
  Google's tokens https://developers.google.com/merchant/ucp/faq
- Visa Intelligent Commerce / Mastercard Agent Pay: agentic card tokens.
iDEAL / Wero stay required for the Dutch customer (bank redirect, handed back to the shop).

Sources: the checkout page (probe), the home page and policy pages (payment logos and text).
Privacy pages are excluded: they list data processors (e.g. Klarna), not payment methods.
Pass: a card option (Visa, Mastercard, Amex, or the card wallets Apple Pay / Google Pay) AND
iDEAL or Wero. One of the two: warn (0.5). Neither: fail when the probe saw the checkout.
Unverifiable -> error, never a guessed warn/fail (changed 2026-11-12): no payment
information at all, or neither cards nor iDEAL/Wero on home/policy pages while the checkout
was not inspected (missing logos are not proof), or a checkout entry page without any
payment marker (the payment choice is usually a later step, which the probe never opens).
"""

from __future__ import annotations

from scanner.checkout.markers import payment_haystack, payment_methods_in
from scanner.checks.base import result
from scanner.models import CheckResult, Evidence, ScanContext

CHECK_ID = "C3.payment_methods"
DUTCH = ("iDEAL", "Wero")
CARDS = ("Visa", "Mastercard", "American Express", "Apple Pay", "Google Pay")


async def check(ctx: ScanContext) -> CheckResult:
    found: dict[str, str] = dict(ctx.checkout.payment_methods)
    pages = [ctx.basics.home] + [p for k, p in ctx.pages.policies.items() if k != "privacy"]
    for page in pages:
        if page is None or not page.ok:
            continue
        for m in payment_methods_in(payment_haystack(page.body or "")):
            found.setdefault(m, page.final_url or page.url)
    if not found:
        detail = (
            "No payment methods visible on the first checkout page; the payment choice is "
            "probably a later step, which we never open, so we cannot tell"
            if ctx.checkout.checkout_reached
            else "No payment method information on the home or policy pages and checkout "
            "not inspected, so we cannot tell which payment methods are offered"
        )
        return result(
            CHECK_ID, ctx, "error", 0.0, [Evidence(url=ctx.checkout.checkout_url, detail=detail)]
        )
    evidence = [Evidence(url=url, detail=f"{m} shown") for m, url in sorted(found.items())]
    dutch = [m for m in DUTCH if m in found]
    cards = [m for m in CARDS if m in found]
    if dutch and cards:
        evidence.insert(
            0,
            Evidence(detail=f"Cards ({', '.join(cards)}) and {' and '.join(dutch)} offered"),
        )
        return result(CHECK_ID, ctx, "pass", 1.0, evidence)
    if dutch or cards:
        missing = (
            "no card payment (Visa/Mastercard or Apple/Google Pay) seen: needed for agent payments"
            if dutch
            else "iDEAL / Wero not seen: the payment Dutch customers expect"
        )
        where = "" if ctx.checkout.checkout_reached else " (checkout not inspected)"
        evidence.insert(0, Evidence(detail=f"{', '.join(dutch + cards)} offered; {missing}{where}"))
        return result(CHECK_ID, ctx, "warn", 0.5, evidence)
    if ctx.checkout.checkout_reached:
        evidence.insert(
            0,
            Evidence(
                url=ctx.checkout.checkout_url,
                detail="Neither cards nor iDEAL / Wero offered on the checkout page",
            ),
        )
        return result(CHECK_ID, ctx, "fail", 0.0, evidence)
    evidence.insert(
        0,
        Evidence(
            detail="Cards and iDEAL / Wero not listed on the home or policy pages and checkout "
            "not inspected, so we cannot tell which payment methods are offered"
        ),
    )
    return result(CHECK_ID, ctx, "error", 0.0, evidence)

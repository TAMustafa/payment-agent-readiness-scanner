"""C3 (from home/policy pages, no probe) and C5 (policy text) on fixtures."""

from __future__ import annotations

from scanner.checks import c1_add_to_cart, c2_guest_checkout, c3_payment_methods, c5_policies
from scanner.models import (
    CheckoutProbe,
    FetchedResource,
    PageSample,
    PlatformInfo,
    ScanContext,
    ScanOptions,
    SiteBasics,
)

ORIGIN = "https://shop.example.nl"


def page(path: str, body: str, status: int = 200) -> FetchedResource:
    return FetchedResource(url=f"{ORIGIN}{path}", status_code=status, body=body)


def ctx(
    home: str = "<html></html>",
    policies: dict[str, FetchedResource] | None = None,
    probe: CheckoutProbe | None = None,
) -> ScanContext:
    return ScanContext(
        origin=ORIGIN,
        options=ScanOptions(),
        basics=SiteBasics(final_url=f"{ORIGIN}/", origin=ORIGIN, https=True, home=page("/", home)),
        platform=PlatformInfo(),
        pages=PageSample(policies=policies or {}),
        checkout=probe or CheckoutProbe(),
    )


async def test_c3_from_footer_logos_and_payment_page() -> None:
    footer = '<footer><img src="/logos/ideal.svg" alt=""><img alt="Klarna"></footer>'
    r = await c3_payment_methods.check(ctx(home=footer))
    assert r.status == "pass" and "iDEAL" in r.evidence[0].detail
    no_ideal = await c3_payment_methods.check(
        ctx(policies={"payment": page("/betaalmethoden", "<p>Betaal met PayPal of Visa</p>")})
    )
    assert no_ideal.status == "warn" and "not proof" in no_ideal.evidence[0].detail
    seen = ctx(
        policies={"payment": page("/betaalmethoden", "<p>PayPal</p>")},
        probe=CheckoutProbe(checkout_reached=True, checkout_url=f"{ORIGIN}/checkout"),
    )
    assert (await c3_payment_methods.check(seen)).status == "fail"
    processors = ctx(policies={"privacy": page("/privacy", "<p>Wij delen data met Klarna</p>")})
    assert (await c3_payment_methods.check(processors)).status == "warn"
    assert "Klarna" not in str((await c3_payment_methods.check(processors)).evidence)
    nothing = await c3_payment_methods.check(ctx())
    assert nothing.status == "warn"


async def test_c3_ignores_challenge_home_page() -> None:
    c = ctx(home="<html><title>Just a moment...</title>ideal</html>")
    assert c.basics.home is not None
    c.basics.home.status_code = 403
    assert (await c3_payment_methods.check(c)).status == "warn"


async def test_c5_policy_text() -> None:
    full = {
        "shipping": page(
            "/verzenden", "<p>Gratis verzending vanaf €50. Levertijd 1-2 werkdagen.</p>"
        ),
        "returns": page("/retour", "<p>Je hebt 30 dagen bedenktijd om te retourneren.</p>"),
    }
    r = await c5_policies.check(ctx(policies=full))
    assert r.status == "pass" and r.score_fraction == 1.0
    partial = {"returns": page("/retour", "<p>Retourneren kan binnen 14 dagen.</p>")}
    r2 = await c5_policies.check(ctx(policies=partial))
    assert r2.status == "warn" and abs(r2.score_fraction - 1 / 3) < 1e-3
    assert (await c5_policies.check(ctx())).status == "error"


async def test_c5_embedded_page_data_gets_half_credit() -> None:
    nextjs = (
        "<html><body><h1>Bezorgen</h1><p>Wat zijn de verzendkosten?</p>"
        '<script>self.__next_f.push([1,"\\u003cli\\u003eThuislevering: 1-3 werkdagen'
        '\\u003c/li\\u003e"])</script></body></html>'
    )
    r = await c5_policies.check(ctx(policies={"shipping": page("/bezorgen", nextjs)}))
    delivery = next(e for e in r.evidence if e.detail.startswith("delivery time"))
    assert "only in embedded page data" in delivery.detail
    assert abs(r.score_fraction - 1.5 / 3) < 1e-3


async def test_c_checks_when_probe_disabled_or_without_products() -> None:
    disabled = ctx(probe=CheckoutProbe(skipped_kind="disabled"))
    assert (await c1_add_to_cart.check(disabled)).status == "not_applicable"
    no_products = ctx(
        probe=CheckoutProbe(skipped_kind="technical", skipped_reason="no product page sampled")
    )
    r = await c2_guest_checkout.check(no_products)
    assert r.status == "error" and "no product page sampled" in r.evidence[0].detail

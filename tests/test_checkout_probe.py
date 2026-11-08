"""Checkout probe in real headless Chromium against a fake shop (no network).

The browser's requests are fulfilled by a Playwright route hook, so nothing leaves the
machine. Skipped automatically when Chromium is not installed.
"""

from __future__ import annotations

from typing import Any

import pytest

from scanner.checkout import probe as probe_mod
from scanner.checks import (
    c1_add_to_cart,
    c2_guest_checkout,
    c3_payment_methods,
    c4_captcha_checkout,
    d4_rendering,
)
from scanner.fetch.client import PoliteClient
from scanner.fetch.robots import RobotsTxt
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
PRODUCT_URL = f"{ORIGIN}/product/fietstas/"

PRODUCT_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Fietstas</title>
<script type="application/ld+json">{"@type":"Product","name":"Fietstas","image":"x",
"description":"y","offers":{"@type":"Offer","price":"49.95","priceCurrency":"EUR",
"availability":"https://schema.org/InStock"}}</script>
</head><body>
<div id="cookies" role="dialog"><p>Wij gebruiken cookies</p>
  <button onclick="document.getElementById('cookies').remove()">Alles accepteren</button>
  <button onclick="document.getElementById('cookies').remove()">Alles weigeren</button></div>
<h1>Fietstas</h1><div id="price"></div>
<button class="buy-now">Koop nu met PayPal</button>
<button id="atc"
 onclick="fetch('/cart/add',{method:'POST'}).then(()=>location.href='/cart')"
>In winkelwagen</button>
<script>document.getElementById('price').textContent='€ 49,95 - Op voorraad'</script>
</body></html>"""

CART_FULL = """<html><body><h1>Winkelwagen</h1><p>Fietstas x1</p>
<a href="/checkout">Afrekenen</a> <button>Betaal met PayPal</button></body></html>"""
CART_EMPTY = "<html><body><p>Je winkelwagen is leeg</p></body></html>"

CHECKOUT_GUEST = """<html><body><h1>Afrekenen</h1>
<p>Bestellen als gast of <a href="/login">inloggen</a></p>
<input type="email" name="email"><input name="postcode">
<img alt="iDEAL" src="/img/ideal.svg"><img alt="Visa" src="/img/visa.svg">
<button>Bestelling plaatsen</button></body></html>"""
CHECKOUT_LOGIN = """<html><body><h1>Inloggen</h1><p>Log in om je bestelling af te ronden</p>
<input type="email" name="email"><input type="password" name="password">
<button>Inloggen</button></body></html>"""
CHECKOUT_CAPTCHA = """<html><head><script src="https://www.google.com/recaptcha/api.js"></script>
</head><body><h1>Afrekenen</h1><p>Bestellen als gast</p><div class="g-recaptcha"></div>
<input type="email" name="email"></body></html>"""
CHALLENGE = "<html><head><title>Just a moment...</title></head><body>cf-chl-</body></html>"


class BrowserShop:
    def __init__(self, checkout_html: str = CHECKOUT_GUEST, challenge: bool = False) -> None:
        self.checkout_html = checkout_html
        self.challenge = challenge
        self.added = False
        self.requests: list[tuple[str, str]] = []  # (method, path)

    async def hook(self, route: Any) -> None:
        req = route.request
        path = req.url.replace(ORIGIN, "").split("?")[0] or "/"
        self.requests.append((req.method, path))
        if not req.url.startswith(ORIGIN):
            await route.abort()
        elif path == "/product/fietstas/":
            if self.challenge:
                await route.fulfill(
                    status=403,
                    body=CHALLENGE,
                    content_type="text/html",
                    headers={"cf-mitigated": "challenge"},
                )
            else:
                await route.fulfill(status=200, body=PRODUCT_HTML, content_type="text/html")
        elif path == "/cart/add" and req.method == "POST":
            self.added = True
            await route.fulfill(status=200, body="{}", content_type="application/json")
        elif path == "/cart":
            body = CART_FULL if self.added else CART_EMPTY
            await route.fulfill(status=200, body=body, content_type="text/html")
        elif path == "/checkout":
            await route.fulfill(status=200, body=self.checkout_html, content_type="text/html")
        else:
            await route.fulfill(status=404, body="nf", content_type="text/html")


@pytest.fixture(autouse=True)
def fast_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probe_mod, "SETTLE_MS", 50)
    monkeypatch.setattr(probe_mod, "ADD_WAIT_MS", 300)
    monkeypatch.setattr(probe_mod, "BANNER_WAIT_MS", 50)


def pages() -> PageSample:
    return PageSample(
        products=[FetchedResource(url=PRODUCT_URL, status_code=200, body=PRODUCT_HTML)]
    )


async def run(shop: BrowserShop, robots: str | None = None, consent: bool = False) -> CheckoutProbe:
    async with PoliteClient(min_interval_s=0) as client:
        if robots is not None:
            client.set_robots("shop.example.nl", RobotsTxt.parse(robots))
        probe = await probe_mod.run_probe(
            client, ORIGIN, "woocommerce", pages(), consent=consent, route_hook=shop.hook
        )
    if probe.skipped_reason and "Chromium not available" in probe.skipped_reason:
        pytest.skip("Chromium not installed")
    return probe


def ctx_with(probe: CheckoutProbe) -> ScanContext:
    return ScanContext(
        origin=ORIGIN,
        options=ScanOptions(),
        basics=SiteBasics(final_url=f"{ORIGIN}/", origin=ORIGIN, https=True),
        platform=PlatformInfo(platform="woocommerce"),
        pages=pages(),
        checkout=probe,
    )


async def test_happy_path_guest_checkout_with_ideal() -> None:
    shop = BrowserShop()
    p = await run(shop)
    assert p.added_to_cart and p.checkout_reached and p.guest_option and not p.login_wall
    assert p.interstitials == ["cookie banner"]
    assert any("rejected" in s.detail for s in p.steps if s.name == "cookie_banner")
    assert "iDEAL" in p.payment_methods
    # read-only: one POST (add to cart), never a click on PayPal / order buttons
    assert [r for r in shop.requests if r[0] == "POST"] == [("POST", "/cart/add")]
    c = ctx_with(p)
    assert (await c1_add_to_cart.check(c)).status == "pass"
    assert (await c2_guest_checkout.check(c)).status == "pass"
    assert (await c3_payment_methods.check(c)).status == "pass"
    assert (await c4_captcha_checkout.check(c)).status == "pass"
    # D4: the probe recorded what the rendered page shows
    assert p.rendered and p.rendered[0].price_visible and p.rendered[0].stock_visible


async def test_d4_tells_js_only_apart_from_absent() -> None:
    from scanner.models import RenderedPage

    js_only = FetchedResource(
        url=PRODUCT_URL,
        status_code=200,
        body="<html><body><h1>Lamp</h1><div id=p></div></body></html>",
    )
    c = ctx_with(
        CheckoutProbe(
            rendered=[RenderedPage(url=PRODUCT_URL, price_visible=True, stock_visible=True)]
        )
    )
    c.pages.products = [js_only]
    d4 = await d4_rendering.check(c)
    assert d4.status == "fail"
    assert any("after JavaScript rendering: price, availability" in e.detail for e in d4.evidence)
    c.checkout.rendered[0].price_visible = c.checkout.rendered[0].stock_visible = False
    d4b = await d4_rendering.check(c)
    assert any("also absent after JavaScript rendering" in e.detail for e in d4b.evidence)


async def test_login_wall_fails_c2() -> None:
    p = await run(BrowserShop(checkout_html=CHECKOUT_LOGIN))
    assert p.checkout_reached and p.login_wall
    assert (await c2_guest_checkout.check(ctx_with(p))).status == "fail"


async def test_captcha_on_checkout_fails_c4() -> None:
    p = await run(BrowserShop(checkout_html=CHECKOUT_CAPTCHA))
    assert "reCAPTCHA" in p.captcha_markers
    assert (await c4_captcha_checkout.check(ctx_with(p))).status == "fail"


async def test_bot_challenge_fails_c1() -> None:
    p = await run(BrowserShop(challenge=True))
    assert p.challenge and not p.added_to_cart
    assert (await c1_add_to_cart.check(ctx_with(p))).status == "fail"


async def test_robots_disallowed_checkout_is_never_requested() -> None:
    shop = BrowserShop()
    p = await run(shop, robots="User-agent: *\nDisallow: /checkout\n")
    assert p.added_to_cart and not p.checkout_reached and p.skipped_kind == "robots"
    assert ("GET", "/checkout") not in shop.requests
    c = ctx_with(p)
    assert (await c1_add_to_cart.check(c)).status == "pass"  # cart step was allowed
    c2 = await c2_guest_checkout.check(c)
    assert c2.status == "not_applicable" and "--checkout-consent" in c2.evidence[0].detail


async def test_consent_lifts_robots_for_checkout() -> None:
    shop = BrowserShop()
    p = await run(shop, robots="User-agent: *\nDisallow: /checkout\n", consent=True)
    assert p.checkout_reached and ("GET", "/checkout") in shop.requests

"""Safety guarantees: the scanner can never pay, order, log in or enter data.

1. Source scan: no code path that types, fills, uploads or sends non-GET HTTP requests.
2. Guard table: payment hosts, order paths and non-GET requests are refused.
3. Hostile fake shops in real headless Chromium: a cart whose "checkout" button posts to a
   place-order URL and redirects to a payment provider; a one-page checkout with a
   "Bestellen" button; a page that fires a background POST. None of it gets through.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Any

import pytest

from scanner.checkout import probe as probe_mod
from scanner.checkout.markers import FORBIDDEN_CLICK
from scanner.fetch.client import PoliteClient
from scanner.models import FetchedResource, PageSample

ROOT = pathlib.Path(__file__).parent.parent / "scanner"
ORIGIN = "https://shop.example.nl"
PRODUCT_URL = f"{ORIGIN}/product/x/"


# --- 1. source scan --------------------------------------------------------------------

FORBIDDEN_CALLS = {
    "fill",
    "type",
    "press",
    "press_sequentially",
    "set_input_files",
    "check",
    "uncheck",
    "post",
    "put",
    "patch",
    "delete",
    "submit",
    "insert_text",
    "dispatch_event",
}


def _called_attrs(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }


# The single documented exception: the V1 OpenRouter client must POST its chat requests,
# and only to https://openrouter.ai (asserted by test_openrouter_client_is_pinned_to_openrouter).
ALLOWED = {ROOT / "visibility" / "openrouter.py": {"post"}}


@pytest.mark.parametrize("path", sorted(ROOT.rglob("*.py")), ids=lambda p: str(p.name))
def test_no_code_types_submits_or_sends_non_get(path: pathlib.Path) -> None:
    bad = _called_attrs(path) & FORBIDDEN_CALLS - ALLOWED.get(path, set())
    assert not bad, f"{path}: forbidden calls {bad}"


def test_openrouter_client_is_pinned_to_openrouter() -> None:
    from scanner.visibility import openrouter

    assert openrouter.BASE_URL == "https://openrouter.ai/api/v1"
    assert openrouter.ALLOWED_HOST == "openrouter.ai"
    src = (ROOT / "visibility" / "openrouter.py").read_text(encoding="utf-8")
    assert src.count(".post(") == 1 and '.post("/chat/completions"' in src


async def test_openrouter_client_refuses_other_hosts() -> None:
    from scanner.visibility.openrouter import OpenRouterClient, OpenRouterError

    client = OpenRouterClient("test-key")
    with pytest.raises(OpenRouterError):
        client._check_host("https://shop.example.nl/cart/add")
    await client.__aexit__()


def test_visibility_package_never_touches_shops() -> None:
    """V1 talks to OpenRouter only: no crawler client, no browser, no shop fetches."""
    for path in (ROOT / "visibility").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        for forbidden in ("PoliteClient", "playwright", "scanner.fetch", "scanner.checkout"):
            assert forbidden not in src, f"{path} uses {forbidden}"


def test_no_api_keys_in_git_tracked_files() -> None:
    """Keys belong in .env (gitignored) only. Caught a real near-miss on 2026-11-09, when an
    OpenRouter key was pasted into .env.example."""
    import re
    import subprocess

    repo = ROOT.parent
    files = subprocess.run(
        ["git", "ls-files"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.split()
    key = re.compile(
        r"(sk-or-v1-[0-9a-f]{20,}|sk-(proj-)?[A-Za-z0-9_-]{32,}|AIza[0-9A-Za-z_-]{30,}"
        r"|ghp_[A-Za-z0-9]{30,})"
    )
    for name in files:
        path = repo / name
        if path.suffix in {".png", ".jpg", ".gz"} or not path.is_file():
            continue
        assert not key.search(path.read_text(encoding="utf-8", errors="ignore")), name
    assert ".env" in (repo / ".gitignore").read_text(encoding="utf-8").split()


def test_http_client_only_uses_get() -> None:
    src = (ROOT / "fetch" / "client.py").read_text(encoding="utf-8")
    assert 'stream("GET"' in src
    for verb in ("POST", "PUT", "PATCH", "DELETE"):
        assert f'"{verb}"' not in src


def test_no_credentials_or_payment_data_in_code() -> None:
    import re

    secret = re.compile(
        r"(sk_live|sk_test|api[_-]?key\s*=\s*['\"]\w|\b4[0-9]{15}\b|\bIBAN\b\s*[:=]|"
        r"password\s*=\s*['\"]\w)",
        re.I,
    )
    for path in ROOT.rglob("*.py"):
        assert not secret.search(path.read_text(encoding="utf-8")), path


@pytest.mark.parametrize(
    "label",
    [
        "Bestellen en betalen",
        "Plaats bestelling",
        "Betaal nu",
        "Bestelling afronden",
        "Place order",
        "Koop nu",
        "PayPal",
        "Bevestigen",
        "Inloggen",
        "Account aanmaken",
    ],
)
def test_forbidden_labels(label: str) -> None:
    assert FORBIDDEN_CLICK.search(label)


# --- 2. guard table --------------------------------------------------------------------


def _probe(allow_post: bool = False) -> Any:
    p = probe_mod._Probe(PoliteClient(), ORIGIN, "woocommerce", False, None)
    p.allow_post = allow_post
    return p


@pytest.mark.parametrize(
    ("method", "url", "allow_post", "blocked"),
    [
        ("GET", f"{ORIGIN}/product/x/", False, False),
        ("POST", f"{ORIGIN}/cart/add", True, False),  # the one allowed write: add to cart
        ("POST", f"{ORIGIN}/cart/add", False, True),  # ... but only during that click
        ("POST", "https://evil.example.com/cart/add", True, True),  # other host
        ("GET", "https://www.mollie.com/checkout/select-method/abc", False, True),
        ("GET", "https://ideal.ing.nl/x", False, True),
        ("GET", "https://checkout.stripe.com/pay/cs_1", False, True),
        ("GET", "https://www.paypal.com/checkoutnow?token=1", False, True),
        ("GET", f"{ORIGIN}/checkout/onepage/success/", False, True),
        ("POST", f"{ORIGIN}/checkout/place-order", True, True),  # order path, even in window
        ("GET", f"{ORIGIN}/checkouts/abc/processing", False, True),
        ("GET", f"{ORIGIN}/betaling/start", False, True),
        # wallets and card fields (missed until 2026-11-12)
        ("GET", "https://pay.google.com/gp/p/js/pay.js", False, True),
        ("GET", "https://payments.amazon.nl/x", False, True),
        ("GET", "https://static-eu.payments-amazon.com/checkout.js", False, True),
        ("GET", "https://apple-pay-gateway.apple.com/x", False, True),
        ("GET", "https://checkout.shopifycs.com/number", False, True),
        # order endpoints that live in the query string or were not listed
        ("POST", f"{ORIGIN}/?wc-ajax=checkout", True, True),
        ("GET", f"{ORIGIN}/checkout/order-received/123/", False, True),
        ("POST", f"{ORIGIN}/checkout/onepage/saveOrder", True, True),
        # ... without blocking normal shop traffic
        ("POST", f"{ORIGIN}/?wc-ajax=add_to_cart", True, False),
        ("GET", f"{ORIGIN}/?wc-ajax=get_refreshed_fragments", False, False),
        ("GET", "https://www.google.com/recaptcha/api.js", False, False),
        # a shop page must not make our browser talk to the machine or network we run on
        ("GET", "http://localhost:9222/json", False, True),
        ("GET", "http://192.168.1.1/", False, True),
    ],
)
def test_guard_table(method: str, url: str, allow_post: bool, blocked: bool) -> None:
    assert (_probe(allow_post).guard(method, url) is not None) is blocked


# --- 3. hostile fake shops in a real browser ---------------------------------------------

PRODUCT = """<!doctype html><html><head><meta charset="utf-8">
<script type="application/ld+json">{"@type":"Product","name":"X","offers":{"@type":"Offer",
"price":"5.00","priceCurrency":"EUR","availability":"https://schema.org/InStock"}}</script>
</head><body><h1>X</h1>
<script>fetch('/api/track',{method:'POST'})</script>
<button onclick="fetch('/cart/add',{method:'POST'}).then(()=>location.href='/cart')"
>In winkelwagen</button></body></html>"""

CART_HOSTILE = """<html><body><p>X x1</p>
<form method="post" action="/checkout/place-order"><button>Afrekenen</button></form>
<script>setTimeout(()=>location.href='https://www.mollie.com/checkout/abc',200)</script>
</body></html>"""

ONE_PAGE = """<html><body><p>X x1</p><h2>Gegevens</h2>
<input type="email" required name="email"><input required name="postcode">
<label><input type="radio" name="payment_method" value="ideal"> iDEAL</label>
<button onclick="fetch('/order',{method:'POST'})">Bestellen</button></body></html>"""


class HostileShop:
    def __init__(self, cart_html: str, product_html: str = PRODUCT) -> None:
        self.cart_html = cart_html
        self.product_html = product_html
        self.added = False
        self.seen: list[tuple[str, str]] = []

    async def hook(self, route: Any) -> None:
        req = route.request
        self.seen.append((req.method, req.url))
        path = req.url.replace(ORIGIN, "") or "/"
        if not req.url.startswith(ORIGIN):
            await route.abort()
        elif path.startswith("/product/x"):
            await route.fulfill(status=200, body=self.product_html, content_type="text/html")
        elif path == "/sw.js":
            await route.fulfill(status=200, body="", content_type="application/javascript")
        elif path == "/cart/add":
            self.added = True
            await route.fulfill(status=200, body="{}", content_type="application/json")
        elif path == "/cart":
            await route.fulfill(status=200, body=self.cart_html, content_type="text/html")
        else:
            await route.fulfill(status=200, body="<html>ok</html>", content_type="text/html")


@pytest.fixture(autouse=True)
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probe_mod, "SETTLE_MS", 600)
    monkeypatch.setattr(probe_mod, "ADD_WAIT_MS", 400)
    monkeypatch.setattr(probe_mod, "BANNER_WAIT_MS", 50)


async def _run(shop: HostileShop) -> Any:
    pages = PageSample(products=[FetchedResource(url=PRODUCT_URL, status_code=200, body=PRODUCT)])
    async with PoliteClient(min_interval_s=0) as client:
        p = await probe_mod.run_probe(client, ORIGIN, "woocommerce", pages, route_hook=shop.hook)
    if p.skipped_reason and "Chromium not available" in p.skipped_reason:
        pytest.skip("Chromium not installed")
    return p


async def test_hostile_cart_cannot_place_order_or_reach_payment_provider() -> None:
    shop = HostileShop(CART_HOSTILE)
    p = await _run(shop)
    urls = [u for _, u in shop.seen]
    assert not any("place-order" in u for u in urls)  # order form never submitted
    assert not any("mollie" in u for u in urls)  # payment provider never contacted
    posts = [u for m, u in shop.seen if m == "POST"]
    assert posts == [f"{ORIGIN}/cart/add"]  # background POST /api/track was blocked too
    guard = next(s for s in p.steps if s.name == "safety_guard")
    assert "order/payment path" in guard.detail or "payment provider" in guard.detail


async def test_one_page_checkout_bestellen_button_is_never_clicked() -> None:
    shop = HostileShop(ONE_PAGE)
    p = await _run(shop)
    assert ("POST", f"{ORIGIN}/order") not in shop.seen
    assert any("already is the checkout; not clicking" in s.detail for s in p.steps)
    assert p.checkout_reached and "iDEAL" in p.payment_methods


async def test_service_workers_and_websockets_cannot_bypass_the_guard() -> None:
    # Playwright routing does not see requests handled by a service worker, and WebSockets
    # are a write channel of their own: both are refused outright.
    sneaky = PRODUCT.replace(
        "<script>",
        "<script>navigator.serviceWorker.register('/sw.js').then("
        "()=>0,()=>0);"
        "new WebSocket('wss://shop.example.nl/ws');",
        1,
    )
    shop = HostileShop(CART_HOSTILE, product_html=sneaky)
    p = await _run(shop)
    urls = [u for _, u in shop.seen]
    assert f"{ORIGIN}/sw.js" not in urls  # the worker script is never even fetched
    guard = next(s for s in p.steps if s.name == "safety_guard")
    assert "websocket" in guard.detail


async def test_checkout_probe_is_opt_in() -> None:
    from scanner.graph import run_scan
    from scanner.models import ScanOptions
    from tests.conftest import FakeShop

    report = await run_scan(
        "example.nl",
        ScanOptions(checks=["C1", "C2"]),
        transport=FakeShop().transport,
        min_interval_s=0,
    )
    for r in report.results:
        assert r.status == "not_applicable"
        assert "checkout probe not enabled" in r.evidence[0].detail
    assert ScanOptions().checkout is False and ScanOptions().checkout_consent is False

"""Checkout probe: open a product page, add the cheapest in-stock product to the cart,
open checkout, and STOP (SPEC §4 C, CLAUDE.md rule 1).

Never types into any field, never clicks pay / order / express-payment buttons, never
logs in or creates an account. Decisions (Tarek, 2026-11-08):
- robots.txt is respected for every navigation, and for the likely checkout destinations
  before clicking "checkout"; `checkout_consent` (merchant asked for the scan) lifts this;
- images/fonts/media/known trackers are blocked; >= 1 s between navigations through the
  shared per-host limiter; each navigation counts against the page budget;
- cookie banners: reject first, otherwise accept (counted as one interstitial).
Playwright API: https://playwright.dev/python/docs/api/class-page
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

from scanner.checkout.markers import (
    ACCEPT_COOKIES,
    ACCEPT_SELECTORS,
    ADD_TO_CART,
    CART_EMPTY,
    CHECKOUT,
    CLOSE_POPUP,
    FORBIDDEN_CLICK,
    GUEST,
    LOGIN,
    NOT_ADD_TO_CART,
    ORDER_PATHS,
    PAYMENT_HOSTS,
    REJECT_COOKIES,
    REJECT_SELECTORS,
    VISIBLE_CAPTCHA,
    captcha_in,
    payment_haystack,
    payment_methods_in,
)
from scanner.fetch.challenge import classify
from scanner.fetch.client import PoliteClient, private_host
from scanner.models import (
    CheckoutProbe,
    FetchedResource,
    PageSample,
    Platform,
    ProbeStep,
    RenderedPage,
)
from scanner.parse.product import offer_price, offers_of, product_data

BLOCKED_TYPES = frozenset({"image", "media", "font"})
TRACKERS = re.compile(
    r"google-analytics|googletagmanager|doubleclick|facebook\.(net|com)|connect\.facebook|"
    r"hotjar|clarity\.ms|bing\.com/bat|tiktok|snap\.licdn|criteo|pinterest",
    re.I,
)
# Platform default checkout paths, checked against robots.txt before clicking "checkout".
CHECKOUT_PATHS: dict[Platform, tuple[str, ...]] = {
    "shopify": ("/checkout", "/checkouts/"),
    "woocommerce": ("/checkout/", "/afrekenen/"),
    "shopware6": ("/checkout/confirm", "/checkout/register"),
    "magento": ("/checkout/",),
    "lightspeed": ("/checkout/",),
    "other": (),
}
CART_PATHS = ("/cart", "/winkelwagen", "/winkelmand", "/winkelmandje", "/checkout/cart")
MAX_NAVIGATIONS = 5
NAV_TIMEOUT_MS = 20_000
SETTLE_MS = 1_500
ADD_WAIT_MS = 2_500  # let the shop's add-to-cart request and mini-cart finish
BANNER_WAIT_MS = 800
PROBE_RESERVE_S = 0.0  # last network step of the scan: may use the remaining time

RouteHook = Callable[[Any], Awaitable[None]]  # tests serve a fake shop through this


# Payment choices or required address fields; or a visible required e-mail field that is
# not a newsletter sign-up (most shops have one in the footer of every page: it made the
# cart look like the checkout, found 2026-11-12).
_CHECKOUT_FORM_JS = """() => {
  const strong = "input[name*=payment i], input[name*=betaal i], [data-payment-method], " +
    "input[required][name*=street i], input[required][name*=postcode i], " +
    "input[required][autocomplete*=address i]";
  if (document.querySelector(strong)) return true;
  const aside = "footer, [class*=newsletter i], [id*=newsletter i], [class*=nieuwsbrief i], " +
    "[id*=nieuwsbrief i], [class*=subscribe i], form[action*=newsletter i], " +
    "form[action*=subscribe i], form[action*=nieuwsbrief i]";
  return [...document.querySelectorAll("input[required][type=email]")].some(
    e => e.getClientRects().length > 0 && !e.closest(aside));
}"""
# Signs that a checkout step is open: guest/login choice or visible e-mail/password fields.
_CHECKOUT_SIGNS_JS = """() => [...document.querySelectorAll(
  "input[type=email], input[type=password], input[name*=email i]")]
  .filter(e => e.getClientRects().length > 0).length"""
SHOPIFY_CHECKOUT = "/checkout"  # plain GET: Shopify redirects to the checkout of this cart


async def looks_like_checkout(page: Any) -> bool:
    """Payment-method choices or required address/e-mail fields = a checkout form."""
    try:
        return bool(await page.evaluate(_CHECKOUT_FORM_JS))
    except Exception:
        return True  # unsure -> treat as checkout -> do not click


def pick_product(pages: PageSample) -> FetchedResource | None:
    """Cheapest in-stock product; simple products (no variants) preferred."""
    scored: list[tuple[int, float, FetchedResource]] = []
    for page in pages.products:
        d = product_data(page.body or "")
        offers = offers_of(d.product) if d.source else []
        in_stock = [o for o in offers if "instock" in str(o.get("availability", "")).lower()]
        prices = [p for p in (offer_price(o) for o in in_stock) if p is not None and p > 0]
        if not prices:
            continue
        has_variants = bool(d.product.get("hasVariant"))
        scored.append((1 if has_variants else 0, float(min(prices)), page))
    if scored:
        return sorted(scored, key=lambda t: (t[0], t[1]))[0][2]
    return pages.products[0] if pages.products else None


class _Probe:
    def __init__(
        self,
        client: PoliteClient,
        origin: str,
        platform: Platform,
        consent: bool,
        artifacts: Path | None,
    ) -> None:
        self.client = client
        self.origin = origin
        self.host = urlsplit(origin).hostname or ""
        self.platform = platform
        self.consent = consent
        self.artifacts = artifacts
        self.out = CheckoutProbe(ran=True)
        # Safety: non-GET requests are only allowed while the add-to-cart click settles.
        self.allow_post = False
        self.blocked_requests: list[str] = []
        self.navigations = 0

    # --- helpers -------------------------------------------------------------------------

    def step(
        self,
        name: str,
        outcome: Literal["ok", "blocked", "skipped", "failed"],
        detail: str,
        url: str | None = None,
        shot: str | None = None,
    ) -> None:
        self.out.steps.append(
            ProbeStep(
                name=name,
                url=url,
                outcome=outcome,
                detail=detail,
                screenshot=shot,
            )
        )

    def allowed(self, url: str) -> bool:
        return self.consent or self.client.robots_allows(url)

    async def shot(self, page: Any, name: str) -> str | None:
        if self.artifacts is None:
            return None
        self.artifacts.mkdir(parents=True, exist_ok=True)
        file = f"checkout_{len(self.out.steps):02d}_{name}.png"
        try:
            await page.screenshot(path=str(self.artifacts / file), full_page=False)
        except Exception:  # screenshots are evidence, never a reason to fail the probe
            return None
        return file

    async def goto(self, page: Any, url: str, name: str) -> Any | None:
        if not self.allowed(url):
            self.out.skipped_kind = "robots"
            self.out.skipped_reason = f"robots.txt disallows {urlsplit(url).path} for our scanner"
            self.step(name, "skipped", self.out.skipped_reason, url)
            return None
        if self.navigations >= MAX_NAVIGATIONS or not self.client.take_navigation():
            self.step(name, "failed", "page budget reached", url)
            return None
        if not await self.client.pace(self.host, reserve_s=PROBE_RESERVE_S):
            self.step(name, "failed", "scan time budget reached", url)
            return None
        self.navigations += 1
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        except Exception as exc:
            self.step(name, "failed", f"{type(exc).__name__}: {str(exc)[:120]}", url)
            return None
        if resp is not None:
            self.client.note_status(self.host, resp.status, resp.headers.get("retry-after"))
        await page.wait_for_timeout(SETTLE_MS)
        return resp

    async def challenge_on(self, page: Any, resp: Any, *, visible_only: bool = True) -> str | None:
        """Bot challenge page, or a captcha. Before checkout (`visible_only`) only a captcha
        the visitor must solve counts; on checkout entry any captcha marker counts (C4)."""
        html = await page.content()
        res = FetchedResource(
            url=page.url,
            status_code=resp.status if resp is not None else 200,
            headers=dict(resp.headers) if resp is not None else {},
            body=html,
        )
        v = classify(res)
        if v.outcome == "blocked":
            return v.reason
        if visible_only:
            seen = [name for name, sel in VISIBLE_CAPTCHA if await page.locator(sel).count() > 0]
            return f"visible captcha on page ({', '.join(seen)})" if seen else None
        markers = captcha_in(html)
        return f"captcha on page ({', '.join(markers)})" if markers else None

    async def click_first(
        self, page: Any, selectors: tuple[str, ...], text: re.Pattern[str] | None
    ) -> str | None:
        for sel in selectors:
            loc = page.locator(sel)
            if await loc.count() and await loc.first.is_visible():
                await loc.first.click(timeout=3_000)
                return sel
        if text is None:
            return None
        buttons = page.locator("button, [role=button], a[role=button], input[type=button]")
        n = min(await buttons.count(), 60)
        for i in range(n):
            b = buttons.nth(i)
            try:
                label = (await b.inner_text(timeout=500)).strip() or (
                    await b.get_attribute("value") or ""
                )
            except Exception:
                continue
            if label and len(label) < 60 and text.search(label) and await b.is_visible():
                await b.click(timeout=3_000)
                return label
        return None

    def guard(self, method: str, url: str) -> str | None:
        """Hard safety net (CLAUDE.md rule 1): reasons to abort a request, or None.

        - never any request to a payment provider / bank host, or to a private address;
        - never any request to an order/payment/confirmation path or query;
        - non-GET only during the add-to-cart click, and only to the shop's own host.
        """
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if PAYMENT_HOSTS.search(host):
            return "payment provider"
        if private_host(host):
            return "private or local address"
        if ORDER_PATHS.search(parts.path + (f"?{parts.query}" if parts.query else "")):
            return "order/payment path"
        if method.upper() not in ("GET", "HEAD", "OPTIONS"):
            same_shop = host == self.host or host.endswith("." + self.host)
            if not (self.allow_post and same_shop):
                return "non-GET outside add-to-cart"
        return None

    # --- steps ---------------------------------------------------------------------------

    async def cookie_banner(self, page: Any) -> None:
        try:
            how = await self.click_first(page, REJECT_SELECTORS, REJECT_COOKIES)
            kind = "rejected"
            if how is None:
                how = await self.click_first(page, ACCEPT_SELECTORS, ACCEPT_COOKIES)
                kind = "accepted (no reject option found)"
        except Exception as exc:
            self.step("cookie_banner", "failed", f"{type(exc).__name__}", page.url)
            return
        if how:
            self.out.interstitials.append("cookie banner")
            await page.wait_for_timeout(BANNER_WAIT_MS)
            self.step("cookie_banner", "ok", f"cookie banner {kind} via '{how}'", page.url)

    async def popups(self, page: Any) -> None:
        try:
            dialogs = page.locator("[role=dialog]:visible, .modal.show, .modal.is-open")
            if not await dialogs.count():
                return
            closers = dialogs.first.locator("button, [role=button], a")
            for i in range(min(await closers.count(), 20)):
                c = closers.nth(i)
                label = (
                    (await c.get_attribute("aria-label", timeout=500))
                    or (await c.inner_text(timeout=500))
                    or ""
                ).strip()
                if CLOSE_POPUP.search(label):
                    await c.click(timeout=2_000)
                    self.out.interstitials.append("popup")
                    self.step("popup", "ok", f"closed a popup via '{label}'", page.url)
                    return
        except Exception as exc:  # a popup we cannot close must not end the probe
            self.step(
                "popup", "failed", f"could not close a popup ({type(exc).__name__})", page.url
            )

    async def add_to_cart(self, page: Any) -> bool:
        # Variant selects (e.g. WooCommerce variable products): pick the first real option.
        # Only inside the form that holds the add-to-cart button: language, currency and
        # sort selects elsewhere on the page are left alone.
        cart_forms = page.locator("form").filter(has_text=ADD_TO_CART)
        for sel in await cart_forms.locator("select:visible").all():
            try:
                options = await sel.locator("option").all()
                values = [await o.get_attribute("value") for o in options]
                first = next((v for v in values if v), None)
                if first:
                    await sel.select_option(first)
            except Exception:
                continue
        # Two passes: a locator returns matches in page order, so the platforms' own
        # add-to-cart buttons are tried before any other button with a matching label.
        specific = page.locator(
            "form[action*='cart'] button[type=submit], button[name='add'], "
            "button[name='add-to-cart'], button.single_add_to_cart_button"
        )
        generic = page.locator("button, input[type=submit]")
        candidates = [specific.nth(i) for i in range(min(await specific.count(), 20))]
        candidates += [generic.nth(i) for i in range(min(await generic.count(), 80))]
        for b in candidates:
            try:
                label = (await b.inner_text(timeout=500)).strip() or (
                    await b.get_attribute("value") or ""
                )
                if not label or FORBIDDEN_CLICK.search(label) or not ADD_TO_CART.search(label):
                    continue
                if NOT_ADD_TO_CART.search(label):
                    continue
                if not await b.is_visible() or await b.is_disabled():
                    continue
                self.allow_post = True
                await b.click(timeout=5_000)
            except Exception:
                self.allow_post = False
                continue
            await page.wait_for_timeout(ADD_WAIT_MS)
            self.allow_post = False
            self.step(
                "add_to_cart",
                "ok",
                f"clicked '{label[:50]}'",
                page.url,
                await self.shot(page, "added"),
            )
            return True
        self.step("add_to_cart", "failed", "no add-to-cart button found", page.url)
        return False

    async def open_cart(self, page: Any) -> bool:
        # Unless the shop already navigated to its cart, open it.
        if not re.search(r"cart|winkel(wagen|mand)", urlsplit(page.url).path, re.I):
            hrefs = await page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.getAttribute('href'))"
            )
            cart_href = next(
                (
                    h
                    for h in hrefs
                    if h and re.search(r"/(cart|winkel(wagen|mand|mandje))\b", h, re.I)
                ),
                None,
            )
            url = urljoin(page.url, cart_href or CART_PATHS[0])
            resp = await self.goto(page, url, "cart")
            if resp is None:
                return False
            if resp.status >= 400:  # an error page has no "cart is empty" text either
                self.step("cart", "failed", f"cart page returned HTTP {resp.status}", page.url)
                return False
        html = await page.content()
        if CART_EMPTY.search(html):
            self.out.added_to_cart = False
            self.step(
                "cart",
                "failed",
                "cart is empty after add-to-cart",
                page.url,
                await self.shot(page, "cart_empty"),
            )
            return False
        self.step("cart", "ok", "cart has an item", page.url, await self.shot(page, "cart"))
        return True

    async def open_checkout(self, page: Any) -> Any | None:
        # Where can "checkout" lead? Check robots before clicking (no redirect into a
        # disallowed checkout).
        hrefs = await page.eval_on_selector_all(
            "a[href], form[action]",
            "els => els.map(e => e.getAttribute('href') || e.getAttribute('action'))",
        )
        dests = [
            urljoin(page.url, h)
            for h in hrefs
            if h and re.search(r"check ?out|afrekenen|kassa", h, re.I)
        ]
        dests += [urljoin(self.origin, p) for p in CHECKOUT_PATHS.get(self.platform, ())]
        blocked = next((d for d in dests if not self.allowed(d)), None)
        if blocked:
            self.out.skipped_kind = "robots"
            self.out.skipped_reason = (
                f"robots.txt disallows the checkout ({urlsplit(blocked).path}) for our scanner"
            )
            self.step("checkout", "skipped", self.out.skipped_reason, blocked)
            return None
        if self.navigations >= MAX_NAVIGATIONS or not self.client.take_navigation():
            self.step("checkout", "failed", "page budget reached", page.url)
            return None
        if not await self.client.pace(self.host, reserve_s=PROBE_RESERVE_S):
            self.step("checkout", "failed", "scan time budget reached", page.url)
            return None
        self.navigations += 1
        if await looks_like_checkout(page):
            # One-page cart+checkout: a "bestellen" button here could place an order.
            self.step("checkout", "ok", "cart page already is the checkout; not clicking", page.url)
            return "current page"
        before = await self._checkout_state(page)
        clicked = await self._click_checkout(page)
        if not clicked:
            self.step("checkout", "failed", "no checkout button found on the cart", page.url)
            return None
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
        await page.wait_for_timeout(SETTLE_MS)
        if not await self._arrived(page, before):
            # The click led nowhere, e.g. a cart form that POSTs (refused by the guard).
            # Shopify also opens the checkout of the current cart on a plain GET.
            where = urljoin(self.origin, SHOPIFY_CHECKOUT)
            resp = await self.goto(page, where, "checkout") if self.platform == "shopify" else None
            if resp is None or resp.status >= 400 or page.url.startswith("chrome-error:"):
                self.step(
                    "checkout",
                    "failed",
                    f"clicked '{clicked[:50]}' but no checkout page or step opened",
                    None if page.url.startswith("chrome-error:") else page.url,
                )
                return None
        if not self.allowed(page.url):  # redirect leak: do not read or keep the page
            self.out.skipped_kind = "robots"
            self.out.skipped_reason = (
                f"checkout redirected to {urlsplit(page.url).path}, disallowed by robots.txt"
            )
            self.step("checkout", "skipped", self.out.skipped_reason, page.url)
            return None
        return clicked

    async def _checkout_state(self, page: Any) -> tuple[str, bool, int]:
        """(URL, guest option visible, visible e-mail/password fields) of the current page."""
        try:
            text = await page.inner_text("body", timeout=2_000)
            fields = int(await page.evaluate(_CHECKOUT_SIGNS_JS))
        except Exception:
            text, fields = "", 0
        return page.url, bool(GUEST.search(text)), fields

    async def _arrived(self, page: Any, before: tuple[str, bool, int]) -> bool:
        """Did the checkout click open something? Another page, a checkout form, or a
        guest/login step on the same URL (HEMA opens a drawer). A click that changes
        nothing is not "checkout reached"."""
        if page.url.startswith("chrome-error:"):
            return False
        url, guest, fields = await self._checkout_state(page)
        if url.split("#")[0] != before[0].split("#")[0]:
            return True
        return (guest and not before[1]) or fields > before[2] or await looks_like_checkout(page)

    async def _click_checkout(self, page: Any) -> str | None:
        items = page.locator("a, button, input[type=submit]")
        for i in range(min(await items.count(), 120)):
            el = items.nth(i)
            try:
                label = (await el.inner_text(timeout=500)).strip() or (
                    await el.get_attribute("value") or ""
                )
                if not label or len(label) > 50 or FORBIDDEN_CLICK.search(label):
                    continue
                if not CHECKOUT.search(label) or not await el.is_visible():
                    continue
                await el.click(timeout=5_000)
                return label
            except Exception:
                continue
        return None

    async def inspect_checkout(self, page: Any) -> None:
        html = await page.content()
        self.out.checkout_reached = True
        self.out.checkout_url = page.url
        self.out.captcha_markers = captcha_in(html)
        text = re.sub(r"\s+", " ", await page.inner_text("body"))
        has_password = await page.locator("input[type=password]:visible").count() > 0
        has_email = (
            await page.locator("input[type=email]:visible, input[name*=email i]:visible").count()
            > 0
        )
        self.out.guest_option = bool(GUEST.search(text)) or (has_email and not has_password)
        self.out.login_wall = (
            has_password and not self.out.guest_option and bool(LOGIN.search(text))
        )
        for m in payment_methods_in(payment_haystack(html)):
            self.out.payment_methods.setdefault(m, page.url)
        self.step(
            "checkout",
            "ok",
            "checkout page reached; stopped here (nothing entered)",
            page.url,
            await self.shot(page, "checkout"),
        )

    # --- run -----------------------------------------------------------------------------

    async def run(
        self, browser: Any, product: FetchedResource, route_hook: RouteHook | None
    ) -> CheckoutProbe:
        context = await browser.new_context(
            user_agent=self.client.user_agent,
            locale="nl-NL",
            viewport={"width": 1366, "height": 900},
            java_script_enabled=True,
            # Requests handled by a service worker are invisible to the route guard below
            # (https://playwright.dev/python/docs/service-workers): no service workers.
            service_workers="block",
            accept_downloads=False,
        )

        async def refuse_websocket(ws: Any) -> None:
            # A WebSocket is a write channel the request guard cannot inspect.
            self.blocked_requests.append(f"websocket: {ws.url[:120]}")
            await ws.close()

        async def router(route: Any) -> None:
            req = route.request
            why = self.guard(req.method, req.url)
            if why:
                self.blocked_requests.append(f"{why}: {req.method} {req.url[:120]}")
                await route.abort()
            elif req.resource_type in BLOCKED_TYPES or TRACKERS.search(req.url):
                await route.abort()
            elif route_hook is not None:
                await route_hook(route)
            else:
                await route.continue_()

        await context.route("**/*", router)
        await context.route_web_socket("**/*", refuse_websocket)
        page = await context.new_page()
        try:
            self.out.product_url = product.url
            resp = await self.goto(page, product.url, "product")
            if resp is None:
                return self.out
            if (why := await self.challenge_on(page, resp)) is not None:
                self.out.challenge = why
                self.step("product", "blocked", why, page.url, await self.shot(page, "challenge"))
                return self.out
            self.step("product", "ok", f"HTTP {resp.status}", page.url)
            await self.cookie_banner(page)
            await self.popups(page)
            await self.render_check(page)
            if not await self.add_to_cart(page):
                return self.out
            if (why := await self.challenge_on(page, None)) is not None:
                self.out.challenge = why
                self.step("add_to_cart", "blocked", why, page.url)
                return self.out
            if not await self.open_cart(page):
                return self.out
            self.out.added_to_cart = True
            if await self.open_checkout(page) is None:
                return self.out
            if (why := await self.challenge_on(page, None, visible_only=False)) is not None:
                self.out.challenge = why
                self.out.checkout_reached = True
                self.out.checkout_url = page.url
                self.out.captcha_markers = captcha_in(await page.content()) or [why]
                self.step("checkout", "blocked", why, page.url, await self.shot(page, "captcha"))
                return self.out
            await self.inspect_checkout(page)
            return self.out
        finally:
            await context.close()  # discards cookies/session: nothing is kept
            if self.blocked_requests:
                self.step(
                    "safety_guard",
                    "blocked",
                    f"{len(self.blocked_requests)} request(s) blocked: "
                    + "; ".join(self.blocked_requests[:5]),
                )

    async def render_check(self, page: Any) -> None:
        """D4: what a JS-rendering browser sees on this product page."""
        from scanner.checks.d4_rendering import STOCK_TEXT, VISIBLE_PRICE

        try:
            text = await page.inner_text("body")
        except Exception:
            return
        self.out.rendered.append(
            RenderedPage(
                url=page.url,
                price_visible=bool(VISIBLE_PRICE.search(text)),
                stock_visible=bool(STOCK_TEXT.search(text)),
            )
        )


async def run_probe(
    client: PoliteClient,
    origin: str,
    platform: Platform,
    pages: PageSample,
    *,
    consent: bool = False,
    artifacts: Path | None = None,
    route_hook: RouteHook | None = None,
) -> CheckoutProbe:
    product = pick_product(pages)
    if product is None:
        return CheckoutProbe(skipped_reason="no product page sampled", skipped_kind="technical")
    if not consent and not client.robots_allows(product.url):
        return CheckoutProbe(
            skipped_reason="robots.txt disallows the product page",
            skipped_kind="robots",
            product_url=product.url,
        )
    try:
        from playwright.async_api import async_playwright
    except ImportError:  # pragma: no cover - dependency is pinned
        return CheckoutProbe(skipped_reason="playwright not installed", skipped_kind="technical")

    probe = _Probe(client, origin, platform, consent, artifacts)
    try:
        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as exc:
                return CheckoutProbe(
                    skipped_reason=f"Chromium not available ({type(exc).__name__}); run "
                    "`uv run playwright install chromium`",
                    skipped_kind="technical",
                )
            try:
                return await probe.run(browser, product, route_hook)
            finally:
                await browser.close()
    except Exception as exc:  # a broken probe must never abort the scan
        probe.out.steps.append(
            ProbeStep(
                name="probe", outcome="failed", detail=f"{type(exc).__name__}: {str(exc)[:160]}"
            )
        )
        return probe.out

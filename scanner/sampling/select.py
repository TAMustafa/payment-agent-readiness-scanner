"""Choose and fetch the pages checks will read (SPEC.md §3 step 4).

Sample sizes are small on purpose (default 8 products, 2 categories, 4 policies): shops
that rate-limit polite crawlers (e.g. Shopify: 429 + Retry-After 60 after ~10 requests,
observed 2026-11-08) must still yield usable data within the scan time budget.

Order: policies first (4 cheap pages; Shopify rate-limits product pages, not these), then
- sitemap lists products  -> products -> categories
- otherwise (link crawl)  -> categories (their product tiles are the candidates) -> products
On Shopify our UA gets ~1-2 product pages before HTTP 429 + Retry-After 60 (observed
2026-11-08, even at 3 s/request); product markup comes from one theme template, so a
small sample is still representative there.
Products are confirmed by a single JSON-LD Product/ProductGroup, Product microdata, a
platform's product-page body class (no markup at all), or an
unambiguous URL shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from scanner.fetch.client import PoliteClient
from scanner.models import (
    Evidence,
    FetchedResource,
    PageSample,
    Platform,
    PlatformInfo,
    SiteBasics,
    SitemapEntry,
)
from scanner.parse.html import (
    Link,
    is_listing_page,
    is_platform_product_page,
    is_single_product_page,
    links,
    product_tile_urls,
)
from scanner.sampling.urls import (
    SHOPIFY_POLICY_PATHS,
    is_catalogue_link,
    is_category_entry,
    is_product_candidate,
    is_product_entry,
    looks_like_category_url,
    looks_like_product_url,
    policy_kind,
)

DEFAULT_MAX_PRODUCTS = 8
DEFAULT_MAX_CATEGORIES = 2
POLICY_KINDS = ("shipping", "returns", "terms", "privacy", "payment")  # payment: C3
MAX_PROBES_FACTOR = 1.5  # unconfirmed candidates we may fetch per wanted product
# Seconds of fetch time kept free for the policy pages while sampling products.
POLICY_RESERVE_S = 10.0
# Seconds kept free after sampling: D2 user-agent probes (9 requests at >= 1 s), plus the
# headless checkout probe (~4 paced navigations) when it is enabled.
PROBE_RESERVE_S = 15.0
CHECKOUT_RESERVE_S = 30.0


def spread(items: list[str], n: int) -> list[str]:
    """n evenly spaced items (deterministic variety instead of the first n)."""
    if len(items) <= n:
        return list(items)
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def _ok(res: FetchedResource) -> bool:
    return res.status_code is not None and 200 <= res.status_code < 300 and bool(res.body)


# A leading language segment (/nl/, /en-gb/): Shopify Markets and multi-language shops serve
# the same product under several paths. Seen 2026-11-12 on stoov.com: /products/big-hug-s3-
# original and /nl/products/big-hug-s3-original both sampled, wasting 1 of 5 product slots.
LOCALE_PREFIX = re.compile(r"^/[a-z]{2}(?:[-_][a-z]{2})?(?=/)", re.I)


def same_page_key(url: str) -> str:
    """Host + path without a language prefix, trailing slash, query or fragment."""
    parts = urlsplit(url)
    path = LOCALE_PREFIX.sub("", parts.path).rstrip("/").lower() or "/"
    return f"{parts.netloc.lower()}{path}"


def _dedupe(urls: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for u in urls:
        seen.setdefault(same_page_key(u), u)
    return list(seen.values())


@dataclass
class _Run:
    client: PoliteClient
    basics: SiteBasics
    plat: Platform
    max_products: int
    max_categories: int
    home_links: list[Link]
    entries: list[SitemapEntry]
    policy_urls: dict[str, str]
    out: PageSample = field(default_factory=PageSample)
    tile_links: list[str] = field(default_factory=list)  # links on category pages
    # Links inside product tiles on category pages: tried before other category links,
    # which start with menus, filters and sub-categories (fixje.nl 2026-11-12: 8 probes
    # used up on those, the product links came last).
    product_tiles: list[str] = field(default_factory=list)
    policies_done: bool = False
    reserve_s: float = PROBE_RESERVE_S

    def budget(self) -> int:
        return self.client.max_requests - self.client.requests_made

    def reserved(self) -> int:
        """Requests kept back for policy pages that have not been fetched yet."""
        return 0 if self.policies_done else len(self.policy_urls)

    def out_of_time(self) -> bool:
        return self.client.stopped_for_time or self.client.reserve_hit

    async def get(self, url: str, *, extra_reserve_s: float = 0.0) -> FetchedResource:
        return await self.client.get(url, reserve_s=self.reserve_s + extra_reserve_s)

    def note(self, detail: str, url: str | None = None) -> None:
        self.out.notes.append(Evidence(url=url, detail=detail))

    async def categories(self) -> None:
        home_urls = {lk.url for lk in self.home_links}
        candidates = _dedupe(
            spread([e.loc for e in self.entries if is_category_entry(e)], self.max_categories)
            + [lk.url for lk in self.home_links if looks_like_category_url(lk.url)]
            + [
                lk.url
                for lk in self.home_links
                if is_catalogue_link(lk.url) and not looks_like_product_url(lk.url)
            ]
        )
        for url in candidates:
            if len(self.out.categories) >= self.max_categories:
                break
            if self.budget() <= self.reserved() or self.out_of_time():
                break
            res = await self.get(url)
            if not _ok(res):
                continue
            if not looks_like_category_url(url) and is_single_product_page(res.body or ""):
                # e.g. a Magento/Lightspeed nav link that is really a product: keep it as one
                if len(self.out.products) < self.max_products:
                    self.out.products.append(res)
                continue
            self.out.categories.append(res)
            self.product_tiles += [
                u
                for u in product_tile_urls(res.body or "", res.final_url or url)
                if is_catalogue_link(u)
            ]
            self.tile_links += [
                lk.url
                for lk in links(res.body or "", res.final_url or url)
                if lk.url not in home_urls and is_catalogue_link(lk.url)
            ]
        self.note(
            f"Categories: {len(self.out.categories)} fetched from {len(candidates)} candidates"
        )

    async def products(self, *, from_sitemap: list[str]) -> None:
        shaped = [
            u
            for u in [lk.url for lk in self.home_links] + self.tile_links
            if is_product_candidate(u, self.plat)
        ]
        tiles = [u for u in self.product_tiles if not is_product_candidate(u, self.plat)]
        unshaped = [u for u in self.tile_links if not is_product_candidate(u, self.plat)]
        # Generic sitemaps (Shopware, Lightspeed, Magento): plain entries as a last resort,
        # confirmed by markup after fetching.
        generic = spread(
            [
                e.loc
                for e in self.entries
                if not is_product_entry(e) and not is_category_entry(e) and is_catalogue_link(e.loc)
            ],
            self.max_products,
        )
        already = {same_page_key(p.url) for p in self.out.categories + self.out.products}
        candidates = [
            u
            for u in _dedupe(from_sitemap + shaped + tiles + unshaped + generic)
            if same_page_key(u) not in already
        ]

        max_probes = int(self.max_products * MAX_PROBES_FACTOR)
        probes = rejected = unreadable = 0
        for url in candidates:
            if len(self.out.products) >= self.max_products or probes >= max_probes:
                break
            if self.budget() <= self.reserved():
                self.note("Product sampling stopped: request budget reached")
                break
            policy_reserve = 0.0 if self.policies_done else POLICY_RESERVE_S
            if self.out_of_time():
                self.note("Product sampling stopped: scan time budget reached")
                break
            probes += 1
            res = await self.get(url, extra_reserve_s=policy_reserve)
            if res.error and "time" in res.error:
                probes -= 1
                self.note("Product sampling stopped: scan time budget reached")
                break
            body = res.body or ""
            ok = (
                _ok(res)
                and not is_listing_page(body)
                and (
                    is_single_product_page(body)
                    or is_platform_product_page(body)
                    or looks_like_product_url(url)
                )
            )
            if ok:
                self.out.products.append(res)
            else:
                rejected += 1
                unreadable += not _ok(res)
        source = "sitemap" if from_sitemap else "link crawl"
        self.note(
            f"Products: {len(self.out.products)} confirmed out of {probes} fetched "
            f"({rejected} rejected, {unreadable} of them unreadable e.g. HTTP 429); "
            f"main source: {source}"
        )

    async def policies(self) -> None:
        for kind in POLICY_KINDS:
            url = self.policy_urls.get(kind)
            if url is None:
                self.note(f"No {kind} policy link found on home page")
                continue
            res = await self.get(url)
            if _ok(res):
                self.out.policies[kind] = res
            else:
                self.note(
                    f"{kind} policy page not fetched: {res.error or f'HTTP {res.status_code}'}",
                    url=url,
                )
        self.policies_done = True


async def sample(
    client: PoliteClient,
    basics: SiteBasics,
    platform: PlatformInfo,
    *,
    max_products: int = DEFAULT_MAX_PRODUCTS,
    max_categories: int = DEFAULT_MAX_CATEGORIES,
    checkout_probe: bool = False,
) -> PageSample:
    origin = basics.origin
    host = urlsplit(origin).hostname
    home_links: list[Link] = []
    if basics.home and _ok(basics.home):
        home_links = links(basics.home.body or "", basics.home.final_url or basics.home.url)

    # Policy links are located up front (no fetch) so their requests can be reserved.
    policy_urls: dict[str, str] = {}
    for link in home_links:
        kind = policy_kind(link.url, link.text)
        if kind and kind not in policy_urls:
            policy_urls[kind] = link.url
    if platform.platform == "shopify":
        for kind, path in SHOPIFY_POLICY_PATHS.items():
            policy_urls.setdefault(kind, urljoin(origin, path))

    run = _Run(
        client=client,
        basics=basics,
        plat=platform.platform,
        max_products=max_products,
        max_categories=max_categories,
        home_links=home_links,
        entries=[e for e in basics.sitemap.entries if urlsplit(e.loc).hostname == host],
        policy_urls=policy_urls,
        reserve_s=PROBE_RESERVE_S + (CHECKOUT_RESERVE_S if checkout_probe else 0.0),
    )
    # Shopify product sitemaps list the home page first: never a product candidate.
    roots = {origin, origin + "/"}
    run.entries = [e for e in run.entries if e.loc not in roots]
    from_sitemap = spread([e.loc for e in run.entries if is_product_entry(e)], max_products)
    await run.policies()
    if from_sitemap:
        run.note("Order: policies -> products -> categories (sitemap lists products)")
        await run.products(from_sitemap=from_sitemap)
        await run.categories()
    else:
        run.note("Order: policies -> categories -> products (link crawl)")
        await run.categories()
        await run.products(from_sitemap=[])
    return run.out

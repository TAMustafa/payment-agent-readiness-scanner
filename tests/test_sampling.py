"""Page sampling against offline fake shops."""

from __future__ import annotations

from urllib.parse import urlsplit

from scanner.fetch.client import PoliteClient
from scanner.models import (
    FetchedResource,
    PlatformInfo,
    SiteBasics,
    SitemapEntry,
    SitemapInfo,
)
from scanner.parse.html import (
    has_product_jsonld,
    is_platform_product_page,
    is_single_product_page,
    jsonld_nodes,
    links,
)
from scanner.platform.fingerprint import fingerprint
from scanner.sampling.select import _dedupe, same_page_key, sample, spread
from scanner.sampling.sitemap import _child_priority
from scanner.sampling.urls import is_catalogue_link
from tests.conftest import FakeShop, fixture

ORIGIN = "https://shop.example.nl"
PRODUCT = fixture("pages/product_jsonld.html")


def basics(home_html: str, entries: list[SitemapEntry] | None = None) -> SiteBasics:
    home = FetchedResource(
        url=f"{ORIGIN}/", final_url=f"{ORIGIN}/", status_code=200, body=home_html
    )
    return SiteBasics(
        final_url=f"{ORIGIN}/",
        origin=ORIGIN,
        https=True,
        home=home,
        sitemap=SitemapInfo(entries=entries or []),
    )


def paths(pages: list[FetchedResource]) -> list[str]:
    return [urlsplit(p.url).path for p in pages]


def test_jsonld_graph_flattening() -> None:
    types = [n["@type"] for n in jsonld_nodes(PRODUCT)]
    assert types == ["BreadcrumbList", "Product"] and has_product_jsonld(PRODUCT)


def test_links_skip_external_and_fragments() -> None:
    found = links(fixture("home/woocommerce.html"), f"{ORIGIN}/")
    assert all(urlsplit(lk.url).hostname == "shop.example.nl" for lk in found)
    assert any(lk.text == "verzenden & levering" for lk in found)


def test_spread_is_even_and_deterministic() -> None:
    assert spread([str(i) for i in range(10)], 3) == ["0", "3", "6"]


async def test_woocommerce_sitemap_first() -> None:
    entries = [
        SitemapEntry(loc=f"{ORIGIN}/product/p{i}/", source=f"{ORIGIN}/product-sitemap.xml")
        for i in range(30)
    ] + [
        SitemapEntry(
            loc=f"{ORIGIN}/product-category/accus/", source=f"{ORIGIN}/product_cat-sitemap.xml"
        ),
    ]
    routes = {e.loc: (200, PRODUCT) for e in entries[:30]}
    routes[f"{ORIGIN}/product-category/accus/"] = (200, "<html><a href='/product/p1/'>x</a></html>")
    for p in ("verzenden-en-levering", "retourneren", "algemene-voorwaarden", "privacy"):
        routes[f"{ORIGIN}/{p}/"] = (200, f"<html>{p}</html>")
    shop = FakeShop(routes)
    home = fixture("home/woocommerce.html")
    async with PoliteClient(transport=shop.transport, min_interval_s=0) as c:
        pages = await sample(c, basics(home, entries), fingerprint(basics(home).home))

    assert len(pages.products) == 8  # default sample size
    assert paths(pages.products)[:3] == ["/product/p0/", "/product/p3/", "/product/p7/"]  # spread
    assert paths(pages.categories)[0] == "/product-category/accus/"
    assert sorted(pages.policies) == ["privacy", "returns", "shipping", "terms"]
    assert any("main source: sitemap" in n.detail for n in pages.notes)
    # policies first, then products (sitemap lists them), then categories
    order = shop.paths()
    assert order.index("/retourneren/") < order.index("/product/p0/")
    assert order.index("/product-category/accus/") > order.index("/product/p0/")


async def test_home_page_in_product_sitemap_is_skipped() -> None:
    entries = [
        SitemapEntry(loc=f"{ORIGIN}/", source=f"{ORIGIN}/sitemap_products_1.xml"),
        SitemapEntry(loc=f"{ORIGIN}/products/a", source=f"{ORIGIN}/sitemap_products_1.xml"),
    ]
    shop = FakeShop({f"{ORIGIN}/products/a": (200, PRODUCT)})
    async with PoliteClient(transport=shop.transport, min_interval_s=0) as c:
        await sample(c, basics("<html></html>", entries), PlatformInfo(platform="shopify"))
    assert "/" not in shop.paths()


async def test_max_products_is_configurable() -> None:
    entries = [
        SitemapEntry(loc=f"{ORIGIN}/product/p{i}/", source=f"{ORIGIN}/product-sitemap.xml")
        for i in range(30)
    ]
    shop = FakeShop({e.loc: (200, PRODUCT) for e in entries})
    async with PoliteClient(transport=shop.transport, min_interval_s=0) as c:
        pages = await sample(
            c,
            basics("<html></html>", entries),
            PlatformInfo(platform="woocommerce"),
            max_products=3,
        )
    assert len(pages.products) == 3


async def test_magento_link_crawl_confirms_by_jsonld() -> None:
    shop = FakeShop(
        {
            f"{ORIGIN}/accus.html": (200, fixture("pages/magento_category.html")),
            f"{ORIGIN}/laders.html": (200, fixture("pages/magento_category.html")),
            f"{ORIGIN}/accu-500wh.html": (200, PRODUCT),
            f"{ORIGIN}/accu-625wh.html": (200, PRODUCT),
            f"{ORIGIN}/accu-tas.html": (200, "<html>no structured data</html>"),
        }
    )
    home = fixture("pages/magento_home.html")
    platform = fingerprint(basics(home).home)
    assert platform.platform == "magento"
    async with PoliteClient(transport=shop.transport, min_interval_s=0) as c:
        pages = await sample(c, basics(home), platform)

    assert paths(pages.categories) == ["/accus.html", "/laders.html"]
    assert paths(pages.products) == ["/accu-500wh.html", "/accu-625wh.html"]
    assert any("1 rejected" in n.detail and "link crawl" in n.detail for n in pages.notes)
    assert "/klantenservice" not in shop.paths()  # service pages are not catalogue candidates
    assert "shipping" not in pages.policies  # 404 in this fake shop -> noted, not stored
    assert any("shipping policy page not fetched" in n.detail for n in pages.notes)


async def test_shopify_policy_fallback_paths() -> None:
    home = "<html><head><script>Shopify.theme={}</script></head><body></body></html>"
    shop = FakeShop({f"{ORIGIN}/policies/refund-policy": (200, "<html>30 dagen</html>")})
    async with PoliteClient(transport=shop.transport, min_interval_s=0) as c:
        pages = await sample(c, basics(home), PlatformInfo(platform="shopify"))
    assert list(pages.policies) == ["returns"]
    assert "/policies/shipping-policy" in shop.paths()


async def test_budget_reserves_room_for_policies() -> None:
    entries = [
        SitemapEntry(loc=f"{ORIGIN}/product/p{i}/", source=f"{ORIGIN}/product-sitemap.xml")
        for i in range(30)
    ]
    shop = FakeShop({e.loc: (200, PRODUCT) for e in entries})
    home = fixture("home/woocommerce.html")  # 4 policy links
    async with PoliteClient(transport=shop.transport, min_interval_s=0, max_requests=10) as c:
        pages = await sample(c, basics(home, entries), PlatformInfo(platform="woocommerce"))
        assert c.requests_made == 10
    policy_requests = [p for p in shop.paths() if not p.startswith("/product")]
    assert len(policy_requests) == 4
    assert any("budget" in n.detail for n in pages.notes)


MICRO = (
    '<div itemscope itemtype="https://schema.org/Product"><span itemprop="name">Tas</span></div>'
)


def test_single_product_rules() -> None:
    assert is_single_product_page(PRODUCT)  # one Product in @graph
    listing = (
        '<script type="application/ld+json">[{"@type":"Product","name":"a"},'
        '{"@type":"Product","name":"b"}]</script>'
    )
    assert not is_single_product_page(listing)  # Shopify-collection-like listing
    group = (
        '<script type="application/ld+json">{"@type":"ProductGroup","hasVariant":'
        '[{"@type":"Product"},{"@type":"Product"}]}</script>'
    )
    assert is_single_product_page(group)
    assert is_single_product_page(f"<html>{MICRO}</html>")  # Shopware 6 microdata
    assert not is_single_product_page(f"<html>{MICRO * 3}</html>")  # category tiles


def test_locale_copies_deprioritised_and_locale_roots_skipped() -> None:
    urls = [
        "https://s.nl/it/sitemap_products_1.xml",
        "https://s.nl/sitemap_pages_1.xml",
        "https://s.nl/nl/sitemap_products_1.xml",
        "https://s.nl/sitemap_products_1.xml",
    ]
    assert sorted(urls, key=_child_priority)[:2] == [
        "https://s.nl/nl/sitemap_products_1.xml",
        "https://s.nl/sitemap_products_1.xml",
    ]
    assert not is_catalogue_link("https://s.nl/de")
    assert not is_catalogue_link("https://s.nl/en-gb/")
    assert is_catalogue_link("https://s.nl/de/products/x")


def _ld(*nodes: object) -> str:
    import json

    return (
        '<html><script type="application/ld+json">'
        + json.dumps({"@context": "https://schema.org", "@graph": list(nodes)})
        + "</script></html>"
    )


ITEM_LIST = {
    "@type": "ItemList",
    "itemListElement": [
        {"@type": "ListItem", "position": i, "url": f"https://shop.nl/p/{i}"} for i in range(5)
    ],
}


def test_category_with_offerless_product_line_is_not_a_product_page() -> None:
    # fixje.nl /refurbished-iphone/: Product (name, brand, aggregateRating, no offers) + ItemList
    line = {"@type": "Product", "name": "Refurbished iPhone", "aggregateRating": {"ratingValue": 9}}
    assert not is_single_product_page(_ld(line, ITEM_LIST))


def test_product_with_offer_and_related_list_is_still_a_product_page() -> None:
    product = {"@type": "Product", "name": "iPhone 12", "offers": {"price": "229"}}
    assert is_single_product_page(_ld(product, ITEM_LIST))
    assert is_single_product_page(_ld({"@type": "Product", "name": "x"}))  # no list: unchanged


def test_platform_product_page_without_markup() -> None:
    # fixje.nl /iphone-12-tempered-glass: WooCommerce product page, no Product JSON-LD
    woo = '<html><body class="wp-singular single single-product postid-1 woocommerce">x</body>'
    assert is_platform_product_page(woo) and not is_single_product_page(woo)
    archive = '<html><body class="archive tax-product_cat woocommerce">x</body></html>'
    assert not is_platform_product_page(archive)
    assert is_platform_product_page('<body class="catalog-product-view page-layout-1column">')
    assert is_platform_product_page('<body class="is-ctl-product is-act-index">')
    assert not is_platform_product_page("<body>")  # no class
    assert not is_platform_product_page('<body class="single-product-list">')  # whole token


def test_language_variants_of_one_page_are_sampled_once() -> None:
    # stoov.com 2026-11-12: /products/x and /nl/products/x both sampled.
    urls = [
        "https://shop.nl/products/big-hug",
        "https://shop.nl/nl/products/big-hug",
        "https://shop.nl/en-gb/products/big-hug/",
        "https://shop.nl/products/homey",
        "https://shop.nl/nl/products/homey-2",
    ]
    assert _dedupe(urls) == [
        "https://shop.nl/products/big-hug",
        "https://shop.nl/products/homey",
        "https://shop.nl/nl/products/homey-2",
    ]
    assert same_page_key("https://shop.nl/nl/") == "shop.nl/"
    # A non-language first segment is kept.
    assert same_page_key("https://shop.nl/tuin/bank") != same_page_key("https://shop.nl/bank")

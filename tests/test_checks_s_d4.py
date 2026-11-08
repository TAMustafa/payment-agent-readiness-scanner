"""D4 and S1-S6 on fixture pages (checks read ScanContext only, so no network needed)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from scanner.checks import (
    d4_rendering,
    s1_product,
    s2_offer,
    s3_identifiers,
    s4_shipping_returns,
    s5_reviews,
    s6_organization,
)
from scanner.models import (
    CheckResult,
    Evidence,
    FetchedResource,
    PageSample,
    PlatformInfo,
    ScanContext,
    ScanOptions,
    SiteBasics,
)
from scanner.parse.product import price_patterns, to_decimal, valid_gtin
from tests.conftest import fixture

ORIGIN = "https://shop.example.nl"


def page(name: str) -> FetchedResource:
    return FetchedResource(
        url=f"{ORIGIN}/{name}", status_code=200, body=fixture(f"pages/{name}.html")
    )


def ctx(products: list[str], home: str = "<html></html>") -> ScanContext:
    home_res = FetchedResource(url=f"{ORIGIN}/", status_code=200, body=home)
    return ScanContext(
        origin=ORIGIN,
        options=ScanOptions(),
        basics=SiteBasics(final_url=f"{ORIGIN}/", origin=ORIGIN, https=True, home=home_res),
        platform=PlatformInfo(),
        pages=PageSample(
            products=[page(p) for p in products],
            notes=[Evidence(detail="Products: 0 confirmed out of 3 fetched")],
        ),
    )


def details(r: CheckResult) -> str:
    return " | ".join(e.detail for e in r.evidence)


# --- helpers ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "value"),
    [
        ("49.95", "49.95"),
        ("49,95", "49.95"),
        ("1.299,00", "1299.00"),
        ("1,299.00", "1299.00"),
        (1299.0, "1299.0"),
        ("€ 5", "5"),
        ("n/a", None),
    ],
)
def test_to_decimal(raw: object, value: str | None) -> None:
    got = to_decimal(raw)
    assert (str(got) if got is not None else None) == value


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("€ 49,95", True),
        ("49.95 EUR", True),
        ("€49,96", True),
        ("€ 149,95", False),
        ("49,9", False),
    ],
)
def test_visible_price_match(text: str, ok: bool) -> None:
    assert any(p.search(text) for p in price_patterns(Decimal("49.95"))) is ok


# --- checks ----------------------------------------------------------------------------


async def test_no_products_is_error_with_sampling_reason() -> None:
    r = await s1_product.check(ctx([]))
    assert r.status == "error" and "0 confirmed out of 3" in r.evidence[0].detail


async def test_s1_full_microdata_and_broken() -> None:
    assert (await s1_product.check(ctx(["product_full"]))).status == "pass"
    micro = await s1_product.check(ctx(["product_microdata"]))
    # name + image present, description missing -> 2/3 * 0.75
    assert micro.score_fraction == pytest.approx(0.5, abs=1e-3)
    assert "microdata only" in details(micro) and "missing: description" in details(micro)
    bad = await s1_product.check(ctx(["product_bad_jsonld"]))
    assert bad.status == "fail" and "Unparseable JSON-LD" in details(bad)


async def test_s2_offer_scoring() -> None:
    full = await s2_offer.check(ctx(["product_full"]))
    assert full.status == "pass" and "matches visible price" in details(full)
    group = await s2_offer.check(ctx(["product_shopify_group"]))  # variant offer, 1.299,00
    assert group.status == "pass", details(group)
    micro = await s2_offer.check(ctx(["product_microdata"]))  # "€89,99*" visible
    assert micro.status == "pass", details(micro)
    js = await s2_offer.check(ctx(["product_js_only"]))
    assert js.status == "fail" and "No offers" in details(js)


async def test_s3_identifiers_threshold() -> None:
    r = await s3_identifiers.check(
        ctx(["product_full", "product_shopify_group", "product_microdata", "product_js_only"])
    )
    # gtin13 / variant gtin / mpn+brand pass, js-only fails -> 75% < 80% -> warn
    assert r.status == "warn" and r.score_fraction == 0.75
    assert "gtin=8720000000016" in details(r)


async def test_s4_offer_level_and_organization_level() -> None:
    offer = await s4_shipping_returns.check(ctx(["product_full"]))
    assert offer.status == "pass" and "shipping: offer; returns: offer" in details(offer)
    org = await s4_shipping_returns.check(
        ctx(["product_jsonld"], home=fixture("home/org_full.html"))
    )
    assert org.status == "pass" and "shipping: organization" in details(org)
    none = await s4_shipping_returns.check(ctx(["product_jsonld"]))
    assert none.status == "fail"


async def test_s5_reviews_applicability() -> None:
    assert (await s5_reviews.check(ctx(["product_full"]))).status == "pass"
    shown_no_markup = await s5_reviews.check(ctx(["product_js_only"]))  # "12 beoordelingen"
    assert shown_no_markup.status == "fail"
    na = await s5_reviews.check(ctx(["product_jsonld", "product_microdata"]))
    assert na.status == "not_applicable"


async def test_s6_organization() -> None:
    full = await s6_organization.check(ctx([], home=fixture("home/org_full.html")))
    assert full.status == "pass" and full.score_fraction == 1.0
    nested = await s6_organization.check(ctx([], home=fixture("home/org_missing_vat.html")))
    # publisher Organization found; missing contact + KvK/VAT (page shows a KvK number)
    assert nested.status == "warn" and nested.score_fraction == pytest.approx(3 / 5)
    assert "contact" in details(nested) and "KvK/VAT" in details(nested)
    none = await s6_organization.check(ctx([], home="<html><body>hi</body></html>"))
    assert none.status == "fail"


async def test_d4_raw_html() -> None:
    assert (await d4_rendering.check(ctx(["product_full", "product_microdata"]))).status == "pass"
    js = await d4_rendering.check(ctx(["product_js_only"]))
    assert js.status == "fail" and "Not in raw HTML: price, availability" in details(js)


@pytest.mark.parametrize(
    ("gtin", "ok"),
    [
        ("8712345678913", True),
        ("8712345678918", False),
        ("0000000000000", False),
        ("96385074", True),
        ("12345", False),
        ("abc", False),
    ],
)
def test_valid_gtin(gtin: str, ok: bool) -> None:
    assert valid_gtin(gtin) is ok


def _variant_image_page() -> FetchedResource:
    body = (
        '<script type="application/ld+json">{"@type":"ProductGroup","name":"Romper",'
        '"description":"x","hasVariant":[{"@type":"Product","image":"https://h/i.jpg",'
        '"gtin13":"0000000000000","sku":"1"}]}</script>'
    )
    return FetchedResource(url=f"{ORIGIN}/romper", status_code=200, body=body)


async def test_s1_counts_variant_fields_and_s3_rejects_placeholder_gtin() -> None:
    c = ctx([])
    c.pages.products = [_variant_image_page()]
    assert (await s1_product.check(c)).status == "pass"
    s3 = await s3_identifiers.check(c)
    assert s3.status == "fail" and "Invalid GTIN ignored: gtin13=0000000000000" in details(s3)


async def test_s5_zero_reviews_is_not_shown_and_identical_ratings_warn() -> None:
    c = ctx([])
    c.pages.products = [
        FetchedResource(
            url=f"{ORIGIN}/a", status_code=200, body="<body><p>0 beoordelingen</p></body>"
        )
    ]
    assert (await s5_reviews.check(c)).status == "not_applicable"
    shop_rating = await s5_reviews.check(ctx(["product_full", "product_full"]))
    assert shop_rating.status == "warn" and "looks like a shop rating" in details(shop_rating)


def test_shop_rating_tolerates_small_count_drift() -> None:
    from scanner.checks.s5_reviews import looks_like_shop_rating

    assert looks_like_shop_rating([("4.45", 3916.0), ("4.45", 3919.0), ("4.45", 3916.0)])
    assert not looks_like_shop_rating([("4.45", 3916.0), ("4.2", 3916.0)])
    assert not looks_like_shop_rating([("4.5", 12.0), ("4.5", 40.0)])


async def test_s6_errors_when_home_is_a_challenge_page() -> None:
    c = ctx([], home="<html><title>Just a moment...</title></html>")
    assert c.basics.home is not None
    c.basics.home.status_code = 403
    r = await s6_organization.check(c)
    assert r.status == "error" and "HTTP 403" in details(r)

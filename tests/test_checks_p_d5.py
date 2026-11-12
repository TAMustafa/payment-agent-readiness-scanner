"""P1-P3 and D5 on fixtures (checks read ScanContext only)."""

from __future__ import annotations

import json

from scanner.checks import d5_merchant_center, p1_ucp, p2_platform, p3_endpoints
from scanner.checks.copy import get_guidance
from scanner.models import (
    AgentEndpoints,
    CheckResult,
    FetchedResource,
    PageSample,
    Platform,
    PlatformInfo,
    ScanContext,
    ScanOptions,
    SiteBasics,
)
from tests.conftest import fixture

ORIGIN = "https://shop.example.nl"
UCP_URL = f"{ORIGIN}/.well-known/ucp"
GOOD_HEADERS = {"cache-control": "public, max-age=60", "content-type": "application/json"}


def res(
    url: str,
    status: int | None,
    body: str = "",
    headers: dict[str, str] | None = None,
    final_url: str | None = None,
) -> FetchedResource:
    return FetchedResource(
        url=url,
        final_url=final_url or url,
        status_code=status,
        body=body,
        headers=headers or {},
    )


def ctx(
    ucp: FetchedResource | None = None,
    platform: Platform = "other",
    llms: FetchedResource | None = None,
    catalog: FetchedResource | None = None,
    options: ScanOptions | None = None,
) -> ScanContext:
    return ScanContext(
        origin=ORIGIN,
        options=options or ScanOptions(),
        basics=SiteBasics(final_url=f"{ORIGIN}/", origin=ORIGIN, https=True),
        platform=PlatformInfo(platform=platform),
        pages=PageSample(),
        endpoints=AgentEndpoints(
            ucp=ucp or res(UCP_URL, 404),
            ai_catalog=catalog or res(f"{ORIGIN}/.well-known/ai-catalog.json", 404),
            llms_txt=llms or res(f"{ORIGIN}/llms.txt", 404),
        ),
    )


def details(r: CheckResult) -> str:
    return " | ".join(e.detail for e in r.evidence)


SHOPIFY_UCP = fixture("ucp/shopify_profile.json")


# --- P1 --------------------------------------------------------------------------------


async def test_p1_valid_shopify_profile_passes() -> None:
    r = await p1_ucp.check(ctx(res(UCP_URL, 200, SHOPIFY_UCP, GOOD_HEADERS)))
    assert r.status == "pass" and "version 2026-08-25" in details(r)
    assert "checkout: yes" in details(r)


async def test_p1_missing_profile_fails_and_copy_says_not_live_in_nl() -> None:
    r = await p1_ucp.check(ctx())
    assert r.status == "fail" and "HTTP 404" in details(r)
    # never claim agent checkout is live in NL (English is the default report language)
    assert "not live in the Netherlands yet" in r.guidance
    assert "nog niet live" in get_guidance("P1.ucp_profile", "nl")


async def test_p1_spec_errors_and_hosting_issues() -> None:
    broken = json.dumps(
        {
            "ucp": {
                "version": "2026-08-25",
                "services": {
                    "dev.ucp.shopping": [{"transport": "mcp"}, {"transport": "carrier-pigeon"}]
                },
            }
        }
    )
    r = await p1_ucp.check(ctx(res(UCP_URL, 200, broken, GOOD_HEADERS)))
    assert r.status == "fail" and r.score_fraction == 0.5
    d = details(r)
    assert "`ucp.payment_handlers` missing" in d
    assert "mcp transport without endpoint" in d and "invalid transport 'carrier-pigeon'" in d

    redirected = res(
        UCP_URL, 200, SHOPIFY_UCP, {"cache-control": "max-age=10"}, final_url=f"{ORIGIN}/ucp.json"
    )
    r2 = await p1_ucp.check(ctx(redirected))
    assert r2.status == "warn" and "MUST NOT redirect" in details(r2)
    assert "Cache-Control should be public" in details(r2)


async def test_p1_profile_that_cannot_take_orders_is_a_warning() -> None:
    base = json.loads(SHOPIFY_UCP)
    no_pay = json.loads(SHOPIFY_UCP)
    no_pay["ucp"]["payment_handlers"] = {}
    r = await p1_ucp.check(ctx(res(UCP_URL, 200, json.dumps(no_pay), GOOD_HEADERS)))
    assert r.status == "warn" and r.score_fraction == 0.7
    assert "Orders: no payment handler declared" in details(r)
    no_checkout = json.loads(SHOPIFY_UCP)
    del no_checkout["ucp"]["capabilities"]["dev.ucp.shopping.checkout"]
    r2 = await p1_ucp.check(ctx(res(UCP_URL, 200, json.dumps(no_checkout), GOOD_HEADERS)))
    assert r2.status == "warn" and "no checkout capability" in details(r2)
    # Order gaps and hosting issues add up.
    r3 = await p1_ucp.check(ctx(res(UCP_URL, 200, json.dumps(no_pay), {})))
    assert r3.status == "warn" and r3.score_fraction == 0.5
    assert base["ucp"]["payment_handlers"]  # the fixture itself passes (see above)


async def test_p1_html_or_blocked() -> None:
    html = res(UCP_URL, 200, "<!doctype html><html>shop</html>")
    soft = await p1_ucp.check(ctx(html))
    assert soft.status == "fail" and "soft 404" in details(soft)
    blocked = res(UCP_URL, 403, "")
    assert (await p1_ucp.check(ctx(blocked))).status == "error"


# --- P2 --------------------------------------------------------------------------------


async def test_p2_levels() -> None:
    live = await p2_platform.check(ctx(res(UCP_URL, 200, SHOPIFY_UCP, GOOD_HEADERS), "shopify"))
    assert live.status == "pass"
    shopify_off = await p2_platform.check(ctx(platform="shopify"))
    assert shopify_off.status == "warn" and "not enabled" in details(shopify_off)
    assert "verified 2026-11-08" in (shopify_off.evidence[1].snippet or "")
    woo = await p2_platform.check(ctx(platform="woocommerce"))
    assert woo.status == "warn" and "staging" in details(woo)
    assert (await p2_platform.check(ctx(platform="lightspeed"))).status == "not_applicable"
    assert (await p2_platform.check(ctx(platform="other"))).status == "not_applicable"


# --- P3 --------------------------------------------------------------------------------


async def test_p3_mcp_from_ucp_catalog_llms() -> None:
    via_ucp = await p3_endpoints.check(ctx(res(UCP_URL, 200, SHOPIFY_UCP)))
    assert via_ucp.status == "pass"
    assert "https://shop.example.nl/api/ucp/mcp" in details(via_ucp)

    catalog = res(f"{ORIGIN}/.well-known/ai-catalog.json", 200, '{"cards": []}')
    assert (await p3_endpoints.check(ctx(catalog=catalog))).status == "pass"

    llms = res(f"{ORIGIN}/llms.txt", 200, "# Example Shop\n> Fietsaccu's\n")
    only_llms = await p3_endpoints.check(ctx(llms=llms))
    assert only_llms.status == "warn" and only_llms.score_fraction == 0.5

    soft404 = res(f"{ORIGIN}/llms.txt", 200, "<!DOCTYPE html><html>404</html>")
    nothing = await p3_endpoints.check(ctx(llms=soft404))
    assert nothing.status == "warn" and nothing.score_fraction == 0.0  # never fail in v1


# --- D5 --------------------------------------------------------------------------------


async def test_d5_manual_input_only() -> None:
    def opts(active: bool | None, pct: float | None = None) -> ScanOptions:
        return ScanOptions(merchant_center_active=active, merchant_center_disapproved_pct=pct)

    assert (await d5_merchant_center.check(ctx())).status == "not_applicable"
    assert (await d5_merchant_center.check(ctx(options=opts(False)))).status == "fail"
    assert (await d5_merchant_center.check(ctx(options=opts(True, 2)))).status == "pass"
    warn = await d5_merchant_center.check(ctx(options=opts(True, 12)))
    assert warn.status == "warn" and warn.score_fraction == 0.88
    assert (await d5_merchant_center.check(ctx(options=opts(True, 40)))).status == "fail"

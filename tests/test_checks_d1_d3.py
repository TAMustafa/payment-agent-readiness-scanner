"""D1 and D3 end-to-end through the graph against offline fake shops."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from scanner.graph import run_scan
from scanner.models import CheckResult, ScanOptions
from tests.conftest import FakeShop, fixture

ORIGIN = "https://shop.example.nl"


async def scan(shop: FakeShop, check: str) -> CheckResult:
    report = await run_scan(
        ORIGIN, ScanOptions(checks=[check]), transport=shop.transport, min_interval_s=0
    )
    [result] = report.results
    return result


def woo_shop(robots: str) -> FakeShop:
    return FakeShop(
        {
            f"{ORIGIN}/robots.txt": (200, robots),
            f"{ORIGIN}/": (200, "<html></html>"),
            f"{ORIGIN}/sitemap_index.xml": (200, fixture("sitemaps/index.xml")),
            f"{ORIGIN}/product-sitemap.xml": (200, fixture("sitemaps/products.xml")),
            f"{ORIGIN}/page-sitemap.xml": (200, fixture("sitemaps/pages_no_lastmod.xml")),
        }
    )


# --- D1 -------------------------------------------------------------------------------


async def test_d1_no_robots_is_pass(make_shop: Callable[..., FakeShop]) -> None:
    r = await scan(make_shop({f"{ORIGIN}/": (200, "<html></html>")}), "D1")
    assert r.status == "pass" and r.score_fraction == 1.0
    assert "404" in r.evidence[0].detail and r.guidance == ""


async def test_d1_shopify_default_is_pass() -> None:
    robots = fixture("robots/shopify_default.txt")
    r = await scan(FakeShop({f"{ORIGIN}/robots.txt": (200, robots)}), "D1")
    assert r.status == "pass"


async def test_d1_training_only_blocked_is_warn() -> None:
    r = await scan(woo_shop(fixture("robots/training_blocked.txt")), "D1")
    assert r.status == "warn" and r.score_fraction == 1.0
    blocked = " ".join(e.detail for e in r.evidence)
    for token in ("GPTBot", "ClaudeBot", "Google-Extended", "Applebot-Extended"):
        assert token in blocked
    assert r.guidance  # NL guidance shown for non-pass


async def test_d1_search_bots_blocked_is_fail_with_partial_credit() -> None:
    r = await scan(woo_shop(fixture("robots/search_blocked.txt")), "D1")
    assert r.status == "fail"
    # 4 of 9 search/user_agent bots blocked (Claude-SearchBot only on /product/ paths,
    # which are tested via the sitemap's product URLs).
    assert r.score_fraction == round(1 - 4 / 9, 4)
    claude = next(e for e in r.evidence if e.detail.startswith("Claude-SearchBot"))
    assert (
        "/product/" in claude.detail and claude.snippet and "Disallow: /product/" in claude.snippet
    )
    chatgpt = next(e for e in r.evidence if e.detail.startswith("ChatGPT-User"))
    assert "may not apply" in chatgpt.detail


async def test_d1_server_error_is_fail() -> None:
    r = await scan(FakeShop({f"{ORIGIN}/robots.txt": (503, "down")}), "D1")
    assert r.status == "fail" and "503" in r.evidence[0].detail


async def test_d1_network_error_is_error() -> None:
    r = await scan(FakeShop({f"{ORIGIN}/robots.txt": httpx.ConnectError("refused")}), "D1")
    assert r.status == "error"


# --- D3 -------------------------------------------------------------------------------


async def test_d3_full_marks_when_all_subcriteria_met() -> None:
    shop = FakeShop(
        {
            f"{ORIGIN}/robots.txt": (200, fixture("robots/shopify_default.txt")),
            f"{ORIGIN}/sitemap.xml": (200, fixture("sitemaps/products.xml")),
        }
    )
    r = await scan(shop, "D3")
    # products.xml: 2/3 entries have lastmod (67%) >= 50%
    assert r.status == "pass" and r.score_fraction == 1.0


async def test_d3_index_with_low_lastmod_share_is_warn() -> None:
    r = await scan(woo_shop(fixture("robots/training_blocked.txt")), "D3")
    # 7 URLs, 2 with lastmod -> lastmod criterion fails; other three pass
    assert r.status == "warn" and r.score_fraction == 0.75
    assert any("2/7" in e.detail for e in r.evidence)


async def test_d3_no_sitemap_is_fail() -> None:
    r = await scan(FakeShop({f"{ORIGIN}/robots.txt": (200, "User-agent: *\nDisallow:\n")}), "D3")
    assert r.status == "fail" and r.score_fraction == 0.0
    assert "/sitemap.xml" in r.evidence[0].detail and "/sitemap_index.xml" in r.evidence[0].detail


async def test_d3_not_referenced_in_robots_and_no_products() -> None:
    shop = FakeShop({f"{ORIGIN}/sitemap.xml": (200, fixture("sitemaps/pages_no_lastmod.xml"))})
    r = await scan(shop, "D3")
    assert r.status == "warn" and r.score_fraction == 0.25


async def test_d1_and_d3_blocked_for_scanner_is_error_not_guess() -> None:
    shop = FakeShop(
        {
            f"{ORIGIN}/robots.txt": (403, "Forbidden"),
            f"{ORIGIN}/sitemap.xml": (403, "Forbidden"),
            f"{ORIGIN}/sitemap_index.xml": (403, "Forbidden"),
        }
    )
    d1 = await scan(shop, "D1")
    d3 = await scan(shop, "D3")
    assert d1.status == "error" and "403" in d1.evidence[0].detail
    assert d3.status == "error" and "refused" in d3.evidence[0].detail

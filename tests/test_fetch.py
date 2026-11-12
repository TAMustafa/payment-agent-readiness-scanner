"""Polite client + sitemap collection, fully offline."""

from __future__ import annotations

import gzip
import time
from collections.abc import Callable

import httpx

from scanner.fetch.client import ROBOTS_TOKEN, PoliteClient
from scanner.fetch.robots import RobotsTxt
from scanner.sampling.sitemap import collect_sitemaps, parse_sitemap
from tests.conftest import FakeShop, fixture

ORIGIN = "https://shop.example.nl"


async def test_sends_user_agent_and_drops_set_cookie(make_shop: Callable[..., FakeShop]) -> None:
    shop = make_shop({f"{ORIGIN}/": (200, "<html></html>", {"set-cookie": "sid=secret"})})
    async with PoliteClient(transport=shop.transport, min_interval_s=0) as c:
        res = await c.get(f"{ORIGIN}/")
    assert shop.requests[0].headers["user-agent"].startswith(f"{ROBOTS_TOKEN}/")
    assert res.status_code == 200 and "set-cookie" not in res.headers


async def test_respects_robots_for_own_token(make_shop: Callable[..., FakeShop]) -> None:
    shop = make_shop()
    async with PoliteClient(transport=shop.transport, min_interval_s=0) as c:
        c.set_robots(
            "shop.example.nl", RobotsTxt.parse(f"User-agent: {ROBOTS_TOKEN}\nDisallow: /p\n")
        )
        res = await c.get(f"{ORIGIN}/p/1")
    assert res.status_code is None and res.error and "robots" in res.error
    assert shop.requests == []  # never sent


async def test_request_budget(make_shop: Callable[..., FakeShop]) -> None:
    shop = make_shop()
    async with PoliteClient(transport=shop.transport, min_interval_s=0, max_requests=2) as c:
        results = [await c.get(f"{ORIGIN}/{i}") for i in range(3)]
    assert len(shop.requests) == 2
    assert results[2].error and "budget" in results[2].error


async def test_rate_limit_per_host(make_shop: Callable[..., FakeShop]) -> None:
    shop = make_shop()
    async with PoliteClient(transport=shop.transport, min_interval_s=0.2) as c:
        t0 = time.monotonic()
        for i in range(3):
            await c.get(f"{ORIGIN}/{i}")
        await c.get("https://other.example.nl/")  # other host: no wait for it
    assert time.monotonic() - t0 >= 0.4


async def test_network_error_is_captured(make_shop: Callable[..., FakeShop]) -> None:
    shop = make_shop({f"{ORIGIN}/": httpx.ConnectError("boom")})
    async with PoliteClient(transport=shop.transport, min_interval_s=0) as c:
        res = await c.get(f"{ORIGIN}/")
    assert res.status_code is None and res.error and "ConnectError" in res.error


async def test_gzip_sitemap_decoded(make_shop: Callable[..., FakeShop]) -> None:
    gz = gzip.compress(fixture("sitemaps/products.xml").encode())
    shop = make_shop({f"{ORIGIN}/sitemap.xml.gz": (200, gz)})
    async with PoliteClient(transport=shop.transport, min_interval_s=0) as c:
        res = await c.get(f"{ORIGIN}/sitemap.xml.gz")
    assert len(parse_sitemap(res.body or "").entries) == 3


async def test_index_follows_product_child_first(make_shop: Callable[..., FakeShop]) -> None:
    shop = make_shop(
        {
            f"{ORIGIN}/sitemap_index.xml": (200, fixture("sitemaps/index.xml")),
            f"{ORIGIN}/product-sitemap.xml": (200, fixture("sitemaps/products.xml")),
            f"{ORIGIN}/page-sitemap.xml": (200, fixture("sitemaps/pages_no_lastmod.xml")),
        }
    )
    async with PoliteClient(transport=shop.transport, min_interval_s=0) as c:
        info = await collect_sitemaps(c, ORIGIN, [f"{ORIGIN}/sitemap_index.xml"])
    # max 3 sitemap files: index, then product sitemap, then category sitemap (404 here)
    assert shop.paths() == [
        "/sitemap_index.xml",
        "/product-sitemap.xml",
        "/product_cat-sitemap.xml",
    ]
    assert [s.kind for s in info.sources] == ["index", "urlset", "unreachable"]
    assert len(info.entries) == 3 and info.truncated


async def test_fallback_to_sitemap_index_when_no_robots_line(
    make_shop: Callable[..., FakeShop],
) -> None:
    shop = make_shop({f"{ORIGIN}/sitemap_index.xml": (200, fixture("sitemaps/products.xml"))})
    async with PoliteClient(transport=shop.transport, min_interval_s=0) as c:
        info = await collect_sitemaps(c, ORIGIN, [])
    assert shop.paths() == ["/sitemap.xml", "/sitemap_index.xml"]
    assert len(info.entries) == 3 and info.from_robots == []


def test_invalid_sitemap_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        parse_sitemap(fixture("sitemaps/invalid.html"))


async def test_time_budget_stops_fetching_gracefully(make_shop: Callable[..., FakeShop]) -> None:
    shop = make_shop()
    async with PoliteClient(
        transport=shop.transport, min_interval_s=0.3, time_budget_s=0.5, timeout_s=0.1
    ) as c:
        results = [await c.get(f"{ORIGIN}/{i}") for i in range(5)]
    assert c.stopped_for_time
    assert results[-1].error == "scan time budget reached"
    assert 1 <= len(shop.requests) < 5


async def test_reserve_refuses_request_that_would_eat_kept_time(
    make_shop: Callable[..., FakeShop],
) -> None:
    shop = make_shop()
    async with PoliteClient(
        transport=shop.transport, min_interval_s=0, time_budget_s=5, timeout_s=1
    ) as c:
        refused = await c.get(f"{ORIGIN}/a", reserve_s=4.5)  # 1 s timeout > 0.5 s left
        allowed = await c.get(f"{ORIGIN}/b")  # later step: no reserve
    assert refused.error and "kept for later" in refused.error and c.reserve_hit
    assert allowed.status_code == 404 and not c.stopped_for_time
    assert shop.paths() == ["/b"]


async def test_budget_can_be_extended_but_never_shortened(
    make_shop: Callable[..., FakeShop],
) -> None:
    shop = make_shop()
    async with PoliteClient(transport=shop.transport, min_interval_s=0, time_budget_s=10) as c:
        before = c.time_left()
        c.extend_budget(5)  # shorter: ignored
        assert c.time_left() <= before and c.budget_extended_to is None
        c.extend_budget(230)
        assert c.time_left() > 200 and c.budget_extended_to == 230
    async with PoliteClient(transport=shop.transport, min_interval_s=0) as unbounded:
        unbounded.extend_budget(230)  # no budget at all: stays unbounded
        assert unbounded.time_left() == float("inf")

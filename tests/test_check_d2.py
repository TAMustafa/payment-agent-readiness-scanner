"""D2 edge blocking + challenge detection against offline fake shops (UA-aware routes)."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from scanner.fetch.challenge import classify
from scanner.graph import run_scan
from scanner.models import CheckResult, FetchedResource, ScanOptions
from tests.conftest import FakeShop

ORIGIN = "https://shop.example.nl"
CF_CHALLENGE = (
    403,
    "<html><head><title>Just a moment...</title></head><body>cf-chl-</body></html>",
    {"cf-mitigated": "challenge", "server": "cloudflare"},
)


class UaShop(FakeShop):
    """Home page 200 for everyone except user agents containing a blocked substring."""

    def __init__(self, blocked_ua: tuple[str, ...], robots: str = "", block_all: bool = False):
        routes = {f"{ORIGIN}/robots.txt": (200, robots)} if robots else {}
        super().__init__(routes)
        self.blocked_ua = blocked_ua
        self.block_all = block_all

    def handler(self, request: httpx.Request) -> httpx.Response:
        ua = request.headers.get("user-agent", "")
        if str(request.url) == f"{ORIGIN}/" and (
            self.block_all or any(b in ua for b in self.blocked_ua)
        ):
            self.requests.append(request)
            status, body, headers = CF_CHALLENGE
            return httpx.Response(status, text=body, headers=headers)
        if str(request.url) == f"{ORIGIN}/":
            self.requests.append(request)
            return httpx.Response(200, text="<html><body>Welkom</body></html>")
        return super().handler(request)


async def scan(shop: FakeShop) -> CheckResult:
    report = await run_scan(
        ORIGIN, ScanOptions(checks=["D2"]), transport=shop.transport, min_interval_s=0
    )
    [r] = report.results
    return r


def test_classify_markers() -> None:
    def res(status: int, body: str = "", headers: dict[str, str] | None = None) -> FetchedResource:
        return FetchedResource(url="u", status_code=status, body=body, headers=headers or {})

    assert classify(res(200, "<html>shop</html>")).outcome == "ok"
    assert classify(res(403, CF_CHALLENGE[1], CF_CHALLENGE[2])).outcome == "blocked"
    # 200 interstitial without a block status is still a block
    assert classify(res(200, "<title>Just a moment...</title>")).outcome == "blocked"
    assert classify(res(429, "", {"retry-after": "60"})).outcome == "rate_limited"
    assert classify(res(500)).outcome == "inconclusive"
    assert classify(FetchedResource(url="u", error="timeout")).outcome == "inconclusive"
    # a big normal page that merely mentions a vendor is not a block
    assert classify(res(200, "x" * 70_000 + "captcha-delivery.com")).outcome == "ok"


async def test_all_allowed_is_pass() -> None:
    shop = UaShop(blocked_ua=())
    r = await scan(shop)
    assert r.status == "pass" and r.score_fraction == 1.0
    ua_requests = [q for q in shop.requests if q.url.path == "/"]
    assert len(ua_requests) == 1 + 9  # baseline + 9 search/user_agent bots, no training bots
    assert not any("GPTBot" in q.headers["user-agent"] for q in ua_requests)


async def test_some_bots_blocked_is_fail_with_partial_credit() -> None:
    r = await scan(UaShop(blocked_ua=("OAI-SearchBot", "PerplexityBot", "Claude-SearchBot")))
    assert r.status == "fail" and r.score_fraction == round(6 / 9, 4)
    assert (
        r.evidence[0].detail
        == "Blocked at the edge: OAI-SearchBot, PerplexityBot, Claude-SearchBot"
    )
    assert any("cf-mitigated" in e.detail for e in r.evidence)
    assert r.guidance


async def test_everything_blocked_including_us_is_inconclusive() -> None:
    r = await scan(UaShop(blocked_ua=(), block_all=True))
    assert r.status == "error"
    assert r.evidence[0].detail.startswith("Inconclusive")


async def test_robots_disallowed_bot_is_not_impersonated() -> None:
    shop = UaShop(blocked_ua=(), robots="User-agent: PerplexityBot\nDisallow: /\n")
    r = await scan(shop)
    assert r.status == "pass"
    assert not any("PerplexityBot" in q.headers["user-agent"] for q in shop.requests)
    assert any(e.detail.startswith("PerplexityBot (search): skipped") for e in r.evidence)


async def test_probe_budget_is_separate_from_page_budget() -> None:
    shop = UaShop(blocked_ua=())
    report = await run_scan(
        ORIGIN,
        ScanOptions(checks=["D2"], max_pages=3),
        transport=shop.transport,
        min_interval_s=0,
    )
    assert report.results[0].status == "pass"  # probes still ran although page budget tiny


class RateLimitShop(UaShop):
    """Every 2nd request to the home page gets 429, whatever the user agent (like Shopify)."""

    n = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == f"{ORIGIN}/":
            self.n += 1
            self.requests.append(request)
            if self.n % 2 == 0:
                return httpx.Response(429, headers={"retry-after": "0"})
            return httpx.Response(200, text="<html><body>Welkom</body></html>")
        return super().handler(request)


async def test_rate_limiting_is_not_counted_as_blocking() -> None:
    r = await scan(RateLimitShop(blocked_ua=()))
    assert r.status == "pass" and r.score_fraction == 1.0
    assert r.evidence[0].detail.startswith("Rate limited (HTTP 429), not counted as blocked")


async def test_client_backs_off_after_429() -> None:
    import time

    from scanner.fetch.client import PoliteClient

    shop = RateLimitShop(blocked_ua=())
    async with PoliteClient(transport=shop.transport, min_interval_s=0.1) as c:
        await c.get(f"{ORIGIN}/")
        await c.get(f"{ORIGIN}/")  # 429 -> interval for this host doubles to 0.2s
        t0 = time.monotonic()
        await c.get(f"{ORIGIN}/")
    assert time.monotonic() - t0 >= 0.19
    assert c.rate_limited == {"shop.example.nl": 1}


class CdnShop(UaShop):
    """Like UaShop but every response carries Cloudflare headers."""

    def handler(self, request: httpx.Request) -> httpx.Response:
        resp = super().handler(request)
        resp.headers["cf-ray"] = "abc-AMS"
        resp.headers["server"] = "cloudflare"
        return resp


async def test_cdn_fronted_spoofed_block_is_warn_not_fail() -> None:
    r = await scan(CdnShop(blocked_ua=("Googlebot", "bingbot")))
    assert r.status == "warn" and r.score_fraction == round(7 / 9, 4)
    assert r.evidence[0].detail.startswith("Blocked by Cloudflare when claiming to be: Googlebot")


async def test_retry_after_is_honoured(make_shop: Callable[..., FakeShop]) -> None:
    import time

    from scanner.fetch.client import PoliteClient

    shop = make_shop({f"{ORIGIN}/a": (429, "", {"retry-after": "1"})})
    async with PoliteClient(transport=shop.transport, min_interval_s=0) as c:
        await c.get(f"{ORIGIN}/a")
        t0 = time.monotonic()
        await c.get(f"{ORIGIN}/b")
    assert time.monotonic() - t0 >= 0.95

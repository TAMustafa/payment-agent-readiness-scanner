"""End to end against fake merchants: fetching rules, verdicts, and the web API."""

from __future__ import annotations

import json

import httpx
import pytest

from ap2check.runner import InvalidTarget, check_merchant, normalise_target
from ap2check.web.app import create_app
from tests.helpers import (
    SHOP,
    MerchantKey,
    agent_card_1_0,
    merchant,
    profile,
    public_resolver,
    sample_checkout,
)


async def run(shop, sample: str | None = None, resolver=public_resolver):  # type: ignore[no-untyped-def]
    return await check_merchant(
        SHOP, sample, transport=shop.transport, resolver=resolver, min_interval_s=0
    )


@pytest.mark.parametrize(
    ("raw", "out"),
    [
        ("Shop.Example.nl", "https://shop.example.nl"),
        ("http://shop.example.nl/p/1?x", "https://shop.example.nl"),
        ("https://shop.example.nl:8443/", "https://shop.example.nl:8443"),
    ],
)
def test_normalise(raw: str, out: str) -> None:
    assert normalise_target(raw) == out


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "localhost",
        "http://127.0.0.1",
        "ftp://x.nl",
        "https://[::1]/",
        "169.254.169.254",
        "intranet",
        "https://u:p@shop.nl",
    ],
)
def test_normalise_refuses(raw: str) -> None:
    with pytest.raises(InvalidTarget):
        normalise_target(raw)


async def test_ready_with_valid_sample() -> None:
    k = MerchantKey()
    shop = merchant(profile(k))
    report = await run(shop, json.dumps(k.sign_checkout(sample_checkout())))
    assert report.verdict.level == "ready", report.verdict
    assert {r.method for r in shop.requests} == {"GET"}
    assert shop.paths() == ["/robots.txt", "/.well-known/ucp", "/.well-known/agent-card.json"]
    ua = shop.requests[0].headers["user-agent"]
    assert ua.startswith("AP2ReadinessCheck/")


async def test_untested_without_sample_and_failed_with_bad_one() -> None:
    k = MerchantKey()
    assert (await run(merchant(profile(k)))).verdict.level == "untested"
    bad = json.dumps(MerchantKey().sign_checkout(sample_checkout()))
    assert (await run(merchant(profile(k)), bad)).verdict.level == "signature_failed"


async def test_not_discoverable_and_no_ap2() -> None:
    assert (await run(merchant(None))).verdict.level == "not_discoverable"
    p = profile()
    del p["ucp"]["capabilities"]["dev.ucp.common.payment.ap2_mandate"]
    assert (await run(merchant(p))).verdict.level == "no_ap2"


async def test_incomplete_when_keys_missing() -> None:
    report = await run(merchant(profile(keys=[])))
    assert report.verdict.level == "incomplete"
    assert "signing keys" in report.verdict.summary.lower()


async def test_agent_card_only_is_incomplete_because_keys_have_no_home() -> None:
    report = await run(merchant(None, card=agent_card_1_0()))
    assert report.verdict.level == "incomplete"


async def test_redirect_is_not_followed() -> None:
    shop = merchant(None)
    shop.routes[f"{SHOP}/.well-known/ucp"] = (302, "", {"location": "https://evil.example/ucp"})
    report = await run(shop)
    assert all(r.url.host == "shop.example.nl" for r in shop.requests)
    assert report.results[0].status == "fail"


async def test_s3_static_site_without_profile_is_not_discoverable() -> None:
    denied = (
        403,
        '<?xml version="1.0"?><Error><Code>AccessDenied</Code></Error>',
        {"server": "AmazonS3", "content-type": "application/xml"},
    )
    shop = merchant(None)
    shop.routes[f"{SHOP}/.well-known/ucp"] = denied
    shop.routes[f"{SHOP}/.well-known/agent-card.json"] = denied
    report = await run(shop)
    assert report.verdict.level == "not_discoverable", report.verdict


async def test_robots_disallow_is_respected() -> None:
    shop = merchant(profile(), robots="User-agent: AP2ReadinessCheck\nDisallow: /.well-known/\n")
    report = await run(shop)
    assert "/.well-known/ucp" not in shop.paths()
    assert report.verdict.level == "unknown"


async def test_dns_to_private_address_is_refused() -> None:
    async def evil(host: str) -> list[str]:
        return ["10.0.0.5"]

    shop = merchant(profile())
    report = await run(shop, resolver=evil)
    assert shop.requests == []
    assert "private address" in report.results[0].evidence[0].detail
    assert report.verdict.level == "unknown"


async def test_a_crashing_check_becomes_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import ap2check.runner as runner
    from ap2check.checks import ALL_CHECKS

    def boom(inp):  # type: ignore[no-untyped-def]
        raise RuntimeError("bug")

    boom.__name__ = "u5_payment_handlers"
    monkeypatch.setattr(runner, "ALL_CHECKS", [*ALL_CHECKS[:4], boom, *ALL_CHECKS[5:]])
    report = await run(merchant(profile()))
    assert next(r for r in report.results if r.id.startswith("U5")).status == "error"


# --- web -----------------------------------------------------------------------------------


def client(shop, clock=None):  # type: ignore[no-untyped-def]
    kwargs = {"clock": clock} if clock else {}
    app = create_app(transport=shop.transport, resolver=public_resolver, min_interval_s=0, **kwargs)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_index_and_security_headers() -> None:
    async with client(merchant(None)) as c:
        r = await c.get("/")
        assert r.status_code == 200 and "AP2 Readiness Check" in r.text
        assert "script-src 'self'" in r.headers["content-security-policy"]
        assert (await c.get("/static/app.js")).status_code == 200
        assert (await c.get("/docs")).status_code == 404


async def test_api_check_returns_report() -> None:
    k = MerchantKey()
    async with client(merchant(profile(k))) as c:
        sample = json.dumps(k.sign_checkout(sample_checkout()))
        r = await c.post("/api/check", json={"url": "shop.example.nl", "sample": sample})
        assert r.status_code == 200, r.text
        assert r.json()["verdict"]["level"] == "ready"
        assert r.headers["cache-control"] == "no-store"


async def test_api_rejects_private_and_oversized() -> None:
    async with client(merchant(None)) as c:
        assert (await c.post("/api/check", json={"url": "localhost"})).status_code == 422
        big = {"url": "shop.example.nl", "sample": "x" * 300_000}
        assert (await c.post("/api/check", json=big)).status_code == 422


async def test_api_rate_limits_per_target() -> None:
    async with client(merchant(None), clock=lambda: 1000.0) as c:
        codes = [
            (await c.post("/api/check", json={"url": "shop.example.nl"})).status_code
            for _ in range(5)
        ]
    assert codes[:4] == [200] * 4 and codes[4] == 429

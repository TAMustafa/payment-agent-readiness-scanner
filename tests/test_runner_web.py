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


async def test_ladder_and_next_step() -> None:
    k = MerchantKey()
    # No profile: rung 1 is the problem and the next step is U1's fix.
    report = await run(merchant(None))
    assert [s.state for s in report.steps] == ["problem", "todo", "todo", "todo", "todo"]
    assert report.steps[0].current and "/.well-known/ucp" in report.next_step
    # AP2 declared but no keys: rungs 1-3 done, rung 4 is current.
    report = await run(merchant(profile(keys=[])))
    assert [s.state for s in report.steps] == ["done", "done", "done", "problem", "todo"]
    assert report.steps[3].current and "keys" in report.next_step
    # Everything public is fine: the next step is to paste a sample.
    report = await run(merchant(profile(k)))
    assert [s.state for s in report.steps][:4] == ["done"] * 4
    assert report.steps[4].current and "Paste one checkout response" in report.next_step
    # Sample verifies: nothing left to do.
    report = await run(merchant(profile(k)), json.dumps(k.sign_checkout(sample_checkout())))
    assert all(s.state == "done" and not s.current for s in report.steps)
    assert "Nothing to fix" in report.next_step


async def test_blocked_profile_is_unknown_on_the_ladder() -> None:
    shop = merchant(None)
    shop.routes[f"{SHOP}/.well-known/ucp"] = (403, "blocked", {"server": "cloudflare"})
    report = await run(shop)
    assert report.steps[0].state == "unknown" and report.steps[0].current
    assert "/.well-known/ucp" in report.next_step


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


async def test_robots_redirect_is_followed_and_applied_to_the_original_host() -> None:
    # www -> apex redirect of robots.txt must not be read as "everything disallowed".
    shop = merchant(profile())
    shop.routes[f"{SHOP}/robots.txt"] = (301, "", {"location": "https://example.nl/robots.txt"})
    shop.routes["https://example.nl/robots.txt"] = (200, "User-agent: *\nDisallow: /cart\n")
    report = await run(shop)
    assert report.verdict.level == "untested", report.verdict
    assert [str(r.url) for r in shop.requests][:2] == [
        f"{SHOP}/robots.txt",
        "https://example.nl/robots.txt",
    ]
    # The redirected robots.txt still binds us.
    shop = merchant(profile())
    shop.routes[f"{SHOP}/robots.txt"] = (301, "", {"location": "https://example.nl/robots.txt"})
    shop.routes["https://example.nl/robots.txt"] = (200, "User-agent: *\nDisallow: /.well-known/\n")
    assert (await run(shop)).verdict.level == "unknown"


async def test_robots_redirect_to_private_or_endless_chain_is_not_followed() -> None:
    shop = merchant(profile())
    shop.routes[f"{SHOP}/robots.txt"] = (302, "", {"location": "https://127.0.0.1/robots.txt"})
    report = await run(shop)
    assert all(r.url.host == "shop.example.nl" for r in shop.requests)
    assert report.verdict.level == "untested"
    shop = merchant(profile())
    shop.routes[f"{SHOP}/robots.txt"] = (302, "", {"location": f"{SHOP}/robots.txt"})
    report = await run(shop)
    assert shop.paths().count("/robots.txt") == 3 and len(shop.requests) == 5
    assert report.verdict.level == "untested"


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


async def test_demo_scenarios_cover_the_ladder() -> None:
    from ap2check.demo import DEMO_NOTE, SCENARIOS, run_demo

    expected = {"ready": "ready", "no_ap2": "no_ap2", "signature_failed": "signature_failed"}
    assert set(SCENARIOS) == set(expected)
    for name, level in expected.items():
        report, sample = await run_demo(name)
        assert report.verdict.level == level, name
        assert report.target == "https://demo-shop.example" and report.notes[0] == DEMO_NOTE
        assert (sample is None) == (name == "no_ap2")
    ready, _ = await run_demo("ready")
    assert all(r.status in ("pass", "not_applicable") for r in ready.results)
    assert all(s.state == "done" for s in ready.steps)


def test_demo_fixture_holds_public_data_only() -> None:
    from ap2check.demo import DATA

    profile_doc = json.loads((DATA / "profile.json").read_text())
    assert all(set(k) <= {"kid", "kty", "crv", "x", "y", "use", "alg"} for k in profile_doc["keys"])
    assert "PRIVATE KEY" not in "".join(p.read_text() for p in DATA.iterdir())


async def test_api_demo() -> None:
    shop = merchant(None)
    async with client(shop) as c:
        r = await c.get("/api/demo/ready")
        assert r.status_code == 200 and r.json()["report"]["verdict"]["level"] == "ready"
        assert "merchant_authorization" in r.json()["sample"]
        assert (await c.get("/api/demo/nope")).status_code == 404
        r = await c.post("/api/check", json={"url": "demo-shop.example"})
        assert r.status_code == 422 and "demo" in r.json()["detail"]
    assert shop.requests == []  # the demo never touches the network


async def test_api_rejects_private_and_oversized() -> None:
    async with client(merchant(None)) as c:
        assert (await c.post("/api/check", json={"url": "localhost"})).status_code == 422
        big = {"url": "shop.example.nl", "sample": "x" * 300_000}
        assert (await c.post("/api/check", json=big)).status_code == 422


def test_rate_limiter_forgets_idle_keys() -> None:
    from ap2check.web.app import RateLimiter

    now = [0.0]
    limiter = RateLimiter(2, clock=lambda: now[0])
    for i in range(500):
        assert limiter.allow(f"visitor-{i}")
    now[0] = 200.0
    assert limiter.allow("fresh")
    assert set(limiter._hits) == {"fresh"}
    assert limiter.allow("fresh") and not limiter.allow("fresh")


async def test_api_rate_limits_per_target() -> None:
    async with client(merchant(None), clock=lambda: 1000.0) as c:
        codes = [
            (await c.post("/api/check", json={"url": "shop.example.nl"})).status_code
            for _ in range(5)
        ]
    assert codes[:4] == [200] * 4 and codes[4] == 429

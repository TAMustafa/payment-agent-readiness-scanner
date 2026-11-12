"""Skeleton tests: graph wiring, fan-out, error isolation, registry integrity."""

from __future__ import annotations

import pytest

from scanner.checks import registry
from scanner.checks.registry import REGISTRY, CheckSpec, static_check_ids
from scanner.graph import build_graph, run_scan
from scanner.models import CheckResult, ScanContext, ScanOptions, ScanReport
from scanner.nodes import normalise
from tests.conftest import FakeShop, fixture


async def offline_scan(options: ScanOptions | None = None) -> ScanReport:
    return await run_scan("example.nl", options, transport=FakeShop().transport, min_interval_s=0)


def test_weights_sum_to_100() -> None:
    assert sum(s.weight for s in REGISTRY.values()) == 100


def test_category_weights_match_spec() -> None:
    totals: dict[str, int] = {}
    for s in REGISTRY.values():
        totals[s.category] = totals.get(s.category, 0) + s.weight
    assert totals == {
        "discovery": 30,
        "data": 30,
        "checkout": 20,
        "protocol": 10,
        "visibility": 10,
    }


def test_static_check_filter_by_prefix() -> None:
    assert static_check_ids(["D1", "S2.offer"]) == ["D1.robots_ai_crawlers", "S2.offer"]
    assert "C1.add_to_cart" in static_check_ids()  # reads checkout_probe data
    assert "V1.prompt_visibility" not in static_check_ids()  # produced by visibility node
    assert static_check_ids(["S"]) == [i for i in static_check_ids() if i.startswith("S")]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.nl", "https://example.nl"),
        ("HTTPS://Shop.Example.NL/some/path?q=1", "https://shop.example.nl"),
        ("http://example.nl:8080/", "http://example.nl:8080"),
    ],
)
def test_normalise(raw: str, expected: str) -> None:
    assert normalise(raw) == expected


def test_normalise_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        normalise("ftp://example.nl")


def test_graph_compiles_with_expected_nodes() -> None:
    nodes = set(build_graph().get_graph().nodes)
    assert {
        "normalise_url",
        "fetch_basics",
        "fingerprint_platform",
        "sample_pages",
        "run_check",
        "checkout_probe",
        "visibility",
        "score",
        "render_report",
    } <= nodes


async def test_offline_scan_runs_every_static_check() -> None:
    report = await offline_scan()
    assert report.origin == "https://example.nl"
    assert [r.id for r in report.results] == sorted(static_check_ids())
    assert len(report.results) == 19  # D1-D5, S1-S6, P1-P3, C1-C5 (V1: visibility node)
    for r in report.results:
        assert r.evidence, r.id  # no result without evidence (CLAUDE.md rule 4)
        assert "Traceback" not in r.evidence[0].detail, r.id


async def test_check_selection_limits_fan_out() -> None:
    report = await offline_scan(ScanOptions(checks=["D1", "P1"]))
    assert [r.id for r in report.results] == ["D1.robots_ai_crawlers", "P1.ucp_profile"]


async def test_no_checks_selected_still_completes() -> None:
    report = await offline_scan(ScanOptions(checks=["nope"]))
    assert report.results == []


async def test_one_failing_check_does_not_abort_others(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(ctx: ScanContext) -> CheckResult:
        raise RuntimeError("simulated bug")

    spec = REGISTRY["P2.platform_support"]
    patched = {**REGISTRY, "P2.platform_support": CheckSpec(**{**spec.__dict__, "func": boom})}
    monkeypatch.setattr(registry, "REGISTRY", patched)
    monkeypatch.setattr("scanner.nodes.REGISTRY", patched)

    report = await offline_scan(ScanOptions(checks=["P2", "D1"]))
    by_id = {r.id: r for r in report.results}
    assert by_id["P2.platform_support"].status == "error"
    assert "RuntimeError: simulated bug" in by_id["P2.platform_support"].evidence[0].detail
    assert by_id["D1.robots_ai_crawlers"].status == "pass"


@pytest.mark.parametrize(
    ("home", "fixed_s", "extended"),
    [
        ("shopify", None, True),  # automatic: Shopify gets 240 s
        ("woocommerce", None, False),  # automatic: others keep 120 s
        ("shopify", 120.0, False),  # explicit --timeout is never extended
    ],
)
async def test_shopify_scans_get_more_time(
    home: str, fixed_s: float | None, extended: bool
) -> None:
    shop = FakeShop({"https://example.nl/": (200, fixture(f"home/{home}.html"))})
    report = await run_scan(
        "example.nl",
        ScanOptions(checks=["D1"], timeout_s=fixed_s),
        transport=shop.transport,
        min_interval_s=0,
    )
    assert (report.platform.platform == "shopify") == (home == "shopify")
    notes = " | ".join(n.detail for n in report.sampling_notes)
    assert ("Scan time extended to 240 s for Shopify" in notes) == extended


def test_option_timeouts() -> None:
    assert ScanOptions().start_timeout_s == 120 and ScanOptions().max_timeout_s == 240
    fixed = ScanOptions(timeout_s=90)
    assert fixed.start_timeout_s == fixed.max_timeout_s == 90


# --- 2026-11-12 review ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "localhost",
        "http://127.0.0.1:8000",
        "192.168.1.10",
        "http://[::1]/",
        "shop.local",
        "10.0.0.5",
    ],
)
def test_normalise_rejects_private_and_local_addresses(raw: str) -> None:
    with pytest.raises(ValueError, match="private or local"):
        normalise(raw)


def test_tracing_never_uploads_page_content(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    from scanner.graph import enforce_trace_privacy

    for name in (
        "LANGSMITH_HIDE_INPUTS",
        "LANGSMITH_HIDE_OUTPUTS",
        "LANGCHAIN_HIDE_INPUTS",
        "LANGCHAIN_HIDE_OUTPUTS",
    ):
        monkeypatch.setenv(name, "false")
    enforce_trace_privacy()  # run_scan calls this before the graph starts
    assert os.environ["LANGSMITH_HIDE_INPUTS"] == os.environ["LANGSMITH_HIDE_OUTPUTS"] == "true"


async def test_probe_that_overruns_does_not_lose_the_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from scanner import nodes

    async def stuck(*args: object, **kwargs: object) -> None:
        await asyncio.sleep(60)

    monkeypatch.setattr(nodes, "run_probe", stuck)
    monkeypatch.setattr(nodes, "PROBE_GRACE_S", 0.0)
    shop = FakeShop({"https://example.nl/": (200, fixture("home/woocommerce.html"))})
    report = await asyncio.wait_for(
        run_scan(
            "example.nl",
            ScanOptions(checks=["C1"], checkout=True, timeout_s=11),
            transport=shop.transport,
            min_interval_s=0,
        ),
        timeout=11,
    )
    c1 = report.results[0]
    assert c1.status == "error" and "ran out of time" in c1.evidence[0].detail


def test_hard_timeout_leaves_room_for_the_paid_visibility_run() -> None:
    from scanner.cli import hard_timeout_s
    from scanner.visibility.config import load_config

    cfg = load_config()
    calls = (
        len(cfg.assistants) * cfg.run.runs * (cfg.run.brand_questions + cfg.run.category_questions)
    )
    assert cfg.max_duration_s() == -(-calls // cfg.run.concurrency) * cfg.run.timeout_s
    assert hard_timeout_s(ScanOptions()) == 240
    assert hard_timeout_s(ScanOptions(visibility=True)) == 240 + cfg.max_duration_s()

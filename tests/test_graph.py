"""Skeleton tests: graph wiring, fan-out, error isolation, registry integrity."""

from __future__ import annotations

import pytest

from scanner.checks import registry
from scanner.checks.registry import REGISTRY, CheckSpec, static_check_ids
from scanner.graph import build_graph, run_scan
from scanner.models import CheckResult, ScanContext, ScanOptions, ScanReport
from scanner.nodes import normalise
from tests.conftest import FakeShop


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
    assert "C1.add_to_cart" not in static_check_ids()  # produced by checkout_probe
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
    assert len(report.results) == 14  # D1-D5, S1-S6, P1-P3 (C* and V1 come from other nodes)
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

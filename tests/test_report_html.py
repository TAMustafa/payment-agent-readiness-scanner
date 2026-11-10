"""HTML report (SPEC §5): self-contained, escaped, NL/EN, honest about agent checkout."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from scanner.checks.registry import REGISTRY
from scanner.cli import app
from scanner.graph import run_scan
from scanner.models import (
    CheckResult,
    CheckStatus,
    Evidence,
    PlatformInfo,
    ScanOptions,
    ScanReport,
    VisibilityCall,
    VisibilityResult,
)
from scanner.report.html import MAX_EVIDENCE, render_html
from scanner.report.scoring import summarise
from tests.conftest import FakeShop

HOSTILE = '<script>alert("x")</script><img src=x onerror=alert(1)>'


def res(
    check_id: str, status: CheckStatus, fraction: float, evidence: list[Evidence] | None = None
) -> CheckResult:
    spec = REGISTRY[check_id]
    return CheckResult(
        id=spec.id,
        category=spec.category,
        label=spec.label,
        status=status,
        weight=spec.weight,
        score_fraction=fraction,
        evidence=evidence or [Evidence(detail="seen")],
        guidance="" if status == "pass" else "stored guidance",
        effort=spec.effort,
    )


def make_report(results: list[CheckResult], **extra: object) -> ScanReport:
    s = summarise(results)
    now = datetime(2026, 11, 10, 9, 30, tzinfo=UTC)
    fields: dict[str, object] = {
        "scanner_version": "0.1.0",
        "url": "https://shop.example.nl",
        "origin": "https://shop.example.nl",
        "started_at": now,
        "finished_at": now,
        "platform": PlatformInfo(platform="woocommerce"),
        "sampled": {"products": ["https://shop.example.nl/p/1"], "categories": []},
        "requests_made": 12,
        "score": s.score,
        "grade": s.grade,
        "excluded_checks": s.excluded_checks,
        "not_run": s.not_run,
        "categories": s.categories,
        "top_fixes": s.top_fixes,
        "results": results,
        **extra,
    }
    return ScanReport.model_validate(fields)


def sample_results() -> list[CheckResult]:
    return [
        res("D1.robots_ai_crawlers", "fail", 0.0),
        res("D2.edge_blocking", "error", 0.0),
        res("S1.product_jsonld", "pass", 1.0),
        res("S2.offer", "warn", 0.5),
        res("S5.reviews", "not_applicable", 0.0),
        res("P3.mcp_or_feed_endpoint", "warn", 0.0),
    ]


def test_nl_report_has_all_sections() -> None:
    html = render_html(make_report(sample_results()))
    assert html.startswith("<!doctype html>") and '<html lang="nl">' in html
    for heading in (
        "Samenvatting",
        "Top 3 verbeterpunten",
        "Wat eraan komt",
        "Resultaten per check",
        "Methode en beperkingen",
    ):
        assert heading in html, heading
    assert "Niet klaar" in html  # (0 + 6 + 4 + 0) / 26 = 38.5
    assert "AI-crawlers toegestaan in robots.txt" in html  # Dutch label
    assert "Niet uitgevoerd" in html  # V1 and others had no result
    assert "Niet te controleren" in html  # D2 error
    assert "1/5 gemeten" in html  # discovery: only D1 counted (D2 error, rest not run)


def test_en_fallback_and_guidance_from_copy() -> None:
    html = render_html(make_report(sample_results()), lang="en")
    assert '<html lang="en">' in html and "Top 3 fixes" in html and "Not ready" in html
    assert "AI crawlers allowed in robots.txt" in html
    # guidance is re-read from checks/copy in the report language
    assert "Allow AI search and assistant bots" in html


def test_agent_checkout_is_never_claimed_live() -> None:
    for lang in ("nl", "en"):
        html = render_html(make_report(sample_results()), lang=lang)
        text = re.sub(r"<[^>]+>", " ", html).lower()
        assert "nog niet beschikbaar" in text or "not yet available" in text
        assert "is live" not in text and "is nu beschikbaar" not in text


def test_shop_content_is_escaped() -> None:
    ev = [
        Evidence(url="javascript:alert(1)", detail=HOSTILE, snippet=HOSTILE),
        Evidence(url='https://shop.example.nl/"><script>x</script>', detail="ok"),
    ]
    html = render_html(make_report([res("S1.product_jsonld", "fail", 0.0, ev)]))
    assert "<script" not in html and "<img" not in html
    assert "&lt;script&gt;" in html
    assert 'href="javascript:' not in html  # non-http URLs are never linked
    assert 'href="https://shop.example.nl/&quot;&gt;&lt;script&gt;' in html


def test_self_contained_no_external_resources() -> None:
    html = render_html(make_report(sample_results()))
    assert "<script" not in html and "<link" not in html
    assert not re.search(r"\bsrc\s*=", html)
    assert "url(" not in html  # no CSS-loaded fonts/images
    assert "@media print" in html


def test_evidence_is_capped_with_pointer_to_json() -> None:
    ev = [Evidence(detail=f"line {i}") for i in range(MAX_EVIDENCE + 7)]
    html = render_html(make_report([res("S2.offer", "warn", 0.5, ev)]))
    assert f"line {MAX_EVIDENCE - 1}" in html and f"line {MAX_EVIDENCE}<" not in html
    assert "7 regels meer in report.json" in html


def test_no_score_report_renders() -> None:
    html = render_html(make_report([res("D5.merchant_center", "not_applicable", 0.0)]))
    assert "Geen score" in html


def test_methodology_reflects_what_ran() -> None:
    vis = VisibilityResult(
        ran=True,
        calls=[
            VisibilityCall(assistant=a, model="m", run=r, kind="brand", prompt="q")
            for a in ("ChatGPT", "Gemini")
            for r in (1, 2)
        ],
    )
    on = render_html(make_report(sample_results(), checkout_tested=True, visibility=vis))
    assert "ChatGPT en Gemini" in on and "2x" in on and "anonieme winkelwagen" in on
    off = render_html(make_report(sample_results()))
    assert "niet gemeten" in off and "alleen met toestemming" in off


def test_brand_is_configurable() -> None:
    html = render_html(make_report(sample_results()), brand="Mijn Scan & Co")
    assert "Mijn Scan &amp; Co" in html


async def test_graph_fills_score_grade_and_fixes() -> None:
    report = await run_scan(
        "example.nl", ScanOptions(), transport=FakeShop().transport, min_interval_s=0
    )
    expected = summarise(report.results)
    assert report.score == expected.score and report.grade == expected.grade
    assert report.top_fixes == expected.top_fixes
    assert report.not_run == ["V1.prompt_visibility"]
    assert len(report.categories) == 5
    assert render_html(report).endswith("</html>")


def test_cli_report_rerenders_saved_json(tmp_path: Path) -> None:
    old = make_report(sample_results()).model_copy(
        update={"score": None, "grade": None, "top_fixes": [], "categories": []}
    )  # as written before build step 4
    path = tmp_path / "report.json"
    path.write_text(old.model_dump_json(), encoding="utf-8")
    out = CliRunner().invoke(app, ["report", str(path), "--lang", "en"])
    assert out.exit_code == 0, out.output
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "Not ready" in html and "Top 3 fixes" in html


def test_cli_rejects_unknown_lang(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text(make_report(sample_results()).model_dump_json(), encoding="utf-8")
    out = CliRunner().invoke(app, ["report", str(path), "--lang", "de"])
    assert out.exit_code != 0


@pytest.mark.parametrize("lang", ["nl", "en"])
def test_every_check_has_a_label_and_guidance(lang: str) -> None:
    from scanner.checks.copy import get_guidance
    from scanner.report.i18n import LABEL_NL

    assert set(LABEL_NL) == set(REGISTRY)
    for check_id in REGISTRY:
        assert get_guidance(check_id, lang), check_id  # type: ignore[arg-type]

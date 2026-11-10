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
)
from scanner.report.html import MAX_EVIDENCE, render_html
from scanner.report.i18n import WHY
from scanner.report.scoring import IN_SCOPE, summarise
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
        "coverage": s.coverage,
        "excluded_checks": s.excluded_checks,
        "not_run": s.not_run,
        "stages": s.stages,
        "out_of_scope": s.out_of_scope,
        "top_fixes": s.top_fixes,
        "results": results,
        "lang": "nl",  # most assertions below check the Dutch copy; English is the default
        **extra,
    }
    return ScanReport.model_validate(fields)


def sample_results() -> list[CheckResult]:
    return [
        res("D1.robots_ai_crawlers", "fail", 0.0),
        res("D2.edge_blocking", "error", 0.0),
        res("S1.product_jsonld", "pass", 1.0),
        res("S2.offer", "warn", 0.5),
        res("S3.identifiers", "pass", 1.0),
        res("S4.shipping_returns", "fail", 0.0),
        res("C1.add_to_cart", "pass", 1.0),
        res("C2.guest_checkout", "pass", 1.0),
        res("S5.reviews", "not_applicable", 0.0),  # out of scope
        res("S6.organization", "fail", 0.0),  # out of scope
        res("P3.mcp_or_feed_endpoint", "warn", 0.0),
    ]


def text_of(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def test_nl_report_sections_follow_the_agent_order() -> None:
    html = render_html(make_report(sample_results()))
    assert html.startswith("<!doctype html>") and '<html lang="nl">' in html
    order = [
        "<h1>Klaar voor AI-shoppingagents?",
        "<h2>Eerst doen",
        "<h2>De vier stappen van een agent-bestelling",
        "<h3>1. Vinden en bereiken",
        "<h3>2. Begrijpen",
        "<h3>3. Afrekenen",
        "<h3>4. Aansluiten",
        "<h2>Hoe we hebben gemeten",
    ]
    positions = [html.index(h) for h in order]
    assert positions == sorted(positions)
    assert "Niet klaar" in html  # 27 earned / 51 measured weight = 52.9
    assert "AI-bots toegestaan in robots.txt" in html  # Dutch label
    assert "Niet te controleren" in html  # D2 error
    assert "10 van 19 checks konden we niet meten" in html
    assert "1/4 gemeten" in html  # access: only D1 counted (D2 error, D3/D4 not run)


def test_dropped_sections_are_gone() -> None:
    html = render_html(make_report(sample_results()))
    for gone in ("Wat eraan komt", "Opmerkingen bij deze scan", "weegt ", "Samenvatting"):
        assert gone not in html, gone


def test_out_of_scope_checks_are_not_shown() -> None:
    v1 = res("V1.prompt_visibility", "fail", 0.0)
    html = render_html(make_report([*sample_results(), v1]))
    assert "V1." not in html and "Genoemd door AI-assistenten" not in html
    # discovery checks are back in scope (2026-11-10)
    assert "Organization / OnlineStore-markup" in html and "S6" in html


def test_every_in_scope_check_has_a_why_box() -> None:
    html = render_html(make_report(sample_results()))
    assert set(WHY) == set(IN_SCOPE)
    assert html.count("class='box why'") == len(IN_SCOPE)  # also for unmeasured checks
    for lang in ("nl", "en"):
        for check_id in IN_SCOPE:
            assert WHY[check_id][lang], (check_id, lang)


def test_fix_box_only_when_failing_or_warning() -> None:
    html = render_html(make_report(sample_results()))
    assert html.count("class='box guide'") == 5  # D1, S2, S4, S6, P3


def test_en_fallback_and_guidance_from_copy() -> None:
    html = render_html(make_report(sample_results()), lang="en")
    assert '<html lang="en">' in html and "Do first" in html and "Not ready" in html
    assert "AI crawlers allowed in robots.txt" in html
    assert "Why it matters" in html
    # guidance is re-read from checks/copy in the report language
    assert "Allow AI search and assistant bots" in html


def test_agent_checkout_is_never_claimed_live() -> None:
    for lang in ("nl", "en"):
        text = text_of(render_html(make_report(sample_results()), lang=lang)).lower()
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
    assert "+ 7 bevindingen meer in de technische bijlage" in html
    assert "report.json" not in html  # customers do not get the JSON file


def test_unmeasured_check_shows_one_evidence_line() -> None:
    ev = [Evidence(detail="first reason"), Evidence(detail="second line")]
    html = render_html(make_report([res("C1.add_to_cart", "not_applicable", 0.0, ev)]))
    assert "first reason" in html and "second line" not in html


def test_low_coverage_report_says_so() -> None:
    rs = [res("D1.robots_ai_crawlers", "pass", 1.0), res("C5.policies_clear", "pass", 1.0)]
    html = render_html(make_report(rs))
    assert "Te weinig gemeten voor een oordeel" in html and "voorlopig" in html
    assert "Klaar" not in text_of(html).replace("Klaar voor AI-shoppingagents", "")


def test_no_score_report_renders() -> None:
    html = render_html(make_report([res("D5.merchant_center", "not_applicable", 0.0)]))
    assert "Geen score" in html


def test_methodology_reflects_checkout_test() -> None:
    on = render_html(make_report(sample_results(), checkout_tested=True))
    assert "anonieme winkelwagen" in on
    off = render_html(make_report(sample_results()))
    assert "alleen met jouw toestemming" in off


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
    assert report.not_run == []  # V1 is out of scope, so never "not run"
    assert report.out_of_scope == []  # V1 only runs with --visibility
    assert [s.stage for s in report.stages] == ["access", "product_data", "checkout", "protocols"]
    assert render_html(report).endswith("</html>")


def test_cli_report_rescores_saved_json(tmp_path: Path) -> None:
    old = make_report(sample_results()).model_copy(
        update={"score": 12.0, "grade": None, "top_fixes": [], "stages": []}
    )  # as scored by an older version
    path = tmp_path / "report.json"
    path.write_text(old.model_dump_json(), encoding="utf-8")
    out = CliRunner().invoke(app, ["report", str(path), "--lang", "en"])
    assert out.exit_code == 0, out.output
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "52.9" in html and "Not ready" in html and "Do first" in html


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


def test_english_is_the_default_language() -> None:
    assert ScanOptions().lang == "en"
    report = make_report(sample_results()).model_copy(update={"lang": "en"})
    html = render_html(report)
    assert '<html lang="en">' in html and "Ready for AI shopping agents?" in html
    assert "Why it matters" in html and "How to fix" in html


def test_unmeasured_checks_get_plain_language_reasons() -> None:
    probe_off = Evidence(
        detail="Not tested: checkout probe not enabled (opt-in: --checkout when you have "
        "permission to test this shop, --checkout-consent when the merchant asked)"
    )
    gmc = Evidence(detail="No Merchant Center input provided (manual input; never guessed)")
    rs = [
        *sample_results(),
        res("C4.captcha_checkout", "not_applicable", 0.0, [probe_off]),
        res("D5.merchant_center", "not_applicable", 0.0, [gmc]),
    ]
    html = render_html(make_report(rs).model_copy(update={"lang": "en"}))
    assert "--checkout" not in html and "opt-in" not in html  # no operator CLI text
    assert "We only run the checkout test with your permission" in html
    assert "This needs data from your Google Merchant Center" in html


def test_platform_shown_by_name() -> None:
    html = render_html(make_report(sample_results()).model_copy(update={"lang": "en"}))
    assert "Platform: WooCommerce" in html
    other = make_report(sample_results()).model_copy(
        update={"lang": "en", "platform": PlatformInfo(platform="other")}
    )
    assert "Platform: custom or other" in render_html(other)


def test_customer_report_has_snapshot_note() -> None:
    html = render_html(make_report(sample_results()).model_copy(update={"lang": "en"}))
    assert "This is a snapshot from 2026-11-10" in html


def test_internal_probe_lines_are_not_shown() -> None:
    ev = [
        Evidence(detail="Bot challenge before the cart"),
        Evidence(
            url="https://shop.example.nl/p",
            detail="product: blocked - captcha",
            snippet="checkout_00_challenge.png",
        ),
        Evidence(detail="safety_guard: blocked - 11 request(s) blocked: POST /wp-admin/x"),
    ]
    html = render_html(make_report([*sample_results(), res("C1.add_to_cart", "fail", 0.0, ev)]))
    assert "safety_guard" not in html and "checkout_00_challenge.png" not in html
    assert "Bot challenge before the cart" in html

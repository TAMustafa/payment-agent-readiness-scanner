"""Scoring and top fixes (SPEC §5)."""

from __future__ import annotations

import pytest

from scanner.checks.registry import REGISTRY
from scanner.models import CheckResult, CheckStatus, Evidence
from scanner.report.scoring import (
    category_scores,
    grade_for,
    overall_score,
    summarise,
    top_fixes,
)


def res(check_id: str, status: CheckStatus, fraction: float) -> CheckResult:
    spec = REGISTRY[check_id]
    return CheckResult(
        id=spec.id,
        category=spec.category,
        label=spec.label,
        status=status,
        weight=spec.weight,
        score_fraction=fraction,
        evidence=[Evidence(detail="test")],
        guidance="" if status == "pass" else f"fix {check_id}",
        effort=spec.effort,
    )


def all_pass() -> list[CheckResult]:
    return [res(i, "pass", 1.0) for i in REGISTRY]


def test_all_pass_is_100_ready() -> None:
    s = summarise(all_pass())
    assert s.score == 100.0 and s.grade == "Ready"
    assert s.excluded_checks == 0 and s.not_run == [] and s.top_fixes == []


def test_weighted_partial_credit() -> None:
    # D1 (10) full, S2 (8) half, P1 (5) zero -> (10 + 4 + 0) / 23
    rs = [
        res("D1.robots_ai_crawlers", "pass", 1.0),
        res("S2.offer", "warn", 0.5),
        res("P1.ucp_profile", "fail", 0.0),
    ]
    assert overall_score(rs) == pytest.approx(round(100 * 14 / 23, 1))


def test_excluded_checks_are_renormalised_away() -> None:
    rs = [
        res("D1.robots_ai_crawlers", "pass", 1.0),
        res("D2.edge_blocking", "error", 0.0),  # blocked/unverifiable -> never a fail
        res("S5.reviews", "not_applicable", 0.0),
    ]
    s = summarise(rs)
    assert s.score == 100.0
    assert s.excluded_checks == 2
    assert "V1.prompt_visibility" in s.not_run and "D1.robots_ai_crawlers" not in s.not_run


def test_nothing_scorable_gives_no_score() -> None:
    s = summarise([res("D5.merchant_center", "not_applicable", 0.0)])
    assert s.score is None and s.grade is None
    assert summarise([]).score is None


@pytest.mark.parametrize(
    ("score", "grade"),
    [
        (100.0, "Ready"),
        (80.0, "Ready"),
        (79.9, "Partly ready"),
        (60.0, "Partly ready"),
        (59.9, "Not ready"),
        (0.0, "Not ready"),
    ],
)
def test_grade_boundaries(score: float, grade: str) -> None:
    assert grade_for(score) == grade


def test_top_fixes_order_by_points_over_effort() -> None:
    rs = [
        res("D1.robots_ai_crawlers", "fail", 0.0),  # 10 / S1 = 10
        res("S2.offer", "fail", 0.0),  # 8 / M2 = 4
        res("P1.ucp_profile", "fail", 0.0),  # 5 / L3 = 1.67
        res("D3.sitemap", "warn", 0.5),  # 2.5 / S1 = 2.5
        res("S6.organization", "fail", 0.0),  # 3 / S1 = 3
        res("C5.policies_clear", "fail", 0.0),  # 2 / S1 = 2
        res("S1.product_jsonld", "pass", 1.0),
    ]
    fixes = top_fixes(rs)
    assert [f.check_id for f in fixes] == [
        "D1.robots_ai_crawlers",
        "S2.offer",
        "S6.organization",
        "D3.sitemap",
        "C5.policies_clear",
    ]
    assert [f.rank for f in fixes] == [1, 2, 3, 4, 5]
    assert fixes[0].priority == 10.0 and fixes[0].points_available == 10.0
    assert fixes[0].guidance == "fix D1.robots_ai_crawlers"
    # re-normalised over the 39 scorable weight points: fixing D1 adds 10/39 of 100
    assert fixes[0].score_gain == round(100 * 10 / 39, 1)


def test_top_fixes_skip_excluded_and_full_credit_warnings() -> None:
    rs = [
        res("D1.robots_ai_crawlers", "warn", 1.0),  # training bots blocked: no points to gain
        res("D2.edge_blocking", "error", 0.0),  # unverifiable is not a fix
        res("S5.reviews", "not_applicable", 0.0),
        res("P3.mcp_or_feed_endpoint", "warn", 0.0),
    ]
    assert [f.check_id for f in top_fixes(rs)] == ["P3.mcp_or_feed_endpoint"]


def test_top_fixes_tie_break_is_deterministic() -> None:
    # S3 (6, M) and S1 (6, M) both 3.0 -> same weight -> by id
    rs = [res("S3.identifiers", "fail", 0.0), res("S1.product_jsonld", "fail", 0.0)]
    assert [f.check_id for f in top_fixes(rs)] == ["S1.product_jsonld", "S3.identifiers"]


def test_category_scores() -> None:
    rs = [
        res("D1.robots_ai_crawlers", "pass", 1.0),
        res("D2.edge_blocking", "fail", 0.0),
        res("D5.merchant_center", "not_applicable", 0.0),
    ]
    cats = {c.category: c for c in category_scores(rs)}
    d = cats["discovery"]
    assert d.score == pytest.approx(round(100 * 10 / 18, 1))
    assert d.scorable_weight == 18 and d.total_weight == 30
    assert d.excluded == ["D3.sitemap", "D4.rendering", "D5.merchant_center"]
    assert cats["visibility"].score is None and cats["visibility"].total_weight == 10
    assert [c.category for c in category_scores(rs)] == [
        "discovery",
        "data",
        "checkout",
        "protocol",
        "visibility",
    ]

"""Scoring and top fixes (SPEC §5), scoped to readiness for agent orders."""

from __future__ import annotations

import pytest

from scanner.checks.registry import REGISTRY
from scanner.models import CheckResult, CheckStatus, Evidence
from scanner.report.scoring import (
    IN_SCOPE,
    STAGES,
    grade_for,
    overall_score,
    stage_scores,
    summarise,
    top_fixes,
)

OUT_OF_SCOPE = {"V1.prompt_visibility"}


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


def test_scope_covers_every_check_once() -> None:
    assert len(IN_SCOPE) == len(set(IN_SCOPE)) == 19
    assert set(IN_SCOPE) | OUT_OF_SCOPE == set(REGISTRY)
    assert not set(IN_SCOPE) & OUT_OF_SCOPE
    assert [s for s, _ in STAGES] == ["access", "product_data", "checkout", "protocols"]


def test_all_pass_is_100_ready() -> None:
    s = summarise(all_pass())
    assert s.score == 100.0 and s.grade == "Ready"
    assert s.excluded_checks == 0 and s.not_run == [] and s.top_fixes == []
    assert s.out_of_scope == sorted(OUT_OF_SCOPE)


def test_out_of_scope_checks_never_count() -> None:
    rs = [res("D1.robots_ai_crawlers", "pass", 1.0)] + [res(i, "fail", 0.0) for i in OUT_OF_SCOPE]
    s = summarise(rs)
    assert s.score == 100.0
    assert s.top_fixes == []  # a failing sitemap or V1 is not an agent-order fix
    assert s.excluded_checks == 0


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
        res("C1.add_to_cart", "not_applicable", 0.0),
    ]
    s = summarise(rs)
    assert s.score == 100.0
    assert s.excluded_checks == 2
    assert "S2.offer" in s.not_run and "D1.robots_ai_crawlers" not in s.not_run
    assert "V1.prompt_visibility" not in s.not_run  # out of scope is never "not run"


def test_low_coverage_gives_no_grade() -> None:
    # 25 of 90 weight measured (like stoov.com with 0 product pages): score, but no grade
    rs = [
        res("D1.robots_ai_crawlers", "pass", 1.0),
        res("D2.edge_blocking", "pass", 1.0),
        res("D4.rendering", "error", 0.0),
        res("P1.ucp_profile", "pass", 1.0),
        res("C5.policies_clear", "fail", 0.0),
    ]
    s = summarise(rs)
    assert s.coverage == round(25 / 90, 3)
    assert s.score == round(100 * 23 / 25, 1) and s.grade is None
    rs.append(res("S2.offer", "pass", 1.0))
    rs.append(res("S1.product_jsonld", "pass", 1.0))
    rs.append(res("S3.identifiers", "pass", 1.0))  # 25 + 20 = 45 of 90 = 50 %
    s2 = summarise(rs)
    assert s2.coverage == 0.5
    # 50 % overall, but the checkout stage (1 of 20 weight) is unmeasured -> no overall grade
    assert s2.grade is None
    parts = {p.part: p for p in s2.parts}
    assert parts["find"].grade == "Ready"  # access 17/27, product data 20/33: both >= 50 %
    assert parts["buy"].grade is None and parts["buy"].unmeasured_stages == ["checkout"]
    rs += [res(i, "pass", 1.0) for i in ("C1.add_to_cart", "C2.guest_checkout")]
    s3 = summarise(rs)
    assert {p.part: p.grade for p in s3.parts} == {"find": "Ready", "buy": "Ready"}
    assert s3.grade == "Ready"


def test_stage_needs_half_its_weight_for_a_score() -> None:
    # A default scan: only C3 + C5 (6 of 20) measured used to show "Check out: 100".
    rs = [res("C3.payment_methods", "pass", 1.0), res("C5.policies_clear", "pass", 1.0)]
    checkout = {s.stage: s for s in stage_scores(rs)}["checkout"]
    assert checkout.score is None and checkout.scorable_weight == 6
    rs.append(res("C2.guest_checkout", "fail", 0.0))  # 12 of 20
    checkout = {s.stage: s for s in stage_scores(rs)}["checkout"]
    assert checkout.score == 50.0


def test_buy_verdict_weighs_payments_on_their_own() -> None:
    # Discovery perfect, checkout and protocols poor: overall looks fine, "buy" does not.
    rs = [res(i, "pass", 1.0) for _, ids in STAGES[:2] for i in ids]
    rs += [res(i, "fail", 0.0) for _, ids in STAGES[2:] for i in ids]
    s = summarise(rs)
    parts = {p.part: p for p in s.parts}
    assert parts["find"].score == 100.0 and parts["find"].grade == "Ready"
    assert parts["buy"].score == 0.0 and parts["buy"].grade == "Not ready"
    assert s.score == round(100 * 60 / 90, 1) and s.grade == "Partly ready"


def test_ucp_dependent_fixes_are_folded_into_p1() -> None:
    rs = [
        res("P1.ucp_profile", "fail", 0.0),  # 5
        res("P2.platform_support", "warn", 0.5),  # 1.5, follows from P1
        res("P3.mcp_or_feed_endpoint", "warn", 0.0),  # 2, follows from P1
        res("S4.shipping_returns", "fail", 0.0),
    ]
    fixes = top_fixes(rs)
    assert [f.check_id for f in fixes] == ["P1.ucp_profile", "S4.shipping_returns"]
    p1 = fixes[0]
    assert p1.also_fixes == ["P2.platform_support", "P3.mcp_or_feed_endpoint"]
    assert p1.points_available == 8.5 and p1.priority == round(8.5 / 3, 2)
    # Without a failing P1 (e.g. profile blocked -> error), P3 is a fix of its own.
    rs[0] = res("P1.ucp_profile", "error", 0.0)
    assert "P3.mcp_or_feed_endpoint" in [f.check_id for f in top_fixes(rs)]


def test_nothing_scorable_gives_no_score() -> None:
    s = summarise([res("D5.merchant_center", "not_applicable", 0.0)])
    assert s.score is None and s.grade is None
    assert summarise([]).score is None
    assert summarise([res("V1.prompt_visibility", "pass", 1.0)]).score is None


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
        res("C3.payment_methods", "fail", 0.0),  # 4 / S1 = 4 (lower weight than S2)
        res("P1.ucp_profile", "fail", 0.0),  # 5 / L3 = 1.67
        res("C5.policies_clear", "warn", 0.5),  # 1 / S1 = 1
        res("S4.shipping_returns", "fail", 0.0),  # 5 / M2 = 2.5
        res("S1.product_jsonld", "pass", 1.0),
    ]
    fixes = top_fixes(rs)
    assert [f.check_id for f in fixes] == [
        "D1.robots_ai_crawlers",
        "S2.offer",
        "C3.payment_methods",
        "S4.shipping_returns",
        "P1.ucp_profile",
    ]
    assert [f.rank for f in fixes] == [1, 2, 3, 4, 5]
    assert fixes[0].priority == 10.0 and fixes[0].points_available == 10.0
    assert fixes[0].guidance == "fix D1.robots_ai_crawlers"
    # re-normalised over the 40 scorable weight points: fixing D1 adds 10/40 of 100
    assert fixes[0].score_gain == 25.0


def test_top_fixes_skip_excluded_and_full_credit_warnings() -> None:
    rs = [
        res("D1.robots_ai_crawlers", "warn", 1.0),  # training bots blocked: no points to gain
        res("D2.edge_blocking", "error", 0.0),  # unverifiable is not a fix
        res("C2.guest_checkout", "not_applicable", 0.0),
        res("P3.mcp_or_feed_endpoint", "warn", 0.0),
    ]
    assert [f.check_id for f in top_fixes(rs)] == ["P3.mcp_or_feed_endpoint"]


def test_top_fixes_tie_break_is_deterministic() -> None:
    # S3 (6, M) and S1 (6, M) both 3.0 -> same weight -> by id
    rs = [res("S3.identifiers", "fail", 0.0), res("S1.product_jsonld", "fail", 0.0)]
    assert [f.check_id for f in top_fixes(rs)] == ["S1.product_jsonld", "S3.identifiers"]


def test_stage_scores() -> None:
    rs = [
        res("D1.robots_ai_crawlers", "pass", 1.0),
        res("D2.edge_blocking", "fail", 0.0),
        res("D5.merchant_center", "not_applicable", 0.0),
        res("D3.sitemap", "fail", 0.0),  # discovery: part of stage 1 since 2026-11-10
    ]
    stages = {s.stage: s for s in stage_scores(rs)}
    access = stages["access"]
    assert access.score == pytest.approx(round(100 * 10 / 23, 1))
    assert access.scorable_weight == 23 and access.total_weight == 27
    assert access.excluded == ["D4.rendering"]
    data = stages["product_data"]
    assert data.score is None and data.total_weight == 33
    assert "D5.merchant_center" in data.excluded
    assert sum(s.total_weight for s in stages.values()) == 90

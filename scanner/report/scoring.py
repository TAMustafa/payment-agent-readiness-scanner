"""Scoring and top fixes (SPEC §5). Pure functions over check results — no I/O.

Scope (Tarek, 2026-11-10): the report measures how ready a merchant is to be found by AI
agents and to accept their orders and payments. The in-scope checks are grouped in four
stages (`STAGES`). D3, S5, S6 were briefly out of scope and are back for merchant discovery.
Only V1 (paid AI-visibility snapshot) is out of scope: it runs on request, stays in
report.json, is not scored, not shown in the HTML and never a fix.

- Score = sum(weight x score_fraction) over in-scope checks that are not
  `not_applicable` / `error`, re-normalised to 100. In-scope checks without a result are
  "not run" and not counted either.
- Grade: >= 80 Ready, 60-79 Partly ready, < 60 Not ready (on the rounded score) — only when
  at least MIN_COVERAGE of the in-scope weight was measured. Below that (e.g. a Shopify shop
  that rate-limits product sampling) the score is provisional and there is no grade.
- Top fixes: failing/warning in-scope checks sorted by (weight x (1 - score_fraction)) /
  effort factor (S=1, M=2, L=3). A warning with full credit (e.g. D1 "training bots
  blocked", the merchant's own choice) adds no points and is not a fix.
"""

from __future__ import annotations

from dataclasses import dataclass

from scanner.checks.registry import REGISTRY
from scanner.models import CheckResult, Effort, Fix, Grade, StageScore

EXCLUDED_STATUSES = ("not_applicable", "error")
EFFORT_FACTOR: dict[Effort, int] = {"S": 1, "M": 2, "L": 3}
READY_AT = 80.0
PARTLY_AT = 60.0
TOP_N = 5
MIN_COVERAGE = 0.5  # share of in-scope weight that must be measured for a grade

# The four steps of an agent order, in order. Weights come from the registry (SPEC §4).
STAGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Can an agent find the shop's products, reach the shop and read its pages?
    (
        "access",
        ("D1.robots_ai_crawlers", "D2.edge_blocking", "D3.sitemap", "D4.rendering"),
    ),
    # Can an agent tell exactly what is sold, for how much, delivered how, and by whom?
    (
        "product_data",
        (
            "S1.product_jsonld",
            "S2.offer",
            "S3.identifiers",
            "S4.shipping_returns",
            "S5.reviews",
            "S6.organization",
            "D5.merchant_center",
        ),
    ),
    # Can a browser agent get from product to checkout and pay in a Dutch way?
    (
        "checkout",
        (
            "C1.add_to_cart",
            "C2.guest_checkout",
            "C3.payment_methods",
            "C4.captcha_checkout",
            "C5.policies_clear",
        ),
    ),
    # Is the shop connected (or connectable) to agent protocols for direct orders?
    ("protocols", ("P1.ucp_profile", "P2.platform_support", "P3.mcp_or_feed_endpoint")),
)
IN_SCOPE: tuple[str, ...] = tuple(i for _, ids in STAGES for i in ids)


@dataclass(frozen=True)
class ScoreSummary:
    score: float | None
    grade: Grade | None
    coverage: float  # measured share of in-scope weight, 0..1
    excluded_checks: int
    not_run: list[str]
    stages: list[StageScore]
    top_fixes: list[Fix]
    out_of_scope: list[str]


def scorable(r: CheckResult) -> bool:
    return r.status not in EXCLUDED_STATUSES


def in_scope(results: list[CheckResult]) -> list[CheckResult]:
    return [r for r in results if r.id in IN_SCOPE]


def grade_for(score: float | None) -> Grade | None:
    if score is None:
        return None
    if score >= READY_AT:
        return "Ready"
    if score >= PARTLY_AT:
        return "Partly ready"
    return "Not ready"


def overall_score(results: list[CheckResult]) -> float | None:
    used = [r for r in in_scope(results) if scorable(r)]
    weight = sum(r.weight for r in used)
    if weight == 0:
        return None
    return round(100 * sum(r.weight * r.score_fraction for r in used) / weight, 1)


def stage_scores(results: list[CheckResult]) -> list[StageScore]:
    by_id = {r.id: r for r in results}
    out: list[StageScore] = []
    for stage, ids in STAGES:
        used = [by_id[i] for i in ids if i in by_id and scorable(by_id[i])]
        earned = sum(r.weight * r.score_fraction for r in used)
        weight = sum(r.weight for r in used)
        out.append(
            StageScore(
                stage=stage,
                score=round(100 * earned / weight, 1) if weight else None,
                earned=round(earned, 2),
                scorable_weight=weight,
                total_weight=sum(REGISTRY[i].weight for i in ids),
                check_ids=list(ids),
                excluded=[i for i in ids if i not in by_id or not scorable(by_id[i])],
            )
        )
    return out


def coverage(results: list[CheckResult]) -> float:
    total = sum(REGISTRY[i].weight for i in IN_SCOPE)
    measured = sum(r.weight for r in in_scope(results) if scorable(r))
    return round(measured / total, 3)


def points_available(r: CheckResult) -> float:
    return r.weight * (1.0 - r.score_fraction)


def top_fixes(results: list[CheckResult], n: int = TOP_N) -> list[Fix]:
    scoped = in_scope(results)
    candidates = [r for r in scoped if r.status in ("fail", "warn") and points_available(r) > 1e-9]

    def priority(r: CheckResult) -> float:
        return points_available(r) / EFFORT_FACTOR[r.effort]

    # Ties: bigger check first, then stable by id so reports are reproducible.
    ranked = sorted(candidates, key=lambda r: (-priority(r), -r.weight, r.id))[:n]
    scorable_weight = sum(r.weight for r in scoped if scorable(r))
    return [
        Fix(
            rank=i,
            check_id=r.id,
            label=r.label,
            status=r.status,
            priority=round(priority(r), 2),
            points_available=round(points_available(r), 2),
            score_gain=round(100 * points_available(r) / scorable_weight, 1),
            effort=r.effort,
            guidance=r.guidance,
        )
        for i, r in enumerate(ranked, start=1)
    ]


def summarise(results: list[CheckResult]) -> ScoreSummary:
    seen = {r.id for r in results}
    score = overall_score(results)
    cov = coverage(results)
    return ScoreSummary(
        score=score,
        grade=grade_for(score) if cov >= MIN_COVERAGE else None,
        coverage=cov,
        excluded_checks=sum(not scorable(r) for r in in_scope(results)),
        not_run=[i for i in IN_SCOPE if i not in seen],
        stages=stage_scores(results),
        top_fixes=top_fixes(results),
        out_of_scope=sorted(r.id for r in results if r.id not in IN_SCOPE),
    )

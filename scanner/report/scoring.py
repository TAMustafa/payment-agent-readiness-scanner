"""Scoring and top fixes (SPEC §5). Pure functions over check results — no I/O.

- Score = sum(weight x score_fraction) over checks that are not `not_applicable` / `error`,
  re-normalised to 100. Checks without a result (not selected, V1 without --visibility)
  are listed as "not run" and are not counted either.
- Grade: >= 80 Ready, 60-79 Partly ready, < 60 Not ready (on the rounded score).
- Top fixes: failing/warning checks sorted by (weight x (1 - score_fraction)) / effort
  factor (S=1, M=2, L=3). A warning with full credit (e.g. D1 "training bots blocked",
  the merchant's own choice) adds no points and is not a fix.
"""

from __future__ import annotations

from dataclasses import dataclass

from scanner.checks.registry import REGISTRY
from scanner.models import Category, CategoryScore, CheckResult, Effort, Fix, Grade

EXCLUDED_STATUSES = ("not_applicable", "error")
EFFORT_FACTOR: dict[Effort, int] = {"S": 1, "M": 2, "L": 3}
CATEGORY_ORDER: tuple[Category, ...] = ("discovery", "data", "checkout", "protocol", "visibility")
READY_AT = 80.0
PARTLY_AT = 60.0
TOP_N = 5


@dataclass(frozen=True)
class ScoreSummary:
    score: float | None
    grade: Grade | None
    excluded_checks: int
    not_run: list[str]
    categories: list[CategoryScore]
    top_fixes: list[Fix]


def scorable(r: CheckResult) -> bool:
    return r.status not in EXCLUDED_STATUSES


def grade_for(score: float | None) -> Grade | None:
    if score is None:
        return None
    if score >= READY_AT:
        return "Ready"
    if score >= PARTLY_AT:
        return "Partly ready"
    return "Not ready"


def overall_score(results: list[CheckResult]) -> float | None:
    used = [r for r in results if scorable(r)]
    weight = sum(r.weight for r in used)
    if weight == 0:
        return None
    return round(100 * sum(r.weight * r.score_fraction for r in used) / weight, 1)


def category_scores(results: list[CheckResult]) -> list[CategoryScore]:
    by_id = {r.id: r for r in results}
    out: list[CategoryScore] = []
    for cat in CATEGORY_ORDER:
        specs = [s for s in REGISTRY.values() if s.category == cat]
        used = [by_id[s.id] for s in specs if s.id in by_id and scorable(by_id[s.id])]
        earned = sum(r.weight * r.score_fraction for r in used)
        weight = sum(r.weight for r in used)
        out.append(
            CategoryScore(
                category=cat,
                score=round(100 * earned / weight, 1) if weight else None,
                earned=round(earned, 2),
                scorable_weight=weight,
                total_weight=sum(s.weight for s in specs),
                excluded=[s.id for s in specs if s.id not in by_id or not scorable(by_id[s.id])],
            )
        )
    return out


def points_available(r: CheckResult) -> float:
    return r.weight * (1.0 - r.score_fraction)


def top_fixes(results: list[CheckResult], n: int = TOP_N) -> list[Fix]:
    candidates = [r for r in results if r.status in ("fail", "warn") and points_available(r) > 1e-9]

    def priority(r: CheckResult) -> float:
        return points_available(r) / EFFORT_FACTOR[r.effort]

    # Ties: bigger check first, then stable by id so reports are reproducible.
    ranked = sorted(candidates, key=lambda r: (-priority(r), -r.weight, r.id))[:n]
    scorable_weight = sum(r.weight for r in results if scorable(r))
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
    return ScoreSummary(
        score=score,
        grade=grade_for(score),
        excluded_checks=sum(not scorable(r) for r in results),
        not_run=[i for i in REGISTRY if i not in seen],
        categories=category_scores(results),
        top_fixes=top_fixes(results),
    )

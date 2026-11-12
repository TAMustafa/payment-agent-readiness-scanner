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
- Stage minimum (2026-11-12): a stage gets no score when less than STAGE_MIN_COVERAGE of its
  weight was measured (a default scan measured 2 of 5 checkout checks and showed "100").
- Two verdicts (2026-11-12, `PARTS`): "find" (stages 1-2: can agents find and understand
  the shop?) and "buy" (stages 3-4: can agents order and pay?). Each is scored over its own
  checks, so payments are not drowned out by the larger discovery weight, and graded only
  when every one of its stages has a score. "buy" therefore needs the checkout test. The
  overall grade needs both verdicts graded; the overall score stays in report.json.
- Top fixes: failing/warning in-scope checks sorted by (weight x (1 - score_fraction)) /
  effort factor (S=1, M=2, L=3). Checks that follow from another fix (`FOLLOWS`: P2 and P3
  pass once a valid UCP profile is live) are folded into that fix (`also_fixes`) instead of
  taking their own slots. A warning with full credit (e.g. D1 "training bots
  blocked", the merchant's own choice) adds no points and is not a fix.
"""

from __future__ import annotations

from dataclasses import dataclass

from scanner.checks.registry import REGISTRY
from scanner.models import CheckResult, Effort, Fix, Grade, PartScore, StageScore

EXCLUDED_STATUSES = ("not_applicable", "error")
EFFORT_FACTOR: dict[Effort, int] = {"S": 1, "M": 2, "L": 3}
READY_AT = 80.0
PARTLY_AT = 60.0
TOP_N = 5
MIN_COVERAGE = 0.5  # share of in-scope weight that must be measured for a grade
STAGE_MIN_COVERAGE = 0.5  # share of a stage's weight that must be measured for its score

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

# The two headline verdicts: can agents find the shop, and can they order and pay?
PARTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("find", ("access", "product_data")),
    ("buy", ("checkout", "protocols")),
)

# check id -> the check whose fix also fixes it. P2 is "enabled" exactly when a valid UCP
# profile is live; the agentic-commerce plugins that publish the profile also declare the
# MCP service P3 looks for (Shopify /api/ucp/mcp, Shopware SwagAgenticCommerce).
FOLLOWS: dict[str, str] = {
    "P2.platform_support": "P1.ucp_profile",
    "P3.mcp_or_feed_endpoint": "P1.ucp_profile",
}


@dataclass(frozen=True)
class ScoreSummary:
    score: float | None
    grade: Grade | None
    coverage: float  # measured share of in-scope weight, 0..1
    excluded_checks: int
    not_run: list[str]
    stages: list[StageScore]
    parts: list[PartScore]
    top_fixes: list[Fix]
    out_of_scope: list[str]

    def report_fields(self) -> dict[str, object]:
        """The ScanReport fields this summary fills (graph node and `scanner report`)."""
        return {
            "score": self.score,
            "grade": self.grade,
            "coverage": self.coverage,
            "excluded_checks": self.excluded_checks,
            "not_run": self.not_run,
            "stages": self.stages,
            "parts": self.parts,
            "out_of_scope": self.out_of_scope,
            "top_fixes": self.top_fixes,
        }


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
        total = sum(REGISTRY[i].weight for i in ids)
        enough = weight > 0 and weight >= STAGE_MIN_COVERAGE * total
        out.append(
            StageScore(
                stage=stage,
                score=round(100 * earned / weight, 1) if enough else None,
                earned=round(earned, 2),
                scorable_weight=weight,
                total_weight=total,
                check_ids=list(ids),
                excluded=[i for i in ids if i not in by_id or not scorable(by_id[i])],
            )
        )
    return out


def part_scores(stages: list[StageScore]) -> list[PartScore]:
    by_stage = {s.stage: s for s in stages}
    out: list[PartScore] = []
    for part, names in PARTS:
        parts = [by_stage[n] for n in names]
        earned = sum(s.earned for s in parts)
        weight = sum(s.scorable_weight for s in parts)
        total = sum(s.total_weight for s in parts)
        score = round(100 * earned / weight, 1) if weight else None
        cov = round(weight / total, 3) if total else 0.0
        unmeasured = [s.stage for s in parts if s.score is None]
        graded = score is not None and cov >= MIN_COVERAGE and not unmeasured
        out.append(
            PartScore(
                part=part,
                score=score,
                grade=grade_for(score) if graded else None,
                coverage=cov,
                stages=list(names),
                unmeasured_stages=unmeasured,
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
    candidates = {
        r.id: r for r in scoped if r.status in ("fail", "warn") and points_available(r) > 1e-9
    }
    # Fold checks that follow from another candidate fix into that fix.
    folded: dict[str, list[CheckResult]] = {}
    for cid, parent in FOLLOWS.items():
        if cid in candidates and parent in candidates:
            folded.setdefault(parent, []).append(candidates.pop(cid))

    def points(r: CheckResult) -> float:
        return points_available(r) + sum(points_available(f) for f in folded.get(r.id, []))

    def priority(r: CheckResult) -> float:
        return points(r) / EFFORT_FACTOR[r.effort]

    # Ties: bigger check first, then stable by id so reports are reproducible.
    ranked = sorted(candidates.values(), key=lambda r: (-priority(r), -r.weight, r.id))[:n]
    scorable_weight = sum(r.weight for r in scoped if scorable(r))
    return [
        Fix(
            rank=i,
            check_id=r.id,
            label=r.label,
            status=r.status,
            priority=round(priority(r), 2),
            points_available=round(points(r), 2),
            score_gain=round(100 * points(r) / scorable_weight, 1),
            effort=r.effort,
            guidance=r.guidance,
            also_fixes=sorted(f.id for f in folded.get(r.id, [])),
        )
        for i, r in enumerate(ranked, start=1)
    ]


def summarise(results: list[CheckResult]) -> ScoreSummary:
    seen = {r.id for r in results}
    score = overall_score(results)
    cov = coverage(results)
    stages = stage_scores(results)
    parts = part_scores(stages)
    graded = cov >= MIN_COVERAGE and all(p.grade is not None for p in parts)
    return ScoreSummary(
        score=score,
        grade=grade_for(score) if graded else None,
        coverage=cov,
        excluded_checks=sum(not scorable(r) for r in in_scope(results)),
        not_run=[i for i in IN_SCOPE if i not in seen],
        stages=stages,
        parts=parts,
        top_fixes=top_fixes(results),
        out_of_scope=sorted(r.id for r in results if r.id not in IN_SCOPE),
    )

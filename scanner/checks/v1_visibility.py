"""V1.prompt_visibility — shop mentioned by AI assistants with web search (SPEC §4 V).

Built from the visibility subgraph's calls (not part of the check fan-out). Score = mention
rate over all successful calls, both runs. Status thresholds are an initial choice, to be
confirmed with Tarek: pass >= 0.6, warn >= 0.3, fail below. Always labelled as a snapshot.
"""

from __future__ import annotations

from scanner.checks.base import result
from scanner.models import CheckResult, CheckStatus, Evidence, ScanContext, VisibilityResult

CHECK_ID = "V1.prompt_visibility"
PASS_AT = 0.6
WARN_AT = 0.3
SNAPSHOT = (
    "Snapshot: AI answers vary between runs and over time. Asked via OpenRouter with each "
    "assistant's own web search; not identical to the consumer apps."
)


def _rate(calls: list[object]) -> str:
    ok = [c for c in calls if getattr(c, "error", None) is None]
    hit = sum(1 for c in ok if getattr(c, "mentioned", False))
    return f"{hit}/{len(ok)}" if ok else "0/0"


def build(ctx: ScanContext, vis: VisibilityResult) -> CheckResult:
    cost = (
        f"Cost this scan USD {vis.total_cost_usd:.3f} (estimate USD {vis.estimate_usd:.2f}); "
        f"month to date USD {vis.month_to_date_usd:.2f} of USD {vis.monthly_cap_usd:.2f} cap"
    )
    if vis.skipped_reason or not vis.calls:
        return result(
            CHECK_ID,
            ctx,
            "error",
            0.0,
            [
                Evidence(detail=f"Not run: {vis.skipped_reason or 'no calls made'}"),
                Evidence(detail=cost),
            ],
        )
    ok = [c for c in vis.calls if c.error is None]
    if not ok:
        first = vis.calls[0].error or "unknown"
        return result(
            CHECK_ID,
            ctx,
            "error",
            0.0,
            [
                Evidence(detail=f"All {len(vis.calls)} calls failed, e.g. {first}"),
                Evidence(detail=cost),
            ],
        )

    rate = sum(1 for c in ok if c.mentioned) / len(ok)
    status: CheckStatus = "pass" if rate >= PASS_AT else "warn" if rate >= WARN_AT else "fail"
    evidence = [
        Evidence(detail=f"Mentioned in {_rate(list(ok))} answers ({rate:.0%}). {SNAPSHOT}"),
        Evidence(
            detail=f"Brand questions: {_rate([c for c in ok if c.kind == 'brand'])}; "
            f"category questions: {_rate([c for c in ok if c.kind == 'category'])}; "
            f"custom: {_rate([c for c in ok if c.kind == 'custom'])}"
        ),
    ]
    for name in sorted({c.assistant for c in vis.calls}):
        for run in sorted({c.run for c in vis.calls}):
            group = [c for c in vis.calls if c.assistant == name and c.run == run]
            errors = sum(1 for c in group if c.error)
            evidence.append(
                Evidence(
                    detail=f"{name} run {run}: {_rate(list(group))} mentioned"
                    + (f", {errors} call(s) failed" if errors else "")
                )
            )
    evidence.append(Evidence(detail=cost))
    for c in vis.calls:
        if c.error:
            detail = f"[{c.assistant} r{c.run}] ERROR {c.error}"
        else:
            where = (
                f"cited #{c.position}"
                if c.cited
                else "named in text only"
                if c.mentioned_in_text
                else "not mentioned"
            )
            top = ", ".join(c.cited_domains[:3]) or "no citations"
            detail = f"[{c.assistant} r{c.run}] {where}; top cited: {top}"
        evidence.append(Evidence(url=c.cited_url, detail=detail, snippet=c.prompt))
    return result(CHECK_ID, ctx, status, round(rate, 4), evidence)

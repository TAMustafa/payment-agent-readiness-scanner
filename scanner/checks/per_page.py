"""Shared scoring for checks measured over sampled product pages (SPEC §4 category S).

Score = mean per-page score. Status from thresholds (pass >= pass_at, warn >= warn_at).
Every page contributes one evidence line so a human can verify each result.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from scanner.checks.base import result
from scanner.models import CheckResult, CheckStatus, Evidence, FetchedResource, ScanContext


@dataclass(frozen=True)
class PageScore:
    url: str
    score: float  # 0..1
    detail: str
    snippet: str | None = None


def no_products(check_id: str, ctx: ScanContext) -> CheckResult:
    why = "; ".join(n.detail for n in ctx.pages.notes if "Product" in n.detail) or "none sampled"
    return result(
        check_id,
        ctx,
        "error",
        0.0,
        [Evidence(detail=f"No product pages could be sampled, so this cannot be measured ({why})")],
    )


def score_pages(
    check_id: str,
    ctx: ScanContext,
    scorer: Callable[[FetchedResource], PageScore | None],
    *,
    pass_at: float = 0.9,
    warn_at: float = 0.5,
    extra: list[Evidence] | None = None,
) -> CheckResult:
    """`scorer` returns None for a page the check does not apply to."""
    pages = ctx.pages.products
    if not pages:
        return no_products(check_id, ctx)
    scores = [s for s in (scorer(p) for p in pages) if s is not None]
    if not scores:
        return result(
            check_id,
            ctx,
            "not_applicable",
            0.0,
            extra or [Evidence(detail="Not applicable to any sampled product page")],
        )
    mean = sum(s.score for s in scores) / len(scores)
    full = sum(1 for s in scores if s.score >= 0.999)
    status: CheckStatus = "pass" if mean >= pass_at else "warn" if mean >= warn_at else "fail"
    evidence = [
        Evidence(
            detail=f"{full}/{len(scores)} sampled product pages fully meet this "
            f"(average {mean:.0%})"
        )
    ]
    evidence += extra or []
    evidence += [Evidence(url=s.url, detail=s.detail, snippet=s.snippet) for s in scores]
    return result(check_id, ctx, status, mean, evidence)

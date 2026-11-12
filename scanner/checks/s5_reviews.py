"""S5.reviews — aggregateRating with ratingValue + reviewCount where reviews are shown.

Google requires ratingValue and at least one of ratingCount / reviewCount
(https://developers.google.com/search/docs/appearance/structured-data/review-snippet).
A page counts only if it has rating markup or visibly shows product reviews (heuristic:
"<n> reviews / beoordelingen / recensies" in the page text). No such page -> not_applicable.
The same "<n> reviews" text on two or more sampled product pages is a shop-wide widget
(Trustpilot, Kiyoh, ...), not product reviews, and is ignored (2026-11-12: stoov.com showed
"4.3 | 17,117 reviews" in the footer of every product page, S5 was a false fail).
"""

from __future__ import annotations

import re

from scanner.checks.copy import get_guidance
from scanner.checks.per_page import PageScore, score_pages
from scanner.models import CheckResult, Evidence, FetchedResource, ScanContext
from scanner.parse.product import first_dict, product_data, to_decimal, visible_text

CHECK_ID = "S5.reviews"
REVIEWS_SHOWN = re.compile(
    # count >= 1: "0 beoordelingen" means no reviews are shown
    r"\b[1-9][\d.]*\s*(reviews?|beoordelingen|beoordeling|recensies?|ervaringen)\b",
    re.I,
)


def review_mentions(page: FetchedResource) -> list[str]:
    """Normalised "<n> reviews" texts visible on the page."""
    text = visible_text(page.body or "")
    return [" ".join(m.group(0).lower().split()) for m in REVIEWS_SHOWN.finditer(text)]


def shop_wide_mentions(pages: list[FetchedResource]) -> set[str]:
    """Review counts that appear on two or more product pages: a shop-level widget."""
    counts: dict[str, int] = {}
    for p in pages:
        for m in set(review_mentions(p)):
            counts[m] = counts.get(m, 0) + 1
    return {m for m, n in counts.items() if n >= 2}


def score(page: FetchedResource, ignore: frozenset[str] = frozenset()) -> PageScore | None:
    html = page.body or ""
    d = product_data(html)
    rating = first_dict(d.product.get("aggregateRating")) if d.source else None
    shown = next((m for m in review_mentions(page) if m not in ignore), None)
    if rating is None:
        if not shown:
            return None  # no reviews shown, no markup: not applicable to this page
        return PageScore(
            page.url,
            0.0,
            "Reviews appear to be shown but no aggregateRating markup",
            snippet=shown,
        )
    value = rating.get("ratingValue")
    count = rating.get("reviewCount") or rating.get("ratingCount")
    if value and count:
        return PageScore(page.url, 1.0, f"aggregateRating {value} from {count}")
    missing = [n for n, v in (("ratingValue", value), ("reviewCount/ratingCount", count)) if not v]
    return PageScore(page.url, 0.5, f"aggregateRating missing {', '.join(missing)}")


def _rating_key(page: FetchedResource) -> tuple[str, float] | None:
    d = product_data(page.body or "")
    rating = first_dict(d.product.get("aggregateRating")) if d.source else None
    if not rating:
        return None
    count = to_decimal(rating.get("reviewCount") or rating.get("ratingCount"))
    return (str(rating.get("ratingValue")), float(count) if count is not None else 0.0)


def looks_like_shop_rating(keys: list[tuple[str, float]]) -> bool:
    """Same ratingValue everywhere and review counts within 1% (cached pages lag a little:
    observed 3916 vs 3919 on one shop, 2026-11-08)."""
    if len(keys) < 2 or len({v for v, _ in keys}) != 1:
        return False
    counts = [c for _, c in keys]
    return min(counts) > 0 and max(counts) <= min(counts) * 1.01


async def check(ctx: ScanContext) -> CheckResult:
    ignore = frozenset(shop_wide_mentions(ctx.pages.products))
    res = score_pages(CHECK_ID, ctx, lambda page: score(page, ignore))
    keys = [k for k in (_rating_key(p) for p in ctx.pages.products) if k]
    if looks_like_shop_rating(keys) and res.status == "pass":
        # Same rating on every product page = shop-level rating (e.g. a review widget)
        # put into product markup. Google: ratings must be about the item itself
        # (https://developers.google.com/search/docs/appearance/structured-data/review-snippet).
        value = keys[0][0]
        counts = sorted({int(c) for _, c in keys})
        res.evidence.insert(
            0,
            Evidence(
                detail=f"All {len(keys)} product pages carry the same rating {value} with "
                f"review counts {', '.join(map(str, counts))}: this looks like a shop rating, "
                "not product reviews.",
            ),
        )
        res.status = "warn"
        res.score_fraction = 0.5
        res.guidance = get_guidance(CHECK_ID, ctx.options.lang)
    return res

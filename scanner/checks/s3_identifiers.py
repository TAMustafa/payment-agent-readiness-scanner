"""S3.identifiers — GTIN, or MPN + brand. Pass when >= 80% of sampled pages have them.

Identifiers may sit on the Product, its variants (ProductGroup.hasVariant) or the Offer.
"""

from __future__ import annotations

from typing import Any

from scanner.checks.per_page import PageScore, score_pages
from scanner.models import CheckResult, FetchedResource, ScanContext
from scanner.parse.product import (
    GTIN_KEYS,
    offers_of,
    product_data,
    valid_gtin,
    variants_and_self,
)

CHECK_ID = "S3.identifiers"


def _brand_name(value: Any) -> str | None:
    if isinstance(value, dict):
        return str(value.get("name") or "") or None
    if isinstance(value, list):
        return next((n for n in (_brand_name(v) for v in value) if n), None)
    return str(value) if value else None


def score(page: FetchedResource) -> PageScore:
    d = product_data(page.body or "")
    if d.source is None:
        return PageScore(page.url, 0.0, "No Product structured data")
    nodes = variants_and_self(d.product) + offers_of(d.product)
    gtins = [(k, n[k]) for n in nodes for k in GTIN_KEYS if n.get(k)]
    good = [(k, v) for k, v in gtins if k == "isbn" or valid_gtin(v)]
    bad = [(k, v) for k, v in gtins if (k, v) not in good]
    gtin = f"{good[0][0]}={good[0][1]}" if good else None
    mpn = next((str(n["mpn"]) for n in nodes if n.get("mpn")), None)
    sku = next((str(n["sku"]) for n in nodes if n.get("sku")), None)
    brand = _brand_name(d.product.get("brand"))
    found = (
        ", ".join(
            x
            for x in (gtin, mpn and f"mpn={mpn}", sku and f"sku={sku}", brand and f"brand={brand}")
            if x
        )
        or "no identifiers"
    )
    ok = bool(gtin) or bool(mpn and brand)
    invalid = f" Invalid GTIN ignored: {bad[0][0]}={bad[0][1]}." if bad else ""
    return PageScore(
        page.url, 1.0 if ok else 0.0, f"{'OK' if ok else 'Missing'}: {found}.{invalid}"
    )


async def check(ctx: ScanContext) -> CheckResult:
    return score_pages(CHECK_ID, ctx, score, pass_at=0.8, warn_at=0.4)

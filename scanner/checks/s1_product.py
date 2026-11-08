"""S1.product_jsonld — valid JSON-LD Product with name, image, description.

Per page: share of {name, image, description} present. Microdata-only Product pages get
0.75 of that: Google treats valid microdata as equally fine but recommends JSON-LD
(https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data).
"""

from __future__ import annotations

from scanner.checks.per_page import PageScore, score_pages
from scanner.models import CheckResult, FetchedResource, ScanContext
from scanner.parse.product import product_data, variants_and_self

CHECK_ID = "S1.product_jsonld"
FIELDS = ("name", "image", "description")
MICRODATA_FACTOR = 0.75


def score(page: FetchedResource) -> PageScore:
    d = product_data(page.body or "")
    errs = f" Unparseable JSON-LD block: {d.jsonld_errors[0]}." if d.jsonld_errors else ""
    if d.source is None:
        return PageScore(page.url, 0.0, f"No Product structured data.{errs}")
    # ProductGroup: a field on the group or on any variant counts (e.g. image per variant)
    nodes = variants_and_self(d.product)
    present = [f for f in FIELDS if any(n.get(f) for n in nodes)]
    missing = [f for f in FIELDS if f not in present]
    frac = len(present) / len(FIELDS)
    kind = "JSON-LD" if d.source == "jsonld" else "microdata only (no JSON-LD)"
    if d.source == "microdata":
        frac *= MICRODATA_FACTOR
    multi = f" {d.product_count} Product nodes on the page." if d.product_count > 1 else ""
    detail = (
        f"Product as {kind}; "
        + (f"missing: {', '.join(missing)}." if missing else "name, image, description present.")
        + multi
        + errs
    )
    return PageScore(page.url, frac, detail, snippet=str(d.product.get("name") or "")[:120] or None)


async def check(ctx: ScanContext) -> CheckResult:
    return score_pages(CHECK_ID, ctx, score)

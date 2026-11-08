"""D3.sitemap — valid sitemap reachable, referenced in robots.txt, contains product URLs,
lastmod present. 0.25 credit per sub-criterion. Fail if no valid sitemap at all.
"""

from __future__ import annotations

from scanner.checks.base import result
from scanner.checks.d1_robots import BLOCKED_FOR_US
from scanner.models import CheckResult, CheckStatus, Evidence, ScanContext
from scanner.sampling.urls import is_product_entry

CHECK_ID = "D3.sitemap"
LASTMOD_MIN_SHARE = 0.5


async def check(ctx: ScanContext) -> CheckResult:
    sm = ctx.basics.sitemap
    robots_url = ctx.origin + "/robots.txt"
    evidence: list[Evidence] = []
    passed = 0

    # 1. valid sitemap reachable
    valid = [s for s in sm.sources if s.kind in ("urlset", "index")]
    if valid and sm.entries:
        passed += 1
        evidence.append(
            Evidence(
                url=valid[0].url,
                detail=f"Valid sitemap: {len(sm.sources)} file(s) read, {len(sm.entries)} URLs"
                + (" (sample; more files not read)" if sm.truncated else ""),
            )
        )
    else:
        tried = (
            "; ".join(
                f"{s.url} -> {s.kind}"
                + (f" (HTTP {s.status_code})" if s.status_code else "")
                + (f": {s.error}" if s.error else "")
                for s in sm.sources
            )
            or "no sitemap URL tried"
        )
        evidence.append(Evidence(detail=f"No valid sitemap with URLs found. Tried: {tried}"))

    # 2. referenced in robots.txt
    if sm.from_robots:
        passed += 1
        evidence.append(
            Evidence(
                url=robots_url,
                detail="Sitemap referenced in robots.txt",
                snippet="\n".join(f"Sitemap: {u}" for u in sm.from_robots[:5]),
            )
        )
    else:
        evidence.append(Evidence(url=robots_url, detail="No 'Sitemap:' line in robots.txt"))

    # 3. contains product URLs (URL-shape / sitemap-name heuristic)
    products = [e for e in sm.entries if is_product_entry(e)]
    if products:
        passed += 1
        evidence.append(
            Evidence(
                url=products[0].source,
                detail=f"{len(products)} product URLs recognised, e.g. {products[0].loc}",
            )
        )
    elif sm.entries:
        evidence.append(
            Evidence(
                detail="No product URLs recognised in the sitemap (heuristic: /product(s)/ or /p/ "
                "paths, or a sitemap file named '*product*'). Verify manually.",
            )
        )

    # 4. lastmod present
    if sm.entries:
        with_lastmod = sum(1 for e in sm.entries if e.lastmod)
        share = with_lastmod / len(sm.entries)
        if share >= LASTMOD_MIN_SHARE:
            passed += 1
        evidence.append(
            Evidence(
                detail=f"lastmod on {with_lastmod}/{len(sm.entries)} URLs ({share:.0%}); "
                f"threshold {LASTMOD_MIN_SHARE:.0%}",
            )
        )

    if (
        not (valid and sm.entries)
        and sm.sources
        and all(s.status_code in BLOCKED_FOR_US for s in sm.sources)
    ):
        evidence.insert(
            0,
            Evidence(
                detail="Every sitemap request was refused to our scanner (HTTP 401/403/429, likely "
                "bot protection), so the sitemap cannot be verified.",
            ),
        )
        return result(CHECK_ID, ctx, "error", 0.0, evidence)

    fraction = passed / 4
    status: CheckStatus
    if not (valid and sm.entries):
        status = "fail"
    elif passed == 4:
        status = "pass"
    else:
        status = "warn"
    return result(CHECK_ID, ctx, status, fraction, evidence)

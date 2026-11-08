"""C5.policies_clear — shipping cost, delivery time and return window in plain text on the
policy pages (NL + EN patterns). 1/3 credit each.
"""

from __future__ import annotations

import re

from scanner.checks.base import result
from scanner.models import CheckResult, CheckStatus, Evidence, ScanContext
from scanner.parse.product import visible_text

CHECK_ID = "C5.policies_clear"
SHIPPING_COST = re.compile(
    r"(gratis (verzend|bezorg|levering)|verzend(ing)?kosten|bezorgkosten|verzending (is )?gratis|"
    r"free (shipping|delivery)|shipping (costs?|fee))",
    re.I,
)
DELIVERY_TIME = re.compile(
    r"(\b\d+\s*(-|\u2013|tot|à|a)?\s*\d*\s*(werk)?dag(en)?\b|binnen \d+ (uur|(werk)?dagen)|"
    r"morgen (in huis|bezorgd|geleverd)|vandaag besteld|next[- ]day|\d+\s*business days)",
    re.I,
)
RETURN_WINDOW = re.compile(
    r"(\d+\s*dagen[^.]{0,60}(retour|bedenktijd|terug|ruil)|(retour|bedenktijd|terugsturen|"
    r"ruilen)[^.]{0,60}\d+\s*dagen|\d+[- ]day return|return[^.]{0,40}\d+\s*days)",
    re.I,
)


def embedded_text(html: str) -> str:
    """Text inside embedded page data (e.g. Next.js JSON with escaped HTML for an FAQ
    accordion): visible only after JavaScript runs."""
    unescaped = html.replace("\\u003c", "<").replace("\\u003e", ">").replace("\\n", " ")
    return re.sub(r"<[^>]+>", " ", unescaped)


# (name, pattern, own policy kind, may fall back to the other policy page)
# Delivery time never falls back: "retourneren binnen 14 dagen" is a return window.
ITEMS = (
    ("shipping cost", SHIPPING_COST, "shipping", True),
    ("delivery time", DELIVERY_TIME, "shipping", False),
    ("return window", RETURN_WINDOW, "returns", True),
)


async def check(ctx: ScanContext) -> CheckResult:
    pages = [p for k, p in ctx.pages.policies.items() if k in ("shipping", "returns") and p.ok]
    if not pages:
        return result(
            CHECK_ID,
            ctx,
            "error",
            0.0,
            [Evidence(detail="No shipping or returns policy page could be fetched")],
        )
    texts = {
        kind: (p.final_url or p.url, visible_text(p.body or ""))
        for kind, p in ctx.pages.policies.items()
        if kind in ("shipping", "returns") and p.ok
    }
    raw = {
        kind: (p.final_url or p.url, embedded_text(p.body or ""))
        for kind, p in ctx.pages.policies.items()
        if kind in ("shipping", "returns") and p.ok
    }
    evidence: list[Evidence] = []
    found = 0.0
    for name, rx, own, fallback in ITEMS:
        order = [own] + ([k for k in texts if k != own] if fallback else [])
        hit = next(
            ((texts[k][0], m) for k in order if k in texts and (m := rx.search(texts[k][1]))),
            None,
        )
        if hit:
            found += 1
            evidence.append(Evidence(url=hit[0], detail=f"{name} stated", snippet=hit[1].group(0)))
            continue
        hidden = next(
            ((raw[k][0], m) for k in order if k in raw and (m := rx.search(raw[k][1]))), None
        )
        if hidden:
            found += 0.5
            evidence.append(
                Evidence(
                    url=hidden[0],
                    detail=f"{name} only in embedded page data (shown after JavaScript, e.g. a "
                    "collapsed FAQ), not in the plain page text",
                    snippet=hidden[1].group(0),
                )
            )
        else:
            evidence.append(Evidence(detail=f"{name} not found in plain text"))
    status: CheckStatus = "pass" if found >= 3 else "warn" if found else "fail"
    return result(CHECK_ID, ctx, status, found / 3, evidence)

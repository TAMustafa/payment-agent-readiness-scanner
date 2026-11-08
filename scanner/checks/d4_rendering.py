"""D4.rendering — product name, price and availability present in the raw HTML.

Many AI crawlers do not run JavaScript, so data that only appears after rendering is
invisible to them. Per page: 1/3 each for name (markup name or <h1>), price (markup price
or a visible price) and availability (markup availability or a NL/EN stock phrase).
Static only for now: telling "only after JS" apart from "missing everywhere" needs the
Playwright render comparison (build step 2). Both mean crawlers do not see the data.
"""

from __future__ import annotations

import re

from scanner.checks.per_page import PageScore, score_pages
from scanner.models import CheckResult, FetchedResource, ScanContext
from scanner.parse.html import parse
from scanner.parse.product import offer_price, offers_of, product_data, visible_text

CHECK_ID = "D4.rendering"
STOCK_TEXT = re.compile(
    r"\b(op voorraad|niet op voorraad|uitverkocht|leverbaar|voorradig|morgen in huis|"
    r"in stock|out of stock|sold out|available)\b",
    re.I,
)
VISIBLE_PRICE = re.compile(r"(€|EUR)\s?\d+[.,]\d{2}|\d+[.,]\d{2}\s?(€|EUR)|€\s?\d+,-")


def score(page: FetchedResource) -> PageScore:
    html = page.body or ""
    d = product_data(html)
    offers = offers_of(d.product) if d.source else []
    text = visible_text(html)
    h1 = parse(html).css_first("h1")

    name = bool(d.product.get("name")) or bool(h1 and h1.text(strip=True))
    price = any(offer_price(o) is not None for o in offers) or bool(VISIBLE_PRICE.search(text))
    stock = any(o.get("availability") for o in offers) or bool(STOCK_TEXT.search(text))
    have = {"name": name, "price": price, "availability": stock}
    missing = [k for k, v in have.items() if not v]
    detail = (
        "name, price, availability in raw HTML"
        if not missing
        else f"Not in raw HTML: {', '.join(missing)} (JS-only or absent; render check in step 2)"
    )
    return PageScore(page.url, sum(have.values()) / 3, detail)


async def check(ctx: ScanContext) -> CheckResult:
    return score_pages(CHECK_ID, ctx, score)

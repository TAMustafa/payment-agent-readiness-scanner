"""D4.rendering — product name, price and availability present in the raw HTML.

Many AI crawlers do not run JavaScript, so data that only appears after rendering is
invisible to them. Per page: 1/3 each for name (markup name or <h1>), price (markup price
or a visible price) and availability (markup availability or a NL/EN stock phrase).
The checkout probe's Playwright render of the probed product page tells "only after JS"
apart from "absent" for that page; other pages stay raw-HTML only.
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
        else f"Not in raw HTML: {', '.join(missing)} (JS-only or absent)"
    )
    return PageScore(page.url, sum(have.values()) / 3, detail)


async def check(ctx: ScanContext) -> CheckResult:
    rendered = {r.url: r for r in ctx.checkout.rendered}

    def scored(page: FetchedResource) -> PageScore:
        s = score(page)
        r = rendered.get(page.url) or rendered.get(page.final_url or "")
        if r is None or s.score >= 0.999:
            return s
        after = [k for k, v in (("price", r.price_visible), ("availability", r.stock_visible)) if v]
        if after:
            return PageScore(
                s.url,
                s.score,
                s.detail.split(" (")[0]
                + f"; after JavaScript rendering: {', '.join(after)} appear(s) "
                "-> only visible to crawlers that run JavaScript",
            )
        return PageScore(
            s.url, s.score, s.detail.split(" (")[0] + "; also absent after JavaScript rendering"
        )

    return score_pages(CHECK_ID, ctx, scored)

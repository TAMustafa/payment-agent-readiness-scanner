"""S2.offer — offers with price, priceCurrency=EUR, availability, url; price matches the
visible price (±0.01).

Google merchant listings: price + priceCurrency required, availability + url recommended,
and an Offer is required (AggregateOffer only for product snippets)
(https://developers.google.com/search/docs/appearance/structured-data/merchant-listing).
Per-page weights: price 0.3, EUR 0.2, availability 0.2, url 0.1, visible match 0.2.
"""

from __future__ import annotations

from scanner.checks.per_page import PageScore, score_pages
from scanner.models import CheckResult, FetchedResource, ScanContext
from scanner.parse.html import types_of
from scanner.parse.product import (
    offer_currency,
    offer_price,
    offers_of,
    price_patterns,
    product_data,
    visible_text,
)

CHECK_ID = "S2.offer"


def score(page: FetchedResource) -> PageScore:
    html = page.body or ""
    d = product_data(html)
    offers = offers_of(d.product) if d.source else []
    if not offers:
        return PageScore(page.url, 0.0, "No offers in Product structured data")
    offer = offers[0]
    price = offer_price(offer)
    currency = offer_currency(offer)
    got: list[str] = []
    missing: list[str] = []
    s = 0.0
    if price is not None:
        s += 0.3
        got.append(f"price {price}")
    else:
        missing.append("price")
    if currency == "EUR":
        s += 0.2
    else:
        missing.append(f"priceCurrency EUR (found {currency or 'none'})")
    if offer.get("availability"):
        s += 0.2
        got.append(str(offer["availability"]).rsplit("/", 1)[-1])
    else:
        missing.append("availability")
    if offer.get("url"):
        s += 0.1
    else:
        missing.append("url")
    if price is not None:
        text = visible_text(html)
        if any(p.search(text) for p in price_patterns(price)):
            s += 0.2
            got.append("matches visible price")
        else:
            missing.append(
                f"visible price matching {price} (±0.01) not found in the raw page text "
                "(may be rendered by JavaScript)"
            )
    note = ""
    if "AggregateOffer" in types_of(offer):
        note = " AggregateOffer used; Google merchant listings require an Offer."
    detail = (
        (f"Has {', '.join(got)}. " if got else "")
        + (f"Missing: {'; '.join(missing)}." if missing else "")
        + note
    ).strip()
    return PageScore(page.url, s, detail)


async def check(ctx: ScanContext) -> CheckResult:
    return score_pages(CHECK_ID, ctx, score)

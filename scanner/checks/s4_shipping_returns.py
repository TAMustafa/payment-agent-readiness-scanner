"""S4.shipping_returns — shipping and return policy markup, on the Offer or the Organization.

Google accepts both levels: Offer.shippingDetails / Offer.hasMerchantReturnPolicy, and
Organization.hasShippingService / Organization.hasMerchantReturnPolicy
(https://developers.google.com/search/docs/appearance/structured-data/merchant-listing,
https://developers.google.com/search/docs/appearance/structured-data/organization).
Per page: 0.5 shipping + 0.5 returns. Organization markup from the home page counts for
every product page.
"""

from __future__ import annotations

from typing import Any

from scanner.checks.per_page import PageScore, score_pages
from scanner.models import CheckResult, Evidence, FetchedResource, ScanContext
from scanner.parse.product import offers_of, organizations, product_data

CHECK_ID = "S4.shipping_returns"


def _org_flags(orgs: list[dict[str, Any]]) -> tuple[bool, bool]:
    ship = any(o.get("hasShippingService") or o.get("shippingDetails") for o in orgs)
    ret = any(o.get("hasMerchantReturnPolicy") for o in orgs)
    return ship, ret


async def check(ctx: ScanContext) -> CheckResult:
    home = ctx.basics.home.body or "" if ctx.basics.home and ctx.basics.home.ok else ""
    home_ship, home_ret = _org_flags(organizations(home))
    extra = [
        Evidence(
            url=ctx.basics.home.url if ctx.basics.home else None,
            detail="Home page Organization markup: "
            f"shipping policy {'yes' if home_ship else 'no'}, "
            f"return policy {'yes' if home_ret else 'no'}",
        )
    ]

    def score(page: FetchedResource) -> PageScore:
        html = page.body or ""
        d = product_data(html)
        offers = offers_of(d.product) if d.source else []
        page_ship, page_ret = _org_flags(organizations(html))
        ship_where = (
            "offer"
            if any(o.get("shippingDetails") for o in offers)
            else "organization"
            if page_ship or home_ship
            else None
        )
        ret_where = (
            "offer"
            if any(o.get("hasMerchantReturnPolicy") for o in offers)
            else "organization"
            if page_ret or home_ret
            else None
        )
        s = (0.5 if ship_where else 0.0) + (0.5 if ret_where else 0.0)
        detail = f"shipping: {ship_where or 'missing'}; returns: {ret_where or 'missing'}"
        return PageScore(page.url, s, detail)

    return score_pages(CHECK_ID, ctx, score, extra=extra)

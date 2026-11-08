"""Check registry: maps stable SPEC.md check id -> metadata (+ implementation).

All catalogue IDs are listed here so weights can be validated (they must sum to 100).
`func` is set for checks that run in the parallel `run_check` fan-out. C-checks read the
data the checkout_probe node collected; V1 is produced by the visibility node.

Effort values are NOT in SPEC.md — they are initial estimates and need confirming.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from scanner.checks import (
    c1_add_to_cart,
    c2_guest_checkout,
    c3_payment_methods,
    c4_captcha_checkout,
    c5_policies,
    d1_robots,
    d2_edge,
    d3_sitemap,
    d4_rendering,
    d5_merchant_center,
    p1_ucp,
    p2_platform,
    p3_endpoints,
    s1_product,
    s2_offer,
    s3_identifiers,
    s4_shipping_returns,
    s5_reviews,
    s6_organization,
)
from scanner.models import Category, CheckResult, Effort, ScanContext

CheckFunc = Callable[[ScanContext], Awaitable[CheckResult]]


@dataclass(frozen=True)
class CheckSpec:
    id: str
    category: Category
    label: str
    weight: int
    effort: Effort
    func: CheckFunc | None = None  # None = produced by another node (checkout / visibility)


_SPECS: list[CheckSpec] = [
    # D — Discovery & access (30)
    CheckSpec(
        "D1.robots_ai_crawlers",
        "discovery",
        "AI crawlers allowed in robots.txt",
        10,
        "S",
        d1_robots.check,
    ),
    CheckSpec(
        "D2.edge_blocking",
        "discovery",
        "AI agents not blocked by CDN/WAF",
        8,
        "M",
        d2_edge.check,
    ),
    CheckSpec(
        "D3.sitemap", "discovery", "Valid sitemap with product URLs", 5, "S", d3_sitemap.check
    ),
    CheckSpec("D4.rendering", "discovery", "Product data in raw HTML", 4, "L", d4_rendering.check),
    CheckSpec(
        "D5.merchant_center",
        "discovery",
        "Google Merchant Center feed healthy",
        3,
        "M",
        d5_merchant_center.check,
    ),
    # S — Structured product data (30)
    CheckSpec(
        "S1.product_jsonld", "data", "Product JSON-LD present and valid", 6, "M", s1_product.check
    ),
    CheckSpec(
        "S2.offer", "data", "Offer with price, currency, availability", 8, "M", s2_offer.check
    ),
    CheckSpec("S3.identifiers", "data", "GTIN / MPN + brand", 6, "M", s3_identifiers.check),
    CheckSpec(
        "S4.shipping_returns",
        "data",
        "Shipping and return policy markup",
        5,
        "M",
        s4_shipping_returns.check,
    ),
    CheckSpec("S5.reviews", "data", "Review markup (aggregateRating)", 2, "S", s5_reviews.check),
    CheckSpec(
        "S6.organization",
        "data",
        "Organization / OnlineStore markup",
        3,
        "S",
        s6_organization.check,
    ),
    # C — Checkout readiness (20) — data from the checkout_probe node (step 2)
    CheckSpec(
        "C1.add_to_cart", "checkout", "Add to cart works headless", 5, "M", c1_add_to_cart.check
    ),
    CheckSpec(
        "C2.guest_checkout", "checkout", "Guest checkout available", 6, "M", c2_guest_checkout.check
    ),
    CheckSpec(
        "C3.payment_methods", "checkout", "iDEAL / Wero offered", 4, "S", c3_payment_methods.check
    ),
    CheckSpec(
        "C4.captcha_checkout",
        "checkout",
        "No captcha on checkout entry",
        3,
        "M",
        c4_captcha_checkout.check,
    ),
    CheckSpec(
        "C5.policies_clear",
        "checkout",
        "Shipping and returns stated clearly",
        2,
        "S",
        c5_policies.check,
    ),
    # P — Agent protocols (10)
    CheckSpec(
        "P1.ucp_profile", "protocol", "UCP profile at /.well-known/ucp", 5, "L", p1_ucp.check
    ),
    CheckSpec(
        "P2.platform_support", "protocol", "Agentic channel for platform", 3, "M", p2_platform.check
    ),
    CheckSpec(
        "P3.mcp_or_feed_endpoint",
        "protocol",
        "MCP endpoint or agent feed",
        2,
        "L",
        p3_endpoints.check,
    ),
    # V — AI visibility (10) — produced by the visibility node (step 3)
    CheckSpec("V1.prompt_visibility", "visibility", "Mentioned by AI assistants", 10, "L"),
]

REGISTRY: dict[str, CheckSpec] = {s.id: s for s in _SPECS}


def static_check_ids(selected: list[str] | None = None) -> list[str]:
    """IDs of checks that run in the run_check fan-out, optionally filtered.

    `selected` may contain full ids ("D1.robots_ai_crawlers"), codes ("D1") or a category
    letter ("D").
    """
    ids = [s.id for s in _SPECS if s.func is not None]
    if selected is None:
        return ids
    wanted = {w.strip() for w in selected if w.strip()}

    def match(check_id: str) -> bool:
        code = check_id.split(".", 1)[0]  # "D1"
        return check_id in wanted or code in wanted or code[0] in wanted  # id, "D1" or "D"

    return [i for i in ids if match(i)]

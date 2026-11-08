"""Check registry: maps stable SPEC.md check id -> metadata (+ implementation).

All catalogue IDs are listed here so weights can be validated (they must sum to 100).
`func` is set only for checks that run in the parallel `run_check` fan-out (static checks).
C* checks are produced by the checkout_probe node, V1 by the visibility node.

Effort values are NOT in SPEC.md — they are initial estimates and need confirming.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from scanner.checks import d1_robots, d3_sitemap
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


async def _not_implemented(ctx: ScanContext) -> CheckResult:
    # Stub for the skeleton: run_check turns this into status="error".
    raise NotImplementedError("check not implemented yet")


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
        _not_implemented,
    ),
    CheckSpec(
        "D3.sitemap", "discovery", "Valid sitemap with product URLs", 5, "S", d3_sitemap.check
    ),
    CheckSpec("D4.rendering", "discovery", "Product data in raw HTML", 4, "L", _not_implemented),
    CheckSpec(
        "D5.merchant_center",
        "discovery",
        "Google Merchant Center feed healthy",
        3,
        "M",
        _not_implemented,
    ),
    # S — Structured product data (30)
    CheckSpec(
        "S1.product_jsonld", "data", "Product JSON-LD present and valid", 6, "M", _not_implemented
    ),
    CheckSpec(
        "S2.offer", "data", "Offer with price, currency, availability", 8, "M", _not_implemented
    ),
    CheckSpec("S3.identifiers", "data", "GTIN / MPN + brand", 6, "M", _not_implemented),
    CheckSpec(
        "S4.shipping_returns", "data", "Shipping and return policy markup", 5, "M", _not_implemented
    ),
    CheckSpec("S5.reviews", "data", "Review markup (aggregateRating)", 2, "S", _not_implemented),
    CheckSpec(
        "S6.organization", "data", "Organization / OnlineStore markup", 3, "S", _not_implemented
    ),
    # C — Checkout readiness (20) — produced by checkout_probe (step 2)
    CheckSpec("C1.add_to_cart", "checkout", "Add to cart works headless", 5, "M"),
    CheckSpec("C2.guest_checkout", "checkout", "Guest checkout available", 6, "M"),
    CheckSpec("C3.payment_methods", "checkout", "iDEAL / Wero offered", 4, "S"),
    CheckSpec("C4.captcha_checkout", "checkout", "No captcha on checkout entry", 3, "M"),
    CheckSpec("C5.policies_clear", "checkout", "Shipping and returns stated clearly", 2, "S"),
    # P — Agent protocols (10)
    CheckSpec(
        "P1.ucp_profile", "protocol", "UCP profile at /.well-known/ucp", 5, "L", _not_implemented
    ),
    CheckSpec(
        "P2.platform_support", "protocol", "Agentic channel for platform", 3, "M", _not_implemented
    ),
    CheckSpec(
        "P3.mcp_or_feed_endpoint",
        "protocol",
        "MCP endpoint or agent feed",
        2,
        "L",
        _not_implemented,
    ),
    # V — AI visibility (10) — produced by the visibility node (step 3)
    CheckSpec("V1.prompt_visibility", "visibility", "Mentioned by AI assistants", 10, "L"),
]

REGISTRY: dict[str, CheckSpec] = {s.id: s for s in _SPECS}


def static_check_ids(selected: list[str] | None = None) -> list[str]:
    """IDs of checks that run in the run_check fan-out, optionally filtered.

    `selected` may contain full ids ("D1.robots_ai_crawlers") or short prefixes ("D1").
    """
    ids = [s.id for s in _SPECS if s.func is not None]
    if selected is None:
        return ids
    wanted = {w.strip() for w in selected if w.strip()}
    return [i for i in ids if i in wanted or i.split(".", 1)[0] in wanted]

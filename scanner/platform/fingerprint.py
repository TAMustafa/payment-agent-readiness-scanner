"""Platform fingerprinting from the home page: HTML markers, headers, cookie names.

Markers per SPEC.md §6, plus widely documented platform headers/cookies. Each signal has
a weight: 3 = unique to the platform, 1 = suggestive. The best platform needs >= 3 points,
otherwise "other". Every matched signal becomes evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from scanner.models import Evidence, FetchedResource, Platform, PlatformInfo
from scanner.parse.html import body_classes, meta_generator

Where = Literal["html", "header", "cookie", "generator", "body_class"]
MIN_SCORE = 3


@dataclass(frozen=True)
class Signal:
    platform: Platform
    where: Where
    pattern: str  # regex, case-insensitive; for headers/cookies matched against the name
    weight: int
    label: str


SIGNALS: tuple[Signal, ...] = (
    # Shopify
    Signal("shopify", "html", r"cdn\.shopify\.com", 3, "assets on cdn.shopify.com"),
    Signal("shopify", "html", r"Shopify\.theme", 3, "Shopify.theme JS object"),
    Signal("shopify", "header", r"^x-shopid$", 3, "x-shopid header"),
    Signal("shopify", "header", r"^x-shopify-stage$", 3, "x-shopify-stage header"),
    Signal("shopify", "cookie", r"^_shopify_", 3, "_shopify_* cookie"),
    # WooCommerce
    Signal(
        "woocommerce", "html", r"wp-content/plugins/woocommerce", 3, "WooCommerce plugin assets"
    ),
    Signal(
        "woocommerce",
        "body_class",
        r"^woocommerce(-page|-no-js|-js)?$",
        3,
        "woocommerce body class",
    ),
    Signal("woocommerce", "generator", r"^WooCommerce", 3, "generator meta WooCommerce"),
    Signal("woocommerce", "cookie", r"^woocommerce_", 3, "woocommerce_* cookie"),
    Signal("woocommerce", "html", r"/wp-content/", 1, "WordPress /wp-content/ paths"),
    # Shopware 6. Production storefronts serve compiled assets from /theme/<32-hex>/ and set
    # window.salesChannelId / window.themeJsPublicPath in the Storefront base template
    # (https://github.com/shopware/shopware, src/Storefront/Resources/views/storefront);
    # observed on live NL shops 2026-11-08 where /bundles/storefront/ was absent.
    Signal("shopware6", "html", r"/bundles/storefront/", 3, "/bundles/storefront assets"),
    Signal("shopware6", "html", r"window\.salesChannelId\s*=", 3, "window.salesChannelId"),
    Signal("shopware6", "html", r"window\.themeJsPublicPath\s*=", 3, "window.themeJsPublicPath"),
    Signal("shopware6", "html", r"/theme/[0-9a-f]{32}/", 2, "/theme/<hash>/ compiled assets"),
    Signal("shopware6", "generator", r"^Shopware", 3, "generator meta Shopware"),
    Signal("shopware6", "html", r"class=\"[^\"]*\bsw-[a-z]", 1, "sw-* CSS classes"),
    # Lightspeed eCom
    Signal("lightspeed", "html", r"cdn\.webshopapp\.com", 3, "assets on cdn.webshopapp.com"),
    Signal("lightspeed", "html", r"assets\.webshopapp\.com", 3, "assets on assets.webshopapp.com"),
    # Magento / Adobe Commerce
    Signal("magento", "html", r"text/x-magento-init", 3, "x-magento-init scripts"),
    Signal(
        "magento",
        "html",
        r"/static/(version\d+/)?frontend/[^\"']+/Magento_",
        3,
        "Magento_* static frontend assets",
    ),
    Signal("magento", "html", r"data-mage-init", 3, "data-mage-init attributes"),
    Signal("magento", "html", r"\bmage/", 1, "mage/ JS paths"),
    Signal("magento", "cookie", r"^X-Magento-Vary$", 3, "X-Magento-Vary cookie"),
    Signal("magento", "header", r"^x-magento-", 3, "x-magento-* header"),
)


def fingerprint(home: FetchedResource | None) -> PlatformInfo:
    if home is None or not home.ok:
        why = home.unavailable_reason() if home else "not fetched"
        return PlatformInfo(
            signals=[Evidence(detail=f"Home page not available ({why}); platform unknown")]
        )
    html = home.body or ""
    url = home.final_url or home.url
    generator = meta_generator(html) or ""
    classes = body_classes(html)

    scores: dict[Platform, int] = {}
    matched: dict[Platform, list[Evidence]] = {}
    for sig in SIGNALS:
        rx = re.compile(sig.pattern, re.IGNORECASE)
        snippet: str | None = None
        if sig.where == "html":
            m = rx.search(html)
            snippet = _context(html, m.start(), m.end()) if m else None
        elif sig.where == "header":
            snippet = next(
                (f"{k}: {v[:80]}" for k, v in home.headers.items() if rx.search(k)), None
            )
        elif sig.where == "cookie":
            snippet = next((f"cookie {n}" for n in home.cookie_names if rx.search(n)), None)
        elif sig.where == "generator":
            snippet = (
                f'<meta name="generator" content="{generator}">' if rx.search(generator) else None
            )
        elif sig.where == "body_class":
            snippet = next((f"body class {c}" for c in classes if rx.search(c)), None)
        if snippet is None:
            continue
        scores[sig.platform] = scores.get(sig.platform, 0) + sig.weight
        matched.setdefault(sig.platform, []).append(
            Evidence(
                url=url, detail=f"{sig.platform}: {sig.label} (+{sig.weight})", snippet=snippet
            )
        )

    if not scores:
        return PlatformInfo(signals=[Evidence(url=url, detail="No known platform markers found")])
    best = max(scores, key=lambda p: scores[p])
    evidence = [e for p in sorted(matched, key=lambda p: -scores[p]) for e in matched[p]]
    if scores[best] < MIN_SCORE:
        return PlatformInfo(signals=evidence)
    return PlatformInfo(platform=best, signals=evidence)


def _context(text: str, start: int, end: int, pad: int = 40) -> str:
    return " ".join(text[max(0, start - pad) : end + pad].split())

"""URL heuristics for recognising product / category / policy pages before fetching.

Conservative on purpose: a URL shape only *confirms* a product for platforms whose default
product URLs are unambiguous (Shopify, WooCommerce). Everything else must be confirmed by
JSON-LD `Product` after fetching (SPEC.md §3 step 4).
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from scanner.models import Platform, SitemapEntry

# Shapes that confirm a product page by URL alone.
_PRODUCT_PATH = re.compile(
    r"/(products?|produkt|produit)/[^/]+/?$"  # Shopify /products/x, WooCommerce /product/x
    r"|/p/[^/]+/?$",  # common "/p/<slug>" pattern
    re.IGNORECASE,
)
# Category shapes per platform default (Shopify collections, WooCommerce product-category).
_CATEGORY_PATH = re.compile(r"/collections/[^/]+/?$|/product-category/", re.IGNORECASE)

# Platforms whose product pages usually end in .html: a candidate, never a confirmation
# (Magento categories end in .html too).
_HTML_CANDIDATE_PLATFORMS: frozenset[Platform] = frozenset({"magento", "lightspeed"})

POLICY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "shipping": ("verzend", "levering", "bezorg", "shipping", "delivery"),
    "returns": ("retour", "ruilen", "herroep", "return", "refund"),
    "terms": ("voorwaarden", "terms", "conditions"),
    "privacy": ("privacy",),
    "payment": ("betaalmethode", "betaalmogelijkhed", "betaalwijze", "betalen", "payment"),
}
# Words that contain a policy keyword but are something else (fixje.nl 2026-11-12:
# "dropshipping" for businesses was taken as the shipping policy, "iPhone inruilen"
# (trade-in) as the returns policy).
NOT_POLICY = ("dropship", "inruil")
# Shopify's built-in policy pages (used only when no footer link was found).
SHOPIFY_POLICY_PATHS: dict[str, str] = {
    "shipping": "/policies/shipping-policy",
    "returns": "/policies/refund-policy",
    "terms": "/policies/terms-of-service",
    "privacy": "/policies/privacy-policy",
}

_NOT_CATALOGUE = re.compile(
    r"account|login|inloggen|registr|cart|winkelwagen|checkout|afrekenen|wishlist|verlanglijst"
    r"|search|zoeken|blog|nieuws|contact|klantenservice|service|faq|over-ons|about|vacature"
    r"|career|winkels|stores|cadeaukaart|giftcard|policies|/pages?/",
    re.IGNORECASE,
)


def looks_like_product_url(url: str) -> bool:
    return bool(_PRODUCT_PATH.search(urlsplit(url).path))


def looks_like_category_url(url: str) -> bool:
    return bool(_CATEGORY_PATH.search(urlsplit(url).path))


def is_product_candidate(url: str, platform: Platform) -> bool:
    path = urlsplit(url).path.lower()
    if looks_like_product_url(url):
        return True
    return platform in _HTML_CANDIDATE_PLATFORMS and path.endswith(".html")


_LOCALE_ROOT = re.compile(r"^/[a-z]{2}(-[a-z]{2})?/?$", re.I)  # /nl, /de/, /en-gb


def is_catalogue_link(url: str) -> bool:
    """Plausible category/product link: not home/locale roots, account/cart/content/policy."""
    path = urlsplit(url).path
    return (
        path not in ("", "/")
        and not _LOCALE_ROOT.match(path)
        and not _NOT_CATALOGUE.search(path)
        and not policy_kind(url, "")
    )


def policy_kind(url: str, text: str) -> str | None:
    haystack_text = text.lower()
    path = urlsplit(url).path.lower()
    if any(w in haystack_text or w in path for w in NOT_POLICY):
        return None
    for kind, words in POLICY_KEYWORDS.items():
        if any(w in haystack_text for w in words):
            return kind
    for kind, words in POLICY_KEYWORDS.items():
        if any(w in path for w in words):
            return kind
    return None


def _source_name(entry: SitemapEntry) -> str:
    return urlsplit(entry.source).path.rsplit("/", 1)[-1].lower()


def is_product_entry(entry: SitemapEntry) -> bool:
    """Product if the URL has a product shape or came from a product-specific sitemap
    (Shopify sitemap_products_*.xml, Yoast/WooCommerce product-sitemap.xml, ...)."""
    name = _source_name(entry)
    return looks_like_product_url(entry.loc) or ("product" in name and "cat" not in name)


def is_category_entry(entry: SitemapEntry) -> bool:
    name = _source_name(entry)
    return (
        looks_like_category_url(entry.loc)
        or "categor" in name
        or "collection" in name
        or "product_cat" in name
    )

"""URL heuristics for recognising product pages before they are fetched.

Conservative on purpose: a false "product" is worse than a miss, because sampling will
confirm product pages via JSON-LD `Product` later (SPEC.md §3 step 4).
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from scanner.models import SitemapEntry

# Platform default product URL shapes.
_PRODUCT_PATH = re.compile(
    r"/(products?|produkt|produit)/[^/]+/?$"  # Shopify /products/x, WooCommerce /product/x
    r"|/p/[^/]+/?$",  # common "/p/<slug>" pattern
    re.IGNORECASE,
)


def looks_like_product_url(url: str) -> bool:
    return bool(_PRODUCT_PATH.search(urlsplit(url).path))


def is_product_entry(entry: SitemapEntry) -> bool:
    """Product if the URL has a product shape or came from a product-specific sitemap
    (Shopify sitemap_products_*.xml, Yoast/WooCommerce product-sitemap.xml, ...)."""
    source_name = urlsplit(entry.source).path.rsplit("/", 1)[-1].lower()
    return looks_like_product_url(entry.loc) or "product" in source_name

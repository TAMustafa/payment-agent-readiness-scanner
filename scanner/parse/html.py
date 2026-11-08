"""HTML helpers on top of selectolax (lexbor backend): links, meta, JSON-LD."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from selectolax.lexbor import LexborHTMLParser


@dataclass(frozen=True)
class Link:
    url: str  # absolute, fragment stripped
    text: str  # visible anchor text, lower-cased, whitespace-collapsed


def parse(html: str) -> LexborHTMLParser:
    return LexborHTMLParser(html)


def links(html: str, base_url: str, *, same_host: bool = True) -> list[Link]:
    """Unique <a href> links in document order."""
    base_host = urlsplit(base_url).hostname
    seen: set[str] = set()
    out: list[Link] = []
    for node in parse(html).css("a[href]"):
        href = (node.attributes.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        parts = urlsplit(urljoin(base_url, href))
        if parts.scheme not in ("http", "https"):
            continue
        if same_host and parts.hostname != base_host:
            continue
        url = urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))
        if url in seen:
            continue
        seen.add(url)
        text = " ".join(node.text(strip=True, separator=" ").split()).lower()
        out.append(Link(url=url, text=text))
    return out


def meta_generator(html: str) -> str | None:
    node = parse(html).css_first('meta[name="generator" i]')
    return (node.attributes.get("content") or None) if node else None


def body_classes(html: str) -> list[str]:
    body = parse(html).body
    return (body.attributes.get("class") or "").split() if body else []


@dataclass(frozen=True)
class JsonLdBlock:
    index: int  # position among ld+json scripts on the page
    data: Any | None  # parsed JSON, None if invalid
    error: str | None
    raw_snippet: str  # first 300 chars, for evidence


def jsonld_blocks(html: str) -> list[JsonLdBlock]:
    out: list[JsonLdBlock] = []
    for i, node in enumerate(parse(html).css('script[type="application/ld+json" i]')):
        raw = node.text() or ""
        try:
            data: Any = json.loads(raw)
            err = None
        except json.JSONDecodeError as exc:
            data, err = None, f"invalid JSON: {exc.msg} (line {exc.lineno})"
        out.append(JsonLdBlock(index=i, data=data, error=err, raw_snippet=raw.strip()[:300]))
    return out


def jsonld_nodes(html: str) -> list[dict[str, Any]]:
    """All JSON-LD objects on the page, flattening top-level lists and @graph."""
    nodes: list[dict[str, Any]] = []

    def walk(item: Any) -> None:
        if isinstance(item, list):
            for x in item:
                walk(x)
        elif isinstance(item, dict):
            if "@graph" in item:
                walk(item["@graph"])
            if "@type" in item:
                nodes.append(item)

    for block in jsonld_blocks(html):
        walk(block.data)
    return nodes


def types_of(node: dict[str, Any]) -> set[str]:
    """Schema.org types without prefix: "Product", "http://schema.org/Product" -> "Product"."""
    raw = node.get("@type")
    values = raw if isinstance(raw, list) else [raw]
    return {str(v).rsplit("/", 1)[-1].rsplit(":", 1)[-1] for v in values if v}


def has_product_jsonld(html: str) -> bool:
    return any(types_of(n) & {"Product", "ProductGroup"} for n in jsonld_nodes(html))


_MICRODATA_PRODUCT = re.compile(r"""itemtype\s*=\s*["']https?://schema\.org/Product["']""", re.I)


def count_product_microdata(html: str) -> int:
    """schema.org Product microdata items (e.g. Shopware 6 default storefront templates)."""
    return len(_MICRODATA_PRODUCT.findall(html))


def is_single_product_page(html: str) -> bool:
    """Exactly one Product/ProductGroup in JSON-LD, or exactly one Product microdata item.

    Listing pages (Shopify collections, Shopware category tiles) can carry several Product
    items; those are not product pages. A ProductGroup with its variants counts as one.
    """
    nodes = [n for n in jsonld_nodes(html) if types_of(n) & {"Product", "ProductGroup"}]
    groups = [n for n in nodes if "ProductGroup" in types_of(n)]
    if len(groups) == 1 or len(nodes) == 1:
        return True
    if not nodes:
        return count_product_microdata(html) == 1
    return False

"""Product / Offer / Organization data from a page, as schema.org-shaped dicts.

JSON-LD is read as-is. Microdata (e.g. Shopware 6 default templates) is converted to the
same dict shape, so checks read one structure. Google: "all 3 formats are equally fine ...
as long as the markup is valid", but "Google recommends using JSON-LD"
(https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from selectolax.lexbor import LexborNode

from scanner.parse.html import jsonld_blocks, jsonld_nodes, parse, types_of

Source = Literal["jsonld", "microdata"]
ORG_TYPES = frozenset(
    {"Organization", "OnlineStore", "OnlineBusiness", "Corporation", "Store", "LocalBusiness"}
)
EN_DASH = chr(0x2013)
GTIN_KEYS = ("gtin", "gtin8", "gtin12", "gtin13", "gtin14", "isbn")


@dataclass
class ProductData:
    source: Source | None  # None = no Product markup found
    product: dict[str, Any] = field(default_factory=dict)
    jsonld_errors: list[str] = field(default_factory=list)  # unparseable ld+json blocks
    product_count: int = 0  # Product/ProductGroup nodes found (listing pages have many)


# --- microdata ---------------------------------------------------------------------------


def _type_name(itemtype: str) -> str:
    return itemtype.strip().split()[0].rstrip("/").rsplit("/", 1)[-1] if itemtype else ""


def _value(node: LexborNode) -> Any:
    attrs = node.attributes
    if "itemscope" in attrs:
        return _scope(node)
    for key in ("content", "href", "src", "datetime", "value"):
        if attrs.get(key):
            return attrs[key]
    return " ".join((node.text(strip=True, separator=" ") or "").split())


def _scope(scope: LexborNode) -> dict[str, Any]:
    out: dict[str, Any] = {"@type": _type_name(scope.attributes.get("itemtype") or "")}

    def walk(node: LexborNode) -> None:
        child = node.child
        while child is not None:
            if child.tag != "-text":
                prop = child.attributes.get("itemprop")
                if prop:
                    val = _value(child)
                    for name in prop.split():
                        if name in out:
                            prev = out[name]
                            out[name] = (prev if isinstance(prev, list) else [prev]) + [val]
                        else:
                            out[name] = val
                if "itemscope" not in child.attributes:
                    walk(child)  # nested itemscope owns its own properties
            child = child.next

    walk(scope)
    return out


def microdata_items(html: str) -> list[dict[str, Any]]:
    """Top-level microdata items (itemscope without itemprop)."""
    return [_scope(n) for n in parse(html).css("[itemscope]") if "itemprop" not in n.attributes]


# --- extraction --------------------------------------------------------------------------


def product_data(html: str) -> ProductData:
    errors = [b.error for b in jsonld_blocks(html) if b.error]
    nodes = [n for n in jsonld_nodes(html) if types_of(n) & {"Product", "ProductGroup"}]
    if nodes:
        group = next((n for n in nodes if "ProductGroup" in types_of(n)), None)
        return ProductData("jsonld", group or nodes[0], errors, len(nodes))
    items = [i for i in microdata_items(html) if i.get("@type") in ("Product", "ProductGroup")]
    if items:
        return ProductData("microdata", items[0], errors, len(items))
    return ProductData(None, {}, errors, 0)


def organizations(html: str) -> list[dict[str, Any]]:
    """Organization-like nodes from JSON-LD (incl. nested publisher/seller) and microdata."""
    found: list[dict[str, Any]] = []

    def walk(item: Any) -> None:
        if isinstance(item, list):
            for x in item:
                walk(x)
        elif isinstance(item, dict):
            if types_of(item) & ORG_TYPES:
                found.append(item)
            for v in item.values():
                if isinstance(v, (dict, list)):
                    walk(v)

    walk(jsonld_nodes(html))
    walk([i for i in microdata_items(html) if i.get("@type") in ORG_TYPES])
    return found


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def first_dict(value: Any) -> dict[str, Any] | None:
    return next((v for v in as_list(value) if isinstance(v, dict)), None)


def offers_of(product: dict[str, Any]) -> list[dict[str, Any]]:
    """Offers on the product, or on its variants (ProductGroup.hasVariant)."""
    offers = [o for o in as_list(product.get("offers")) if isinstance(o, dict)]
    if offers:
        return offers
    for variant in as_list(product.get("hasVariant")):
        if isinstance(variant, dict):
            offers += [o for o in as_list(variant.get("offers")) if isinstance(o, dict)]
    return offers


def variants_and_self(product: dict[str, Any]) -> list[dict[str, Any]]:
    return [product] + [v for v in as_list(product.get("hasVariant")) if isinstance(v, dict)]


def to_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip().replace("€", "").replace(" ", "")
    if "," in text and "." in text:  # 1.299,00 or 1,299.00
        text = (
            text.replace(".", "").replace(",", ".")
            if text.rfind(",") > text.rfind(".")
            else text.replace(",", "")
        )
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def offer_price(offer: dict[str, Any]) -> Decimal | None:
    spec = first_dict(offer.get("priceSpecification"))
    for value in (offer.get("price"), offer.get("lowPrice"), spec.get("price") if spec else None):
        price = to_decimal(value)
        if price is not None:
            return price
    return None


def offer_currency(offer: dict[str, Any]) -> str | None:
    spec = first_dict(offer.get("priceSpecification"))
    cur = offer.get("priceCurrency") or (spec.get("priceCurrency") if spec else None)
    return str(cur).strip().upper() if cur else None


def price_patterns(price: Decimal) -> list[re.Pattern[str]]:
    """Visible-price regexes for NL/EN formats, ±0.01 (SPEC S2)."""
    pats: list[re.Pattern[str]] = []
    for p in (price - Decimal("0.01"), price, price + Decimal("0.01")):
        if p < 0:
            continue
        whole, cents = f"{p:.2f}".split(".")
        grouped = f"{int(whole):,}"
        variants = {
            f"{whole},{cents}",  # NL 399,00
            f"{whole}.{cents}",  # EN 399.00
            f"{grouped.replace(',', '.')},{cents}",  # NL 1.299,00
            f"{grouped}.{cents}",  # EN 1,299.00
        }
        if cents == "00":
            variants |= {f"{whole},-", f"{whole},{EN_DASH}"}  # NL "399,-" (hyphen or en dash)
        for v in variants:
            pats.append(re.compile(rf"(?<![\d.,]){re.escape(v)}(?![\d])"))
    return pats


def visible_text(html: str) -> str:
    tree = parse(html)
    for node in tree.css("script, style, noscript, template"):
        node.decompose()
    body = tree.body
    return " ".join((body.text(separator=" ") if body else "").split())


def valid_gtin(value: object) -> bool:
    """GS1 GTIN-8/12/13/14 with a correct check digit, not all zeros
    (https://www.gs1.org/services/how-calculate-check-digit-manually)."""
    digits = re.sub(r"\s|-", "", str(value))
    if not digits.isdigit() or len(digits) not in (8, 12, 13, 14) or set(digits) == {"0"}:
        return False
    body, check = digits[:-1], int(digits[-1])
    total = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check

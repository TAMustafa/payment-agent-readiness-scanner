"""V1 questions: fixed Dutch templates filled with the shop's brand and category names
(Tarek, 2026-11-09). Deterministic: the same scan data gives the same questions.

Google native search has no location parameter, so every question says "in Nederland".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from scanner.models import FetchedResource, PageSample
from scanner.parse.html import links, parse
from scanner.parse.product import organizations
from scanner.sampling.urls import is_catalogue_link, looks_like_product_url

BRAND_TEMPLATES = (
    "Is {brand} een betrouwbare webwinkel in Nederland? Wat zijn de ervaringen van klanten?",
    "Wat kun je online kopen bij {brand} en hoe zijn de prijzen en levertijden in Nederland?",
)
CATEGORY_TEMPLATES = (
    "Waar kan ik het beste {cat} online kopen in Nederland?",
    "Welke webwinkels in Nederland raad je aan voor {cat}?",
    "Wat is een goede en betrouwbare webshop voor {cat} in Nederland?",
    "{Cat} kopen in Nederland: welke online winkels zijn het beste?",
)
_SEPARATORS = re.compile(r"\s+[|\-\u2013\u2014:\u00b7]\s+")
_NOISE = re.compile(r"\b(alle|all|bekijk|shop|nieuw|new|sale|outlet|meer|more|cadeaus?)\b", re.I)


@dataclass(frozen=True)
class Question:
    kind: str  # "brand" | "category" | "custom"
    text: str


@dataclass(frozen=True)
class ShopIdentity:
    brand: str
    domain: str  # registrable host without www, e.g. "dille-kamille.nl"
    terms: tuple[str, ...]  # lower-case strings that count as a mention
    categories: tuple[str, ...]


def _domain(origin: str) -> str:
    host = (urlsplit(origin).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def brand_name(origin: str, home: FetchedResource | None) -> str:
    html = home.body or "" if home is not None and home.ok else ""
    for org in organizations(html):
        name = org.get("name")
        if isinstance(name, str) and 1 < len(name.strip()) < 60:
            return name.strip()
    title = parse(html).css_first("title") if html else None
    if title is not None:
        parts = [p.strip() for p in _SEPARATORS.split(title.text(strip=True)) if p.strip()]
        label = _domain(origin).split(".")[0].replace("-", " ")
        for p in parts:
            if label.split()[0] in p.lower():
                return p
    return _domain(origin).split(".")[0].replace("-", " ").title()


def brand_terms(brand: str, domain: str) -> tuple[str, ...]:
    label = domain.split(".")[0]
    terms = {brand.lower(), domain, label}
    if "-" in label:
        terms |= {label.replace("-", " "), label.replace("-", " & "), label.replace("-", "")}
    return tuple(sorted(t for t in terms if len(t) >= 3))


def _clean_category(text: str) -> str | None:
    t = " ".join(_NOISE.sub(" ", text).split()).strip(" -:|").lower()
    if not t or len(t) > 40 or len(t.split()) > 4 or re.search(r"\d|€|%", t):
        return None
    return t


def category_names(pages: PageSample, home: FetchedResource | None, limit: int) -> list[str]:
    """Category names in navigation order: sampled category pages first, then home links."""
    names: list[str] = []
    for page in pages.categories:
        h1 = parse(page.body or "").css_first("h1")
        if h1 is not None and (c := _clean_category(h1.text(strip=True))):
            names.append(c)
    if home is not None and home.ok:
        for link in links(home.body or "", home.final_url or home.url):
            if (
                is_catalogue_link(link.url)
                and not looks_like_product_url(link.url)
                and (c := _clean_category(link.text))
            ):
                names.append(c)
    return list(dict.fromkeys(names))[:limit]


def identify(
    origin: str, home: FetchedResource | None, pages: PageSample, max_categories: int
) -> ShopIdentity:
    brand = brand_name(origin, home)
    domain = _domain(origin)
    return ShopIdentity(
        brand=brand,
        domain=domain,
        terms=brand_terms(brand, domain),
        categories=tuple(category_names(pages, home, max_categories)),
    )


def build_questions(shop: ShopIdentity, n_brand: int, n_category: int) -> list[Question]:
    qs = [Question("brand", t.format(brand=shop.brand)) for t in BRAND_TEMPLATES[:n_brand]]
    cats = list(shop.categories)
    for i in range(n_category if cats else 0):
        cat = cats[i % len(cats)]
        tpl = CATEGORY_TEMPLATES[(i // len(cats) + i) % len(CATEGORY_TEMPLATES)]
        qs.append(Question("category", tpl.format(cat=cat, Cat=cat[:1].upper() + cat[1:])))
    return list(dict.fromkeys(qs))


def load_override(path: Path, limit: int = 20) -> list[Question]:
    """Operator prompts file: one question per line; '#' comments and blank lines ignored."""
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    return [Question("custom", ln) for ln in lines if ln and not ln.startswith("#")][:limit]

"""Sitemap parsing and fetching (https://www.sitemaps.org/protocol.html).

Uses stdlib ElementTree: with the bundled expat >= 2.4.1 it is not vulnerable to
billion-laughs / quadratic blowup and does not resolve external entities
(https://docs.python.org/3/library/xml.html#xml-vulnerabilities).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from scanner.fetch.client import PoliteClient
from scanner.models import SitemapEntry, SitemapInfo, SitemapSource

MAX_SITEMAP_FETCHES = 3  # out of the ~40-request scan budget; kept low for rate limits
MAX_ENTRIES = 5000


@dataclass
class ParsedSitemap:
    kind: str  # "urlset" | "index"
    entries: list[tuple[str, str | None]] = field(default_factory=list)  # (loc, lastmod)
    children: list[str] = field(default_factory=list)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_sitemap(xml_text: str) -> ParsedSitemap:
    """Parse a urlset or sitemapindex. Raises ValueError if it is neither."""
    try:
        root = ET.fromstring(xml_text.lstrip("﻿").strip())
    except ET.ParseError as exc:
        raise ValueError(f"not valid XML: {exc}") from exc
    kind = _local(root.tag)
    if kind not in ("urlset", "sitemapindex"):
        raise ValueError(f"root element is <{kind}>, expected <urlset> or <sitemapindex>")

    parsed = ParsedSitemap(kind="urlset" if kind == "urlset" else "index")
    for item in root:
        fields = {_local(c.tag): (c.text or "").strip() for c in item}
        loc = fields.get("loc")
        if not loc:
            continue
        if parsed.kind == "index":
            parsed.children.append(loc)
        else:
            parsed.entries.append((loc, fields.get("lastmod") or None))
    return parsed


_LOCALE_PREFIX = re.compile(r"^/([a-z]{2})(-[a-z]{2})?/", re.I)


def _child_priority(url: str) -> tuple[int, int]:
    """Product sitemaps first; within a kind, the default or Dutch locale before other
    language copies (e.g. Shopify /it/sitemap_products_1.xml)."""
    u = url.lower()
    if any(k in u for k in ("categor", "collection", "product_cat")):
        kind = 1
    elif "product" in u:
        kind = 0
    else:
        kind = 2
    m = _LOCALE_PREFIX.match(urlsplit(url).path)
    locale = 0 if m is None or m.group(1).lower() == "nl" else 1
    return (kind, locale)


async def collect_sitemaps(
    client: PoliteClient, origin: str, robots_sitemaps: list[str]
) -> SitemapInfo:
    """Fetch sitemaps (robots.txt Sitemap: lines, else /sitemap.xml), following one index level.

    Product-looking child sitemaps are fetched first so D3/sampling see product URLs early.
    """
    info = SitemapInfo(from_robots=list(robots_sitemaps))
    queue = list(robots_sitemaps) or [urljoin(origin, "/sitemap.xml")]
    fallbacks = [] if robots_sitemaps else [urljoin(origin, "/sitemap_index.xml")]
    seen: set[str] = set()

    while queue and len(info.sources) < MAX_SITEMAP_FETCHES:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        res = await client.get(url)
        if res.status_code is None or not (200 <= res.status_code < 300):
            info.sources.append(
                SitemapSource(
                    url=url, status_code=res.status_code, kind="unreachable", error=res.error
                )
            )
            if not queue and fallbacks and not info.entries:
                queue.append(fallbacks.pop(0))
            continue
        try:
            parsed = parse_sitemap(res.body or "")
        except ValueError as exc:
            info.sources.append(
                SitemapSource(url=url, status_code=res.status_code, kind="invalid", error=str(exc))
            )
            continue
        if parsed.kind == "index":
            info.sources.append(
                SitemapSource(
                    url=url,
                    status_code=res.status_code,
                    kind="index",
                    entry_count=len(parsed.children),
                )
            )
            queue.extend(sorted(parsed.children, key=_child_priority))
        else:
            info.sources.append(
                SitemapSource(
                    url=url,
                    status_code=res.status_code,
                    kind="urlset",
                    entry_count=len(parsed.entries),
                )
            )
            room = MAX_ENTRIES - len(info.entries)
            if len(parsed.entries) > room:
                info.truncated = True
            info.entries.extend(
                SitemapEntry(loc=loc, lastmod=lm, source=url) for loc, lm in parsed.entries[:room]
            )
    if queue:
        info.truncated = True
    return info

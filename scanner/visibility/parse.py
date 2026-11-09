"""Deterministic mention detection in an OpenRouter chat response (no LLM involved).

Response shape (OpenRouter, read 2026-11-09): choices[0].message.content (text),
choices[0].message.annotations[] = {"type": "url_citation", "url_citation": {"url", "title",
"start_index", "end_index"}}, usage.cost (USD), usage.server_tool_use_details.
web_search_requests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit


@dataclass
class Parsed:
    text: str = ""
    mentioned_in_text: bool = False
    cited: bool = False
    position: int | None = None
    cited_url: str | None = None
    cited_domains: list[str] = field(default_factory=list)
    searches: int = 0
    usage_cost: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    generation_id: str | None = None

    @property
    def mentioned(self) -> bool:
        return self.mentioned_in_text or self.cited


# Gemini grounding cites opaque redirect links; the real site is in the citation title
# (observed live 2026-11-09: url=vertexaisearch.cloud.google.com/grounding-api-redirect/...,
# title="thuisbezorgd.nl"). The redirect is never followed.
REDIRECT_HOSTS = frozenset({"vertexaisearch.cloud.google.com"})
_DOMAIN = re.compile(r"^(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)+)$", re.I)


def citation_domain(url: str, title: str | None) -> str:
    host = _host(url)
    if host in REDIRECT_HOSTS and title and (m := _DOMAIN.match(title.strip())):
        return m.group(1).lower()
    return host


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def term_in_text(term: str, text: str) -> bool:
    """Whole-word match, case-insensitive ("hema" must not match "schema")."""
    return (
        re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", text.lower()) is not None
    )


def parse_response(raw: dict[str, Any], domain: str, terms: tuple[str, ...]) -> Parsed:
    choices = raw.get("choices") or [{}]
    message = (choices[0] or {}).get("message") or {}
    text = message.get("content") or ""
    if isinstance(text, list):  # some providers return content parts
        text = " ".join(p.get("text", "") for p in text if isinstance(p, dict))

    citations: list[tuple[int, str, str]] = []  # (start, url, site domain)
    for i, ann in enumerate(message.get("annotations") or []):
        if isinstance(ann, dict) and ann.get("type") == "url_citation":
            c = ann.get("url_citation") or {}
            if url := c.get("url"):
                site = citation_domain(str(url), c.get("title"))
                citations.append((int(c.get("start_index", i) or i), str(url), site))
    citations.sort(key=lambda t: t[0])
    domains = list(dict.fromkeys(d for _, _, d in citations if d))

    def ours(host: str) -> bool:
        return host == domain or host.endswith("." + domain)

    cited_url = next((u for _, u, d in citations if ours(d)), None)
    position = next((i + 1 for i, h in enumerate(domains) if ours(h)), None)

    usage = raw.get("usage") or {}
    tool = usage.get("server_tool_use_details") or {}
    cost = usage.get("cost")
    return Parsed(
        text=text,
        mentioned_in_text=any(term_in_text(t, text) for t in terms),
        cited=cited_url is not None,
        position=position,
        cited_url=cited_url,
        cited_domains=domains,
        searches=int(tool.get("web_search_requests") or 0),
        usage_cost=float(cost) if cost is not None else None,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        generation_id=raw.get("id"),
    )

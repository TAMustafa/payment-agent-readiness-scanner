"""NL/EN guidance strings per check id (templated from SPEC.md guidance).

Strings are added per check as each check is implemented. Keep them factual: no claims
about agent checkout being live in NL.
"""

from __future__ import annotations

from typing import Literal

GUIDANCE: dict[str, dict[str, str]] = {
    "D1.robots_ai_crawlers": {
        "nl": (
            "Sta AI-zoek- en assistentbots (zoals OAI-SearchBot, ChatGPT-User, PerplexityBot, "
            "Claude-SearchBot, Googlebot, Bingbot, Applebot) toe in robots.txt voor je home-, "
            "categorie- en productpagina's. Bots die alleen voor AI-training zijn (GPTBot, "
            "ClaudeBot, Google-Extended, Applebot-Extended) mag je blokkeren; dat heeft geen "
            "invloed op gevonden worden."
        ),
        "en": (
            "Allow AI search and assistant bots (e.g. OAI-SearchBot, ChatGPT-User, PerplexityBot, "
            "Claude-SearchBot, Googlebot, Bingbot, Applebot) in robots.txt for your home, "
            "category and product pages. Training-only bots (GPTBot, ClaudeBot, Google-Extended, "
            "Applebot-Extended) may stay blocked; that does not affect being found."
        ),
    },
    "D3.sitemap": {
        "nl": (
            "Zorg voor een geldige XML-sitemap met al je productpagina's en een <lastmod>-datum "
            "per URL, en verwijs ernaar in robots.txt met een regel 'Sitemap: https://...'. "
            "De meeste shopplatformen of SEO-plugins kunnen dit automatisch genereren."
        ),
        "en": (
            "Provide a valid XML sitemap listing all product pages with a <lastmod> date per URL, "
            "and reference it in robots.txt with a 'Sitemap: https://...' line. Most shop "
            "platforms or SEO plugins can generate this automatically."
        ),
    },
}


def get_guidance(check_id: str, lang: Literal["nl", "en"] = "nl") -> str:
    entry = GUIDANCE.get(check_id, {})
    return entry.get(lang) or entry.get("en", "")

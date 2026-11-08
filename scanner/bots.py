"""AI search / agent / training bots tested by D1 (robots.txt) and D2 (edge blocking).

Verified against vendor docs on 2026-11-08. Re-verify before each release.
Sources:
- OpenAI:     https://developers.openai.com/api/docs/bots
              (was platform.openai.com/docs/bots, now 301-redirects)
- Anthropic:  https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler
- Perplexity: https://docs.perplexity.ai/guides/bots
- Google:     https://developers.google.com/search/docs/crawling-indexing/google-common-crawlers
              https://developers.google.com/crawling/docs/crawlers-fetchers/google-user-triggered-fetchers
- Apple:      https://support.apple.com/en-us/119829 (published 2026-09-04)
- Microsoft:  https://www.bing.com/webmasters/help/which-crawlers-does-bing-use-8c184ec0
              (page did not render on 2026-11-08; "bingbot" token is long-standing but UNVERIFIED)

Not included yet: Google-Agent / Google-GeminiNotebook (robots token not stated by Google),
OAI-AdsBot (ads landing-page checks only), Claude-Agent (separate Anthropic doc, unread).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BotKind = Literal["search", "user_agent", "training"]


@dataclass(frozen=True)
class Bot:
    token: str  # robots.txt product token
    vendor: str
    kind: BotKind
    # Full UA example for D2; None = control token only (no HTTP requests of its own).
    user_agent: str | None
    # Vendor note on robots.txt when it is not a plain "yes" (shown as evidence).
    robots_note: str | None = None


BOTS: tuple[Bot, ...] = (
    # OpenAI
    Bot(
        "OAI-SearchBot",
        "OpenAI",
        "search",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.4; "
        "+https://openai.com/searchbot",
    ),
    Bot(
        "ChatGPT-User",
        "OpenAI",
        "user_agent",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; "
        "+https://openai.com/bot",
        robots_note="OpenAI: user-initiated, robots.txt rules may not apply",
    ),
    Bot(
        "GPTBot",
        "OpenAI",
        "training",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.4; "
        "+https://openai.com/gptbot",
    ),
    # Perplexity
    Bot(
        "PerplexityBot",
        "Perplexity",
        "search",
        "Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
    ),
    Bot(
        "Perplexity-User",
        "Perplexity",
        "user_agent",
        "Mozilla/5.0 (compatible; Perplexity-User/1.0; +https://perplexity.ai/perplexity-user)",
        robots_note="Perplexity: user-requested fetches generally ignore robots.txt",
    ),
    # Anthropic (full UA strings not published; token-only UA used for D2)
    Bot("ClaudeBot", "Anthropic", "training", "ClaudeBot"),
    Bot("Claude-User", "Anthropic", "user_agent", "Claude-User"),
    Bot("Claude-SearchBot", "Anthropic", "search", "Claude-SearchBot"),
    # Google
    Bot(
        "Googlebot",
        "Google",
        "search",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Googlebot/2.1; "
        "+http://www.google.com/bot.html) Chrome/131.0.0.0 Safari/537.36",
    ),
    Bot(
        "Google-Extended",
        "Google",
        "training",
        None,
        robots_note="Google: control token for Gemini training/grounding; "
        "does not affect Google Search inclusion",
    ),
    # Microsoft (powers Bing + Copilot search)
    Bot(
        "Bingbot",
        "Microsoft",
        "search",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0; "
        "+http://www.bing.com/bingbot.htm) Chrome/131.0.0.0 Safari/537.36",
    ),
    # Apple
    Bot(
        "Applebot",
        "Apple",
        "search",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15 "
        "(Applebot/0.1; +http://www.apple.com/go/applebot)",
    ),
    Bot(
        "Applebot-Extended",
        "Apple",
        "training",
        None,
        robots_note="Apple: control token for foundation-model training; not used for ranking",
    ),
)

"""Agentic-channel support per platform (SPEC.md §6). Re-verify before each release.

Every row cites the sources read and the date verified. Where a source is silent, the row
says so instead of guessing; NL availability is not stated by any vendor source read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scanner.models import Platform

Level = Literal["native", "third_party", "none", "unknown"]
VERIFIED = "2026-11-08"


@dataclass(frozen=True)
class Support:
    level: Level
    channel: str
    note_en: str
    note_nl: str
    sources: tuple[str, ...]
    verified: str = VERIFIED


SUPPORT: dict[Platform, Support] = {
    "shopify": Support(
        "native",
        "Shopify Agentic Storefronts / Shopify Catalog (UCP)",
        "Enabled automatically for eligible stores; Shopify then serves a UCP profile at "
        "/.well-known/ucp. Eligibility criteria and NL availability are not stated publicly; "
        "check eligibility in the Shopify admin.",
        "Wordt automatisch aangezet voor winkels die in aanmerking komen; Shopify publiceert "
        "dan een UCP-profiel op /.well-known/ucp. De voorwaarden en beschikbaarheid in "
        "Nederland zijn niet openbaar; controleer dit in je Shopify-admin.",
        (
            "https://www.shopify.com/ca/agentic-storefronts",
            "https://shopify.dev/docs/agents",
            "https://www.shopify.com/news/fall-26-edition-merchant",
        ),
    ),
    "woocommerce": Support(
        "third_party",
        "No official channel; partner solutions in testing (Stripe ACP, Google)",
        "WooCommerce has no official agentic checkout; it reports testing partner solutions. "
        "Third-party UCP/feed plugins exist but quality varies: test on staging first.",
        "WooCommerce heeft geen officiële agent-checkout; partneroplossingen worden getest. "
        "Er bestaan plugins van derden voor UCP/feeds, maar de kwaliteit wisselt: test ze "
        "eerst op een stagingomgeving.",
        ("https://developer.woocommerce.com/2025/10/03/ai-agentic-commerce-in-woocommerce/",),
    ),
    "shopware6": Support(
        "third_party",
        "Third-party extension 'Great Agentic Commerce' (AI feeds, llms.txt)",
        "No official Shopware AG agentic channel found. A third-party extension exports AI "
        "product feeds (incl. Google UCP format) and llms.txt; it does not sell inside AI "
        "chats. Self-hosted Shopware 6.7 only.",
        "Geen officieel agentkanaal van Shopware AG gevonden. Een extensie van derden "
        "exporteert AI-productfeeds (o.a. Google UCP-formaat) en llms.txt; verkopen binnen "
        "AI-chats doet die niet. Alleen self-hosted Shopware 6.7.",
        (
            "https://store.shopware.com/de/great69379953545m/agentic-commerce-umsatz-pro-ki-chatgpt-claude-perplexity-copilot.html",
        ),
    ),
    "lightspeed": Support(
        "none",
        "None known",
        "No agentic channel mentioned by Lightspeed; a product-feed approach is the option.",
        "Lightspeed noemt geen agentkanaal; een productfeed is de route.",
        ("https://www.lightspeedhq.com/ecom/",),
    ),
    "magento": Support(
        "unknown",
        "Not verified",
        "Adobe's Commerce pages could not be read on the verification date; status unknown. "
        "A product-feed approach is the safe option.",
        "Adobe Commerce-bronnen konden niet worden gelezen; status onbekend. Een productfeed "
        "is de veilige route.",
        (),
    ),
}

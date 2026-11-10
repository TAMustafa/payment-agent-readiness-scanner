"""Agentic-channel support per platform (SPEC.md §6). Re-verify before each release.

Every row cites the sources read and the date verified (rows re-verified 2026-11-10:
shopware6, magento). Where a source is silent, the row
says so instead of guessing; NL availability is not stated by any vendor source read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scanner.models import Platform

Level = Literal["native", "third_party", "none", "unknown"]

# Customer-facing platform names (reports show these, never the internal codes).
DISPLAY_NAME: dict[str, str] = {
    "shopify": "Shopify",
    "woocommerce": "WooCommerce",
    "shopware6": "Shopware 6",
    "lightspeed": "Lightspeed eCom",
    "magento": "Magento / Adobe Commerce",
}
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
        "native",
        "Official Shopware plugin 'Agentic Commerce' (SwagAgenticCommerce): UCP, agent "
        "discovery files, OpenAI/Google product feeds",
        "Shopware AG publishes an official Agentic Commerce plugin (v1.4.0, October 2026) that "
        "adds a UCP profile and endpoints, agent discovery files and OpenAI/Google product "
        "feeds. Install and configure it per sales channel; test on staging first.",
        "Shopware AG publiceert een officiële Agentic Commerce-plugin (v1.4.0, oktober 2026) "
        "met een UCP-profiel en -endpoints, discovery-bestanden voor agents en productfeeds "
        "voor OpenAI en Google. Installeer en configureer hem per saleskanaal; test eerst op "
        "staging.",
        (
            "https://github.com/shopware/agentic-commerce",
            "https://github.com/shopware/agentic-commerce/releases",
        ),
        "2026-11-10",
    ),
    "lightspeed": Support(
        "none",
        "None known",
        "No agentic channel mentioned by Lightspeed; a product-feed approach is the option.",
        "Lightspeed noemt geen agentkanaal; een productfeed is de route.",
        ("https://www.lightspeedhq.com/ecom/",),
    ),
    "magento": Support(
        "none",
        "No native channel yet (support announced)",
        "Adobe has said Adobe Commerce will support UCP and ACP, but there is no native module "
        "yet (secondary sources). Today the options are a custom module, a third-party "
        "service, or a product feed.",
        "Adobe heeft aangekondigd dat Adobe Commerce UCP en ACP gaat ondersteunen, maar er is "
        "nog geen standaardmodule (bronnen van derden). Nu kan het met een eigen module, een "
        "dienst van derden of een productfeed.",
        (
            "https://www.xictron.com/en/blog/agentic-commerce-ucp-2026/",
            "https://ucphub.ai/",
        ),
        "2026-11-10",
    ),
}

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
    "D2.edge_blocking": {
        "nl": (
            "Je CDN of firewall (bijv. Cloudflare, Akamai) blokkeert of toont een "
            "uitdaging aan AI-zoek- en assistentbots. Sta deze bots toe in je bot-instellingen "
            "(bij Cloudflare: 'Verified bots' toestaan en AI-zoekbots niet blokkeren), zodat "
            "AI-assistenten je productpagina's kunnen lezen. Laat je hostingpartij of "
            "platform dit controleren als je de instelling niet zelf beheert."
        ),
        "en": (
            "Your CDN or firewall (e.g. Cloudflare, Akamai) blocks or challenges AI search and "
            "assistant bots. Allow these bots in your bot settings (on Cloudflare: allow "
            "'Verified bots' and do not block AI search crawlers) so AI assistants can read "
            "your product pages. Ask your host or platform to check this if you do not "
            "manage the setting yourself."
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
    "D4.rendering": {
        "nl": (
            "Zorg dat productnaam, prijs en voorraadstatus direct in de HTML staan die de "
            "server stuurt, niet pas na het laden van JavaScript. Veel AI-crawlers voeren geen "
            "JavaScript uit en zien die gegevens anders niet. Vraag je bouwer om server-side "
            "rendering of om deze gegevens als JSON-LD in de pagina-HTML op te nemen."
        ),
        "en": (
            "Make sure product name, price and stock status are in the HTML the server sends, "
            "not only after JavaScript runs. Many AI crawlers do not run JavaScript and miss "
            "that data. Ask your developer for server-side rendering or to include the data "
            "as JSON-LD in the page HTML."
        ),
    },
    "S1.product_jsonld": {
        "nl": (
            "Voeg op elke productpagina gestructureerde data toe als JSON-LD "
            "(schema.org Product) met minimaal name, image en description. Microdata werkt ook, "
            "maar Google raadt JSON-LD aan en AI-agents lezen het het betrouwbaarst."
        ),
        "en": (
            "Add structured data as JSON-LD (schema.org Product) to every product page, with "
            "at least name, image and description. Microdata also works, but Google recommends "
            "JSON-LD and AI agents read it most reliably."
        ),
    },
    "S2.offer": {
        "nl": (
            'Geef elk product een Offer met price, priceCurrency "EUR", availability en url, '
            "en zorg dat de prijs in de markup gelijk is aan de prijs op de pagina. Een "
            "afwijkende of ontbrekende prijs maakt het voor AI-assistenten onbetrouwbaar om je "
            "product aan te bevelen."
        ),
        "en": (
            'Give every product an Offer with price, priceCurrency "EUR", availability and '
            "url, and make sure the marked-up price equals the price shown on the page. A "
            "missing or different price makes your product unreliable for AI assistants to "
            "recommend."
        ),
    },
    "S3.identifiers": {
        "nl": (
            "Voeg productcodes toe aan je markup: bij voorkeur de GTIN/EAN (gtin13), anders "
            "mpn plus brand. Hiermee kunnen AI-assistenten en vergelijkers je product exact "
            "koppelen aan zoekvragen en prijsvergelijkingen."
        ),
        "en": (
            "Add product identifiers to your markup: preferably the GTIN/EAN (gtin13), "
            "otherwise mpn plus brand. These let AI assistants and comparison tools match your "
            "product exactly to queries and price comparisons."
        ),
    },
    "S4.shipping_returns": {
        "nl": (
            "Beschrijf je verzend- en retourbeleid in gestructureerde data: per product "
            "(shippingDetails en hasMerchantReturnPolicy op de Offer) of één keer voor de hele "
            "winkel (hasShippingService en hasMerchantReturnPolicy op je Organization/"
            "OnlineStore). Dan kunnen AI-assistenten levertijd, verzendkosten en "
            "retourtermijn direct noemen."
        ),
        "en": (
            "Describe your shipping and return policy in structured data: per product "
            "(shippingDetails and hasMerchantReturnPolicy on the Offer) or once for the whole "
            "store (hasShippingService and hasMerchantReturnPolicy on your Organization/"
            "OnlineStore). AI assistants can then quote delivery time, shipping cost and "
            "return window directly."
        ),
    },
    "S5.reviews": {
        "nl": (
            "Je toont reviews op productpagina's, maar ze staan niet in de markup. Voeg "
            "aggregateRating toe met ratingValue en reviewCount (of ratingCount), zodat "
            "AI-assistenten je beoordelingen kunnen meewegen. Gebruik per product de reviews "
            "van dát product, niet de algemene winkelbeoordeling."
        ),
        "en": (
            "You show reviews on product pages, but they are not in the markup. Add "
            "aggregateRating with ratingValue and reviewCount (or ratingCount) so AI "
            "assistants can take your ratings into account. Use each product's own reviews, "
            "not the overall shop rating."
        ),
    },
    "S6.organization": {
        "nl": (
            "Voeg op je homepage OnlineStore- of Organization-markup toe met naam, url, logo en "
            "contactgegevens (contactPoint, telefoon of e-mail), en je KvK- of btw-nummer "
            "(vatID of iso6523Code) als je dat op de site toont. Dit helpt AI-assistenten je "
            "winkel als betrouwbare verkoper te herkennen."
        ),
        "en": (
            "Add OnlineStore or Organization markup to your home page with name, url, logo and "
            "contact details (contactPoint, telephone or email), plus your Chamber of Commerce "
            "or VAT number (vatID or iso6523Code) if the site shows one. This helps AI "
            "assistants recognise your store as a trustworthy seller."
        ),
    },
    "D5.merchant_center": {
        "nl": (
            "Zorg voor een actieve Google Merchant Center-feed met zo min mogelijk afgekeurde "
            "producten. Google AI Mode en Gemini gebruiken deze productgegevens; afgekeurde "
            "producten worden daar niet getoond."
        ),
        "en": (
            "Keep an active Google Merchant Center feed with as few disapproved products as "
            "possible. Google AI Mode and Gemini use this product data; disapproved products "
            "are not shown there."
        ),
    },
    "P1.ucp_profile": {
        "nl": (
            "Publiceer een UCP-profiel (Universal Commerce Protocol) op /.well-known/ucp. "
            "Afrekenen via AI-agents is in Nederland nog niet live; met een geldig profiel ben "
            "je klaar zodra het wel live gaat. Op Shopify gebeurt dit automatisch voor winkels "
            "die in aanmerking komen; op andere platformen via een plugin of maatwerk."
        ),
        "en": (
            "Publish a UCP (Universal Commerce Protocol) profile at /.well-known/ucp. Agent "
            "checkout is not live in the Netherlands yet; a valid profile means you are ready "
            "when it launches. Shopify does this automatically for eligible stores; other "
            "platforms need a plugin or custom work."
        ),
    },
    "P2.platform_support": {
        "nl": (
            "Je platform biedt een route naar agent-commerce die nog niet aanstaat. Afrekenen "
            "via AI-agents is in Nederland nog niet live; zet het kanaal klaar (en test eerst "
            "op staging) zodat je direct mee kunt doen bij de lancering."
        ),
        "en": (
            "Your platform offers a route to agentic commerce that is not switched on yet. "
            "Agent checkout is not live in the Netherlands yet; prepare the channel (test on "
            "staging first) so you can join as soon as it launches."
        ),
    },
    "P3.mcp_or_feed_endpoint": {
        "nl": (
            "Maak je winkel vindbaar voor AI-agents via een machineleesbaar aanspreekpunt: een "
            "MCP-endpoint (bijvoorbeeld via je UCP-profiel) of een AI-catalogus op "
            "/.well-known/ai-catalog.json. Een llms.txt helpt als eerste stap. Dit is een "
            "opkomende standaard; nog geen vereiste."
        ),
        "en": (
            "Make your store discoverable for AI agents through a machine-readable entry "
            "point: an MCP endpoint (e.g. via your UCP profile) or an AI catalog at "
            "/.well-known/ai-catalog.json. An llms.txt is a good first step. This is an "
            "emerging standard, not yet a requirement."
        ),
    },
    "C1.add_to_cart": {
        "nl": (
            "Een browser-agent kon niet (zonder hindernissen) een product in de winkelwagen "
            "leggen. Zorg dat 'In winkelwagen' werkt zonder bot-uitdaging of captcha en beperk "
            "pop-ups tot de cookiemelding. Agent-checkout is in Nederland nog niet live; dit "
            "meet hoe klaar je gewone checkout is voor browser-agents."
        ),
        "en": (
            "A browser agent could not add a product to the cart (without obstacles). Make "
            "'Add to cart' work without bot challenges or captchas and keep pop-ups to the "
            "cookie notice. Agent checkout is not live in the Netherlands yet; this measures "
            "how ready your normal checkout is for browser agents."
        ),
    },
    "C2.guest_checkout": {
        "nl": (
            "Bied afrekenen als gast aan. Een verplicht account blokkeert AI-agents die namens "
            "een klant bestellen, en ook veel gewone klanten."
        ),
        "en": (
            "Offer guest checkout. A mandatory account blocks AI agents ordering on behalf of "
            "a customer, and many regular customers too."
        ),
    },
    "C3.payment_methods": {
        "nl": (
            "Bied iDEAL (en straks Wero) aan en toon de betaalmethoden duidelijk op een "
            "betaalinformatiepagina of in de footer, zodat agents en klanten ze vooraf zien."
        ),
        "en": (
            "Offer iDEAL (and Wero as it rolls out) and show payment methods clearly on a "
            "payment information page or in the footer, so agents and customers see them "
            "up front."
        ),
    },
    "C4.captcha_checkout": {
        "nl": (
            "Er staat een captcha bij het begin van de checkout. Die houdt ook legitieme "
            "browser-agents tegen. Gebruik onzichtbare botbescherming of zet de captcha pas "
            "bij verdacht gedrag in."
        ),
        "en": (
            "There is a captcha at checkout entry. It also stops legitimate browser agents. "
            "Use invisible bot protection or only show the captcha on suspicious behaviour."
        ),
    },
    "C5.policies_clear": {
        "nl": (
            "Vermeld op je verzend- en retourpagina in gewone tekst de verzendkosten, de "
            "levertijd (bijv. '1-2 werkdagen') en de retourtermijn (bijv. '30 dagen'), zodat "
            "AI-assistenten deze vragen direct kunnen beantwoorden."
        ),
        "en": (
            "State shipping cost, delivery time (e.g. '1-2 business days') and return window "
            "(e.g. '30 days') in plain text on your shipping and returns pages, so AI "
            "assistants can answer these questions directly."
        ),
    },
}


def get_guidance(check_id: str, lang: Literal["nl", "en"] = "nl") -> str:
    entry = GUIDANCE.get(check_id, {})
    return entry.get(lang) or entry.get("en", "")

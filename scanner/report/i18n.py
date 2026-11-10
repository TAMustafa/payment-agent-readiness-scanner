"""Report UI strings, NL with EN fallback (SPEC §5). Fix guidance lives in checks/copy.

Copy rules (CLAUDE.md): templated, no fabricated facts, and never claim that agent
checkout is live for Dutch merchants (it is not, as of Nov 2026).
"""

from __future__ import annotations

from typing import Literal

from scanner.platform.support import DISPLAY_NAME

Lang = Literal["nl", "en"]

UI: dict[str, dict[Lang, str]] = {
    "title": {"nl": "Klaar voor AI-shoppingagents?", "en": "Ready for AI shopping agents?"},
    "scanned": {"nl": "Gescand op", "en": "Scanned on"},
    "platform": {"nl": "Platform", "en": "Platform"},
    "intro": {
        "nl": "AI-assistenten zoals ChatGPT en Gemini gaan steeds vaker namens klanten "
        "winkelen en bestellen. Voor Nederlandse webshops is afrekenen binnen een "
        "AI-assistent nog niet beschikbaar. Dit rapport laat zien hoe goed je shop er nu al "
        "op voorbereid is: kan een agent je producten vinden, je aanbod begrijpen, afrekenen en "
        "aansluiten op de nieuwe agent-protocollen?",
        "en": "AI assistants such as ChatGPT and Gemini increasingly shop and order on behalf "
        "of customers. Checkout inside an AI assistant is not yet available to Dutch "
        "webshops. This report shows how well your shop is prepared today: can an agent "
        "find your products, understand your offer, check out, and connect to the new agent "
        "protocols?",
    },
    "score_of": {"nl": "van 100", "en": "out of 100"},
    "no_score": {
        "nl": "Geen score: er was niets dat we betrouwbaar konden meten.",
        "en": "No score: nothing could be measured reliably.",
    },
    "low_coverage": {
        "nl": "Te weinig gemeten voor een oordeel",
        "en": "Too little measured to judge",
    },
    "low_coverage_note": {
        "nl": "We konden maar {pct}% van de checks (naar gewicht) meten, bijvoorbeeld omdat de "
        "shop ons afremde. De score is voorlopig; een nieuwe scan of een scan op jouw verzoek "
        "geeft een volledig beeld.",
        "en": "We could only measure {pct}% of the checks (by weight), for example because "
        "the shop slowed us down. The score is provisional; a new scan or a scan at your "
        "request gives the full picture.",
    },
    "provisional": {"nl": "voorlopig", "en": "provisional"},
    "excluded": {
        "nl": "{n} van {m} checks konden we niet meten; de score gaat over de rest.",
        "en": "{n} of {m} checks could not be measured; the score covers the rest.",
    },
    "measured": {"nl": "{n}/{m} gemeten", "en": "{n}/{m} measured"},
    "top_fixes": {"nl": "Eerst doen", "en": "Do first"},
    "top_fixes_intro": {
        "nl": "De {n} verbeteringen die het meeste opleveren voor de minste moeite.",
        "en": "The {n} fixes that gain the most for the least work.",
    },
    "no_fixes": {
        "nl": "Geen verbeterpunten gevonden in wat we konden meten.",
        "en": "No fixes found in what we could measure.",
    },
    "gain": {"nl": "+{n} punten", "en": "+{n} points"},
    "effort": {"nl": "werk", "en": "effort"},
    "details": {
        "nl": "De vier stappen van een agent-bestelling",
        "en": "The four steps of an agent order",
    },
    "why": {"nl": "Waarom dit telt", "en": "Why it matters"},
    "how_to_fix": {"nl": "Zo los je het op", "en": "How to fix"},
    "found": {"nl": "Wat we zagen", "en": "What we saw"},
    "more_evidence": {
        "nl": "+ {n} bevindingen meer in de technische bijlage",
        "en": "+ {n} more findings in the technical appendix",
    },
    "not_measured_why": {"nl": "Waarom niet gemeten", "en": "Why not measured"},
    "method": {"nl": "Hoe we hebben gemeten", "en": "How we measured"},
    "m_readonly": {
        "nl": "Alleen-lezen: we hebben niets ingevuld, geen account aangemaakt, niets besteld "
        "en geen betaling gestart. We bekeken {products} productpagina's, met maximaal 1 "
        "verzoek per seconde.",
        "en": "Read-only: we filled in nothing, created no account, ordered nothing and "
        "started no payment. We looked at {products} product pages, at most 1 request per "
        "second.",
    },
    "m_checkout_on": {
        "nl": "Checkout-test: een browser legde één product in een anonieme winkelwagen en "
        "stopte bij het eerste checkout-scherm, zonder iets in te typen.",
        "en": "Checkout test: a browser put one product in an anonymous cart and stopped at "
        "the first checkout screen, without typing anything.",
    },
    "m_checkout_off": {
        "nl": "De checkout-test doen we alleen met jouw toestemming; zonder die test blijven "
        "drie checkout-checks ongemeten.",
        "en": "We only run the checkout test with your permission; without it three checkout "
        "checks stay unmeasured.",
    },
    "m_d2": {
        "nl": "Bottoegang testen we met de User-Agent van elke AI-bot plus onze eigen naam; "
        "echte bots kunnen door je CDN anders behandeld worden.",
        "en": "We test bot access with each AI bot's User-Agent plus our own name; real bots "
        "may be treated differently by your CDN.",
    },
    "m_snapshot": {
        "nl": "Dit is een momentopname van {date}: de resultaten gelden voor de pagina's die we "
        "toen bekeken. Wijzigingen in je shop daarna zijn niet meegenomen.",
        "en": "This is a snapshot from {date}: results apply to the pages we looked at then. "
        "Changes to your shop after that date are not included.",
    },
    "footer": {
        "nl": "{brand} {version} · technische bijlage op aanvraag",
        "en": "{brand} {version} · technical appendix available on request",
    },
}

# Plain-language reasons for checks we could not measure, matched on the operator evidence
# (report.json keeps the technical wording). First match wins.
UNMEASURED: tuple[tuple[str, dict[Lang, str]], ...] = (
    (
        "checkout probe not enabled",
        {
            "nl": "De checkout-test doen we alleen met jouw toestemming. Laat het ons weten als "
            "we deze stap mogen testen.",
            "en": "We only run the checkout test with your permission. Let us know if we may "
            "test this step.",
        },
    ),
    (
        "robots.txt disallows",
        {
            "nl": "Je robots.txt vraagt automatische bezoekers dit deel van de shop over te "
            "slaan, dus we hebben het niet getest. Met jouw toestemming kan dat wel.",
            "en": "Your robots.txt asks automated visitors to skip this part of the shop, so we "
            "did not test it. With your permission we can.",
        },
    ),
    (
        "No Merchant Center input",
        {
            "nl": "Hiervoor hebben we gegevens uit je Google Merchant Center nodig: is je feed "
            "actief en welk deel van je producten is afgekeurd?",
            "en": "This needs data from your Google Merchant Center: is your feed active and "
            "what share of your products is disapproved?",
        },
    ),
    (
        "No product pages could be sampled",
        {
            "nl": "We konden in deze scan geen productpagina's lezen, vaak omdat de shop ons "
            "afremde. Een nieuwe scan geeft meestal wel resultaat.",
            "en": "We could not read any product pages in this scan, often because the shop "
            "slowed us down. A new scan usually works.",
        },
    ),
    (
        "no product page sampled",
        {
            "nl": "Zonder productpagina kon de checkout-test niet starten.",
            "en": "Without a product page the checkout test could not start.",
        },
    ),
    (
        "Probe could not reach this step",
        {
            "nl": "Onze checkout-test kwam niet voorbij deze stap op je site, dus dit konden "
            "we niet meten.",
            "en": "Our checkout test could not get past this step on your site, so we could "
            "not measure it.",
        },
    ),
    (
        "429",
        {
            "nl": "Je shop remde onze scan af (rate limiting), dus dit konden we deze keer niet "
            "meten.",
            "en": "Your shop slowed down our scan (rate limiting), so we could not measure "
            "this time.",
        },
    ),
    (
        "rate limit",
        {
            "nl": "Je shop remde onze scan af (rate limiting), dus dit konden we deze keer niet "
            "meten.",
            "en": "Your shop slowed down our scan (rate limiting), so we could not measure "
            "this time.",
        },
    ),
    (
        "Chromium",
        {
            "nl": "Door een technisch probleem aan onze kant kon deze test niet draaien.",
            "en": "A technical problem on our side prevented this test.",
        },
    ),
    (
        "playwright",
        {
            "nl": "Door een technisch probleem aan onze kant kon deze test niet draaien.",
            "en": "A technical problem on our side prevented this test.",
        },
    ),
)

PLATFORM_NAME = DISPLAY_NAME
PLATFORM_OTHER: dict[Lang, str] = {"nl": "eigen of ander platform", "en": "custom or other"}

GRADE: dict[str, dict[Lang, str]] = {
    "Ready": {"nl": "Klaar", "en": "Ready"},
    "Partly ready": {"nl": "Deels klaar", "en": "Partly ready"},
    "Not ready": {"nl": "Niet klaar", "en": "Not ready"},
}

STATUS: dict[str, dict[Lang, str]] = {
    "pass": {"nl": "Goed", "en": "Pass"},
    "warn": {"nl": "Aandacht", "en": "Warning"},
    "fail": {"nl": "Onvoldoende", "en": "Fail"},
    "not_applicable": {"nl": "Niet gemeten", "en": "Not measured"},
    "error": {"nl": "Niet te controleren", "en": "Could not verify"},
    "not_run": {"nl": "Niet gemeten", "en": "Not measured"},
}

EFFORT: dict[str, dict[Lang, str]] = {
    "S": {"nl": "weinig", "en": "small"},
    "M": {"nl": "gemiddeld", "en": "medium"},
    "L": {"nl": "veel", "en": "large"},
}

STAGE: dict[str, dict[Lang, str]] = {
    "access": {"nl": "1. Vinden en bereiken", "en": "1. Find and reach"},
    "product_data": {"nl": "2. Begrijpen", "en": "2. Understand"},
    "checkout": {"nl": "3. Afrekenen", "en": "3. Check out"},
    "protocols": {"nl": "4. Aansluiten", "en": "4. Connect"},
}

STAGE_QUESTION: dict[str, dict[Lang, str]] = {
    "access": {
        "nl": "Kan een AI-agent je producten vinden, je shop bereiken en je pagina's lezen?",
        "en": "Can an AI agent find your products, reach your shop and read your pages?",
    },
    "product_data": {
        "nl": "Begrijpt een agent precies wat je verkoopt, voor welke prijs, hoe het "
        "geleverd wordt en wie de verkoper is?",
        "en": "Does an agent understand exactly what you sell, at what price, how it is "
        "delivered and who the seller is?",
    },
    "checkout": {
        "nl": "Komt een agent van product tot checkout, en met een Nederlandse betaalmethode?",
        "en": "Can an agent get from product to checkout, with a Dutch payment method?",
    },
    "protocols": {
        "nl": "Is je shop aangesloten op de protocollen waarmee agents straks rechtstreeks "
        "bestellen?",
        "en": "Is your shop connected to the protocols agents will use to order directly?",
    },
}

# "Why it matters" per in-scope check: what goes wrong for an agent order. Factual only.
WHY: dict[str, dict[Lang, str]] = {
    "D1.robots_ai_crawlers": {
        "nl": "Een agent die namens een klant winkelt, haalt je pagina's op met een eigen bot "
        "(bijv. ChatGPT-User of Claude-User). Blokkeert robots.txt die bot, dan kan de agent "
        "je producten niet bekijken en dus ook niet bij jou bestellen.",
        "en": "An agent shopping for a customer fetches your pages with its own bot (e.g. "
        "ChatGPT-User or Claude-User). If robots.txt blocks that bot, the agent cannot see "
        "your products, so it cannot order from you.",
    },
    "D2.edge_blocking": {
        "nl": "Ook als robots.txt het toestaat, kan je CDN of firewall agents tegenhouden met "
        "een blokkade of een uitdaging. Een agent lost geen captcha op en haakt dan af.",
        "en": "Even when robots.txt allows it, your CDN or firewall can stop agents with a "
        "block or a challenge. An agent does not solve captchas and gives up.",
    },
    "D3.sitemap": {
        "nl": "AI-zoekmachines vinden je productpagina's via je sitemap. Een actuele sitemap "
        "met alle producten en een wijzigingsdatum zorgt dat nieuwe producten en "
        "prijswijzigingen snel bij agents bekend zijn.",
        "en": "AI search engines find your product pages through your sitemap. An up-to-date "
        "sitemap listing every product with a change date means new products and price "
        "changes reach agents quickly.",
    },
    "D4.rendering": {
        "nl": "Veel agents lezen de HTML die je server stuurt en voeren geen JavaScript uit. "
        "Verschijnen prijs en voorraad pas na JavaScript, dan weet de agent niet wat het "
        "product kost of dat het leverbaar is.",
        "en": "Many agents read the HTML your server sends and do not run JavaScript. If "
        "price and stock only appear after JavaScript, the agent does not know what the "
        "product costs or whether it is in stock.",
    },
    "S1.product_jsonld": {
        "nl": "Gestructureerde productgegevens (JSON-LD) vertellen een agent ondubbelzinnig "
        "welk product dit is. Zonder deze gegevens moet de agent het uit de paginatekst "
        "afleiden, met kans op fouten.",
        "en": "Structured product data (JSON-LD) tells an agent unambiguously which product "
        "this is. Without it the agent has to infer it from page text, which is error-prone.",
    },
    "S2.offer": {
        "nl": "Een agent bestelt alleen als prijs, valuta en voorraad vaststaan. Ontbreken die "
        "in het aanbod (Offer), dan kan hij de bestelling niet betrouwbaar voorbereiden.",
        "en": "An agent only orders when price, currency and stock are certain. If the offer "
        "(Offer) lacks them, it cannot prepare the order reliably.",
    },
    "S3.identifiers": {
        "nl": "Met een GTIN (EAN) of MPN plus merk koppelt een agent je product aan wat de "
        "klant zoekt en vergelijkt hij het met andere winkels. Zonder deze codes valt je "
        "aanbod sneller af.",
        "en": "With a GTIN (EAN) or MPN plus brand, an agent matches your product to what the "
        "customer wants and compares it with other shops. Without these codes your offer is "
        "more easily dropped.",
    },
    "S4.shipping_returns": {
        "nl": "Een agent moet de klant vóór de bestelling de totaalprijs en de "
        "retourvoorwaarden kunnen noemen. Staan verzendkosten en retourtermijn in de "
        "productdata, dan kan dat direct.",
        "en": "Before ordering, an agent must be able to tell the customer the total price "
        "and the return terms. With shipping cost and return window in the product data, it "
        "can do so directly.",
    },
    "S5.reviews": {
        "nl": "Agents vergelijken winkels en producten, ook op beoordelingen. Staan je "
        "reviews als gestructureerde gegevens (aggregateRating) op de pagina, dan kan een "
        "agent ze meewegen; anders tellen ze niet mee.",
        "en": "Agents compare shops and products, including on ratings. If your reviews are "
        "in the page as structured data (aggregateRating), an agent can take them into "
        "account; otherwise they do not count.",
    },
    "S6.organization": {
        "nl": "Een agent moet weten bij wie hij bestelt: naam, logo, contactgegevens en "
        "KvK- of btw-nummer als gestructureerde gegevens maken je shop herkenbaar en "
        "betrouwbaar als verkoper. Agent-checkouts vragen ook om de gegevens van de verkoper.",
        "en": "An agent needs to know who it is ordering from: name, logo, contact details "
        "and Chamber of Commerce or VAT number as structured data make your shop "
        "recognisable and trustworthy as a seller. Agent checkouts also ask for seller "
        "details.",
    },
    "D5.merchant_center": {
        "nl": "Google haalt producten voor zijn AI-zoekfuncties uit je Merchant Center-feed. "
        "Een actieve feed zonder afgekeurde producten is de basis om daar te verschijnen, "
        "nu en wanneer afrekenen via Google beschikbaar komt.",
        "en": "Google takes products for its AI search features from your Merchant Center "
        "feed. An active feed without disapproved products is the basis for appearing there, "
        "now and when checkout via Google becomes available.",
    },
    "C1.add_to_cart": {
        "nl": "Browser-agents bestellen door je site te bedienen zoals een klant dat doet. "
        "Werkt 'in winkelwagen' niet zonder captcha of uitdaging, dan stopt de bestelling "
        "bij de eerste stap.",
        "en": "Browser agents order by operating your site the way a customer does. If 'add "
        "to cart' does not work without a captcha or challenge, the order stops at step one.",
    },
    "C2.guest_checkout": {
        "nl": "Een agent kan meestal geen account voor de klant aanmaken. Afrekenen als gast "
        "houdt de weg naar de bestelling open.",
        "en": "An agent usually cannot create an account for the customer. Guest checkout "
        "keeps the path to the order open.",
    },
    "C3.payment_methods": {
        "nl": "AI-agents betalen met kaarttokens: OpenAI's agent-checkout (ACP) en Google's "
        "UCP-checkout werken met kaarten (ook via Google Pay), net als de agentbetalingen van "
        "Visa en Mastercard. De meeste Nederlandse klanten betalen online met iDEAL (dat "
        "overgaat in Wero). Je hebt dus allebei nodig.",
        "en": "AI agents pay with card tokens: OpenAI's agent checkout (ACP) and Google's UCP "
        "checkout work with cards (also via Google Pay), as do Visa's and Mastercard's agent "
        "payments. Most Dutch customers pay online with iDEAL (which is moving to Wero). So "
        "you need both.",
    },
    "C4.captcha_checkout": {
        "nl": "Een captcha bij de start van de checkout houdt elke agent tegen, ook die van "
        "een echte klant.",
        "en": "A captcha at checkout entry stops every agent, including one acting for a real "
        "customer.",
    },
    "C5.policies_clear": {
        "nl": "Klanten vragen een agent naar levertijd, verzendkosten en retour. Staat dat in "
        "duidelijke tekst op je beleidspagina's, dan kan de agent het beantwoorden voordat "
        "hij bestelt.",
        "en": "Customers ask an agent about delivery time, shipping cost and returns. If your "
        "policy pages state this plainly, the agent can answer before it orders.",
    },
    "P1.ucp_profile": {
        "nl": "UCP (Universal Commerce Protocol) is een open standaard waarmee AI-agents "
        "rechtstreeks bij een shop kunnen bestellen. Het profiel op /.well-known/ucp vertelt "
        "agents wat je shop ondersteunt.",
        "en": "UCP (Universal Commerce Protocol) is an open standard that lets AI agents "
        "order directly from a shop. The profile at /.well-known/ucp tells agents what your "
        "shop supports.",
    },
    "P2.platform_support": {
        "nl": "Platforms bieden of ontwikkelen kanalen en plugins voor agent-bestellingen. Of "
        "jouw platform er een heeft, bepaalt hoeveel werk aansluiten kost.",
        "en": "Platforms offer or are building channels and plugins for agent orders. Whether "
        "yours has one decides how much work connecting takes.",
    },
    "P3.mcp_or_feed_endpoint": {
        "nl": "Met een MCP-endpoint of agent-feed vragen agents je assortiment rechtstreeks "
        "op, zonder pagina's te lezen. Dit is nog in ontwikkeling; we tellen het als "
        "voorbereiding, nooit als fout.",
        "en": "With an MCP endpoint or agent feed, agents query your catalogue directly "
        "without reading pages. This is still emerging; we count it as preparation, never "
        "as a failure.",
    },
}

# Dutch check labels; English comes from the registry label.
LABEL_NL: dict[str, str] = {
    "D1.robots_ai_crawlers": "AI-bots toegestaan in robots.txt",
    "D2.edge_blocking": "AI-bots niet geblokkeerd door CDN/firewall",
    "D3.sitemap": "Geldige sitemap met product-URL's",
    "D4.rendering": "Prijs en voorraad zonder JavaScript leesbaar",
    "D5.merchant_center": "Google Merchant Center-feed gezond",
    "S1.product_jsonld": "Productgegevens als JSON-LD",
    "S2.offer": "Prijs, valuta en voorraad in de productdata",
    "S3.identifiers": "EAN/GTIN of MPN + merk",
    "S4.shipping_returns": "Verzendkosten en retourbeleid in de productdata",
    "S5.reviews": "Reviewmarkup (aggregateRating)",
    "S6.organization": "Organization / OnlineStore-markup",
    "C1.add_to_cart": "In winkelwagen werkt voor een agent",
    "C2.guest_checkout": "Afrekenen als gast mogelijk",
    "C3.payment_methods": "Kaarten en iDEAL / Wero aangeboden",
    "C4.captcha_checkout": "Geen captcha bij start checkout",
    "C5.policies_clear": "Levertijd, verzendkosten en retour duidelijk vermeld",
    "P1.ucp_profile": "UCP-profiel op /.well-known/ucp",
    "P2.platform_support": "Agent-kanaal voor je platform",
    "P3.mcp_or_feed_endpoint": "MCP-endpoint of agent-feed",
    "V1.prompt_visibility": "Genoemd door AI-assistenten",
}


def t(table: dict[str, dict[Lang, str]], key: str, lang: Lang) -> str:
    entry = table.get(key, {})
    return entry.get(lang) or entry.get("en") or key


def label(check_id: str, fallback: str, lang: Lang) -> str:
    return LABEL_NL.get(check_id, fallback) if lang == "nl" else fallback

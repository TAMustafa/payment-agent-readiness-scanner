"""Report UI strings, NL with EN fallback (SPEC §5). Fix guidance lives in checks/copy.

Copy rules (CLAUDE.md): templated, no fabricated facts, and never claim that agent
checkout is live for Dutch merchants (it is not, as of Nov 2026).
"""

from __future__ import annotations

from typing import Literal

Lang = Literal["nl", "en"]

UI: dict[str, dict[Lang, str]] = {
    "title": {"nl": "Rapport AI-agent-gereedheid", "en": "AI agent readiness report"},
    "scanned": {"nl": "Gescand op", "en": "Scanned on"},
    "platform": {"nl": "Platform", "en": "Platform"},
    "summary": {"nl": "Samenvatting", "en": "Summary"},
    "score_of": {"nl": "van 100", "en": "out of 100"},
    "no_score": {
        "nl": "Geen score: er was niets dat we betrouwbaar konden meten.",
        "en": "No score: nothing could be measured reliably.",
    },
    "counted": {
        "nl": "{n} checks meegeteld in de score.",
        "en": "{n} checks counted in the score.",
    },
    "excluded": {
        "nl": "{n} niet meegeteld (niet van toepassing of niet te controleren); de score is "
        "herberekend over de rest.",
        "en": "{n} not counted (not applicable or could not be verified); the score is "
        "re-normalised over the rest.",
    },
    "not_run": {
        "nl": "Niet uitgevoerd in deze scan: {ids}.",
        "en": "Not run in this scan: {ids}.",
    },
    "by_category": {"nl": "Score per onderdeel", "en": "Score per area"},
    "measured": {"nl": "{n}/{m} gemeten", "en": "{n}/{m} measured"},
    "top_fixes": {"nl": "Top {n} verbeterpunten", "en": "Top {n} fixes"},
    "top_fixes_intro": {
        "nl": "Gesorteerd op wat het meeste oplevert per hoeveelheid werk.",
        "en": "Sorted by what gains the most per amount of work.",
    },
    "no_fixes": {
        "nl": "Geen verbeterpunten gevonden in de gemeten checks.",
        "en": "No fixes found in the checks that were measured.",
    },
    "gain": {"nl": "tot +{n} punten", "en": "up to +{n} points"},
    "effort": {"nl": "Inspanning", "en": "Effort"},
    "details": {"nl": "Resultaten per check", "en": "Results per check"},
    "evidence": {"nl": "Bewijs", "en": "Evidence"},
    "evidence_lang": {
        "nl": "Technisch bewijs staat in het Engels, zodat je bouwer of platform het direct "
        "kan nalopen.",
        "en": "Technical evidence is in English so your developer or platform can verify it.",
    },
    "more_evidence": {
        "nl": "… en {n} regels meer in report.json.",
        "en": "… and {n} more lines in report.json.",
    },
    "how_to_fix": {"nl": "Zo los je het op", "en": "How to fix"},
    "weight": {"nl": "weegt {n} van 100", "en": "weight {n} of 100"},
    "coming": {
        "nl": "Wat eraan komt: afrekenen via AI-agents",
        "en": "What's coming: agent checkout",
    },
    "coming_body": {
        "nl": "Afrekenen binnen AI-assistenten (agentic checkout via protocollen als ACP en "
        "UCP) is nog niet beschikbaar voor Nederlandse webshops. De checks in 'Checkout voor "
        "browser-agents' en 'Agent-protocollen' meten hoe goed je shop voorbereid is op het "
        "moment dat dit wel beschikbaar komt. Gevonden en aanbevolen worden door "
        "AI-assistenten (de onderdelen vindbaarheid, productdata en zichtbaarheid) telt nu "
        "al.",
        "en": "Checkout inside AI assistants (agentic checkout via protocols such as ACP and "
        "UCP) is not yet available to Dutch webshops. The 'Checkout for browser agents' and "
        "'Agent protocols' checks measure how ready your shop is for when it launches. Being "
        "found and recommended by AI assistants (discovery, product data and visibility) "
        "matters today.",
    },
    "method": {"nl": "Methode en beperkingen", "en": "Methodology and limitations"},
    "m_readonly": {
        "nl": "Alleen-lezen: we hebben niets ingevuld, geen account aangemaakt, niet "
        "ingelogd, niets besteld en geen betaling gestart.",
        "en": "Read-only: we filled in nothing, created no account, did not log in, ordered "
        "nothing and started no payment.",
    },
    "m_sample": {
        "nl": "Steekproef: {products} productpagina's en {categories} categoriepagina's, "
        "{requests} verzoeken in totaal, maximaal 1 per seconde, met inachtneming van "
        "robots.txt. Productdata-checks gelden voor deze steekproef, niet voor elke pagina.",
        "en": "Sample: {products} product pages and {categories} category pages, {requests} "
        "requests in total, at most 1 per second, respecting robots.txt. Product data "
        "checks apply to this sample, not to every page.",
    },
    "m_d2": {
        "nl": "Bottoegang (D2): onze testverzoeken sturen de User-Agent van elke AI-bot mét "
        "onze eigen identificatie mee; we doen ons nooit voor als die bot. Echte bots komen "
        "van hun eigen IP-adressen en kunnen door je CDN anders behandeld worden.",
        "en": "Bot access (D2): our test requests send each AI bot's User-Agent together "
        "with our own identity; we never impersonate the bot. Real bots come from their own "
        "IP addresses and your CDN may treat them differently.",
    },
    "m_checkout_on": {
        "nl": "Checkout-test: een headless browser heeft één product in een anonieme "
        "winkelwagen gelegd en is gestopt bij het eerste checkout-scherm, zonder iets in te "
        "typen.",
        "en": "Checkout test: a headless browser put one product in an anonymous cart and "
        "stopped at the first checkout screen, without typing anything.",
    },
    "m_checkout_off": {
        "nl": "Checkout-test: niet uitgevoerd (alleen met toestemming); C1, C2 en C4 staan "
        "daarom op 'niet van toepassing'.",
        "en": "Checkout test: not run (only with permission), so C1, C2 and C4 are 'not "
        "applicable'.",
    },
    "m_v1_on": {
        "nl": "AI-zichtbaarheid (V1) is een momentopname: we stelden vaste Nederlandse "
        "koopvragen aan {assistants} met hun eigen webzoekfunctie, {runs}x. "
        "Antwoorden wisselen per keer en over tijd en zijn niet identiek aan de "
        "consumentenapps.",
        "en": "AI visibility (V1) is a snapshot: we asked fixed Dutch buying questions to "
        "{assistants} with their own web search, {runs}x. Answers vary per run and over "
        "time and are not identical to the consumer apps.",
    },
    "m_v1_off": {
        "nl": "AI-zichtbaarheid (V1) is in deze scan niet gemeten.",
        "en": "AI visibility (V1) was not measured in this scan.",
    },
    "m_score": {
        "nl": "Score: som van (gewicht x behaalde fractie) over de gemeten checks, "
        "herberekend naar 100. 80+ = Klaar, 60-79 = Deels klaar, onder 60 = Niet klaar.",
        "en": "Score: sum of (weight x fraction achieved) over the measured checks, "
        "re-normalised to 100. 80+ = Ready, 60-79 = Partly ready, below 60 = Not ready.",
    },
    "m_platform": {
        "nl": "Platformondersteuning voor agent-kanalen verandert maandelijks; onze tabel "
        "is gecontroleerd op {date}.",
        "en": "Platform support for agent channels changes monthly; our table was verified "
        "on {date}.",
    },
    "notes": {"nl": "Opmerkingen bij deze scan", "en": "Notes on this scan"},
    "footer": {
        "nl": "Gemaakt met {brand} {version}. Volledige gegevens: report.json.",
        "en": "Made with {brand} {version}. Full data: report.json.",
    },
}

GRADE: dict[str, dict[Lang, str]] = {
    "Ready": {"nl": "Klaar", "en": "Ready"},
    "Partly ready": {"nl": "Deels klaar", "en": "Partly ready"},
    "Not ready": {"nl": "Niet klaar", "en": "Not ready"},
}

STATUS: dict[str, dict[Lang, str]] = {
    "pass": {"nl": "Goed", "en": "Pass"},
    "warn": {"nl": "Aandacht", "en": "Warning"},
    "fail": {"nl": "Onvoldoende", "en": "Fail"},
    "not_applicable": {"nl": "Niet van toepassing", "en": "Not applicable"},
    "error": {"nl": "Niet te controleren", "en": "Could not verify"},
    "not_run": {"nl": "Niet uitgevoerd", "en": "Not run"},
}

EFFORT: dict[str, dict[Lang, str]] = {
    "S": {"nl": "klein", "en": "small"},
    "M": {"nl": "middel", "en": "medium"},
    "L": {"nl": "groot", "en": "large"},
}

CATEGORY: dict[str, dict[Lang, str]] = {
    "discovery": {"nl": "Vindbaarheid en toegang", "en": "Discovery and access"},
    "data": {"nl": "Gestructureerde productdata", "en": "Structured product data"},
    "checkout": {"nl": "Checkout voor browser-agents", "en": "Checkout for browser agents"},
    "protocol": {"nl": "Agent-protocollen", "en": "Agent protocols"},
    "visibility": {"nl": "Zichtbaarheid in AI-assistenten", "en": "Visibility in AI assistants"},
}

# Dutch check labels; English comes from the registry label.
LABEL_NL: dict[str, str] = {
    "D1.robots_ai_crawlers": "AI-crawlers toegestaan in robots.txt",
    "D2.edge_blocking": "AI-bots niet geblokkeerd door CDN/firewall",
    "D3.sitemap": "Geldige sitemap met product-URL's",
    "D4.rendering": "Productgegevens in de HTML (zonder JavaScript)",
    "D5.merchant_center": "Google Merchant Center-feed gezond",
    "S1.product_jsonld": "Product-JSON-LD aanwezig en geldig",
    "S2.offer": "Aanbod met prijs, valuta en voorraad",
    "S3.identifiers": "GTIN / MPN + merk",
    "S4.shipping_returns": "Verzend- en retourbeleid in markup",
    "S5.reviews": "Reviewmarkup (aggregateRating)",
    "S6.organization": "Organization / OnlineStore-markup",
    "C1.add_to_cart": "In winkelwagen werkt headless",
    "C2.guest_checkout": "Afrekenen als gast mogelijk",
    "C3.payment_methods": "iDEAL / Wero aangeboden",
    "C4.captcha_checkout": "Geen captcha bij start checkout",
    "C5.policies_clear": "Verzending en retour duidelijk vermeld",
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

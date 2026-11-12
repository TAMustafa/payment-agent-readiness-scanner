"""Text / HTML markers used by the checkout probe and C-checks (NL + EN). Pure functions."""

from __future__ import annotations

import re

# --- buttons -----------------------------------------------------------------------------
REJECT_COOKIES = re.compile(
    r"\b(alles weigeren|weigeren|weiger|alleen (functionele|noodzakelijke)|"
    r"alleen noodzakelijk|noodzakelijke cookies|reject( all)?|decline|deny|only necessary|"
    r"necessary only)\b",
    re.I,
)
ACCEPT_COOKIES = re.compile(
    r"\b(alles accepteren|accepteren|accepteer|akkoord|alle cookies toestaan|toestaan|"
    r"accept( all)?|allow( all)?|agree|ok(é)?)\b",
    re.I,
)
# Stock CMP button selectors (OneTrust, Cookiebot, CookieYes, Complianz, Usercentrics).
REJECT_SELECTORS = (
    "#onetrust-reject-all-handler",
    "#CybotCookiebotDialogBodyButtonDecline",
    ".cky-btn-reject",
    ".cmplz-deny",
    "button[data-testid='uc-deny-all-button']",
)
ACCEPT_SELECTORS = (
    "#onetrust-accept-btn-handler",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    ".cky-btn-accept",
    ".cmplz-accept",
    "button[data-testid='uc-accept-all-button']",
)
CLOSE_POPUP = re.compile(r"^(sluiten|sluit|close|\u00d7|x|nee,? bedankt|no,? thanks)$", re.I)

ADD_TO_CART = re.compile(
    r"(in (de |het |mijn )?(winkel(wagen|mand|mandje|tje)|mandje)|toevoegen( aan)?|"
    r"add to (cart|bag|basket)|in winkelwagen|leg in (winkelmand|mandje))",
    re.I,
)
# "Toevoegen aan verlanglijst" also says "toevoegen": never an add-to-cart button.
NOT_ADD_TO_CART = re.compile(
    r"(verlang|wens|wish|favor|vergelijk|compare|review|beoordeling|lijst\b|\blist\b)", re.I
)
CHECKOUT = re.compile(
    r"(afrekenen|naar de kassa|verder naar (afrekenen|bestellen)|doorgaan naar (afrekenen|"
    r"bestellen|de kassa)|veilig afrekenen|check ?out|proceed to checkout|bestellen)",
    re.I,
)
# Never click these: express/one-click payment buttons and anything that places an order.
FORBIDDEN_CLICK = re.compile(
    r"(paypal|apple ?pay|google ?pay|shop ?pay|klarna|amazon ?pay|betaal|betal|pay now|"
    r"plaats bestelling|bestelling (plaatsen|afronden|bevestigen)|bestellen en betalen|"
    r"place order|complete (order|purchase)|koop nu|buy (it )?now|bevestig|confirm|"
    r"inloggen|log ?in|sign ?in|registr|account aanmaken|create account)",
    re.I,
)

# --- hard safety guards (network level) ---------------------------------------------------
# Payment service providers and iDEAL/bank hosts: the probe never talks to them at all.
PAYMENT_HOSTS = re.compile(
    r"(^|\.)(mollie\.com|adyen\.com|adyenpayments\.com|stripe\.com|stripe\.network|"
    r"paypal\.com|paypalobjects\.com|braintreegateway\.com|klarna\.com|klarnaservices\.com|"
    r"buckaroo\.nl|multisafepay\.com|pay\.nl|payvision\.com|icepay\.com|sisow\.nl|"
    r"worldline\.com|ogone\.com|ccv\.eu|checkout\.com|riverty\.com|afterpay\.nl|"
    r"ideal\.nl|ideal2\.nl|currencenetworks\.com|ing\.nl|rabobank\.nl|abnamro\.nl|"
    r"snsbank\.nl|asnbank\.nl|regiobank\.nl|triodos\.nl|knab\.nl|bunq\.com|"
    r"wero-wallet\.eu|shop\.app|pay\.shopify\.com|shopifycs\.com|"
    # wallets: Google Pay, Amazon Pay, Apple Pay merchant sessions
    r"pay\.google\.com|payments\.google\.com|pay(ments)?\.amazon\.[a-z.]{2,6}|"
    r"payments-amazon\.com|amazonpay\.com|apple-pay-gateway(-cert)?\.apple\.com|"
    r"in3\.nl|billink\.nl|payplug\.com|worldpay\.com)$",
    re.I,
)
# Paths that place, pay or confirm an order: never requested, whatever the method. Matched
# against path + query string (WooCommerce places orders through `?wc-ajax=checkout`).
ORDER_PATHS = re.compile(
    r"(place[-_]?order|save[-_]?order|order[-_/]?(confirm|complete|submit|place|received|pay)|"
    r"wc-ajax=checkout|/payment|/pay([/?]|$)|"
    r"/processing|/thank[-_]?you|bestelling[-_/]?(plaatsen|afronden)|/betaling|/betalen|"
    r"checkout/(confirm|finish|submit|complete|onepage/success)|/checkouts/.+/(processing|"
    r"thank_you|payments))",
    re.I,
)
CART_EMPTY = re.compile(
    r"(winkel(wagen|mand|mandje)( is)? leeg|je (winkel(wagen|mand|mandje)|mandje) is leeg|"
    r"(your )?(cart|bag|basket) is empty|geen (producten|artikelen) in)",
    re.I,
)

# --- checkout page -----------------------------------------------------------------------
GUEST = re.compile(
    r"(als gast|gast(bestelling| bestellen| afrekenen)|zonder (een )?account|doorgaan als gast|"
    r"guest checkout|continue as guest|checkout as guest|bestellen zonder)",
    re.I,
)
LOGIN = re.compile(r"(inloggen|log in|aanmelden|sign in|wachtwoord|password)", re.I)

CAPTCHA_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("reCAPTCHA", re.compile(r"google\.com/recaptcha|recaptcha/api\.js|g-recaptcha", re.I)),
    ("hCaptcha", re.compile(r"hcaptcha\.com|h-captcha", re.I)),
    (
        "Cloudflare Turnstile",
        re.compile(r"challenges\.cloudflare\.com/turnstile|cf-turnstile", re.I),
    ),
    ("Friendly Captcha", re.compile(r"friendlycaptcha|frc-captcha", re.I)),
    ("AWS WAF captcha", re.compile(r"awswaf.*captcha|captcha\.awswaf", re.I)),
)

# A captcha a visitor actually has to solve: a visible widget or challenge frame. Script
# tags / class names alone (CAPTCHA_MARKERS) are not enough before checkout: many shops load
# invisible reCAPTCHA (v3, or v2 size=invisible with only a corner badge) site-wide for their
# forms, and visitors never see a challenge (false C1 fail on fixje.nl, 2026-11-10).
# Playwright CSS with the :visible pseudo-class.
VISIBLE_CAPTCHA: tuple[tuple[str, str], ...] = (
    (
        "reCAPTCHA",
        "iframe[src*='recaptcha'][src*='anchor']:not([src*='size=invisible']):visible, "
        "iframe[src*='recaptcha'][src*='bframe']:visible",
    ),
    ("hCaptcha", "iframe[src*='hcaptcha.com']:visible"),
    (
        "Cloudflare Turnstile",
        ".cf-turnstile:visible, iframe[src*='challenges.cloudflare.com']:visible",
    ),
    ("Friendly Captcha", ".frc-captcha:visible"),
)

# --- payment methods (text, img alt/src/title) ------------------------------------------
PAYMENT_METHODS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("iDEAL", re.compile(r"\bideal\b", re.I)),
    ("Wero", re.compile(r"\bwero\b", re.I)),
    ("Bancontact", re.compile(r"bancontact", re.I)),
    ("PayPal", re.compile(r"paypal", re.I)),
    ("Klarna", re.compile(r"klarna", re.I)),
    ("Riverty/AfterPay", re.compile(r"riverty|afterpay", re.I)),
    ("Apple Pay", re.compile(r"apple[\s_-]?pay", re.I)),
    ("Google Pay", re.compile(r"google[\s_-]?pay|gpay", re.I)),
    ("Visa", re.compile(r"\bvisa\b", re.I)),
    ("Mastercard", re.compile(r"mastercard|maestro", re.I)),
    ("American Express", re.compile(r"american[\s_-]?express|\bamex\b", re.I)),
)


def payment_methods_in(text: str) -> list[str]:
    return [name for name, rx in PAYMENT_METHODS if rx.search(text)]


def captcha_in(html: str) -> list[str]:
    return [name for name, rx in CAPTCHA_MARKERS if rx.search(html)]


def payment_haystack(html: str) -> str:
    """Visible text plus img alt/src/title and class names, where payment logos live."""
    from scanner.parse.html import parse
    from scanner.parse.product import visible_text

    tree = parse(html)
    bits = [visible_text(html)]
    for node in tree.css("img, svg, use, [class*=payment], [class*=betaal]"):
        a = node.attributes
        bits += [a.get(k) or "" for k in ("alt", "src", "title", "class", "href", "aria-label")]
    return " ".join(bits)

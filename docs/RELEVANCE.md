# Relevance review: do the checks measure agentic payments and merchant discovery?

Review date 2026-11-10, requested by Tarek. Sources were read via web search on that date; most
are secondary (vendor blogs, trade press). Primary sources are marked **[primary]**. Re-check
before each release — this field changes monthly.

## Market status (what the report may claim)
- **Checkout inside an AI assistant is not available to Dutch webshops.** Google's UCP checkout
  in AI Mode / Gemini is live in the US for selected merchants; Europe is announced without a
  date (a Nexi–Google Cloud MoU covers UCP/AP2 in Europe). ChatGPT Instant Checkout (ACP) was
  US-only and was ended as a standalone product in March 2026; ChatGPT now sends buyers to the
  merchant's own checkout. → The report's intro sentence stays correct.
- **Agent payments on the merchant's own site are starting in Europe.** Visa's Agentic Ready
  programme: agent-initiated card payments live at 30+ European issuers since July 2026, at
  participating merchants, with Visa's Trusted Agent Protocol / Agent Directory (deployed via
  Cloudflare and Akamai) to recognise verified agents, and payment passkeys for SCA. Mastercard
  Agent Pay uses agentic tokens; first European live payment early 2026. No source names
  Dutch merchants. **CLAUDE.md's "not live for Dutch merchants" should be read as "checkout
  inside assistants"; card-network agent payments on merchant sites exist in Europe.**
- **iDEAL / Wero:** iDEAL is migrating to Wero (2026–2027). Agentic protocols assume card
  rails; iDEAL is a bank redirect an agent cannot complete itself. No Wero agent product found.

## Per check
Legend: **Disc** = merchant discovery by agents, **Pay** = agent can order/pay.

| Check | Disc | Pay | Verdict |
|---|---|---|---|
| D1 robots.txt | ✔ (OAI-SearchBot, Claude-SearchBot…) | ✔ (ChatGPT-User, Claude-User fetch for a user) | Keep. |
| D2 CDN/WAF blocking | ✔ | ✔ | Keep. **Gap:** real shopping agents sign requests (Web Bot Auth, RFC 9421; Visa TAP). We send UA strings only, so we cannot test whether signed agents are allowed. Guidance now tells merchants to allow signed agents (Cloudflare "Signed agents", Akamai AI bots) [primary: help.openai.com/en/articles/11845367]. |
| D4 price/stock without JS | ✔ (crawlers without JS) | – (browser agents render JS) | Keep, as discovery. |
| S1 Product JSON-LD | ✔ | indirect | Keep. Feeds (ACP, Merchant Center) use the same fields. |
| S2 Offer price/currency/stock | ✔ | ✔ (agent needs certain price/stock) | Keep. |
| S3 GTIN/MPN + brand | ✔ (matching, comparison) | – | Keep. ACP lists gtin as recommended; Merchant Center requires it where assigned. |
| S4 shipping + returns markup | ✔ | ✔ (total price, return terms) | Keep. ACP has shipping and return-policy fields; Google asks for shipping/returns config before UCP. |
| D5 Merchant Center | ✔ | ✔ (Google UCP checkout runs on Merchant Center: account in good standing, `native_commerce` attribute) | Keep. **Under-weighted (3) and manual-only.** |
| C1 add to cart | – | ✔ (browser agents, ChatGPT now sends buyers to merchant checkout) | Keep. |
| C2 guest checkout | – | ✔ | Keep. |
| C3 cards + iDEAL / Wero | – | ✔ | **Changed 2026-11-10** (was iDEAL/Wero only): agent payments run on cards (Visa/Mastercard agentic tokens) and wallets; iDEAL/Wero matter for the Dutch customer hand-off (Google's UCP hands iDEAL buyers back to the shop). Pass should need card acceptance **and** iDEAL/Wero. The probe already records cards, PayPal, Apple/Google Pay. |
| C4 no captcha at checkout | – | ✔ | Keep. |
| C5 delivery/returns stated | ✔ | ✔ | Keep (ACP checkout eligibility also needs ToS/privacy/return policy URLs). |
| P1 UCP profile | ✔ | ✔ | Keep (Google UCP; profile at `/.well-known/ucp`, versions 2026-04-08 seen in Google docs). |
| P2 platform channel | – | ✔ | Keep. |
| P3 MCP / agent feed | ✔ | ✔ | Keep as warn-only. **Limit:** ACP feeds are pushed privately to OpenAI and cannot be seen from outside. |

Since the revision of 2026-11-10 only V1 is outside the report. D3, S5, S6 are back because,
under a *discovery* lens, they are relevant: crawlers use sitemaps; feeds and agents use ratings
(ACP has review fields); S6 carries seller identity (ACP needs seller name/ToS/privacy); V1
measures discovery directly. V1 stays a paid opt-in.

## Not measured (gaps), with what would be needed
1. **Signed-agent access** (Web Bot Auth / Visa TAP): not testable from outside without being
   the agent. Option: ask the merchant (manual input, like D5) or read their CDN setting.
2. **Card acceptance for agent payments:** fold into C3 (proposal above).
3. **ACP feed submitted to OpenAI / Merchant Center `native_commerce`:** only the merchant
   knows. Option: extend the manual inputs (`--gmc-*`) with "UCP/agentic checkout enrolled".
4. **PSP readiness** (Stripe, Adyen, Mollie support for agentic tokens): could be detected
   from checkout-page scripts. Needs research per PSP before building.

## Decisions (Tarek, 2026-11-10)
1. **C3 changed:** cards + iDEAL/Wero required ("only if agent documentation requires cards").
   It does: OpenAI's Delegated Payment Spec accepts a card ("fpan" or "network_token")
   [primary, excerpt: https://developers.openai.com/commerce/specs/payment]; Google UCP uses
   the Google Pay handler with card credentials and the merchant's PSP must process Google's
   tokens [primary, excerpt: https://developers.google.com/merchant/ucp/faq]. Only excerpts of
   these pages were read; re-read in full before the next release.
2. **Discovery back in scope:** D3 (stage 1), S5 and S6 (stage 2) are in the report again.
   V1 stays outside (paid, opt-in).
3. **D2:** guidance now tells merchants to allow signed agents (Web Bot Auth).
4. Open: D5 weight and extra manual inputs (UCP enrolment, signed-agent allowlisting).

## Sources (read 2026-11-10)
- [primary] OpenAI, publishers/developers FAQ on ChatGPT agent signing: https://help.openai.com/en/articles/11845367
- [primary] OpenAI, Buy it in ChatGPT (ACP launch, US scope): https://openai.com/index/buy-it-in-chatgpt/
- [primary] Google, Create a UCP profile: https://developers.google.com/merchant/ucp/implementation/2026-04-08/publish-profile
- [primary] UCP: https://ucp.dev
- [primary] Visa press release, Europe agentic commerce: https://www.visa.co.uk/about-visa/newsroom/press-releases.3457328.html
- ACP feed spec (docs mirror): https://agentic-commerce-protocol.pages.dev/docs/commerce/specs/feed
- Salesforce UCP integration (Merchant Center prerequisites): https://developer.salesforce.com/docs/commerce/b2c-commerce/guide/ucp-index.html
- Google UCP merchant guide: https://commercetools.com/blog/google-ucp-merchant-guide-to-agentic-commerce
- UCP/ACP/AP2 and iDEAL in NL: https://cruxdigits.nl/blog/agentic-commerce-protocols-ucp-acp-ap2/
- Instant Checkout ended: https://www.digitalsilk.com/digital-trends/digital-trends-chatgpt-ecommerce/
- Visa Europe live payments: https://paymentexpert.com/2026/07/02/visa-agentic-payments-merchants-eu/
- Mastercard Agent Pay vs Visa: https://ai2.work/blog/mastercard-agent-pay-vs-visa-intelligent-commerce-showdown
- Card-first protocols vs iDEAL: https://www.apadmi.com/en-nl/insights/agentic-commerce-in-2026-separating-the-real-from-the-hype/
- iDEAL → Wero: https://en.wikipedia.org/wiki/IDEAL

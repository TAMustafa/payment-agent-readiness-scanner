# SPEC.md — agent-ready-scanner v1

## 1. Goal and success criteria
Produce, for any public Dutch webshop URL, a scored report (0–100) with evidence and the
top 5 fixes, in under 2 minutes, without any write interaction with the shop.

v1 is done when:
- [ ] Scans complete without crash on all 5 reference shops (section 7).
- [ ] For each reference shop, every check result matches a manual verification
      (logged in `docs/VERIFY.md`); tolerance: max 1 disputed check per shop.
- [ ] Report is understandable by a non-technical merchant without explanation
      (tested with 1 real merchant).
- [ ] Cost of the visibility check is logged per scan and stays under €0.50.

## 2. Out of scope for v1
- Placing orders, logging in, or any payment step
- Merchant Center / Ads Manager API access (manual input only, see D5)
- Web UI, user accounts, database (JSON files per scan in `./scans/<host>/<timestamp>/`)
- Non-Dutch market specifics

## 3. Scan flow
1. Normalise URL, resolve redirects, record final origin and HTTPS status.
2. Fetch `robots.txt`, `sitemap.xml` (and sitemap index), `/.well-known/ucp`.
3. Fingerprint platform (section 6).
4. Sample pages: up to 8 product pages, 2 category pages, policy pages
   (shipping, returns, terms, privacy). Prefer sitemap; fall back to link crawl from home.
   Product page detection: JSON-LD `Product` (one per page), Product microdata, or
   platform URL patterns.
   *Changed 2026-11-08 (was 20 products / 3 categories):* shops that rate-limit polite
   crawlers (Shopify: HTTP 429 + Retry-After 60 after ~10 requests) must still yield data
   within the 2-minute budget. Sizes are configurable (`max_products`, `max_categories`).
5. Run checks (section 4). Static checks use raw HTML; also render 3 product pages with
   Playwright to compare (JSON-LD injected by JS is invisible to many crawlers → warn).
6. Aggregate score (section 5), render JSON + HTML report.

## 4. Check catalogue
Weights sum to 100. IDs are stable — never renumber.

### Category D — Discovery & access (30)
| ID | Check | Weight | Pass / Warn / Fail |
|---|---|---|---|
| D1.robots_ai_crawlers | robots.txt allows AI search/agent user agents on product + category paths | 10 | Pass: all allowed. Warn: training-only bots blocked (fine, note it). Fail: search/agent bots blocked |
| D2.edge_blocking | Requests with AI agent user agents get 200, not 403/429/challenge page | 8 | Fail if any search/agent UA is blocked by CDN/WAF (detect Cloudflare/Akamai challenge markers) |
| D3.sitemap | Valid sitemap reachable, referenced in robots.txt, contains product URLs, lastmod present | 5 | Partial credit per sub-criterion |
| D4.rendering | Product name, price, availability present in raw HTML (not only after JS) | 4 | Fail if price only appears after JS render |
| D5.merchant_center | Google Merchant Center feed active and healthy (manual input: yes/no + disapproval %) | 3 | not_applicable if no input provided; never guessed |

User agents to test (verify the current official list per vendor before implementing;
cite source URLs in code): OpenAI `OAI-SearchBot`, `ChatGPT-User`, `GPTBot` (training);
Perplexity `PerplexityBot`, `Perplexity-User`; Anthropic `ClaudeBot`, `Claude-User`,
`Claude-SearchBot`; Google `Googlebot` + `Google-Extended` token (training control);
Microsoft `Bingbot`; Apple `Applebot`, `Applebot-Extended`.
Classify each as `search`, `user_agent` (fetch on behalf of a user) or `training`.
Blocking `training` only = warn with neutral wording (merchant's choice).

### Category S — Structured product data (30)
Measured over sampled product pages; score = share of pages passing.
| ID | Check | Weight | Criteria |
|---|---|---|---|
| S1.product_jsonld | Valid JSON-LD `Product` with `name`, `image`, `description` | 6 | Parseable, one Product per page (or ProductGroup with variants) |
| S2.offer | `offers` with `price`, `priceCurrency`=EUR, `availability`, `url` | 8 | Price matches visible price (±0.01) |
| S3.identifiers | `gtin`/`gtin13`, `mpn` or `sku`, and `brand` | 6 | Pass ≥80% of pages have GTIN or MPN+brand |
| S4.shipping_returns | `shippingDetails` (OfferShippingDetails) and `hasMerchantReturnPolicy` on offer or Organization | 5 | Either level accepted |
| S5.reviews | `aggregateRating` with `ratingValue` + `reviewCount` where reviews are shown | 2 | not_applicable if shop shows no reviews |
| S6.organization | `Organization`/`OnlineStore` with name, url, logo, contactPoint, KvK or VAT if shown | 3 | Present on home page |

### Category C — Checkout readiness for browser agents (20)
Playwright probe: open a product page, add the cheapest in-stock simple product to cart,
open checkout. STOP before entering any personal data. Never click pay/order buttons.
| ID | Check | Weight | Criteria |
|---|---|---|---|
| C1.add_to_cart | Add-to-cart works headless without captcha or bot challenge | 5 | Fail on challenge, warn on >2 interstitials (cookie walls count once) |
| C2.guest_checkout | Checkout reachable without forced account creation | 6 | Detect login wall vs guest option |
| C3.payment_methods | iDEAL / Wero listed on checkout or payment info page; note cards, PayPal, Klarna, Apple/Google Pay | 4 | Pass if iDEAL or Wero present |
| C4.captcha_checkout | No captcha on checkout entry | 3 | Detect reCAPTCHA, hCaptcha, Turnstile markers |
| C5.policies_clear | Shipping cost/time and return window stated in plain text on policy pages | 2 | Regex for days/costs in NL + EN |
If the probe cannot reach checkout for a technical reason → `error`, not `fail`.

*Probe decisions (Tarek, 2026-11-08):*
- robots.txt is respected for every probe navigation and for the likely checkout destination
  before clicking "checkout". If disallowed, C1–C4 are `not_applicable` ("not tested").
  `--checkout-consent` lifts this only for scans the merchant asked for.
- Page loads: images, fonts, media and known trackers are blocked; >= 1 s between
  navigations via the shared per-host limiter (incl. Retry-After); each navigation counts
  against the page budget.
- Cookie banners: click reject / "alleen noodzakelijk" first; only if absent, accept (counted
  as one interstitial).
- The probe runs before the check fan-out, so C-checks are plain functions over its data.
- C3: privacy pages are not a source (they list processors); `fail` only when the checkout
  page itself was seen without iDEAL/Wero, otherwise `warn`.
- The probe is **opt-in** (`--checkout`, or `--checkout-consent` for merchant-requested
  scans); default scans report C1, C2 and C4 as "not tested".
- D2 test requests carry the bot's User-Agent plus our own identity (no impersonation).

### Category P — Agent protocols (10)
| ID | Check | Weight | Criteria |
|---|---|---|---|
| P1.ucp_profile | `/.well-known/ucp` returns valid JSON profile | 5 | Validate against current spec at ucp.dev (fetch schema; cite version) |
| P2.platform_support | Platform has an available agentic channel/plugin (lookup table, section 6) | 3 | Informational scoring: pass if enabled, warn if available but not enabled |
| P3.mcp_or_feed_endpoint | Public MCP endpoint or agent-readable product feed discoverable | 2 | warn, never fail, in v1 (emerging) |
Report copy must state: agent checkout via ACP/UCP is not yet live in NL; P-checks
measure readiness for launch.

### Category V — AI visibility (10)
| ID | Check | Weight | Criteria |
|---|---|---|---|
| V1.prompt_visibility | Shop mentioned for N buying prompts across ≥2 assistants with web search | 10 | Score = mention rate; record position + cited URL |
Inputs: 10 prompts, generated from shop category + 2 brand prompts + 8 non-brand
(Dutch language, e.g. "beste e-bike accu kopen nederland"). Operator can override prompts.
Implement as a LangGraph subgraph (prompt generation -> parallel assistant calls via Send -> parse mentions). Store raw responses. Run 2x and report both runs (results are non-deterministic).
Mark clearly as "snapshot, varies over time". Behind `--visibility` flag (costs money).

## 5. Scoring and report
- Score = Σ(weight × scoreFraction) over checks not `not_applicable`/`error`,
  re-normalised to 100. Show how many checks were excluded.
- Grade: ≥80 Ready · 60–79 Partly ready · <60 Not ready.
- Top 5 fixes: sort failing/warning checks by (weight × (1−scoreFraction)) / effortFactor
  (S=1, M=2, L=3).
- Report sections: summary + score, top 5 fixes, category details with evidence,
  "what's coming" (agent checkout in NL), methodology + limitations.
- Language: Dutch report with English fallback; all guidance strings stored per check in
  `scanner/checks/copy/` with `nl` and `en`.
- Outputs: `report.json` (validated by pydantic) and `report.html` (self-contained, printable).

## 6. Platform fingerprinting and support table
Detect via headers, generator meta, asset paths, cookies:
Shopify (`cdn.shopify.com`, `Shopify.theme`), WooCommerce (`wp-content/plugins/woocommerce`,
`woocommerce` body class), Shopware 6 (`/bundles/storefront`, `sw-` classes), Lightspeed eCom
(`cdn.webshopapp.com`), Magento/Adobe Commerce (`Magento_`, `mage/`), other.

Support table (`scanner/platform/support.py`, each row with source URL + date verified):
- Shopify: Agentic Storefronts — US/CA shipping requirement noted; most NL-only shops ineligible
- WooCommerce: third-party UCP plugins exist (quality varies — recommend staging)
- Shopware 6: official "Agentic Commerce (Beta)" plugin (stability issues reported)
- Lightspeed / Magento: no native channel known; feed-based approach
Re-verify this table before each release; it changes monthly.

*Verification 2026-11-08 (implemented in `scanner/platform/support.py`, sources cited there)
differs from the rows above:*
- Shopify: "enabled automatically for eligible stores"; criteria and NL availability are not
  stated publicly. No source confirmed a US/CA shipping requirement. Shopify serves a UCP
  profile at `/.well-known/ucp` when enabled (seen live on a Dutch Shopify shop).
- WooCommerce: no official agentic checkout; Woo reports testing partner solutions (Stripe
  ACP, Google). Third-party UCP plugins on wordpress.org not yet reviewed.
- Shopware 6: no official Shopware AG "Agentic Commerce" plugin found; a third-party
  extension (great2gether, "Great Agentic Commerce") exports AI feeds + llms.txt and does
  not sell inside AI chats.
- Magento/Adobe: sources could not be read; marked "unknown".
- Shopify's old Storefront MCP endpoint `/api/mcp` was removed; MCP now via UCP
  (`/api/ucp/mcp`).

## 7. Reference shops for verification
Pick 5 public Dutch shops, one per platform (Shopify, WooCommerce, Shopware, Lightspeed,
Magento), ideally in the chosen niche. Record them in `docs/VERIFY.md` with the date.
Do not hard-code them in source.

## 8. Build steps
1. **CLI + static checks**: project setup (uv, LangGraph skeleton graph with stub nodes first), fetch layer, robots, sitemap, sampling,
   platform fingerprint, D1–D4, S1–S6, P1–P3, JSON output. Verify on fixtures + 5 shops.
2. **Checkout probe**: Playwright, C1–C5, screenshots saved as evidence.
3. **AI visibility**: V1 behind flag, cost logging, raw response storage.
4. **Report**: scoring, top 5 fixes, NL/EN HTML report.
5. **Web front-end** (only after pilots): URL form → queued scan → report link.

Each step ends with: tests green, VERIFY.md updated, short summary of what's verified,
how, and what is not.

## 9. Open questions (confirm with Tarek)
- Niche for the first outreach (affects default prompts in V1)
- Which assistants/APIs to use for V1 and monthly budget
- Brand name of the service for report header

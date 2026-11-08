# Verification log

## Reference shops (chosen 2026-11-08)

Platform confirmed with the scanner's own fingerprint (home page only), plus DNS for Lightspeed.
Niche is not decided yet; these are a platform spread, not a niche set. Re-confirm before each
release.

| Platform | Shop | How confirmed | Notes / alternates |
|---|---|---|---|
| Shopify | stoov.com | cdn.shopify.com, Shopify.theme, `_shopify_*` cookie; DNS `shops.myshopify.com` | Dutch scale-up on Shopify Plus. Alt: snurkamsterdam.com |
| WooCommerce | fixje.nl | WooCommerce plugin assets + body class | Redirect from fixjeiphone.nl. Alt: soxs.co (body class only) |
| Shopware 6 | duifhuizen.nl | `window.salesChannelId`, `window.themeJsPublicPath`, `/theme/<hash>/` | Luggage retailer. Alt: grapedistrict.nl. Led to fingerprint fix: production builds lack `/bundles/storefront/` |
| Magento | dille-kamille.nl | x-magento-init, Magento_* static assets | Alt: petsplace.nl. (norah-plastics.nl rejected: looks B2B) |
| Lightspeed eCom | jhparts.nl | DNS CNAME `140810.webshopapp.com` only | **Unresolved**: every Lightspeed shop tried (6) returns a Cloudflare challenge (`cf-mitigated: challenge`) to our UA, so no check can be verified. Not bypassed (rule 2 / no bot-detection evasion). |
| other (headless) | hema.nl | no platform markers; Next.js behind CloudFront | Kept as an extra reference for non-platform shops. |

## Log

| Date | Step | Shop (platform) | Checks disputed | Notes |
|---|---|---|---|---|
| 2026-11-08 | 1 (partial: fetch, D1, D3) — smoke, not a reference shop | www.hema.nl (not fingerprinted yet) | 0 | D1 pass, D3 pass. Manual: robots.txt has only `User-agent: *`; no rule blocks `/` or the `.html` product paths tested; sitemap_index referenced, lastmod 100% on 3,318 sampled URLs. Matches. |
| 2026-11-08 | 1 (partial: fetch, D1, D3) — smoke, not a reference shop | www.coolblue.nl (not fingerprinted yet) | 0 | robots.txt and sitemaps return HTTP 403 to our scanner UA → D1/D3 reported `error` (cannot verify) instead of RFC-default "allow all". Real AI-bot behaviour to be tested by D2. |
| 2026-11-08 | 1 (partial: + fingerprint, sampling) — smoke | www.hema.nl (other) | 0 | Fingerprint `other`: manual check shows headless Next.js behind CloudFront (not one of the 5 supported platforms) — correct. Sampled 20 products (all JSON-LD-confirmed; spot-checked one page: Product + ProductGroup + Offer present in raw HTML), 3 categories, 4 policy pages, 36 requests, 45 s. |
| 2026-11-08 | 1 (partial: + fingerprint, sampling) — smoke | www.coolblue.nl (other) | 0 | Home page also 403 to our UA → nothing sampled, platform unknown; notes explain why. Expected given bot protection. |
| 2026-11-08 | 1 (D1–D3 + fingerprint, sampling) — reference run | dille-kamille.nl (magento) | 0 | D1/D2/D3 pass. Manual: sitemap has 2,896 `.html` product URLs (D3 "likely products"); the 19 sampled products (seasonal) really are absent from the sitemap → reported as info. 49 s. |
| 2026-11-08 | same | duifhuizen.nl (shopware6) | 0 | D1/D2/D3 pass; 15 products confirmed via Product **microdata** (manual: 1 `itemtype=schema.org/Product` per product page, no Product JSON-LD). 1× 429. 69 s. |
| 2026-11-08 | same | fixje.nl (woocommerce) | 0 | D1/D2 pass; D3 warn 0.75 — manual: robots.txt has no `Sitemap:` line (correct). 2× 429 with Retry-After → time budget hit, 11 products, **no policy pages** (C5 will lack data). 97 s. |
| 2026-11-08 | same | hema.nl (other) | 0 | D1/D2/D3 pass, 19 products, all policies. 64 s. |
| 2026-11-08 | same | jhparts.nl (other; Lightspeed by DNS) | 0 | Cloudflare challenge is intermittent: earlier run baseline OK and spoofed Googlebot/Bingbot blocked (→ D2 warn, CDN fake-bot protection); this run baseline challenged → D2 `error` (inconclusive). Both outcomes honest; D2 result varies between runs. |
| 2026-11-08 | same | stoov.com (shopify) | 0 | D1/D2/D3 pass on robots/sitemap, but Shopify answers `429 Retry-After: 60` to our UA at 1 req/s → honoured → **0 products, 0 policies** sampled in 120 s. S-checks cannot run on this shop within the time budget. Open decision. |

### Fixes made during this verification (2026-11-08)
- D2: HTTP 429 → `rate_limited` (not "blocked"); blocks behind Cloudflare/Akamai → `warn` (fake-bot protection can't be told apart from AI-bot blocking); probes moved before sampling (home page) so they are never starved.
- Client: honours Retry-After (≤60 s), doubles per-host interval on 429 (≤4 s), stops fetching before the scan timeout so a partial report always renders; cookies not carried between requests.
- Sampling: Product microdata accepted; pages with several Product nodes are listings, not products; default/NL locale sitemaps first; locale root pages skipped; generic sitemap entries as last-resort candidates.
- Fingerprint: Shopware 6 production markers (`window.salesChannelId`, `window.themeJsPublicPath`, `/theme/<hash>/`).
- D3: platform product shapes count as "likely products"; reports sampled products missing from the sitemap.

### 2026-11-08 — smaller samples (decision: fewer pages per scan)
Defaults now 8 products / 2 categories / 3 sitemap files; policy pages fetched first; D2 probes after sampling in reserved time (15 s).

| Shop | Time | Requests | Products / categories / policies | D1 / D2 / D3 | Notes |
|---|---|---|---|---|---|
| dille-kamille.nl | 30 s | 20 | 8 / 2 / 2 | pass / pass / pass | was 49 s |
| duifhuizen.nl | 31 s | 20 | 5 / 2 / 4 | pass / pass / pass | was 69 s |
| fixje.nl | 95 s | 23 | 2 / 2 / 4 | pass / pass / **error** | 4× 429 incl. on sitemap → D3 now `error` ("cannot tell whether a sitemap exists") instead of a false `fail` |
| hema.nl | 43 s | 20 | 8 / 2 / 4 | pass / pass / pass | |
| jhparts.nl | 14 s | 6 | 0 / 0 / 0 | pass / error / error | Cloudflare challenge this run (intermittent) |
| stoov.com | 85 s | 14 | 0 / 0 / 4 | pass / pass / pass | Policies now arrive. Shopify returns 429 + Retry-After 60 on the **2nd product page** even at 3 s/request (traced); a cold single request gets 200. Product pages per scan on Shopify: 0–2. Back-to-back test scans from one IP make it worse. |

### 2026-11-08 — D4 + S1–S6, reference run with manual spot checks

| Shop | D4 | S1 | S2 | S3 | S4 | S5 | S6 | Manual verification |
|---|---|---|---|---|---|---|---|---|
| dille-kamille.nl (magento, 8 products) | pass | pass | pass | fail 0 | fail 0 | **warn** | pass | S3: mpn = sku (internal no.), no brand, no GTIN → fail is per SPEC rule. S5: same rating 4.45 on all 8 products (counts 3916/3919) = shop rating in product markup → warn. |
| duifhuizen.nl (shopware6, 5) | pass | warn 0.75 | pass | pass | fail 0 | n/a | pass | S1: microdata only (confirmed: 1 `itemtype=Product`, no Product JSON-LD). S5 first said fail on text "0 beoordelingen" → fixed (count ≥ 1 required) → n/a. |
| fixje.nl (woocommerce, 4) | pass | pass | warn 0.6 | fail 0 | fail 0 | pass (1 page) | pass | S2: price 112 not in raw page text at all (confirmed; likely JS-rendered). S5: single page with rating 9 from 100000 — implausible, probably a shop rating; not flagged (needs ≥ 2 pages). |
| hema.nl (other, 8) | pass | pass | pass | fail 0.25 | fail 0 | n/a | warn 0.6 | S1 first said "missing image" → wrong: image is on ProductGroup variants → fixed. S3: 6/8 pages carry `gtin13=0000000000000` placeholder → now rejected by GS1 check-digit validation. S6: Organization has name+url but no logo; page shows KvK 34215639 but no vatID/iso6523Code (confirmed). |
| stoov.com, jhparts.nl | error (no products sampled) | | | | | | stoov warn 0.5 / jhparts fail | stoov S6: Organization has url "/" + logo, no name (confirmed in markup). |

Disputed checks after fixes: 0 per shop. Four false results found and fixed during verification (variant fields, "0 reviews", placeholder GTIN, shop-rating drift).

### 2026-11-08 — Build step 1 complete: full reference run (all 14 static checks)

`uv run ruff check . && uv run mypy scanner && uv run pytest` → clean, 115 tests.

| Shop | Platform | Time | Products | D1 | D2 | D3 | D4 | D5 | P1 | P2 | P3 | S1 | S2 | S3 | S4 | S5 | S6 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dille-kamille.nl | magento | 33 s | 8 | pass | pass | pass | pass | n/a | fail | n/a | warn | pass | pass | fail | fail | warn | pass |
| duifhuizen.nl | shopware6 | 56 s | 5 | pass | pass | pass | pass | n/a | fail | warn | warn | warn | pass | pass | fail | n/a | pass |
| fixje.nl | woocommerce | 94 s | 6 | pass | pass | warn | pass | n/a | fail | warn | warn | pass | warn | fail | fail | warn | pass |
| hema.nl | other | 44 s | 8 | pass | pass | pass | pass | n/a | fail | n/a | warn | pass | pass | fail | fail | n/a | warn |
| jhparts.nl | (lightspeed, DNS) | 17 s | 0 | pass | error | error | error | n/a | fail | n/a | warn | error | error | error | error | error | error |
| stoov.com | shopify | 88 s | 0 | pass | pass | pass | error | n/a | **pass** | **pass** | **pass** | error | error | error | error | error | warn |

Manual verification of new checks (P1–P3, D5):
- stoov.com P1: fetched `/.well-known/ucp` by hand → 200, `application/json`, `Cache-Control: public, max-age=60`, `ucp.version` 2026-08-25, services `dev.ucp.shopping` (mcp + embedded), 13 capabilities incl. checkout, 3 payment handlers → pass is correct. P3 MCP endpoint `…/api/ucp/mcp` matches the profile.
- hema.nl P1: `/.well-known/ucp` returns an HTML page with HTTP 200 (soft 404) → fail with that wording. ai-catalog.json is also a soft 404 → correctly not counted.
- D5: n/a everywhere (no operator input given) — by design, never guessed.

Fixes during this run: agent-endpoint files moved before sampling (Shopify Retry-After waits had starved them → stoov P1 was a false `error`); rate-limited/challenged home page no longer read as content (fixje S6 false fail, jhparts S6 false fail, fixje fingerprint flip) and refetched once after a 429; soft-404 wording for P1.

**What is verified:** D1–D4, S1–S6, P1–P3 against manual inspection on the 4 shops that can be sampled (dille-kamille, duifhuizen, fixje, hema) plus P1–P3/D1–D3 on stoov; 0 disputed checks per shop after fixes.
**What is not verified / limits:**
- Shopify (stoov): 0–2 product pages per scan (429 + Retry-After 60 on product pages) → D4/S1–S5 usually `error`.
- Lightspeed (jhparts): intermittent Cloudflare challenge → most checks `error`. No reachable Lightspeed shop found yet.
- D2 results vary between runs on Cloudflare sites; spoofed bot UAs cannot prove what real bots see.
- D4 cannot yet distinguish "JS-only" from "absent" (needs step 2 render).
- S5 shop-rating detection needs ≥ 2 rated pages (fixje's single "9 from 100000" page not flagged).
- P2 support table: Magento/Adobe sources could not be read; NL availability of any channel is not stated by vendors.
- C1–C5 (checkout probe) and V1 (visibility) are build steps 2 and 3; scoring + HTML report are step 4.

### 2026-11-08 — Build step 2: checkout probe (C1–C5) + D4 render comparison

`uv run ruff check . && uv run mypy scanner && uv run pytest` → clean, 127 tests, incl. 7 that
drive real headless Chromium against a fake shop served via Playwright routes (no network):
happy path, login wall, captcha, bot challenge, robots-disallowed checkout (asserts `/checkout`
is never requested), consent override, D4 "JS-only vs absent".

Live probe runs (Tarek approved one run per shop whose robots.txt allows checkout):

| Shop | Probe | C1 | C2 | C3 | C4 | C5 | Manual verification |
|---|---|---|---|---|---|---|---|
| hema.nl | ran | pass | pass | pass | pass | warn | Screenshots checked: cookie banner **rejected**; "in winkelmandje" clicked; cart shows 1 item €3,99; "bestellen" opens a drawer with "inloggen / **bestellen als gast** / account aanmaken" → C2 pass correct; probe stopped there, nothing typed. C5: delivery time ("Thuislevering: 1-3 werkdagen") is only in embedded Next.js FAQ data → now half credit with that explanation. |
| fixje.nl | not run | error | error | warn | error | error | 0 products sampled this run (host rate-limited us after many test scans today) → probe skipped, honestly reported. **Live probe still to verify.** |
| jhparts.nl | not run | error | error | warn | error | error | Cloudflare challenge on home/products → nothing sampled. **Live probe still to verify.** |
| stoov / duifhuizen / dille-kamille | `--no-checkout` (robots disallows checkout; not approved) | n/a | n/a | warn / pass / warn | n/a | warn / pass / error | C3/C5 static only. |

False results found and fixed: Klarna "shown" because a **privacy statement** lists it as a
data processor (privacy pages excluded from C3); footer logos without iDEAL were a `fail`
although checkout wasn't seen (now `warn`; `fail` only when the probe saw the checkout);
"retourneren binnen 14 dagen" counted as a delivery time (C5 items now scoped to their own
policy page).

**Not verified:** live probe on fixje (WooCommerce) and jhparts (Lightspeed); C4 only sees the
first checkout step (HEMA's is a login/guest drawer), a captcha on a later step is not seen;
add-to-cart detection is text-based (NL/EN button labels) and may miss icon-only buttons.

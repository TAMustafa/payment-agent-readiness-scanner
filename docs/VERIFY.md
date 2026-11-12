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

### 2026-11-08 — Residual risks closed
- D2 user agents made transparent (bot UA + "AI-access test by AgentReadyScanner/…"); live
  re-check on hema.nl: D2 still `pass`, baseline 200, 9 probes 200.
- Checkout probe made opt-in; default scan of hema.nl reports C1 "not tested: checkout probe
  not enabled". CLI warns while `SCANNER_CONTACT_URL` is unset.
- 206 tests pass (incl. new tests for both changes).

### 2026-11-09 — Build step 3: V1 AI visibility (offline verified; live run pending)

Built: `scanner/visibility/` (config, prompts, OpenRouter client, ledger, parse, LangGraph
subgraph), `checks/v1_visibility.py`, CLI `--visibility` / `--visibility-prompts`.
`uv run ruff check . && uv run mypy scanner && uv run pytest` → clean, 230 tests (12 V1 tests
against a fake OpenRouter; no paid call made).

Found and fixed by the tests before any live call:
- Pre-run estimate used worst-case searches (2/question) → USD 1.02 > cap → every full scan
  would have been refused. Now: estimate with `max_uses` (1), worst case enforced per call.
- Conservative booking (usage.cost + search fee) makes a full run count ≈ USD 0.96; with a
  USD 0.60 per-scan cap the run stopped after 25/40 calls. Per-scan cap set to USD 1.00.

**Not verified yet (needs Tarek's OK for the first paid run):** live answers on 1–2 reference
shops; whether `usage.cost` already includes the native search fee (then set
`add_search_fee_to_cost = false` → ~18 instead of ~10 scans/month); whether `max_uses: 1`
is honoured by native search; mention detection on real Dutch answers.

### 2026-11-09 — First live V1 run: thuisbezorgd.nl (Tarek's choice), paid

Setup: `--visibility --visibility-prompts <10 custom questions>` (food delivery, Almere/1358;
the site puts our scanner behind a Cloudflare challenge, so no category names could be read;
Tarek chose 10 custom questions over the 2 generated brand questions). Checkout probe off.
OpenRouter key: limit USD 10, monthly reset, usage 0 before the run.

Result: V1 `pass`, mentioned in 23/26 answers (88 %). ChatGPT 9/10 in both runs; Gemini 5/6
before the per-scan guard stopped it. **Real cost: USD 0.60** (OpenRouter `usage_monthly`
after reporting lag = sum of `usage.cost`; ledger had booked USD 1.17 by adding the search
fee twice).

Manual verification (raw answers in `scans/www.thuisbezorgd.nl/20261109T211104Z/visibility/raw/`):
- Mentions correct on spot checks: e.g. "Chinees eten online bestellen in Almere" → ChatGPT
  answers "Ga naar **Thuisbezorgd.nl**…", cited #1; "gezond eten in Almere" → ChatGPT
  recommends ThuysVers / HelloFresh, Thuisbezorgd not mentioned → correctly `not mentioned`.
- `usage.cost` == `/generation` `total_cost` and grows by exactly the per-search fee
  (USD 0.01 OpenAI, 0.014 Google) → **usage.cost includes the search fee**.

Found and fixed (regression tests added; 232 tests):
1. **Per-scan cap leaked** (USD 1.17 booked vs USD 1.00 cap): parallel calls passed the
   guard before any cost was booked, and native search did up to 3 searches. Now each call
   reserves its worst case (3 searches) before it starts; check + reserve are atomic.
2. **Double-booked search fee** → `add_search_fee_to_cost = false` (verified above).
3. **`max_uses: 1` is not honoured by native search** (ChatGPT avg 1.7, Gemini avg 2.7
   searches). The estimate now uses the measured `expected_searches` per assistant.
4. **Gemini citations are Google redirect URLs** (`vertexaisearch.cloud.google.com/...`) →
   real site taken from the citation title; re-parsed the 6 saved Gemini answers offline:
   Thuisbezorgd now cited at #3, #9, #3 among real competitors (Uber Eats, Febo, …).

Measured cost per question: ChatGPT (`openai/gpt-6-luna`) USD 0.0186, Gemini
(`google/gemini-3.1-flash-lite`) USD 0.0383 → full run (10 × 2 runs × 2) ≈ **USD 1.15**,
approved by Tarek; per-scan ceiling USD 1.40; ≈ 8 full scans per USD 10 month.

**Not yet verified live:** generated (non-custom) questions on a shop that is not
bot-protected.

### 2026-11-09 — Second live V1 run (fixed version): thuisbezorgd.nl, same 10 questions

New OpenRouter key (Tarek rotated it; limit USD 10, monthly reset; usage 0 before). The local
ledger got a labelled correction entry (−USD 0.564) for run 1's double-counted search fee, so
it matched the real USD 0.60 billed before this run.

| | Run 1 (before fixes) | Run 2 (fixed) |
|---|---|---|
| Calls completed | 26/40 (per-scan guard stopped Gemini) | **40/40** |
| Booked vs. billed | USD 1.17 booked / 0.60 billed | **USD 1.160 booked = 1.160 billed** (key `usage_monthly`, to the cent) |
| Estimate | USD 0.54 | **USD 1.156** |
| Mention rate | 23/26 (88 %) | **36/40 (90 %)** — ChatGPT 8/10 + 8/10, Gemini 10/10 + 10/10 |
| Gemini citations | redirect URLs only | real sites (thuisbezorgd.nl, ubereats.com, …); Thuisbezorgd cited in 10/20, positions 1–7 |
| ChatGPT citations | | Thuisbezorgd cited in 13/20, position 1 in 12 |
| Searches per question | ChatGPT 1.70, Gemini 2.67 | ChatGPT 1.75, Gemini 2.70 (stable) |

Month to date after both runs: USD 1.76 of USD 10 (ledger = old key 0.60 + new key 1.16).
V1 is verified live end-to-end. Disputed results: 0.

### 2026-11-10 — Build step 4: scoring, top 5 fixes, NL/EN HTML report

Built `scanner/report/` (scoring.py, html.py, i18n.py); `nodes.score` is no longer a stub.
`report.html` is written next to `report.json` with `--out`; `scanner report <report.json>
[--lang en]` re-renders offline (also scores reports saved before step 4). HTML is built with
the stdlib (`html.escape`), so no new dependency (Jinja2 not needed). 264 tests green
(+14 scoring, +14 HTML: escaping of hostile evidence, no external resources, NL/EN, "agent
checkout not yet available" copy, CLI).

Scoring choices (SPEC §5; my reading, please confirm):
- Checks with no result (V1 without `--visibility`, or deselected) are "not run", excluded
  from the score like `not_applicable`/`error`, and listed in the summary.
- A `warn` with full credit (D1: only training bots blocked) is not a fix.
- Fix "+N points" = exact rise of the 0–100 score when fixed, after re-normalisation.
- Each category bar shows "n/m measured", so e.g. checkout "100" on 2 of 5 checks is not
  read as a full checkout pass.

| Date | Shop | Result | Manual check |
|---|---|---|---|
| 2026-11-10 | duifhuizen.nl (shopware6), static scan, no probe, no V1 | **78.9 Partly ready**; 14 counted, 5 excluded, V1 not run; 24 requests, 1× 429 | Score recomputed by hand from report.json: 78.9 over 71 scorable weight ✔. Fix order S4 (2.5), P1 (1.67), S1 (0.75), P2 (0.75), P3 (0.67) matches the formula ✔. S4 fail confirmed with curl: product page has Product/Offer microdata, no shippingDetails / hasMerchantReturnPolicy ✔. HTML checked in a browser at desktop and 375 px (no horizontal scroll; fixed narrow-screen bar layout). |
| 2026-11-10 | thuisbezorgd.nl (saved 2026-11-09 V1 run, re-rendered offline) | D1 + V1 only → score computed from saved JSON | Renders; V1 method note names the assistants and run count from the data. |

Found while verifying (not fixed, pre-existing): P3 on duifhuizen reports `warn` while
`llms.txt` answered 429 — the UCP/ai-catalog 404s make `warn` correct, but the llms.txt part
was not actually verified. Low impact (weight 2, never `fail`).

**Not verified yet:** report understood by a real merchant (SPEC §1); a full report with
checkout probe + V1 on one shop (both need approval / cost money); EN copy reviewed by Tarek.

### 2026-11-10 — Report scoped to agent-order readiness; reference run (static, no V1)

Tarek's decision: the report measures readiness to accept orders from AI agents. Score, fixes
and HTML now cover 16 checks in four stages (Reach D1/D2/D4 · Understand S1–S4/D5 · Check out
C1–C5 · Connect P1–P3); D3, S5, S6, V1 run but are `out_of_scope` in report.json. Each check
has a "why it matters" box. Removed from the HTML: separate "what's coming" section (now in
the intro), sampling notes, weights, long methodology; evidence capped at 3 lines.
New rule found during this run: **no grade below 50 % measured weight** (`MIN_COVERAGE`) —
stoov.com scored "Ready 86.7" on 26/80 weight with zero product pages. Now "Too little
measured to judge", score marked provisional. 273 tests green.

V1 was dropped from the planned fixje.nl run (out of the new scope; saved ≈ USD 1.15).

| Shop | Platform | Agent-order score (scope) | Measured weight | Notes / manual check |
|---|---|---|---|---|
| duifhuizen.nl | shopware6 | 76.2 Partly ready | 63/80 | see run above (S4 confirmed by curl) |
| dille-kamille.nl | magento | 62.1 Partly ready | 58/80 | Checkout stage 0: C3 `warn` 0.0 "no payment info found", C5 `error` (no shipping/returns page sampled). Manual: home HTML has no iDEAL text (only PayPal module config) — the result is what the scanner can see, but "not found" weighing as 0 is harsh → **open point**: should C3 "not found" be `error` (unverifiable) instead of `warn`? |
| hema.nl | other | 70.7 Partly ready | 60/80 | 8 products, all policies; P1/P3 no UCP/MCP. |
| jhparts.nl | lightspeed | 75.9 Partly ready | 60/80 | **First run without Cloudflare challenge**: fingerprinted as lightspeed from the page itself, 8 products. D2 warn (CDN fake-bot protection). |
| stoov.com | shopify | 86.7 → **no grade** (provisional) | 26/80 | 429 + Retry-After again: 0 products, policies only. Led to the coverage rule. |

All 5 platforms now scan without a crash (SPEC §1 criterion 1). Not yet verified by hand for
this run: every individual check per shop (criterion 2 is from earlier rounds).

### 2026-11-10 — fixje.nl with checkout probe (approved "once per shop" run used), no V1

`--checkout`, no V1. 58.4 Not ready (old report), coverage 85 %. 2 products only (3× 429).
Probe stopped on the product page: "captcha on page (reCAPTCHA)" → C1 fail, C2/C4 error.
**Manual check: false result.** The probe screenshot (`checkout_00_challenge.png`) shows a
normal product page, no captcha; fixje.nl loads invisible reCAPTCHA site-wide. The safety
guard also blocked 11 non-GET requests (admin-ajax.php, Cloudflare challenge-platform
telemetry), as designed.

**Fix:** before checkout the probe now stops only on a bot-challenge page or a *visible*
captcha (`markers.VISIBLE_CAPTCHA`: reCAPTCHA checkbox/challenge frame, hCaptcha frame,
Turnstile, Friendly Captcha, all with Playwright `:visible`). On checkout entry any captcha
marker still counts for C4 (SPEC). Two new browser tests (invisible badge passes, visible
checkbox blocks). The guards and `tests/test_safety.py` are unchanged.
**Not re-verified live:** a second probe run on fixje.nl needs Tarek's approval (the one
approved run is used).

Other results on fixje.nl, checked against the saved data: S3 fail (no GTIN/MPN on the 2
pages), S4 fail, C5 pass (shipping cost, delivery time, return window stated), P3 warn
(llms.txt present).

### 2026-11-10 — fixje.nl re-run (approved by Tarek), English default, relevance review

- Report language is now **English by default** (`--lang nl` for Dutch); all saved reports
  re-rendered in English.
- **Captcha fix verified live:** the probe passed the product page ("product: ok - HTTP 200");
  no false reCAPTCHA challenge.
- **New false result found:** the only product sampled (3× 429 again) was
  `https://www.fixje.nl/refurbished-iphone/`, a **category page** carrying one offer-less
  `Product` (product line + rating) next to an `ItemList` of 36 product links. So
  "no add-to-cart button found" (C1/C2/C4 `error`) and S2/S3/S4 fails were about the wrong
  page type. Fix: `is_single_product_page` rejects a single Product without `offers` when the
  page also has an ItemList of ≥ 3 items (a product page with a related-products list keeps
  its own offer). Checked against the saved category HTML → now rejected. 2 new tests.
  **Not re-verified live** (another probe run on fixje.nl needs approval).
- D2 guidance now advises allowing signed agents (Web Bot Auth). Relevance review of every
  check against current agent-commerce docs: `docs/RELEVANCE.md`.
- 278 tests green.

### 2026-11-10 (evening) — C3 cards, discovery back in scope, product pages without markup

- **C3** now needs a card option (Visa/Mastercard/Amex or Apple/Google Pay) **and** iDEAL/Wero
  (pass); one of the two = warn 0.5. Reason and sources: `docs/RELEVANCE.md`.
- **Scope revised:** D3, S5, S6 back in the report (merchant discovery); only V1 outside. Stage 1
  renamed "Find and reach". In-scope weight is now 90.
- **New false result found (pre-existing):** fixje.nl accessory product pages
  (`/iphone-12-tempered-glass`) carry **no Product markup**, so the sampler rejected them and
  every S-check became "not measured" instead of a measured fail — this inflated scores.
  Fix: also confirm product pages by the platform's product body class (WooCommerce
  `single-product`, Magento `catalog-product-view`, Shopware 6 `is-ctl-product`, Shopify
  themes `template-product`). Checked on the saved fixje.nl pages: product page → yes,
  category page (`archive tax-product_cat`) → no. 1 new test.
- **fixje.nl reruns (approved):** 20:37 and 20:40 UTC. Both yielded 0 product pages (429 +
  time budget; the first started before the fixes). The second was run only 3 minutes after the
  first, against our spacing rule — my mistake. fixje.nl was scanned 4× this evening;
  **do not scan it again before tomorrow**. Result: no grade (coverage rule), C1/C2/C4 "could
  not verify". **The fixes are verified offline against fixje.nl's real HTML, not live.**
  Suggestion for the next run: `--timeout 240` so sampling has time after the 429 back-off.
- 279 tests green.

### 2026-11-12 — scoring revision: payments get their own verdict

Review finding: the report overstated checkout/payment readiness. Re-scoring the 13 saved
scans showed "Check out: 100" from 2 of 5 checks (duifhuizen.nl, also hema.nl 94, jhparts.nl
89) and grades for shops whose checkout was never tested. Changes (SPEC §4/§5):
- **Stage minimum:** no stage score below 50 % of its weight measured.
- **Two verdicts:** "Found by AI agents" (stages 1–2) and "Orders and payments" (stages 3–4),
  each graded only when all its stages have a score. Overall grade only when both are graded.
- **Dials:** a number only with a grade (thuisbezorgd.nl showed a provisional "100" at 11 %).
- **Top fixes:** P2/P3 folded into the P1 fix (duifhuizen.nl had P1, P2, P3 as 3 of 5 fixes).
- **C3:** unverifiable → `error` (fixje.nl 20:40 had "no payment info found" as fix #1, +10.8).
- **P1:** valid profile without payment handler or checkout capability → warn 0.7.

Re-scored saved scans (offline; C3/P1 changes apply only to new scans):
| Shop (scan) | Overall | Found by AI agents | Orders and payments |
|---|---|---|---|
| duifhuizen.nl (20:57) | 78.9, no grade (was Partly ready) | 88.2 Ready | not measured (no checkout test) |
| fixje.nl (20:15, with probe) | 61.1 Partly ready | 76.3 Partly ready | 21.4 Not ready |
| hema.nl | 72.4, no grade (was Partly ready) | 79.2 Partly ready | not measured |
| jhparts.nl | 73.8, no grade (was Partly ready) | 82.0 Ready | not measured |
| dille-kamille.nl | 66.2, no grade (was Partly ready) | 78.9 Partly ready | not measured |
| stoov.com / thuisbezorgd.nl | no grade (unchanged) | no grade (no product pages) | not measured |

HTML checked by headless screenshots at 900 px and 390 px (duifhuizen.nl, fixje.nl).
Consequence for sales: a free (default) scan grades only "Found by AI agents"; the
"Orders and payments" verdict needs the consent scan (`--checkout-consent`).
289 tests green. No live scans run.

### 2026-11-12 — stoov.com (Shopify) with `--timeout 240` (approved by Tarek)

Question: does a longer scan limit get enough product pages from a Shopify shop that
rate-limits polite crawlers? Read-only default scan (no checkout test, no V1), 19:32 UTC,
2 days after the previous stoov.com scan.

| | 2026-11-10, 120 s | 2026-11-12, 240 s |
|---|---|---|
| Product pages | 0 | 5 (9 fetched, 4 rejected; 3× HTTP 429, slowed down) |
| Measured weight | 38 % | 81 % |
| S1–S5, D2, D4 | not measured | measured |
| Found by AI agents | no grade | 84.4 Ready |
| Orders and payments | – | not measured (no checkout test) |

Wall time 3 min 33 s, 22 requests. Categories still 0 (time budget used up by products);
they only feed V1 prompts. **Conclusion: 240 s turns a useless Shopify report into a usable
one.** Decided by Tarek the same day: automatic 240 s for Shopify (see below).

Manual check (1 extra GET of /products/big-hug-s3-original) found **2 false results**:
1. **S5 false fail:** "Reviews appear to be shown" matched "4.3 | 17,117 reviews", the
   shop-wide Trustpilot score in every product page footer. The product has no reviews
   (Okendo `reviewCount: null`). Fix: a "<n> reviews" text that appears on ≥ 2 sampled product
   pages is a shop widget and is ignored. Checked offline on the saved page. Limit: two
   different products with exactly the same review count would also be ignored.
2. **Duplicate sample:** `/products/big-hug-s3-original` and `/nl/products/big-hug-s3-original`
   were both sampled (1 of 5 slots wasted, and it would defeat fix 1). Fix: URLs are deduped on
   the path without a language prefix (`/nl/`, `/en-gb/`). Limit: a real 2-letter first
   path segment (e.g. `/tv/…`) is treated as a language prefix for dedupe only.
Other results matched the page: S4 fail (no shippingDetails / hasMerchantReturnPolicy in the
Product JSON-LD), S1 one page without description, P1–P3 pass (Shopify UCP profile live).
Also seen: `SCANNER_CONTACT_URL` is still the `example.invalid` placeholder in `.env`.
291 tests green. Fixes not re-verified live (do not re-scan stoov.com today).

**Follow-up (same day):** Shopify scans now get 240 s automatically. The scan starts with the
120 s budget; when the fingerprint says Shopify, the fetch deadline moves to 230 s (240 − 10 s
reserve) and the report notes "Scan time extended to 240 s for Shopify". `--timeout N` fixes
the limit and is never extended. Covered by 5 new tests (296 green); not yet run live.
Contact URL set 2026-11-12: `SCANNER_CONTACT_URL=https://tarek-ai.com/portfolio/` in `.env`
(HTTP 200 checked). Earlier live scans ran without `--env-file .env` and sent the
`contact-url-not-configured.invalid` placeholder; use `uv run --env-file .env scanner scan …`.

### 2026-11-12 (evening) — fixje.nl (WooCommerce), read-only default scan

First live run with the contact URL (`--env-file .env`). 20:01 UTC, 93 s, 22 requests, 4× HTTP
429 (sitemap rate-limited → link crawl). Result: 1 product page out of 8 fetched; overall
52.3, no grade; "Found by AI agents" not graded. Checked by hand (3 spaced GETs: the sampled
product, the chosen shipping page, the home page). **3 false results / sampling faults:**
1. **Category page sampled as a product.** `/refurbished-iphone/iphone-8-plus/` is a
   `CollectionPage` with body class `archive tax-product_cat`; its only "Product" is the shop
   itself (name "Fixje", url = home, 4.7 from 132 reviews, no offers). So S1–S5 all judged a
   category page (S2 "no offers" fail, S5 pass on the shop rating). Fix: listing pages
   (WooCommerce/Magento/Shopify/Shopware category body classes, `CollectionPage` /
   `SearchResultsPage`) are never product pages, and an offer-less Product whose url is the
   home page is the shop, not a product.
2. **Probes wasted on menus and sub-categories.** Category pages list navigation, filters and
   sub-categories before the product tiles; fixje's product URLs are root-level slugs
   (`/refurbished-iphone-8-plus-64gb-goud`) that no URL pattern recognises, so all 8 probes went
   to the wrong links. Fix: links inside product tiles (`product-card`, `li.product`,
   `product-item`, `product-box`, …) are tried first. On the saved category page this finds
   the 8 product links.
3. **Wrong policy pages:** "dropshipping" (B2B) was taken as the shipping policy and
   "iPhone inruilen" (trade-in) as a returns candidate. Fix: these look-alikes are excluded;
   `/verzending/` is now picked.
Correct as measured: C3 "could not verify" (the home page has no payment info at all; the
2026-11-12 C3 change works), P1 fail (404), D3 "could not verify" (429).
Sampling note now says how many rejected pages were unreadable (e.g. 429).
300 tests green. Fixes verified offline against the saved fixje.nl pages, **not yet live**
(fixje.nl was scanned once + 3 manual GETs today; next run tomorrow at the earliest).

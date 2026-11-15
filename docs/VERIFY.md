# Verification log

The scanner-era log (reference shops, probe runs, V1 costs) is in git history at commit
4cd9af7 (`docs/VERIFY.md`); uncommitted work from 2026-11-12 is in `git stash list`
("pre-AP2-pivot").

## 2026-11-13 — pivot to the AP2 Readiness Check
- Removed: the webshop scanner (LangGraph pipeline, Playwright checkout probe, 19 checks,
  V1 AI-visibility via OpenRouter, scoring/HTML report) and its docs/config. Dependencies
  dropped: langgraph, playwright, selectolax. Added (pinned): fastapi 0.162.0, uvicorn 0.54.0,
  cryptography 50.0.2. Kept: robots.txt parser + tests.
- Built: checks U1–U5, A1–A2, G1–G2, M1, verdict, CLI (`ap2check check|serve`), website.
- `uv run ruff check . && uv run mypy ap2check && uv run pytest`: clean, **96 tests green**.
- Fixture coverage: valid profile (all pass); redirect, 404, 403/429/503; missing registries;
  http endpoints; five Cache-Control cases; no handlers; AP2 undeclared / without checkout /
  without `dc+sd-jwt`; leaked private key; keys inside `ucp`; Ed25519-only; P-384-only;
  duplicate kid; `use: enc`; A2A 1.0 card, AP2-sample 0.3 card, non-required and missing
  extension, http interface; UCP signature valid / reformatted / tampered / other key /
  unknown kid / missing / compact-instead-of-detached / no keys; A2A `checkout_jwt` alone and
  in DataPart, hash mismatch, EdDSA, expired, missing merchant; no PII echoed. JCS against the
  RFC 8785 sample.
- Browser check (local server): `example.com` → "AI agents cannot find your AP2 setup", U1
  fail (404), dependent checks n/a; layout OK at 375 px and desktop, dark mode.

## 2026-11-13 — live check tarek-ai.com (Tarek's own site)
- Result before fix: "We could not read your setup" (U1/G1 error, HTTP 403). Wrong.
- Cause (curl, our UA and a browser UA alike): Hugo site on Amazon S3 behind CloudFront.
  Every missing path, e.g. `/this-page-does-not-exist-xyz`, returns `403` with
  `server: AmazonS3` and `<Code>AccessDenied</Code>`, because S3 reports missing objects as
  403 when the bucket does not allow listing. `/`, `/robots.txt`, `/sitemap.xml` are 200.
- Fix: `checks/base.py::s3_missing_object`. Exactly that S3 response is read as "not found"
  (U1 fail, G1 n/a); any other 403 (WAF, Cloudflare, other S3 codes) stays `error`.
  Tests: `test_s3_access_denied_means_not_found`, `test_other_403_stays_error`,
  `test_s3_static_site_without_profile_is_not_discoverable`. 99 tests green.
- Result after fix: "AI agents cannot find your AP2 setup" (correct: no profile, no card).

## 2026-11-13 — review and cleanup
- Sources re-checked: AP2 `main` unchanged (v0.2.0 latest tag); `ucp.dev/latest` is still
  2026-08-25; UCP schema `payment_ap2_mandate.json` matches M1 (detached JWS pattern,
  ES256/384/512, `kid`, error codes).
- M1 `checkout_jwt` payload warnings now follow the AP2 Checkout schema
  (`code/sdk/schemas/ucp/types/checkout.json`): required `id`, `line_items`, `status`,
  `currency`, `totals`, `links`. `merchant` and `exp` are optional there, so their absence no
  longer warns (was a possible false warning); a `merchant` without `id`/`name` still warns.
- Rate limiter forgets idle keys (memory was unbounded on a public site).
- Removed unused code: `profile_usable`, `AP2_CHECKOUT`, `FetchedResource.ok` /
  `unavailable_reason`, `Rule.text`, the fetcher's `respect_robots` switch, the `make_shop`
  fixture, RFC 7797 `b64:false` handling (UCP does not use it). Request budget 6 → 3.
  Stale `.gitignore` entries removed. 100 tests green.

## 2026-11-13 — live check goudenhuisalmere.nl (Tarek's request) and report redesign
- Result: "AI agents cannot find your AP2 setup". Correct: WooCommerce 11.2 shop;
  `/.well-known/ucp` and `/.well-known/agent-card.json` are real 404s (HTML), robots 200.
- Problem was the output, not the result: one failing card followed by nine "N/A" cards, no
  indication of how far the shop is or what to do first.
- Changes: `Report.steps` (five-rung ladder) and `Report.next_step` (`runner.ladder`); page
  shows verdict + ladder, one "Your next step" box, copy-for-developer and download buttons;
  checks are folded unless they need attention; plain status labels (OK / Improve / Problem /
  Not checked / Couldn't check); guidance shows the shop's own address; loading message;
  shareable `?url=` link; CLI prints the ladder too. 102 tests green; checked in the browser.

## 2026-11-13 — live round: looking for a shop that passes (Tarek's request)
One check each (3 GETs), 2 s apart, via the CLI.

| Shop | Verdict | Notes |
|---|---|---|
| www.allbirds.com, www.glossier.com, skims.com, monos.com (Shopify) | no_ap2 | U1–U5 pass: UCP 2026-08-25 profile, MCP endpoint on `*.myshopify.com/api/ucp/mcp`, handlers `com.google.pay`, `dev.shopify.card`, `dev.shopify.shop_pay`, `Cache-Control: public, max-age=60`. No `dev.ucp.common.payment.ap2_mandate`, no top-level `keys` |
| www.gymshark.com | not_discoverable | 404 |
| www.etsy.com, www.wayfair.com, www.target.com, www.walmart.com | not_discoverable | 404 on both files, although all four are UCP co-developers |
| www.stoov.com | unknown (wrong) | robots.txt 301 → apex was read as "disallow all" |

- **No shop with AP2 declared was found.** Shopify's default profile stops after step 2, so
  steps 3–5 are still only proven on fixtures.
- Checks U1–U5 confirmed on real profiles (manual read of allbirds' profile matches the
  report line by line).
- Fix: robots.txt redirects are now followed (RFC 9309 §2.3.1.2), max 2 hops, https and
  public only; a longer chain = no restrictions. Profile and agent-card redirects are still
  never followed. Tests: `test_robots_redirect_is_followed_and_applied_to_the_original_host`,
  `test_robots_redirect_to_private_or_endless_chain_is_not_followed`. 104 tests green.

## 2026-11-13 — built-in demo merchant
- Why: the live round found no shop with AP2 declared, so the passing path could not be
  shown or exercised on the site.
- `ap2check/demo.py` + `ap2check/demo_data/` (UCP profile with AP2 capability and a P-256
  public key; one UCP checkout response signed with it). Scenarios: `ready` (5 of 5),
  `no_ap2` (Shopify-like, 2 of 5), `signature_failed` (total changed after signing, 4 of 5).
- Runs through the normal fetcher and checks via an in-memory transport: this is the first
  end-to-end pass of U1–A2 + M1 outside the test helpers (fixture signed by a separate
  script, verified by the package).
- Website buttons, `GET /api/demo/{scenario}`, `ap2check demo`. Browser check: "A shop that
  passes" → "Set up to accept AP2 payment requests", 5 of 5, 8 OK. 107 tests green.

## 2026-11-15 — market check; project parked
- Market check by web search (`docs/AP2.md`, "Market check 2026-11-15"): no live agent
  checkout requires AP2; free UCP/AP2 checkers and an AP2-signing WooCommerce plugin already
  exist; platforms and PSPs are absorbing the implementation work.
- Decision (Tarek): the app is not pursued further. Not deployed; no pilots run.
- Final state: `uv run ruff check . && uv run mypy ap2check && uv run pytest` clean,
  **107 tests green**. Documentation updated to say so (README, CLAUDE.md, SPEC.md).
- Correction to the 2026-11-13 cleanup entry above: the request budget is 5 since robots.txt
  redirects are followed (3 files plus at most 2 redirect hops), not 3.

## Known limits
- No live merchant with AP2 declared exists in our sample yet (see the live round above).
- UCP signs the full checkout JSON; if a merchant's JCS differs from ours on exotic numbers
  (floats beyond double precision), a valid signature could be reported as failing. Our JCS
  matches the RFC 8785 test vector.
- A2A extension URI comes from the AP2 samples, not the spec text; revisit when FIDO
  publishes the next version.
- Rate limits are in memory (one process); a multi-instance deployment needs a shared store.

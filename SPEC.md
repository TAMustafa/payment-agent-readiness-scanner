# SPEC — AP2 Readiness Check

Version 0.2 (2026-11-13). Supersedes the agent-ready-scanner spec (in git history up to
commit 4cd9af7). Background and sources: `docs/AP2.md`.

## 1. Product
A website (plus CLI) where a merchant enters their domain and learns whether they are set up
correctly to **accept AP2 (Agent Payments Protocol) payment requests** from AI shopping
agents, with evidence and a fix for every finding.

- Free self-check → lead magnet for a paid setup sprint (keys, profile, signing,
  mandate verification) → monitoring.
- Target: merchants and their developers / agencies / PSPs implementing UCP + AP2.
- English report. Honest about maturity: AP2 v0.2 is pre-release (FIDO standardisation).

## 2. Inputs
1. **Domain** (required). Normalised to `https://<host>[:port]`; private/local hosts refused.
2. **Sample** (optional): one checkout response from the merchant's *test* checkout:
   - UCP checkout JSON containing `ap2.merchant_authorization`, or
   - an AP2 `checkout_jwt` (alone, or inside JSON such as the `ap2.checkout` DataPart).
   Processed in memory, never stored or logged; evidence never echoes its values.

## 3. Requests (read-only)
Three files per check (plus at most two redirect hops for robots.txt only, RFC 9309), ≥ 1 s apart, identified as
`AP2ReadinessCheck/<version> (+AP2CHECK_CONTACT_URL)`:
`/robots.txt`, `/.well-known/ucp`, `/.well-known/agent-card.json`.
HTTPS only, redirects never followed (UCP forbids following them), private addresses refused
by name and after DNS resolution, body capped at 1 MB, no cookies kept.
The checker **never calls the merchant's checkout** (no POST anywhere in the package).

## 4. Checks
Status conventions: `pass` / `warn` / `fail`; blocked, rate-limited or unverifiable →
`error` (never a guessed fail); nothing to test or depends on a failed check →
`not_applicable`. Every result carries evidence (URL, header, snippet) and a spec URL.

| ID | Stage | Pass when | Warn | Fail |
|---|---|---|---|---|
| U1.profile_reachable | discovery | `/.well-known/ucp`: 200, JSON, ≤ 128 KiB | > 128 KiB | 3xx (no redirects allowed), 404, Amazon S3 `403 AccessDenied` (S3's answer for a missing file), not JSON. Other 401/403, 429, 5xx, network → error |
| U2.profile_structure | discovery | `ucp.version`, `ucp.services`, `ucp.payment_handlers` present; transports valid; endpoints https | version < 2026-08-25 | missing field, bad transport, endpoint missing / not https |
| U3.profile_caching | discovery | `Cache-Control` has `public`, `max-age ≥ 60`, no `private`/`no-store`/`no-cache`; ETag or Last-Modified | no validator | any MUST broken |
| U4.checkout_capability | checkout | `dev.ucp.shopping.checkout` declared and a rest/mcp/a2a endpoint exists | – | either missing |
| U5.payment_handlers | checkout | ≥ 1 entry in `ucp.payment_handlers` | – | empty |
| A1.ap2_capability | ap2 | `dev.ucp.common.payment.ap2_mandate` declared, version ≥ 2026-08-25, extends checkout, `vp_formats_supported` has `dc+sd-jwt` | version/extends/format issues | not declared, or checkout capability missing |
| A2.signing_keys | ap2 | top-level `keys[]` has a valid public EC P-256 key with `kid` (point on curve, `use` sig, `alg` matches) | only P-384/P-521 keys (agents must only support ES256) | no keys, keys inside `ucp`, private material (`d`) published, duplicate/missing kid, invalid point, only OKP keys |
| G1.agent_card | a2a | A2A 1.0 card with required fields, https interfaces | A2A 0.3-style card (as in the AP2 samples) | not JSON, required field missing, http interface. 404 → n/a |
| G2.ap2_extension | a2a | `capabilities.extensions` has `https://github.com/google-agentic-commerce/ap2/v1` with `required: true` | not required, or AP2-like other URI | card without AP2 extension. No card → n/a |
| M1.merchant_signature | signature | sample signature verifies with the published key of its `kid` | A2A payload lacks a field the AP2 Checkout schema requires (`id`, `line_items`, `status`, `currency`, `totals`, `links`), or `merchant` lacks `id`/`name` | not detached / not compact, alg not ES*, EdDSA, unknown kid, bad signature, `checkout_hash` mismatch, missing `merchant_authorization`. No published keys → error. No sample → n/a |

M1 details: UCP form verifies the detached JWS over JCS (RFC 8785) of the checkout without
`ap2`; A2A form verifies the compact JWS and recomputes
`checkout_hash` = base64url(sha-256(checkout_jwt)). An expired sample is a note, not a warn.

## 5. Verdict (no numeric score)
Evaluated in order:
1. **unknown**: U1 error and no AP2 agent card (blocked, robots, DNS refusal).
2. **not_discoverable**: no usable profile and no agent card with the AP2 extension.
3. **no_ap2**: A1 not pass/warn and G2 not pass/warn.
4. **incomplete**: any fail in U2–U5, A1, A2 (and G1/G2 when a card exists); or AP2 only via
   an agent card (AP2 defines no key publication outside a UCP profile).
5. **ready**: M1 pass/warn. **signature_failed**: M1 fail/error. Otherwise **untested**.

**Readiness ladder** (shown first, with the verdict): five rungs, each `done` (all its checks
pass/warn), `problem` (a fail), `unknown` (an error) or `todo` (not reached):
1 Agents can find your shop (U1–U3) · 2 Agents can start a checkout (U4–U5) · 3 AP2 is
switched on (A1) · 4 Your signing key is published (A2) · 5 Your checkout signature verifies
(M1). The first rung that is not done is "current"; `next_step` is the guidance of its first
failing check (or "paste a sample" for rung 5). G1/G2 are optional and outside the ladder.

Standing notes on every report: AP2 maturity; mandate verification by the merchant is not
testable read-only; sample privacy.

## 6. Website
- `GET /` static page (HTML/CSS/JS, no build step, strict CSP `script-src 'self'`).
- `POST /api/check` `{url, sample?}` → report JSON. URL ≤ 2 kB, sample ≤ 256 kB.
- Limits: 6 checks/min per visitor IP, 4/min per checked host, 4 concurrent checks; 429/503
  with a readable message. No persistence; `Cache-Control: no-store` on the API.
- All report text is rendered with `textContent` (third-party JSON is untrusted).
- Result layout: verdict + ladder ("n of 5 steps done") → "Your next step" with "Copy summary
  for your developer" and "Download full report (JSON)" → all checks, problems unfolded and
  passed / not-checked ones folded → caveats folded. When rung 5 is current, a button opens
  the sample box. After a check the address bar holds `?url=<host>` (never the sample).
- `GET /api/demo/{ready|no_ap2|signature_failed}` → `{report, sample}` for the built-in demo
  shop `demo-shop.example` (static public documents in `ap2check/demo_data/`, served from
  memory through the normal checks; no network). The page offers the three demos as buttons,
  marks the result "Demo", and fills the form with the demo's domain and sample. A real
  check of `demo-shop.example` is refused (422).
- `GET /healthz`. No OpenAPI/docs endpoints in production.

## 7. Out of scope / later
- Active mandate test (send an invalid `complete_checkout` to a merchant **sandbox**, expect
  `mandate_required` / a signed error receipt): needs explicit merchant consent and an
  allow-listed sandbox URL; would be the only write. Not built.
- Signed A2A agent cards (JWS verification), x402, Payment Mandate checks (PSP side).
- Dutch report copy; hosted deployment; saved reports / monitoring.

## 8. Build steps
1. ✅ Checks U1–U5, A1–A2, G1–G2, M1 with fixture tests; CLI; website (2026-11-13).
1b. ✅ Built-in demo merchant (passing, no-AP2 and broken-signature reports) (2026-11-13).
2. Live verification against public UCP profiles (needs Tarek's go-ahead per site) and a
   sample merchant built from the AP2 v0.2 Python sample; record in `docs/VERIFY.md`.
3. Deploy (host + domain + contact URL), then pilots with merchants/agencies.

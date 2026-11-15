# AP2 research notes: what a merchant needs to accept AP2 payment requests

Researched 2026-11-13 from primary sources (spec sites and the AP2 repository itself). This
field changes quickly; re-check the sources below before each release and record the date.

## State of the protocol
- **AP2 v0.2.0, released 2026-04-28**, is current. The last commit on `main` of
  github.com/google-agentic-commerce/AP2 is from 2026-04-29 (checked by cloning the repo on
  2026-11-13). Tags: v0.1.0 (2025-09-16), v0.2.0.
- Google donated AP2 to the **FIDO Alliance** on 2026-04-28; standardisation continues in
  FIDO's Agentic Authentication and Payments technical working groups. Repo licence Apache-2.0.
- Pre-release: version numbers below 1.0, no official conformance suite, SDK installed from
  git (no PyPI release).

## What changed from v0.1 to v0.2
- v0.1 had Intent, Cart and Payment Mandates. **v0.2 has two mandate types: Checkout Mandate
  and Payment Mandate**, each "open" (constraints, signed by the user, for human-not-present)
  or "closed" (exact checkout/payment). `CartMandate`/`IntentMandate` are gone from the spec.
- Mandates are **SD-JWT verifiable credentials with key binding** (`kb+sd-jwt`, ES256 in the
  examples). `vct` values: `mandate.checkout.1`, `mandate.checkout.open.1`,
  `mandate.payment.1`, `mandate.payment.open.1`.
- New receipts: Checkout Receipt (`status` Success/Error, `iss`, `iat`, `reference`,
  `order_id` or `error`/`error_description`) and Payment Receipt.
- Human Not Present flows, x402 support in samples, Go SDK.

## The merchant's obligations (AP2 v0.2 spec, https://ap2-protocol.org/ap2/specification/)
- Provide a **merchant-signed JWT of the Checkout** (`checkout_jwt`), signed with a
  non-deterministic scheme such as ECDSA, not Ed25519 (the spec is internally inconsistent on
  this; AP2 issue #268).
- Receive a Checkout Mandate before completing a checkout; verify the SD-JWT chain, the
  `checkout_hash`, and every open-mandate constraint (unknown constraints fail).
- Return a **Checkout Receipt** on accept or reject.
- Validation must happen "in deterministic code", even if the merchant is an agent.
- The **Merchant Payment Processor** verifies the Payment Mandate / credential is scoped to the
  checkout.
- **AP2 core does not define how a merchant publishes its public keys.** The repo's samples
  load PEM files from local disk.

## Where readiness is visible from outside
### 1. UCP business profile (the standard path)
UCP 2026-08-25, https://ucp.dev/2026-08-25/specification/payment/extensions/ap2-mandates/:
- Declare `dev.ucp.common.payment.ap2_mandate` in `ucp.capabilities` of `/.well-known/ucp`
  (entry: `version` 2026-08-25, `extends: dev.ucp.shopping.checkout`,
  `config.vp_formats_supported: {"dc+sd-jwt": {}}`).
- Once active: the business **MUST include `ap2.merchant_authorization` in all checkout
  responses** and **MUST NOT accept `complete_checkout` without `ap2.checkout_mandate`**.
- `ap2.merchant_authorization` = **detached JWS** (`<header>..<signature>`, RFC 7515 App. F),
  header `alg` ES256/ES384/ES512 + `kid`, over the **JCS (RFC 8785)** canonical checkout with
  the `ap2` member removed.
- Public keys: top-level **`keys[]`** of the profile (JWK set, RFC 7517). EC keys need `kid`,
  `kty`, `crv` (P-256/P-384), `x`, `y`. All implementations must verify ES256. Rotate every 90
  days, keep old keys ≥ 7 days (https://ucp.dev/2026-08-25/specification/signatures/).
- Business verifies: mandate present (`mandate_required`), SD-JWT signature + key binding +
  expiry, embedded checkout's `merchant_authorization` against its own keys, terms match.
  Error codes: `mandate_required`, `agent_missing_key`, `mandate_invalid_signature`,
  `mandate_expired`, `mandate_scope_mismatch`, `merchant_authorization_invalid`,
  `merchant_authorization_missing`.
- Profile hosting: HTTPS, **no redirects**, `Cache-Control: public` with `max-age ≥ 60` and no
  `private`/`no-store`/`no-cache`; SHOULD send ETag/Last-Modified. Consumers bound the body at
  ≥ 128 KiB and refuse special-use IPs.
- Required profile fields: `ucp.version`, `ucp.services`, `ucp.payment_handlers` (registries
  present even when empty).

### 2. A2A agent card (merchant agents that speak A2A)
- A2A 1.0 (https://a2a-protocol.org/latest/specification/): card at
  `/.well-known/agent-card.json`; required `name`, `description`, `supportedInterfaces`
  (`url`, `protocolBinding`, `protocolVersion`), `version`, `capabilities`,
  `defaultInputModes`, `defaultOutputModes`, `skills`. Cards MAY be signed (JWS, JCS).
- The AP2 v0.2 samples' merchant agent cards (still A2A 0.3 format) declare
  `{"uri": "https://github.com/google-agentic-commerce/ap2/v1", "required": true}` in
  `capabilities.extensions`. The v0.2 spec text does not define this URI; it comes from the
  samples (`code/samples/*/roles/merchant_agent/agent.json`).
- Sample DataPart keys: `ap2.mandates.CheckoutMandateSdJwt`,
  `ap2.mandates.PaymentMandateSdJwt`, `ap2.checkout` (with `checkout_jwt`, `checkout_hash`),
  `ap2.PaymentReceipt`.

## What cannot be tested from outside (read-only)
- Whether the merchant actually verifies incoming mandates and refuses bad ones. Testing it
  means sending `complete_checkout` with a crafted mandate, i.e. writing to a live checkout.
  Possible later as a merchant-consented test against a sandbox endpoint (not built).
- PSP / Merchant Payment Processor readiness (not visible publicly).
- Whether any agent platform (Google AI Mode/Gemini) has enrolled the merchant.

## Market check 2026-11-15
Why the project was parked. Unlike the rest of this file, this section comes from web search
summaries of mostly secondary sources (blogs, vendor pages); the pages were not opened and
verified one by one, and the protocol sources below were not re-read.

- **AP2 is not required by any live agent checkout.** Google's Merchant Center help and
  developer pages call UCP "compatible with" AP2. No adoption figures from FIDO were found.
- **Google's UCP checkout is narrow and gated:** select merchants in the US, Canada and
  Australia, UK expected next, no EU date; each integration needs Google's approval and a
  payment provider that processes Google Pay tokens.
- **ChatGPT Instant Checkout was scaled back** around March 2026 (retired or paused, sources
  disagree) after about a dozen Shopify merchants went live. ACP is still maintained by
  OpenAI and Stripe.
- **Platforms and PSPs are absorbing the implementation work:** Shopify agent storefronts on
  by default; Adobe committed to UCP, ACP and AP2; Adyen Agentic (2026-06-16) covers UCP,
  AP2 and ACP in one integration.
- **Netherlands:** one Dutch analysis notes the protocols assume card payments while Dutch
  checkout runs on iDEAL, so the buyer is handed back to the shop's own site.
- **Existing checkers:** ucp-ready (open source, UCP + AP2), UCPtools (free UCP + ACP check,
  monitoring about $9/month per a third-party listing), Apify Agentic Commerce Readiness
  Index, agenticcommerce.shop scanner, Adam Silva Consulting (paid audit).
- **Existing AP2 implementation:** UCPReady for WooCommerce (Zologic, NL) states it signs
  every checkout response with `ap2.merchant_authorization`; €149 (sources disagree on
  one-time or yearly). Its developer reported a capability-name mismatch that silently
  disabled AP2, the kind of fault check M1 exists to catch. Whether the other checkers
  verify signatures was not confirmed.

Conclusion: a free check is not a differentiator, monitoring has a low price ceiling, and a
plugin would compete with a €149 product. If the project is reopened, the more credible
shape is an independent UCP-first setup-and-verification service for EU shops and agencies,
tested with five to ten conversations before more code is written.

Sources (search results, 2026-11-15):
https://support.google.com/merchants/answer/16837055 ·
https://developers.google.com/merchant/ucp · https://shopify.engineering/UCP ·
https://openai.com/index/buy-it-in-chatgpt/ ·
https://thepaypers.com/payments/news/google-donates-agent-payments-protocol-to-fido-alliance ·
https://github.com/monkydot/ucp-ready · https://ucptools.dev/ ·
https://www.g2.com/products/ucptools/pricing ·
https://apify.com/yasaslive/agentic-commerce-radar · https://www.agenticcommerce.shop/ ·
https://www.adamsilvaconsulting.com/services/acra · https://zologic.nl/ucpready/ ·
https://dev.to/zologic/ap2-mandates-are-live-on-ucpready-heres-what-that-actually-means-for-autonomous-payment-1bba ·
https://sanbi.ai/blog/agentic-commerce-tracker-ai-checkout ·
https://cruxdigits.nl/blog/agentic-commerce-protocols-ucp-acp-ap2/ ·
https://lexagentica.com/blog/ucp-commercial-guide-eu-commerce-leaders

## Sources (read 2026-11-13)
- [primary] https://ap2-protocol.org/ap2/specification/, /ap2/checkout_mandate/,
  /ap2/payment_mandate/, /ap2/agent_authorization/, /ap2/flows/
- [primary] https://github.com/google-agentic-commerce/AP2 (README, CHANGELOG, schemas in
  `code/sdk/schemas/ap2/`, samples in `code/samples/`)
- [primary] https://blog.google/products-and-platforms/platforms/google-pay/agent-payments-protocol-fido-alliance/
- [primary] https://ucp.dev/2026-08-25/specification/overview/,
  .../payment/extensions/ap2-mandates/, .../signatures/, https://ucp.dev/documentation/ucp-and-ap2/
- [primary] https://a2a-protocol.org/latest/specification/
- [primary] RFC 7515 (JWS), RFC 7517 (JWK), RFC 7518 (JWA), RFC 8785 (JCS)

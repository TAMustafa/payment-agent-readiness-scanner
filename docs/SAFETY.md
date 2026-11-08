# Safety guarantees (status 2026-11-08, build steps 1–2)

What the scanner can and cannot do to a live shop, and how each point is enforced.
Technical summary, not legal advice.

## No payments, orders, logins or data entry

| Guarantee | Enforced by | Proven by |
|---|---|---|
| HTTP client sends only `GET` | `scanner/fetch/client.py` (single `stream("GET", …)`) | `tests/test_safety.py::test_http_client_only_uses_get`, AST scan of all code for `post/put/patch/delete` |
| Browser never types, fills, uploads or ticks anything | no such calls in the code | AST scan: `fill`, `type`, `press`, `set_input_files`, `check`, `submit`, … forbidden in every module |
| No credentials, card or bank data exist in the code | — | `test_no_credentials_or_payment_data_in_code` |
| Never contacts a payment provider or bank (Mollie, Adyen, Stripe, PayPal, Klarna, Buckaroo, MultiSafepay, Pay.nl, iDEAL/bank hosts, Shop Pay, …) | network guard in the probe: request aborted | guard table + hostile fake shop that redirects to Mollie |
| Never requests an order / payment / confirmation URL (place-order, /payment, /betaling, onepage/success, /checkouts/…/processing, …) | network guard, any HTTP method | guard table + hostile cart whose "Afrekenen" posts to `/checkout/place-order` |
| Only one write-type request: the add-to-cart click, to the shop's own host | non-GET allowed only during that click window | hostile shop: background `POST /api/track` blocked; only `POST /cart/add` gets through |
| Never clicks pay / order / confirm / express-pay / login / register buttons | `FORBIDDEN_CLICK` label filter | `test_forbidden_labels` |
| On a one-page checkout, the "Bestellen" button is never clicked | click guard: a page with payment choices or required address/e-mail fields is inspected, not clicked | `test_one_page_checkout_bestellen_button_is_never_clicked` |
| Stops at the checkout entry; session discarded | probe ends after inspecting; browser context closed | screenshots of HEMA live run (docs/VERIFY.md) |

Even without these guards a payment could not complete: every Dutch payment method
(iDEAL/Wero, cards, PayPal, Klarna) requires the buyer to authenticate with their bank or
provider, and the scanner holds no credentials. The guards make sure no order is even created.

Mutation check (2026-11-08): with the guards disabled, 12 safety tests fail (order form
submitted, Mollie contacted, one-page "Bestellen" clicked); with the guards on, all pass.

## Politeness and access (CLAUDE.md rule 2)
- Identifies as `AgentReadyScanner/<version> (+contact URL)`. **Set `SCANNER_CONTACT_URL`
  to a real page before scanning shops**; the default is a placeholder.
- robots.txt is respected for our own token, including every probe navigation and the
  likely checkout destination. Only `--checkout-consent` (merchant asked for the scan)
  lifts this for cart/checkout.
- 1 request/second per host, doubled on HTTP 429, Retry-After honoured; ≤ 40 pages + ≤ 10
  D2 re-fetches of the home page; hard 120 s timeout.
- Bot challenges and captchas are detected and reported, never solved or bypassed.

## Privacy (CLAUDE.md rule 6)
- No cookies kept between requests; `Set-Cookie` values are dropped (names only, for
  platform detection). The browser session is discarded after the probe.
- Nothing is typed, so screenshots and reports contain no personal data of ours; stored
  evidence is limited to URLs, short snippets, headers and status codes.
- No paid or LLM APIs are called yet (V1 is build step 3, behind `--visibility`).

## Formerly residual risks — closed 2026-11-08
- **D2 no longer impersonates bots.** Each of the 9 home-page requests carries the bot's
  published User-Agent *plus* our own identity, e.g.
  `…OAI-SearchBot/1.4… (AI-access test by AgentReadyScanner/0.1.0 (+contact))`.
  UA-based firewall rules still match the bot name, but the request openly says it is our
  test. Bots that robots.txt disallows are not tested at all.
  Proven by `tests/test_check_d2.py::test_d2_requests_are_transparent_never_pure_bot_impersonation`.
- **The cart/checkout probe is opt-in.** Default scans never touch a cart: C1, C2 and C4 report
  "not tested". Enable with `--checkout` only for shops you have permission to test
  (robots.txt still respected), or `--checkout-consent` when the merchant asked for the scan
  (also lifts robots.txt for cart/checkout). Proven by
  `tests/test_safety.py::test_checkout_probe_is_opt_in`.
- **Contact URL.** The CLI warns on every scan while `SCANNER_CONTACT_URL` is not set.

## Remaining limits (not risks to the shop)
- Label and path patterns are Dutch/English heuristics; new wording could be missed by the
  click filter. The network guard (payment hosts, order paths, non-GET) is the backstop.
- CDNs that verify bots by IP may treat the real bots differently from our test requests;
  D2 reports this caveat with every result.

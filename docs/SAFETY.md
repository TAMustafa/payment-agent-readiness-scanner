# Safety guarantees (status 2026-11-09, build steps 1–3)

What the scanner can and cannot do to a live shop, and how each point is enforced.
Technical summary, not legal advice.

## No payments, orders, logins or data entry

| Guarantee | Enforced by | Proven by |
|---|---|---|
| HTTP client sends only `GET` | `scanner/fetch/client.py` (single `stream("GET", …)`) | `tests/test_safety.py::test_http_client_only_uses_get`, AST scan of all code for `post/put/patch/delete` |
| Browser never types, fills, uploads or ticks anything | no such calls in the code | AST scan: `fill`, `type`, `press`, `set_input_files`, `check`, `submit`, … forbidden in every module |
| No credentials, card or bank data exist in the code | — | `test_no_credentials_or_payment_data_in_code` |
| Never contacts a listed payment provider or bank (Mollie, Adyen, Stripe, PayPal, Klarna, Buckaroo, MultiSafepay, Pay.nl, iDEAL/bank hosts, Shop Pay and Shopify card fields, Google Pay, Amazon Pay, Apple Pay sessions, …; list in `checkout/markers.py::PAYMENT_HOSTS`) | network guard in the probe: request aborted | guard table + hostile fake shop that redirects to Mollie |
| Never requests an order / payment / confirmation URL (place-order, /payment, /betaling, onepage/success, order-received, `?wc-ajax=checkout`, /checkouts/…/processing, …) | network guard on path + query string, any HTTP method | guard table + hostile cart whose "Afrekenen" posts to `/checkout/place-order` |
| Only one write-type request: the add-to-cart click, to the shop's own host | non-GET allowed only during that click window | hostile shop: background `POST /api/track` blocked; only `POST /cart/add` gets through |
| No request can go around the guard | service workers blocked (their requests are invisible to Playwright routing), WebSockets refused, downloads off | `test_service_workers_and_websockets_cannot_bypass_the_guard` |
| Only an add-to-cart button gets the write window | platform add-to-cart buttons tried first; wishlist / compare / review labels excluded; only selects inside the add-to-cart form are changed | `test_wishlist_button_is_never_clicked_as_add_to_cart`, `test_only_selects_in_the_add_to_cart_form_are_changed` |
| Never clicks pay / order / confirm / express-pay / login / register buttons | `FORBIDDEN_CLICK` label filter | `test_forbidden_labels` |
| On a one-page checkout, the "Bestellen" button is never clicked | click guard: a page with payment choices, required address fields, or a visible required e-mail field outside the footer / newsletter sign-up is inspected, not clicked | `test_one_page_checkout_bestellen_button_is_never_clicked` |
| Stops at the checkout entry; session discarded | probe ends after inspecting; browser context closed | screenshots of HEMA live run (docs/VERIFY.md) |

Even without these guards a payment could not complete: every Dutch payment method
(iDEAL/Wero, cards, PayPal, Klarna) requires the buyer to authenticate with their bank or
provider, and the scanner holds no credentials. The guards make sure no order is even created.

Mutation check (2026-11-08): with the guards disabled, 12 safety tests fail (order form
submitted, Mollie contacted, one-page "Bestellen" clicked); with the guards on, all pass.

## AI visibility (V1): no shop contact, hard spending caps

| Guarantee | Enforced by | Proven by |
|---|---|---|
| V1 contacts **only openrouter.ai**, never a shop | client pinned to `https://openrouter.ai/api/v1`, `_check_host`; visibility package imports no crawler/browser code | `test_openrouter_client_is_pinned_to_openrouter`, `..._refuses_other_hosts`, `test_visibility_package_never_touches_shops` |
| The only POST in the codebase is the OpenRouter chat call | documented allow-list in the AST scan (exactly one `.post("/chat/completions")`) | `test_no_code_types_submits_or_sends_non_get` |
| Max USD 10 per month (≤ EUR 10, Tarek 2026-11-09); per scan ≤ USD 1.40 (typical 1.15) | (1) OpenRouter key limit, monthly reset → HTTP 402 stops all calls; (2) pre-run estimate vs. month-to-date = max(local ledger, OpenRouter `usage_monthly`); (3) before **every** paid call: spent + worst case vs. monthly **and** per-scan cap | `test_monthly_cap_uses_higher_of_ledger_and_openrouter`, `test_per_scan_cap_refuses_before_any_paid_call`, `test_per_scan_cap_is_hard_during_the_run`, `test_openrouter_402_stops_remaining_calls` |
| Costs are booked exactly | ledger books OpenRouter's `usage.cost`, verified live (2026-11-09) to include the search fee and to equal `/generation` `total_cost` | `test_full_run_two_assistants_two_runs`, `docs/VERIFY.md` |
| A call without an answer is never booked as free | timeout or dropped connection after sending → worst case booked (ledger + caps); only refusals and connection failures are free | `test_call_that_times_out_is_booked_at_worst_case` |
| Caps hold with parallel calls | each call reserves its worst case (3 searches) before it starts; check + reserve atomic (fixes a live overshoot: USD 1.17 booked vs USD 1.00 cap) | `test_per_scan_cap_is_hard_during_the_run` |
| No paid call without a key / by default | V1 only with `--visibility` and `OPENROUTER_API_KEY` | `test_no_key_means_no_requests`, `test_visibility_off_by_default` |
| No provider training on our prompts | `provider.data_collection = "deny"` on every request | `test_full_run_two_assistants_two_runs` |
| API keys never committed | `.env` gitignored; scan of all git-tracked files for key patterns | `test_no_api_keys_in_git_tracked_files` (added after a key was pasted into `.env.example` on 2026-11-09 — moved to `.env` before any commit) |

Mutation check (2026-11-09): with the four budget guards disabled, 3 budget tests fail; with
them on, all pass. Tests never make a paid call (fake OpenRouter via `httpx.MockTransport`).

## Politeness and access (CLAUDE.md rule 2)
- Never requests private or local addresses (localhost, private / link-local IPs such as the
  cloud metadata address, `.local` names): refused for the scanned URL, for every redirect
  and inside the probe's browser. Proven by `test_private_addresses_are_never_requested`,
  `test_redirect_to_a_private_address_is_not_followed`, guard table. Limit: a public name
  that resolves to a private address is not caught (no DNS check) — close this before the
  web front-end accepts URLs from strangers.
- robots.txt answered with HTTP 429 twice: nothing else is fetched from that host
  (`test_robots_txt_rate_limited_twice_means_no_crawling`).
- Identifies as `AgentReadyScanner/<version> (+contact URL)`. **Set `SCANNER_CONTACT_URL`
  to a real page before scanning shops**; the default is a placeholder.
- robots.txt is respected for our own token, including every probe navigation and the
  likely checkout destination. Only `--checkout-consent` (merchant asked for the scan)
  lifts this for cart/checkout.
- 1 request/second per host, doubled on HTTP 429, Retry-After honoured; ≤ 40 pages + ≤ 10
  D2 re-fetches of the home page; each request is cut off after 15 s in total; hard 120 s
  timeout (240 s for Shopify; `--visibility` adds its own bounded time).
- Bot challenges and captchas are detected and reported, never solved or bypassed.

## Privacy (CLAUDE.md rule 6)
- No cookies kept between requests; `Set-Cookie` values are dropped (names only, for
  platform detection). The browser session is discarded after the probe.
- Nothing is typed, so screenshots and reports contain no personal data of ours; stored
  evidence is limited to URLs, short snippets, headers and status codes.
- LangSmith tracing (optional) never uploads page content: run inputs and outputs are always
  hidden (`scanner/graph.py::enforce_trace_privacy`, `test_tracing_never_uploads_page_content`).
- LLM calls only in V1 (`--visibility`), only to OpenRouter; questions contain only the shop's
  public brand/category names — no page HTML, no personal data.

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
- The payment-host list is a list: a provider that is not on it can still be loaded (GET
  only). Until 2026-11-12 Google Pay, Amazon Pay, Apple Pay sessions and Shopify card fields
  were missing. Non-GET requests are refused whatever the host.
- Label and path patterns are Dutch/English heuristics; new wording could be missed by the
  click filter. The network guard (payment hosts, order paths, non-GET) is the backstop.
- CDNs that verify bots by IP may treat the real bots differently from our test requests;
  D2 reports this caveat with every result.

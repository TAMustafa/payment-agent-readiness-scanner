# agent-ready-scanner

Read-only scanner (Python + LangGraph) that audits how ready a Dutch webshop is for AI
shopping agents (ChatGPT, Gemini / Google AI Mode, Perplexity, Claude, Copilot) and reports
evidence-backed results per check. Built for merchants on WooCommerce, Shopify, Shopware 6,
Lightspeed eCom and Magento.

**Status (2026-11-09):** build steps 1–3 built and live-verified; step 4 (scoring + HTML
report) is next — see [`docs/NEXT_STEP.md`](docs/NEXT_STEP.md).

| Category | Checks | Status |
|---|---|---|
| D — Discovery & access | D1 robots.txt for AI bots · D2 CDN/WAF blocking · D3 sitemap · D4 data in raw HTML (+ JS render compare) · D5 Merchant Center (manual input) | built |
| S — Structured product data | S1 Product JSON-LD · S2 offer/price match · S3 GTIN/MPN+brand · S4 shipping & returns markup · S5 reviews · S6 Organization | built |
| C — Checkout readiness | C1 add to cart · C2 guest checkout · C3 iDEAL/Wero · C4 captcha · C5 policy text | built (C1/C2/C4 need `--checkout`) |
| P — Agent protocols | P1 UCP profile · P2 platform channel · P3 MCP / ai-catalog / llms.txt | built |
| V — AI visibility | V1 mentions in ChatGPT + Gemini (via OpenRouter, max €10/month) | built and live-verified (`--visibility`) |
| Scoring + HTML report | score, grade, top-5 fixes, NL/EN report | step 4 (not built; JSON only) |

## Setup
```bash
uv sync
uv run playwright install chromium        # headless browser for the checkout probe
cp .env.example .env                      # then set SCANNER_CONTACT_URL to a real page
```
`SCANNER_CONTACT_URL` appears in our User-Agent (`AgentReadyScanner/<version> (+url)`); the
CLI warns while it is unset. Run with `uv run --env-file .env scanner ...`.
For V1 (step 3) add `OPENROUTER_API_KEY` — create the key with a USD 10 limit and monthly
reset so OpenRouter itself enforces the budget (see `config/visibility.toml`).

## Usage
```bash
uv run scanner scan https://example.nl                       # summary in the terminal
uv run scanner scan https://example.nl --out scans/          # + scans/<host>/<ts>/report.json
uv run scanner scan https://example.nl --checks D,S --json   # selected categories as JSON
uv run scanner scan https://example.nl --gmc-active --gmc-disapproved-pct 3   # D5 input
uv run scanner scan https://shop.nl --checkout --out scans/  # + cart/checkout probe
uv run scanner scan https://shop.nl --checkout-consent --out scans/
uv run --env-file .env scanner scan https://shop.nl --visibility --out scans/   # + V1 (paid)
uv run scanner graph                                         # pipeline as Mermaid
```

| Option | Meaning |
|---|---|
| `--checks` | Comma-separated ids, codes or categories: `D1`, `S2.offer`, `C`, … |
| `--out DIR` | Write `report.json` (and probe screenshots) to `DIR/<host>/<timestamp>/` |
| `--json` | Print the report JSON to stdout |
| `--checkout` | Run the headless cart/checkout probe — **only for shops you may test**; adds 1 item to an anonymous cart, stops at checkout entry, robots.txt respected |
| `--checkout-consent` | The merchant asked for the scan: probe may also enter cart/checkout paths that robots.txt disallows |
| `--gmc-active / --gmc-inactive`, `--gmc-disapproved-pct` | Manual Merchant Center input for D5 (never guessed) |
| `--timeout` | Hard scan timeout in seconds (default 120) |
| `--visibility` | V1 AI visibility via OpenRouter — costs money (≈ USD 1.15 per full scan; hard caps USD 1.40/scan and USD 10/month; needs `OPENROUTER_API_KEY`) |
| `--visibility-prompts FILE` | Own V1 questions, one per line (replaces the generated ones) |

Every result has a status (`pass`, `warn`, `fail`, `not_applicable`, `error`), a score
fraction, evidence (URL, detail, snippet) and NL/EN fix guidance. Blocked, rate-limited or
unverifiable checks report `error` with the reason — never a guessed `fail`.

## Safety
The scanner can never pay, order, log in or type into a shop: GET-only HTTP client,
network guards that block payment providers, order paths and non-GET requests in the
browser, a never-click list, and an opt-in probe. Proven by `tests/test_safety.py`
(including a mutation check). Polite crawling: robots.txt, 1 req/s per host, Retry-After,
≤ 40 pages, captchas never bypassed. Details: [`docs/SAFETY.md`](docs/SAFETY.md).

## Documentation
- [`CLAUDE.md`](CLAUDE.md) — working rules, architecture as built, decisions, status
- [`SPEC.md`](SPEC.md) — check catalogue, scoring, build steps, acceptance criteria
- [`docs/NEXT_STEP.md`](docs/NEXT_STEP.md) — hand-off for build step 3 (AI visibility)
- [`docs/VERIFY.md`](docs/VERIFY.md) — reference shops, verification runs, known limits
- [`docs/SAFETY.md`](docs/SAFETY.md) — safety guarantees and how they are enforced

## Development
```bash
uv run ruff check . && uv run mypy scanner && uv run pytest   # ~12 s, 232 tests
```
Tests are fixture-based and offline; the probe tests drive real headless Chromium against
fake shops served through Playwright routes.

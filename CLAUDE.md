# CLAUDE.md — agent-ready-scanner

## What this is
A read-only scanner that audits a Dutch webshop's readiness for AI shopping agents
(ChatGPT, Gemini / Google AI Mode, Perplexity, Claude, Copilot) and produces a scored
report with prioritised fixes.

Business model (context, not code): free scan = lead magnet → paid fix sprint →
monthly monitoring retainer. Owner: Tarek (solo founder). Target: Dutch webshops,
€5–50M revenue, on WooCommerce, Shopify, Shopware 6, Lightspeed eCom, Magento.

The report measures readiness to be **found by AI agents and to accept their orders and
payments** (Tarek, 2026-11-10): 19 checks in 4 stages; only V1 (paid) is outside the report
and stays in report.json. See SPEC §5 and `docs/RELEVANCE.md`. Agentic checkout is NOT
live for Dutch merchants yet (as of Nov 2026) — never claim otherwise in report copy.
This means checkout *inside* AI assistants; card-network agent payments on merchant sites
started in Europe (Visa, July 2026) — see `docs/RELEVANCE.md`. Report language: English by
default (`--lang nl` for Dutch; decided 2026-11-10).

The full check catalogue and acceptance criteria live in `SPEC.md`. Read it before
implementing any check.

## Current status (2026-11-08) — start here
- **Done:** build step 1 (static checks D1–D5, S1–S6, P1–P3, JSON output) and step 2
  (Playwright checkout probe, C1–C5, D4 render comparison, safety guards). 206 tests green.
- **Step 3 (V1 AI visibility): built and verified live (2026-11-09)**, 232 tests green.
  Measured ≈ USD 1.15 per full scan (approved), ≈ 8 scans/month. Remaining items: top of
  **`docs/NEXT_STEP.md`**; details in `docs/VERIFY.md`. Settings: `config/visibility.toml`.
- **Step 4 (scoring + NL/EN HTML report): built and verified (2026-11-10)**, 279 tests green.
  Report scoped to agent-order readiness (4 stages, "why it matters" box per check).
  `scanner/report/`; open points at the end of `docs/VERIFY.md` (merchant test, brand name).
- **Then:** pilots with real merchants; step 5 (web front-end) only after pilots.
- **Logs:** `docs/VERIFY.md` (reference shops, every verification run, known limits),
  `docs/SAFETY.md` (what the scanner can never do to a shop, and the tests that prove it).
- **Repo:** github.com/TAMustafa/payment-agent-readiness-scanner, branch `main`. Tarek commits
  to `main` in this existing repo; commit/push only when he asks.

## Stack (decided)
- Python 3.12+, managed with `uv` (`pyproject.toml`), type hints everywhere, `mypy --strict`
- **LangGraph** (`StateGraph`) orchestrates the scan pipeline; checks fan out in parallel via
  the `Send` API and merge through `Annotated[list[CheckResult], operator.add]` reducers
- Checks themselves are **plain deterministic Python functions** — no LLM calls inside them.
  LLMs are used only in the AI-visibility node (V1), **via OpenRouter with a plain httpx
  client** (`scanner/visibility/openrouter.py`; approved by Tarek 2026-11-09 instead of a
  LangChain wrapper, because V1 needs raw `usage.cost`, annotations and HTTP 402 details)
- `httpx` (async) for HTTP, `playwright` (async, Chromium) for the checkout probe + render
- `selectolax` (lexbor) for HTML. JSON-LD via stdlib `json`, microdata via our own small
  parser (`scanner/parse/product.py`); `extruct` evaluated and not needed
- `pydantic` v2 for config, inputs and check-result validation; stdlib `tomllib` for
  `config/visibility.toml`
- `typer` for the CLI; `pytest` + `pytest-asyncio` for tests; `ruff` for lint/format
- Optional: LangSmith tracing via env vars for debugging the graph and V1 costs

Pinned (exact): langgraph 1.2.20, pydantic 2.14.3, typer 0.28.0, httpx 0.28.1,
selectolax 1.0.2, playwright 1.64.1; dev: mypy 2.4.1, pytest 9.2.0, pytest-asyncio 1.4.1.post1,
ruff 0.17.4. Before adding any other dependency: ask Tarek, check it is maintained, explain
why, keep it minimal, pin it. Check current LangGraph docs
(docs.langchain.com/oss/python/langgraph) before using any API you are not sure about.

## Non-negotiable rules
1. **Read-only.** Never submit forms with data, create accounts, log in, place orders, enter
   payment details, or start a payment redirect. The checkout probe stops at the **checkout
   entry** (first checkout page/drawer) and never types anything. Enforced in code by
   network + click guards (`scanner/checkout/probe.py::_Probe.guard`, `looks_like_checkout`)
   and proven by `tests/test_safety.py` — keep those tests passing; extend them when the
   probe changes. Details: `docs/SAFETY.md`.
2. **Polite crawling.** Identify as `AgentReadyScanner/<version> (+contact URL)`
   (`SCANNER_CONTACT_URL`), respect robots.txt for our own user agent, max 1 request/second
   per host (doubled on 429, Retry-After honoured), max ~40 pages per scan, hard timeout per
   scan (default 120s). Never solve or bypass captchas / bot challenges — report them.
3. **No secrets in code or logs.** API keys via `.env` (gitignored; V1 uses only
   `OPENROUTER_API_KEY`); keep `.env.example` current. LangSmith tracing must not log full page HTML or any personal data.
4. **Deterministic and explainable.** Every check returns evidence (URL, snippet, header,
   status code) so a human can verify the result. No score without evidence.
5. **No fabricated facts in reports.** Report copy is templated from `SPEC.md` guidance;
   LLMs may only be used in the AI-visibility check (step 3), and their raw output is stored.
6. **Privacy/GDPR.** Do not store personal data found on pages. Store only what the check
   needs. No cookies kept between requests; the browser session is discarded.

### Decisions by Tarek (2026-11-08) — do not change without asking
- **Checkout probe is opt-in:** `--checkout` (we may test this shop; robots.txt respected) or
  `--checkout-consent` (merchant asked; may also enter robots-disallowed cart/checkout).
  Default scans report C1/C2/C4 as "not tested".
- Probe pacing: block images/fonts/media/trackers; ≥1 s between navigations via the shared
  per-host limiter; each navigation counts against the page budget.
- Cookie banners: reject first, accept only if there is no other way through.
- Sampling: 8 products / 2 categories / ≤3 sitemap files (shops like Shopify rate-limit
  polite crawlers: 429 + Retry-After 60 after ~2 product pages).
- D2 test requests carry the bot's User-Agent **plus** our identity — never impersonate.
- Live probe runs on third-party shops need Tarek's approval (reference shops: once each).
- **V1 (2026-11-09):** OpenRouter only; **max EUR 10/month** (USD 10 cap enforced by the
  OpenRouter key limit, a local ledger and a pre-scan estimate); ChatGPT + Gemini with
  native search; prompts from the shop's categories via fixed Dutch templates; 2 runs; plain
  httpx client; ≈ USD 1.15 per full scan is fine (ceiling USD 1.40/scan). Native search
  ignores `max_uses`; Gemini cites Google redirect URLs (site = citation title). Never exceed the budget, never make a paid call in tests (fake OpenRouter via
  `httpx.MockTransport`); ask before live paid runs. Keys only in `.env` — a test scans all
  git-tracked files for API keys.

## Architecture (as built)
```
scanner/
  cli.py            # typer: scan <url> [--json] [--out dir] [--checks D,S1,...] [--visibility]
                    #   [--checkout | --checkout-consent] [--gmc-active ...] [--timeout]; graph
  graph.py          # StateGraph wiring + run_scan(); context_schema=ScanDeps
  nodes.py          # all graph nodes (thin; delegate to the packages below)
  state.py          # ScanState TypedDict + reducers; RunCheckInput (Send payload)
  deps.py           # ScanDeps: runtime context (PoliteClient, test route hook) — not in state
  models.py         # pydantic models: CheckResult, ScanContext, ScanReport, CheckoutProbe, ...
  bots.py           # AI bot tokens + UAs per vendor (sources + date verified)
  fetch/            # client.py (polite httpx GET-only client, budgets, backoff), robots.py
                    # (RFC 9309), challenge.py (CDN/WAF detection), agents.py (D2 probes)
  sampling/         # sitemap.py, urls.py (heuristics), select.py (products/categories/policies)
  parse/            # html.py (links, JSON-LD), product.py (product/offer/org extraction)
  platform/         # fingerprint.py, support.py (agentic channel table, sources + date)
  checkout/         # probe.py (Playwright probe + safety guards), markers.py (NL/EN patterns)
  checks/           # one module per check (d1_..., s1_..., c1_..., p1_...); registry.py maps
                    # id -> spec + function; base.py result(); per_page.py; c_common.py
  checks/copy/      # nl/en guidance per check id
  visibility/       # V1: config.py, prompts.py (NL templates), openrouter.py (the ONLY
                    # POST in the codebase, pinned to openrouter.ai), ledger.py (monthly
                    # costs), parse.py (mentions/citations), graph.py (LangGraph subgraph +
                    # budget guards); settings: config/visibility.toml
  report/           # scoring.py (SPEC §5 scope/STAGES, score, grade, top 5 fixes),
                    # html.py (self-contained printable HTML, stdlib only), i18n.py (NL/EN)
tests/
  fixtures/         # robots, sitemaps, home/product pages per platform, UCP profile
  test_safety.py    # never-pay/never-type guarantees (AST scan, guard table, hostile shops,
                    # OpenRouter pinning, no API keys in tracked files)
  test_visibility.py# V1 against a fake OpenRouter: budget caps, 402, ledger, mentions
```

Graph (nodes are async functions; each returns a partial state update):
```
START -> normalise_url -> fetch_basics (robots, home, sitemaps)
      -> fetch_agent_endpoints (/.well-known/ucp, ai-catalog.json, llms.txt)
      -> fingerprint_platform -> sample_pages
      -> probe_user_agents (D2 data) -> checkout_probe (opt-in Playwright; C1-C4, D4 render)
      -> [fan-out via Send] run_check (one per enabled check id, incl. C1-C5)
      -> visibility (only with --visibility: V1 subgraph plan -> budget_check -> Send(ask))
      -> score (scanner.report.scoring)
      -> render_report -> END
```
- Data collection happens in network nodes **before** the fan-out; checks only read
  `ScanContext` and never fetch. The probe runs before the fan-out for the same reason.
- `ScanState.results: Annotated[list[CheckResult], operator.add]` collects parallel results.
- Retry policy only on network nodes, never on checks. An exception inside a check becomes
  `status="error"` and never aborts the graph (`nodes.run_check`).
- The HTTP client lives in the LangGraph runtime context (`ScanDeps`), not in state, so a
  checkpointer can be added later (web UI / queued scans).
- Time budget: the client stops fetching before the hard timeout so a partial report always
  renders; the sampler keeps time free for D2 probes (15 s) and the checkout probe (30 s).

Core contract (do not change without asking):
```python
CheckStatus = Literal["pass", "warn", "fail", "not_applicable", "error"]


class Evidence(BaseModel):
    url: str | None = None
    detail: str
    snippet: str | None = None


class CheckResult(BaseModel):
    id: str  # stable id from SPEC.md, e.g. "D1.robots_ai_crawlers"
    category: Literal["discovery", "data", "checkout", "protocol", "visibility"]
    label: str
    status: CheckStatus
    weight: int  # from SPEC.md
    score_fraction: float  # 0..1, partial credit allowed
    evidence: list[Evidence]
    guidance: str  # fix text from checks/copy, shown when not "pass"
    effort: Literal["S", "M", "L"]


# A check: async def check(ctx: ScanContext) -> CheckResult   (build via checks/base.result)
```
Status conventions used everywhere: blocked/rate-limited/unverifiable → `error` (never a
guessed `fail`); nothing to test → `not_applicable`; emerging standards (P3) → `warn`, never
`fail`.

## How to work (agile, small increments)
- Build in the order of SPEC.md "Build steps". Finish and verify one step before the next.
- Per check: write a fixture-based unit test first, then the implementation.
- After each step: `uv run ruff check . && uv run mypy scanner && uv run pytest`, then a live
  scan of the reference shops in `docs/VERIFY.md`, compare against a manual check (open the
  page / curl it), and record results + fixes + limits in `docs/VERIFY.md`.
- Expect false results on live data and hunt them: every round so far found 2–4 (variant
  fields, soft 404s, rate-limit pages read as content, shop ratings in product markup, …).
- State assumptions explicitly; when a platform behaviour or protocol detail is uncertain,
  check current official docs before implementing and cite the URL in a code comment.
- Ask before: adding dependencies, changing the CheckResult contract, deleting files,
  anything that would write to or interact with a live shop beyond reading, anything that
  costs money (LLM APIs in V1).
- Live-scan etiquette: back-to-back scans from one IP make shops (Shopify, fixje) rate-limit
  harder; space them out. `--checks` limits a run (`--checks D2,C1`, `--checks S`).

## Commands
- `uv sync` then `uv run playwright install chromium`
- `uv run scanner scan https://example.nl --out scans/` (report.json + report.html +
  screenshots; `--lang en` for English)
- `uv run scanner report scans/<host>/<ts>/report.json [--lang en]` (re-render HTML offline)
- `uv run scanner scan https://example.nl --checks D,S --json`
- `uv run scanner graph` (Mermaid of the pipeline)
- `uv run ruff check . && uv run mypy scanner`
- `uv run --env-file .env scanner scan https://example.nl --visibility --out scans/` (V1, paid)
- `uv run pytest` (≈13 s, 279 tests; probe tests drive real headless Chromium against fake
  shops; V1 tests use a fake OpenRouter — no paid calls)

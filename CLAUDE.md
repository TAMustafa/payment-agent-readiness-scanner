# CLAUDE.md — agent-ready-scanner

## What this is
A read-only scanner that audits a Dutch webshop's readiness for AI shopping agents
(ChatGPT, Gemini / Google AI Mode, Perplexity, Claude, Copilot) and produces a scored
report with prioritised fixes.

Business model (context, not code): free scan = lead magnet → paid fix sprint →
monthly monitoring retainer. Owner: Tarek (solo founder). Target: Dutch webshops,
€5–50M revenue, on WooCommerce, Shopify, Shopware 6, Lightspeed eCom, Magento.

The report sells **AI discovery today** (being found and recommended) and
**agent-checkout readiness** as the forward-looking upsell. Agentic checkout is NOT
live for Dutch merchants yet (as of Nov 2026) — never claim otherwise in report copy.

The full check catalogue and acceptance criteria live in `SPEC.md`. Read it before
implementing any check.

## Stack (decided)
- Python 3.12+, managed with `uv` (`pyproject.toml`), type hints everywhere, `mypy --strict`
- **LangGraph** (`StateGraph`) orchestrates the scan pipeline; checks fan out in parallel via
  the `Send` API and merge through `Annotated[list[CheckResult], operator.add]` reducers
- Checks themselves are **plain deterministic Python functions** — no LLM calls inside them.
  LLMs are used only in the AI-visibility node (V1), via LangChain chat model integrations
- `httpx` (async) for HTTP, `playwright` (async, Chromium) for rendering and the checkout probe
- `selectolax` or `beautifulsoup4` for HTML parsing; `extruct` optional for JSON-LD (evaluate first)
- `pydantic` v2 for config, inputs and check-result validation
- `typer` for the CLI; `pytest` + `pytest-asyncio` for tests; `ruff` for lint/format
- Optional: LangSmith tracing via env vars for debugging the graph and V1 costs

Before adding any other dependency: check it is maintained, explain why, keep it minimal.
Check current LangGraph docs (docs.langchain.com/oss/python/langgraph) before using any API
you are not sure about — the API changes between minor versions. Pin versions in pyproject.

## Non-negotiable rules
1. **Read-only.** Never submit forms, create accounts, place orders, enter payment
   details, or start a payment redirect. The checkout probe stops at the payment-method
   selection step.
2. **Polite crawling.** Identify as `AgentReadyScanner/<version> (+contact URL)`, respect
   robots.txt for our own user agent, max 1 request/second per host, max ~40 pages per scan,
   hard timeout per scan (default 120s).
3. **No secrets in code or logs.** API keys via `.env` (gitignored); provide `.env.example`.
   LangSmith tracing must not log full page HTML or any personal data.
4. **Deterministic and explainable.** Every check returns evidence (URL, snippet, header,
   status code) so a human can verify the result. No score without evidence.
5. **No fabricated facts in reports.** Report copy is templated from `SPEC.md` guidance;
   LLMs may only be used in the AI-visibility check (step 3), and their raw output is stored.
6. **Privacy/GDPR.** Do not store personal data found on pages. Store only what the check needs.

## Architecture
```
scanner/
  cli.py                 # typer entry: scan <url> [--json] [--out dir] [--checks a,b] [--visibility]
  graph.py               # LangGraph StateGraph definition (see below)
  state.py               # ScanState TypedDict + reducers
  fetch/                 # httpx client (rate-limit, UA, timeouts), robots parser
  sampling/              # find product/category/policy pages (sitemap -> link crawl fallback)
  checks/                # one module per check; registry maps check id -> function
  checks/copy/           # nl/en guidance strings per check id
  platform/              # fingerprinting + support table
  visibility/            # V1 prompt runner (only LLM-using code)
  report/                # scoring, top-5 fixes, JSON + HTML (Jinja2) rendering
  models.py              # pydantic models: CheckResult, ScanReport, ...
tests/
  fixtures/              # saved HTML/robots/JSON-LD samples per platform
```

Graph (nodes are async functions; each returns a partial state update):
```
START -> normalise_url -> fetch_basics (robots, sitemap, /.well-known/ucp)
      -> fingerprint_platform -> sample_pages
      -> [fan-out via Send] run_check (one invocation per enabled check id)
      -> checkout_probe (step 2)  -> visibility (step 3, only if --visibility)
      -> score -> render_report -> END
```
- `ScanState.results: Annotated[list[CheckResult], operator.add]` collects parallel results.
- Shared fetched data (pages, robots, headers) lives in state so checks never refetch.
- Use a node-level retry policy only for network nodes, never for checks.
- An exception inside a check must become `status="error"` in its CheckResult and must not
  abort the graph.
- No checkpointer needed in v1 (single-run CLI); keep the graph compatible with adding one
  later (web UI / queued scans).

Core contract (reuse of the QualityCheck pattern from AiPoweredMerchantActivation):
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


# A check: async def check_d1(ctx: ScanContext) -> CheckResult
```

## How to work (agile, small increments)
- Build in the order of SPEC.md "Build steps". Finish and verify one step before the next.
- Per check: write a fixture-based unit test first, then the implementation.
- After each step: run `uv run ruff check . && uv run mypy scanner && uv run pytest`, then a live scan of the 5 reference shops
  listed in SPEC.md, and compare against a manual check. Record results in `docs/VERIFY.md`.
- State assumptions explicitly; when a platform behaviour or protocol detail is uncertain,
  check current official docs before implementing and cite the URL in a code comment.
- Ask before: adding dependencies, changing the CheckResult contract, deleting files,
  anything that would write to or interact with a live shop beyond reading.

## Commands (to be created in step 1)
- `uv sync` then `uv run playwright install chromium`
- `uv run scanner scan https://example.nl --out scans/`
- `uv run ruff check . && uv run mypy scanner`
- `uv run pytest`

# Next step: build step 3 — AI visibility (V1)

> **Status 2026-11-09: V1 built and verified live** (2 runs on thuisbezorgd.nl; 4 issues
> found in run 1 and fixed; run 2: 40/40 calls, USD 1.160 booked = billed). ≈ USD 1.15 per
> full scan (approved), ≈ 8 scans per USD 10 month. OpenRouter key rotated. Optional: a run
> with generated questions on a non-protected shop. **Next: build step 4 (scoring + HTML).**

Hand-off written 2026-11-08 after steps 1–2; updated 2026-11-09 (OpenRouter, budget). Read `CLAUDE.md` (status, rules, decisions)
and `SPEC.md` §4 V and §8 first.

## 0. Decisions so far (Tarek, 2026-11-09) and what is still open
Decided:
- **Provider: OpenRouter** for all LLM calls (one key `OPENROUTER_API_KEY`, one bill).
- **Budget: max EUR 10 per month in total** → cap USD 10 (OpenRouter bills USD).
- **Assistants: ChatGPT + Gemini**, both with the provider's *native* web search.
- **Questions:** 2 brand + 8 generic, generic ones built from the **scanned shop's own
  category names**; wording from **fixed Dutch templates** (no LLM-generated prompts).
  Operator override via a prompts file (SPEC).
- Settings live in **`config/visibility.toml`** (models, budget, runs, privacy); key in `.env`.

Resolved 2026-11-09 (Tarek approved the plan): 2 runs, plain httpx. Originally open:
1. **Approve the plan/config** below: 2 runs (SPEC) ≈ USD 0.53/scan ≈ 18 visibility scans per
   month, or 1 run ≈ USD 0.27 ≈ 37 scans; or swap Gemini for Perplexity (≈ 24 scans).
2. **Client: plain `httpx` (recommended, no new dependency) vs `langchain-openrouter` 0.2.9.**
   OpenRouter is OpenAI-compatible; we need raw fields (`usage.cost`, `message.annotations`,
   server-tool parameters, HTTP 402 `limit_source`) that the LangChain wrapper is not
   documented to expose. httpx keeps LangGraph for orchestration but deviates from
   CLAUDE.md's "LLMs via LangChain chat model integrations" → needs Tarek's OK.
3. Tarek creates the OpenRouter key with **limit 10, monthly reset**, sets account privacy
   (no training), and adds the key to `.env` before the live verification.

## 1. What SPEC asks for (V1.prompt_visibility, weight 10)
- 10 Dutch buying prompts: 2 brand + 8 non-brand, from the shop's categories
  (e.g. "beste e-bike accu kopen in Nederland"). Operator can override.
- Run across ≥ 2 assistants **with web search**; run everything **2×** and report both
  (results are non-deterministic). Score = mention rate; record position + cited URL.
- Store raw responses. Log cost per scan. Behind `--visibility`. Mark as
  "snapshot, varies over time".
- Implement as a **LangGraph subgraph**: prompt generation → parallel assistant calls via
  `Send` → parse mentions.

## 2. Design (OpenRouter)
### OpenRouter facts used (read 2026-11-09, docs.openrouter.ai)
- Chat Completions endpoint, OpenAI-compatible: `POST https://openrouter.ai/api/v1/chat/completions`.
- Web search = server tool `{"type": "openrouter:web_search", "parameters": {"engine":
  "native", "max_uses": 1}}` (the `web` plugin and `:online` are **deprecated**).
  Native search: OpenAI GPT-4.1/GPT-5+, Gemini 3 Flash/Pro, 3.1 Flash/Lite, 3.5 Flash,
  Perplexity, Anthropic, Grok 4+. Native fee is passed through (USD 0.01 OpenAI, 0.014
  Google, 0.005 Perplexity/xAI per search, per the models API `pricing.web_search`).
  Google native search has **no location parameter** → say "in Nederland" in the prompt.
- Citations: `message.annotations[]` → `{"type": "url_citation", "url_citation": {"url",
  "title", "start_index", "end_index"}}`.
- Cost: every response has `usage.cost` (USD) and `usage.server_tool_use_details.
  web_search_requests`; `GET /api/v1/generation?id=` for details. Whether search fees are
  inside `usage.cost` is **not stated** → verify on the first live call; until verified add
  `web_search_requests × pricing.web_search` ourselves when computing the ledger amount.
- Spend control: key `limit` + `limit_reset: "monthly"` (resets 1st 00:00 UTC);
  `GET /api/v1/key` → `limit_remaining`, `usage_monthly`. Over the limit → **HTTP 402**
  with `error.metadata.limit_source` (`openrouter_key_limit` / `openrouter_credits`).
- Live prices: `GET /api/v1/models` (public): `pricing.prompt/completion` (USD per token),
  `pricing.web_search` (USD per search), `pricing.request`.
- Privacy: request `provider: {"data_collection": "deny"}`; account setting at
  openrouter.ai/settings/privacy. OpenRouter itself does not train on inputs/outputs.

### Cost model (live prices 2026-11-09; per question ≈ search fee + ~4k in / 600 out tokens)
| Assistant | Model | ≈ USD/question |
|---|---|---|
| ChatGPT (default) | `openai/gpt-6-luna` | 0.0107 |
| Gemini (default) | `google/gemini-3.1-flash-lite` | 0.0159 |
| Perplexity (cheaper alt.) | `perplexity/sonar` | 0.0096 |
| Claude (alt.) | `anthropic/claude-haiku-5.5` | 0.0107 |
| Grok (alt.) | `x-ai/grok-4.3` | 0.0115 |
| Budget, *not representative* | `openai/gpt-oss-20b` + engine `parallel` | 0.0013 |

The search fee dominates; token prices barely matter. The budget option uses a generic
search index, so it does not show what ChatGPT/Gemini tell shoppers — never label it as such.

### Budget guard (three layers, all must hold)
1. **OpenRouter key limit** USD 10/month (hard stop by OpenRouter, HTTP 402 → V1 `error`,
   scan continues).
2. **Local ledger** `scans/visibility_ledger.jsonl` (gitignored): one line per call with
   actual `usage.cost`; month-to-date sum checked before a scan; cross-checked with
   `GET /api/v1/key` `usage_monthly` (take the higher).
3. **Pre-scan estimate** with live prices and `worst_case_searches`: refuse the V1 run
   (status `error`, reason in evidence, no calls made) if estimate > `per_scan_usd` or
   month-to-date + estimate > `monthly_usd`.

### Modules (`scanner/visibility/`)
```
config.py    # load config/visibility.toml (tomllib) into pydantic settings
prompts.py   # NL templates: 2 brand + 8 from category names; prompts-file override
openrouter.py# httpx client: chat call with server tool, 402/429 handling, live prices,
             #   /key usage; GET-free of shop data — only openrouter.ai is contacted
ledger.py    # append/read month-to-date costs; budget checks
parse.py     # mention detection: brand/domain in text, domain in citations; position;
             #   cited URL (deterministic)
graph.py     # subgraph: build_prompts -> budget_check -> Send(call, {assistant, prompt, run})
             #   -> parse -> aggregate -> CheckResult V1 (+ cost + raw file paths)
```
Hook points already in place: `ScanOptions.visibility` (`--visibility`), `nodes.visibility`
stub, `nodes.route_after_checks`, `REGISTRY["V1.prompt_visibility"]` (`func=None`; the node
appends its result to `state["results"]`). Inputs in state: domain, brand (S6 Organization
`name`, else home `<title>`), category pages (`<h1>`/`<title>`).
Models to add: `VisibilityCall` (assistant, model, prompt, run, mentioned, position,
cited_urls, searches, cost_usd, raw_path, error), `VisibilityResult` (calls, mention rate per
assistant and per run, total cost); `visibility` on `ScanReport`.

Rules that apply:
- **No shop requests** in V1 — only openrouter.ai. No page HTML in prompts or traces.
- Raw responses saved under `scans/<host>/<ts>/visibility/raw/*.json` (only with `--out`).
- Every call's cost goes to the ledger; failures → that call `error`, never abort the scan.
- Own timeout (`timeout_s`), concurrency cap, 429 backoff.
- Safety tests (like `tests/test_safety.py`): budget guard refuses before any HTTP call;
  402 handling; no request to any host but openrouter.ai from the visibility package.

## 3. Tests (no money spent)
- Unit tests with an `httpx.MockTransport` serving recorded OpenRouter responses per
  assistant (`tests/fixtures/visibility/`), incl. annotations, `usage.cost`, 402, 429.
- Mention parsing edge cases: brand inside another word, domain only in citations, shop
  listed 4th of 5, Dutch diacritics, `www.` vs bare domain.
- Budget guard: projected cost above per-scan or monthly cap → no calls made; ledger month
  rollover (UTC); 402 from OpenRouter → V1 `error`, rest of the scan unaffected.
- Graph test: `--visibility` off → V1 absent/not_applicable; on with fakes → V1 result with
  both runs reported.

## 4. Verification (live, costs money — get Tarek's OK on prompts + budget first)
- Run on 2 reference shops (e.g. hema.nl, duifhuizen.nl), both runs; check mentions by hand
  in the raw responses; compare ledger cost with the OpenRouter dashboard / `GET /api/v1/key`;
  confirm whether `usage.cost` includes the search fee; record cost per scan in
  `docs/VERIFY.md` (target ≈ USD 0.53 or less; month ≤ USD 10).

## 5. Other open items (not blocking step 3)
- **Live probe not yet verified on fixje.nl (WooCommerce) and jhparts.nl (Lightspeed)** —
  run once each when their rate limits / challenges allow (approval exists: once per shop).
- **Shopify sampling:** 0–2 product pages per scan (429 + Retry-After 60). S1–S5/D4 often
  `error` on Shopify. Option for later: accept 1–2 pages (theme template is shared).
- **Lightspeed:** no reachable reference shop yet (all behind a Cloudflare challenge).
- **Confirm with Tarek:** effort sizes S/M/L per check (my estimates, in `registry.py`);
  D5 thresholds (≤ 5 % pass, ≤ 20 % warn); SPEC §6 support-table differences
  (`scanner/platform/support.py`, re-verify monthly); brand name for the report header.
- **Step 4** (report): `nodes.score` is a stub — implement SPEC §5 scoring, top-5 fixes,
  NL/EN HTML report (Jinja2 would be a new dependency → ask). Include the D2 method note and
  "agent checkout not live in NL" in the methodology section.

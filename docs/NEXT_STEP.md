# Next step: build step 3 — AI visibility (V1)

Hand-off written 2026-11-08 after steps 1–2. Read `CLAUDE.md` (status, rules, decisions)
and `SPEC.md` §4 V and §8 first.

## 0. Ask Tarek before writing code
V1 is the only part that costs money and the only LLM-using code. Get answers to:
1. **Niche for the first outreach** (SPEC §9) — drives the default non-brand prompts.
2. **Which assistants** (SPEC: ≥ 2 with web search). Candidates — verify current APIs,
   web-search/grounding features, model IDs and prices in official docs at build time;
   do not rely on memory:
   - OpenAI (ChatGPT search behaviour) — Responses API with web search tool
   - Google Gemini — grounding with Google Search (closest to AI Mode)
   - Perplexity — Sonar API (search-native, returns citations)
   - Anthropic Claude — web search tool
   - Microsoft Copilot — no public consumer-equivalent API known; confirm
3. **Budget:** SPEC success criterion is < €0.50 per scan (2 runs × 10 prompts × N
   assistants). Also a monthly cap. Who provides the API keys (`.env`)?
4. **Prompt generation:** deterministic templates (recommended; satisfies "no fabricated
   facts", reproducible) vs. LLM-generated prompts. Operator override via a prompts file is
   required either way (SPEC).
5. **New dependencies** (CLAUDE.md: LangChain chat model integrations), e.g.
   `langchain-openai`, `langchain-google-genai`, `langchain-anthropic`, and a Perplexity
   integration — check each is maintained and supports the web-search feature through
   LangChain; otherwise propose the vendor SDK for that one. Pin exact versions.

## 1. What SPEC asks for (V1.prompt_visibility, weight 10)
- 10 Dutch buying prompts: 2 brand + 8 non-brand, from the shop's category
  (e.g. "beste e-bike accu kopen nederland"). Operator can override.
- Run across ≥ 2 assistants **with web search**; run everything **2×** and report both
  (results are non-deterministic). Score = mention rate; record position + cited URL.
- Store raw responses. Log cost per scan. Behind `--visibility`. Mark as
  "snapshot, varies over time".
- Implement as a **LangGraph subgraph**: prompt generation → parallel assistant calls via
  `Send` → parse mentions.

## 2. Design that fits the existing code
Hook points already in place:
- `ScanOptions.visibility` (CLI `--visibility`), `nodes.visibility` (stub, returns `{}`),
  `nodes.route_after_checks` routes to it; `REGISTRY["V1.prompt_visibility"]` has
  `func=None` (produced by the node, not the fan-out). The node appends its CheckResult to
  `state["results"]` (list reducer).
- Inputs available in state: origin/domain, brand (S6 Organization `name`, else home
  `<title>`), category pages (`state["pages"].categories` → `<h1>`/`<title>`), product names.

Proposed modules (`scanner/visibility/`):
```
prompts.py   # templates NL: brand + non-brand from category names; load override file
assistants.py# one adapter per assistant: call(prompt) -> RawResponse(text, citations,
             #   usage tokens, model, latency); LangChain chat models; web search on
parse.py     # deterministic mention detection: brand/domain in text, domain in citations;
             #   position = rank of first mention among shops/citations; cited URL
cost.py      # price table (per model, € per 1k tokens, source URL + date verified) and
             #   budget guard: estimate before running, stop if projected > cap
graph.py     # subgraph: build_prompts -> Send(call, {assistant, prompt, run}) -> parse
             #   -> aggregate -> CheckResult V1 (+ cost + raw file paths)
```
Models to add in `models.py`: `VisibilityCall` (assistant, model, prompt, run, mentioned,
position, cited_urls, cost_eur, raw_path, error), `VisibilityResult` (calls, mention rate
per assistant and per run, total cost). Add `visibility` to `ScanReport`.

Rules that apply:
- **No shop requests** in V1 — only the LLM APIs. No page HTML in prompts or traces.
- Raw responses saved under `scans/<host>/<ts>/visibility/raw/*.json` (only with `--out`);
  never fabricate: report copy comes from `checks/copy`, numbers from parsed results.
- Budget guard before any paid call (`--visibility-budget`, default €0.50); every call's
  usage and cost logged; failures → that call `error`, never abort the scan.
- Own timeout for V1 (separate from the 120 s crawl budget), parallel per assistant with a
  concurrency cap; respect each API's rate limits.
- `.env.example`: add the chosen keys (names only). LangSmith tracing must not log page HTML.

## 3. Tests (no money spent)
- Unit tests with LangChain fake chat models (e.g. `GenericFakeChatModel`) and recorded raw
  response fixtures per assistant (`tests/fixtures/visibility/`).
- Mention parsing edge cases: brand inside another word, domain only in citations, shop
  listed 4th of 5, Dutch diacritics, `www.` vs bare domain.
- Budget guard: projected cost above cap → no calls made.
- Graph test: `--visibility` off → V1 absent/not_applicable; on with fakes → V1 result with
  both runs reported.

## 4. Verification (live, costs money — get Tarek's OK on prompts + budget first)
- Run on 2 reference shops (e.g. hema.nl, duifhuizen.nl), both runs; check mentions by hand
  in the raw responses; record cost per scan in `docs/VERIFY.md` (target < €0.50).

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

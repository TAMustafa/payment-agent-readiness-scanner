# Audit 2026-11-10: agentic-commerce specs and customer-ready report

Requested by Tarek after commit 9b256f3. Scope: does the code follow the current agentic
commerce / payment specifications, and is the HTML report fit to show to customers?
Spec sources and the per-check relevance table: `docs/RELEVANCE.md`.

## 1. Specifications
| Area | Status | Action taken |
|---|---|---|
| P1 UCP profile | Matches the newest dated UCP version **2026-08-25** (`/.well-known/ucp`, required `ucp.version` / `services` / `payment_handlers`, transports, no redirect, cache headers). | Added a note when no payment handler is declared ("agents cannot pay through UCP yet") and list the handlers otherwise. |
| P3 MCP / feed | MCP endpoint via UCP service entry, MCP Server Cards (SEP-2127) at `/.well-known/ai-catalog.json`, llms.txt partial. | None. Known limit: ACP feeds are pushed privately to OpenAI and are invisible from outside. |
| C3 payments | ACP Delegated Payment = cards (fpan / network token); Google UCP = Google Pay handler, card credentials; Visa/Mastercard agent payments = card tokens. | Already changed today: cards **and** iDEAL/Wero. |
| D2 agent access | Shopping agents sign requests (Web Bot Auth, RFC 9421; Visa Trusted Agent Protocol). Cannot be tested from outside. | Guidance advises allowing signed agents (D2, and now also C4). |
| P2 platform table | **Out of date** for two platforms. | **Shopware 6 → native**: official Shopware AG plugin *SwagAgenticCommerce* (v1.4.0, 2026-10-02; UCP, discovery files, OpenAI JSONL + Google feeds), github.com/shopware/agentic-commerce. **Magento → none (announced)**: Adobe has said it will support UCP and ACP; no native module (secondary sources). Shopify, WooCommerce, Lightspeed unchanged. |
| Bots (D1/D2) | List matches vendor docs read 2026-11-08. Google-Agent / Google-GeminiNotebook still without a stated robots token. | None. |

## 2. Customer-facing report
Found and fixed (all covered by new tests; 283 tests green):
1. Operator text reached customers: "checkout probe not enabled (opt-in: --checkout …)",
   "No Merchant Center input provided (manual input; never guessed)", "Probe could not reach
   this step", Chromium/playwright errors. → Unmeasured checks now show a plain-language
   "Why not measured" (`i18n.UNMEASURED`); report.json keeps the technical wording.
2. Probe internals shown: "safety_guard: blocked - 11 request(s) …" and screenshot file
   names. → Hidden in HTML, kept in report.json.
3. Platform codes ("shopware6", "other", "lightspeed: None known (none)") → display names
   ("Shopware 6", "custom or other"); P2 evidence drops the level code.
4. Footer and evidence pointed to `report.json`, which customers do not get → "technical
   appendix available on request".
5. Title changed to "Ready for AI shopping agents?" (covers discovery + orders).
6. Added a snapshot disclaimer with the scan date to "How we measured".
7. Copy accuracy: "agent checkout is not live in NL" made precise as **checkout inside AI
   assistants** (card-network agent payments on shop sites started in Europe); removed an
   unsupported claim in S1 ("AI agents read JSON-LD most reliably"); P1 mentions the
   official Shopware plugin; C4 advises letting signed agents through; D5 notes Google's
   agent checkout runs on Merchant Center.
8. Grammar: D3 evidence "A sitemap request was rate limited our scanner" fixed.

Checked by a fresh read-only scan of duifhuizen.nl (20:57 UTC, 78.9 Partly ready): no internal
strings left in the HTML (scripted search for CLI flags, report.json, probe, safety_guard,
platform codes, "None").

## 3. Before showing reports to customers (open)
- **Brand name** in the header is still the placeholder "Agent-Ready Scan" (`SCANNER_BRAND`).
- **Saved reports from before this audit** carry old evidence wording (e.g. a Dutch P2 note in
  jhparts.nl's report). Re-scan before sending; `scanner report` only re-scores and re-renders.
- **Evidence lines stay in English** even in the Dutch report (technical, for the developer).
- **Merchant test** (SPEC §1) not done yet.
- **Live confirmation** of the sampler fixes on fixje.nl is pending (rate-limited tonight).
- Primary ACP / Google UCP payment pages were read as excerpts only; re-read in full before
  release.

# Verification log

The scanner-era log (reference shops, probe runs, V1 costs) is in git history at commit
4cd9af7 (`docs/VERIFY.md`); uncommitted work from 2026-11-12 is in `git stash list`
("pre-AP2-pivot").

## 2026-11-13 — pivot to the AP2 Readiness Check
- Removed: the webshop scanner (LangGraph pipeline, Playwright checkout probe, 19 checks,
  V1 AI-visibility via OpenRouter, scoring/HTML report) and its docs/config. Dependencies
  dropped: langgraph, playwright, selectolax. Added (pinned): fastapi 0.162.0, uvicorn 0.54.0,
  cryptography 50.0.2. Kept: robots.txt parser + tests.
- Built: checks U1–U5, A1–A2, G1–G2, M1, verdict, CLI (`ap2check check|serve`), website.
- `uv run ruff check . && uv run mypy ap2check && uv run pytest`: clean, **96 tests green**.
- Fixture coverage: valid profile (all pass); redirect, 404, 403/429/503; missing registries;
  http endpoints; five Cache-Control cases; no handlers; AP2 undeclared / without checkout /
  without `dc+sd-jwt`; leaked private key; keys inside `ucp`; Ed25519-only; P-384-only;
  duplicate kid; `use: enc`; A2A 1.0 card, AP2-sample 0.3 card, non-required and missing
  extension, http interface; UCP signature valid / reformatted / tampered / other key /
  unknown kid / missing / compact-instead-of-detached / no keys; A2A `checkout_jwt` alone and
  in DataPart, hash mismatch, EdDSA, expired, missing merchant; no PII echoed. JCS against the
  RFC 8785 sample.
- Browser check (local server): `example.com` → "AI agents cannot find your AP2 setup", U1
  fail (404), dependent checks n/a; layout OK at 375 px and desktop, dark mode.

## Known limits
- No live merchant with a UCP AP2 profile verified yet (next step; ask Tarek per site).
- UCP signs the full checkout JSON; if a merchant's JCS differs from ours on exotic numbers
  (floats beyond double precision), a valid signature could be reported as failing. Our JCS
  matches the RFC 8785 test vector.
- A2A extension URI comes from the AP2 samples, not the spec text; revisit when FIDO
  publishes the next version.
- Rate limits are in memory (one process); a multi-instance deployment needs a shared store.

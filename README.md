# agent-ready-scanner

Read-only scanner (Python + LangGraph) that scores a webshop's readiness for AI shopping agents and outputs a
report with prioritised fixes. Built for Dutch merchants (WooCommerce, Shopify, Shopware,
Lightspeed, Magento).

- `CLAUDE.md` — working rules and architecture for Claude Code
- `SPEC.md` — check catalogue, scoring, build steps and acceptance criteria

Status: build step 1 done (CLI + static checks D1–D5, S1–S6, P1–P3, JSON output).
Next: step 2 (Playwright checkout probe, C1–C5). Verification log: `docs/VERIFY.md`.

```bash
uv sync
uv run scanner scan https://example.nl --out scans/          # summary + report.json
uv run scanner scan https://example.nl --checks D,S --json   # selected categories as JSON
uv run scanner scan https://example.nl --gmc-active --gmc-disapproved-pct 3   # D5 input
uv run scanner graph                                          # pipeline as Mermaid
uv run ruff check . && uv run mypy scanner && uv run pytest
```

Set `SCANNER_CONTACT_URL` (see `.env.example`) before scanning real shops: it appears in our
User-Agent.

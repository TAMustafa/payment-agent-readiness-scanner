# agent-ready-scanner

Read-only scanner (Python + LangGraph) that scores a webshop's readiness for AI shopping agents and outputs a
report with prioritised fixes. Built for Dutch merchants (WooCommerce, Shopify, Shopware,
Lightspeed, Magento).

- `CLAUDE.md` — working rules and architecture for Claude Code
- `SPEC.md` — check catalogue, scoring, build steps and acceptance criteria

Status: build steps 1–2 done (static checks D1–D5, S1–S6, P1–P3; headless checkout probe
C1–C5; JSON output + screenshots). Next: step 3 (AI visibility, V1). Verification log:
`docs/VERIFY.md`.

```bash
uv sync && uv run playwright install chromium
uv run scanner scan https://example.nl --out scans/          # summary + report.json
uv run scanner scan https://example.nl --checks D,S --json   # selected categories as JSON
uv run scanner scan https://example.nl --gmc-active --gmc-disapproved-pct 3   # D5 input
uv run scanner scan https://shop.nl --checkout --out scans/   # + cart/checkout probe (only
                                                              # with permission; robots.txt kept)
uv run scanner scan https://shop.nl --checkout-consent --out scans/  # merchant asked: may also
                                                              # enter robots-disallowed checkout
uv run scanner graph                                          # pipeline as Mermaid
uv run ruff check . && uv run mypy scanner && uv run pytest
```

Set `SCANNER_CONTACT_URL` (see `.env.example`) before scanning real shops: it appears in our
User-Agent. Safety guarantees (no payments, orders, logins or data entry): `docs/SAFETY.md`.

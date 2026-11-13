# AP2 Readiness Check

A website (and CLI) that tells a merchant whether they are set up correctly to accept
**AP2 (Agent Payments Protocol)** payment requests from AI shopping agents. Read-only: it
fetches the merchant's public discovery documents and, optionally, verifies the signature on
one checkout response the merchant pastes in. It never calls the merchant's checkout.

Based on AP2 v0.2 (2026-04-28, now under FIDO Alliance standardisation), UCP 2026-08-25
(AP2 mandates extension) and A2A 1.0. Research notes: [`docs/AP2.md`](docs/AP2.md).
Check catalogue and verdict rules: [`SPEC.md`](SPEC.md).

| Stage | Checks |
|---|---|
| Discovery | U1 `/.well-known/ucp` reachable (HTTPS, no redirect, JSON) · U2 required UCP fields · U3 cache headers |
| Checkout | U4 checkout capability + callable endpoint · U5 payment handlers |
| AP2 | A1 `dev.ucp.common.payment.ap2_mandate` declared · A2 public EC signing keys in `keys[]` |
| A2A (optional) | G1 `/.well-known/agent-card.json` · G2 AP2 extension declared |
| Signature | M1 `ap2.merchant_authorization` (detached JWS over JCS) or `checkout_jwt` verifies against the published key |

Verdicts: not discoverable · AP2 not declared · incomplete · well-formed but untested ·
signature failed · ready.

## Setup
```bash
uv sync
cp .env.example .env      # set AP2CHECK_CONTACT_URL (shown in our User-Agent)
```

## Usage
```bash
uv run --env-file .env ap2check serve                      # website on http://127.0.0.1:8000
uv run --env-file .env ap2check check shop.example.com     # terminal summary
uv run --env-file .env ap2check check shop.example.com --sample checkout.json --json
uv run ruff check . && uv run mypy ap2check && uv run pytest
```

## Layout
```
ap2check/
  fetch.py        # the only network code: GET only, no redirects, SSRF + robots + rate limits
  robots.py       # RFC 9309 parser
  jose.py         # JCS (RFC 8785), EC JWKs, ES256/384/512 verification (verify only)
  checks/         # base.py (spec URLs, guidance), profile.py (U*, A*), agent_card.py (G*),
                  # signature.py (M1)
  runner.py       # normalise URL -> fetch -> checks -> verdict -> Report
  cli.py          # typer: check, serve
  web/app.py      # FastAPI: GET /, POST /api/check, /healthz; rate limits, CSP
  web/static/     # index.html, app.css, app.js (no build step)
tests/            # fixtures built in tests/helpers.py; test_safety.py proves the guarantees
docs/             # AP2.md (research), SAFETY.md, VERIFY.md (log)
```

# Safety guarantees (status 2026-11-13)

What the AP2 Readiness Check can and cannot do to a merchant, and how each point is enforced.
Technical summary, not legal advice.

| Guarantee | Enforced by | Proven by (`tests/`) |
|---|---|---|
| Only GET requests; no write to any merchant | `ap2check/fetch.py` is the only network code and uses one `stream("GET", …)` | `test_safety.py::test_fetcher_sends_get_only_and_never_follows_redirects`, `test_only_fetch_module_does_network_io`; `test_runner_web.py::test_ready_with_valid_sample` asserts every request is GET |
| Never calls a checkout, never sends mandates or payment data | no such code; checks read collected data only | AST scans above |
| At most 3 requests per check, ≥ 1 s apart, polite identity, robots.txt respected | `Fetcher` (budget 6, per-host interval, `AP2ReadinessCheck` UA) | `test_ready_with_valid_sample` (exact paths, UA), `test_robots_disallow_is_respected` |
| Redirects never followed (also UCP's rule) | `follow_redirects=False` | `test_redirect_is_not_followed` |
| Cannot be used to read internal services (SSRF) | `private_host` on the submitted name, DNS resolution checked before any request, https only, no redirects | `test_normalise_refuses`, `test_dns_to_private_address_is_refused`. Limit: DNS rebinding between our lookup and the connection is not prevented |
| Cannot be used to hammer a shop | 4 checks/min per target host, 6/min per visitor, 4 concurrent | `test_api_rate_limits_per_target` |
| The package never signs and never holds private keys | no `sign`/`generate_private_key`/`private_bytes` in `ap2check/` (signing helpers exist only in `tests/helpers.py`) | `test_package_never_signs_or_handles_private_keys` |
| A merchant who publishes a private key is told loudly | A2 fails on `d`/`p`/`q`/… members | `test_checks.py::test_leaked_private_key_fails_loudly` |
| Pasted samples are not stored, logged, or echoed | processed in memory; evidence shows headers, kids, hashes, field names only; no persistence; API responses `no-store` | `test_evidence_never_echoes_sample_values` |
| Hostile profile/card content cannot run in the visitor's browser | front-end uses `textContent` only; strict CSP (`script-src 'self'`) | `test_frontend_never_uses_innerhtml`, `test_index_and_security_headers` |
| No secrets in the repository | `.env` gitignored | `test_no_api_keys_in_tracked_files` (also catches PEM private keys) |

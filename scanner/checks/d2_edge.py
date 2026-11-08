"""D2.edge_blocking — AI search/agent user agents get a normal page, not 403/429/challenge.

Reads AgentProbes collected by the probe_user_agents node (checks never fetch).
- pass: every tested bot got the page
- fail: at least one tested bot blocked; score = share of tested bots that got the page
- warn instead of fail when the site is behind Cloudflare/Akamai: they block spoofed
  bot names (not from the bot's IPs), so our probe cannot prove the real bot is blocked
- HTTP 429 (rate limited) is never counted as blocked: observed shops rate-limit our own
  scanner too, so it does not show bot targeting
- error: inconclusive — everything blocked *including our own scanner* (bot protection
  for all unknown clients; a CDN that verifies real bots by IP may still let them in), or
  no usable responses
- not_applicable: every bot is disallowed by robots.txt on the probe page (D1 covers it)
"""

from __future__ import annotations

from scanner.checks.base import result
from scanner.models import CheckResult, Evidence, ScanContext

CHECK_ID = "D2.edge_blocking"
CAVEAT = (
    "Method: the home page was requested once per bot with a User-Agent containing that "
    "bot's published name plus our own scanner identity (we never pose as the bot), from "
    "our own IP. CDNs that verify bots by IP (e.g. Cloudflare verified bots) may treat the "
    "real bots differently."
)


async def check(ctx: ScanContext) -> CheckResult:
    ap = ctx.agent_probes
    if ap.url is None:
        return result(CHECK_ID, ctx, "error", 0.0, [Evidence(detail=ap.baseline_reason)])

    evidence = [
        Evidence(
            url=ap.url,
            detail=f"Baseline (our scanner): {ap.baseline_outcome}, {ap.baseline_reason}",
        )
    ]
    for p in ap.probes:
        evidence.append(
            Evidence(url=p.url, detail=f"{p.token} ({p.kind}): {p.outcome}, {p.reason}")
        )
    evidence.append(Evidence(detail=CAVEAT))

    tested = [p for p in ap.probes if p.tested]
    ok = [p for p in tested if p.outcome == "ok"]
    blocked = [p for p in tested if p.outcome == "blocked"]

    if not tested:
        return result(CHECK_ID, ctx, "not_applicable", 0.0, evidence)
    limited = [p for p in tested if p.outcome == "rate_limited"]
    if limited:
        evidence.insert(
            0,
            Evidence(
                url=ap.url,
                detail=f"Rate limited (HTTP 429), not counted as blocked: "
                f"{', '.join(p.token for p in limited)}. A 429 can be caused by our own request "
                "rate, so it does not prove the bot is targeted.",
            ),
        )
    if not ok and not blocked:
        return result(CHECK_ID, ctx, "error", 0.0, evidence)
    if not ok and ap.baseline_outcome == "blocked":
        evidence.insert(
            0,
            Evidence(
                url=ap.url,
                detail="Inconclusive: the site blocks all automated clients, including our own "
                "scanner. Whether the real AI bots are let through cannot be verified "
                "from outside.",
            ),
        )
        return result(CHECK_ID, ctx, "error", 0.0, evidence)

    fraction = len(ok) / (len(ok) + len(blocked))
    if blocked:
        names = ", ".join(p.token for p in blocked)
        if ap.cdn:
            # CDNs block requests that claim to be a known bot but do not come from its IP
            # ranges ("fake bot" protection). Our spoofed request cannot tell that apart from
            # a real AI-bot block, so this is a warning to check the CDN settings, not a fail.
            evidence.insert(
                0,
                Evidence(
                    url=ap.url,
                    detail=f"Blocked by {ap.cdn} when claiming to be: {names}. {ap.cdn} may block "
                    "requests that use a bot's name without coming from that bot's IP addresses, "
                    "so the real bots may still get through. Check the bot / AI crawler settings "
                    f"in the {ap.cdn} dashboard.",
                ),
            )
            return result(CHECK_ID, ctx, "warn", fraction, evidence)
        evidence.insert(0, Evidence(url=ap.url, detail=f"Blocked at the edge: {names}"))
        return result(CHECK_ID, ctx, "fail", fraction, evidence)
    return result(CHECK_ID, ctx, "pass", 1.0, evidence)

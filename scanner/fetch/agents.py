"""D2 data collection: re-fetch one page with each AI search/assistant bot's User-Agent.

Politeness:
- the home page only (our earlier home fetch is the baseline); runs after sampling in time
  the sampler keeps free;
- separate small probe budget, same 1 req/s per-host limit;
- a bot that robots.txt disallows on that page is NOT impersonated (D1 reports it);
- training-only bots are not probed (D2 is about search/agent access).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from scanner.bots import BOTS
from scanner.fetch.challenge import classify
from scanner.fetch.client import PoliteClient
from scanner.fetch.robots import robots_from_resource
from scanner.models import AgentProbes, FetchedResource, SiteBasics, UaProbe


def detect_cdn(res: FetchedResource) -> str | None:
    h = {k.lower(): v.lower() for k, v in res.headers.items()}
    if "cf-ray" in h or "cloudflare" in h.get("server", ""):
        return "Cloudflare"
    if "akamai" in h.get("server", "") or any(k.startswith("x-akamai") for k in h):
        return "Akamai"
    return None


async def probe_agents(client: PoliteClient, basics: SiteBasics) -> AgentProbes:
    """Probe the home page; our own earlier home fetch is the baseline (no extra request)."""
    base = basics.home
    if base is None:
        return AgentProbes(baseline_reason="no page available to probe")
    url = base.url
    verdict = classify(base)
    robots = robots_from_resource(basics.robots)
    path = urlsplit(url).path or "/"

    out = AgentProbes(
        url=url,
        baseline_outcome=verdict.outcome,
        baseline_reason=verdict.reason,
        cdn=detect_cdn(base),
    )
    for bot in BOTS:
        if bot.kind == "training" or bot.user_agent is None:
            continue
        if robots is not None and not robots.is_allowed(bot.token, path):
            out.probes.append(
                UaProbe(
                    token=bot.token,
                    kind=bot.kind,
                    url=url,
                    tested=False,
                    outcome="skipped",
                    reason="disallowed by robots.txt for this bot (see D1); not impersonated",
                )
            )
            continue
        res = await client.get(url, user_agent=bot.user_agent, probe=True)
        v = classify(res)
        out.probes.append(
            UaProbe(
                token=bot.token,
                kind=bot.kind,
                url=url,
                tested=True,
                outcome=v.outcome,
                reason=v.reason,
            )
        )
    return out

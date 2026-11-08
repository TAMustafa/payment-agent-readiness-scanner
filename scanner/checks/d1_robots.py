"""D1.robots_ai_crawlers — robots.txt allows AI search/agent user agents.

Pass: every search + user_agent bot allowed on home, product and category paths.
Warn: only training bots/tokens blocked (merchant's choice; neutral wording).
Fail: any search or user_agent bot blocked. Score = share of those bots allowed.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from scanner.bots import BOTS
from scanner.checks.base import result
from scanner.fetch.robots import robots_from_resource
from scanner.models import CheckResult, Evidence, ScanContext
from scanner.sampling.urls import is_product_entry

CHECK_ID = "D1.robots_ai_crawlers"
BLOCKED_FOR_US = frozenset({401, 403, 429})


def refusal_reason(status: int) -> str:
    """Wording for a status that hides a file from our scanner."""
    if status == 429:
        return "rate limited our scanner (HTTP 429)"
    return f"refused to our scanner (HTTP {status}, likely bot protection)"


MAX_PRODUCT_PATHS = 3
MAX_OTHER_PATHS = 2


def paths_to_test(ctx: ScanContext) -> list[str]:
    """Home + sampled product/category pages; falls back to sitemap URLs before sampling."""
    host = urlsplit(ctx.origin).hostname
    urls: list[str] = [p.url for p in ctx.pages.products[:MAX_PRODUCT_PATHS]]
    urls += [p.url for p in ctx.pages.categories[:MAX_OTHER_PATHS]]
    if not urls:
        entries = [e for e in ctx.basics.sitemap.entries if urlsplit(e.loc).hostname == host]
        urls += [e.loc for e in entries if is_product_entry(e)][:MAX_PRODUCT_PATHS]
        urls += [e.loc for e in entries if not is_product_entry(e)][1 : 1 + MAX_OTHER_PATHS]
    paths = ["/"]
    for u in urls:
        parts = urlsplit(u)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        if path not in paths:
            paths.append(path)
    return paths


async def check(ctx: ScanContext) -> CheckResult:
    res = ctx.basics.robots
    robots_url = ctx.origin + "/robots.txt"
    robots = robots_from_resource(res)
    if res is None or robots is None:
        detail = res.error if res and res.error else "robots.txt could not be fetched"
        return result(CHECK_ID, ctx, "error", 0.0, [Evidence(url=robots_url, detail=detail)])

    assert res.status_code is not None
    if res.status_code in BLOCKED_FOR_US:
        # RFC 9309 would treat this as "no robots.txt", but a 401/403/429 to our scanner
        # usually means bot protection: the real file is hidden from us, so do not guess.
        return result(
            CHECK_ID,
            ctx,
            "error",
            0.0,
            [
                Evidence(
                    url=robots_url,
                    detail=f"robots.txt {refusal_reason(res.status_code)}, so it cannot be "
                    "verified. D2 tests AI user agents directly.",
                )
            ],
        )
    if robots.policy == "allow_all":
        return result(
            CHECK_ID,
            ctx,
            "pass",
            1.0,
            [
                Evidence(
                    url=robots_url,
                    detail=f"HTTP {res.status_code}: no robots.txt, so all crawlers are allowed "
                    "(RFC 9309 §2.3.1.3)",
                )
            ],
        )
    if robots.policy == "disallow_all":
        return result(
            CHECK_ID,
            ctx,
            "fail",
            0.0,
            [
                Evidence(
                    url=robots_url,
                    detail=f"HTTP {res.status_code}: robots.txt unreachable (server error); "
                    "crawlers must then assume everything is disallowed (RFC 9309 §2.3.1.4)",
                )
            ],
        )

    paths = paths_to_test(ctx)
    evidence: list[Evidence] = []
    blocked_access: list[str] = []
    blocked_training: list[str] = []
    allowed: list[str] = []

    for bot in BOTS:
        blocked = [(p, robots.decide(bot.token, p)) for p in paths]
        blocked = [(p, d) for p, d in blocked if not d.allowed]
        if not blocked:
            allowed.append(bot.token)
            continue
        path, decision = blocked[0]
        group = f"User-agent: {bot.token}" if decision.group == "token" else "User-agent: *"
        rule = decision.rule.text() if decision.rule else "(no rule)"
        more = f" (+{len(blocked) - 1} more paths)" if len(blocked) > 1 else ""
        note = f" Note — {bot.robots_note}." if bot.robots_note else ""
        evidence.append(
            Evidence(
                url=robots_url,
                detail=f"{bot.token} ({bot.vendor}, {bot.kind}) blocked on {path}{more} "
                f"by group '{group}'.{note}",
                snippet=f"line {decision.rule.line_no}: {rule}" if decision.rule else None,
            )
        )
        (blocked_training if bot.kind == "training" else blocked_access).append(bot.token)

    access_bots = [b for b in BOTS if b.kind != "training"]
    evidence.append(
        Evidence(
            url=robots_url,
            detail=f"Tested paths: {', '.join(paths)}. Allowed: {', '.join(allowed) or 'none'}.",
        )
    )

    if blocked_access:
        fraction = 1 - len(blocked_access) / len(access_bots)
        return result(CHECK_ID, ctx, "fail", fraction, evidence)
    if blocked_training:
        evidence.append(
            Evidence(
                url=robots_url,
                detail="Only AI-training crawlers are blocked. This does not affect being found "
                "by AI search or shopping assistants; it is a business choice.",
            )
        )
        return result(CHECK_ID, ctx, "warn", 1.0, evidence)
    return result(CHECK_ID, ctx, "pass", 1.0, evidence)

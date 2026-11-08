"""Graph nodes. Each is an async function returning a partial ScanState update.

Skeleton: network/sampling/scoring nodes are stubs that return empty-but-valid data.
They will delegate to scanner.fetch / sampling / platform / report as those are built.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from langgraph.runtime import Runtime
from langgraph.types import Send

from scanner import __version__
from scanner.checkout.probe import run_probe
from scanner.checks.copy import get_guidance
from scanner.checks.registry import REGISTRY, static_check_ids
from scanner.deps import ScanDeps
from scanner.fetch.agents import probe_agents
from scanner.fetch.client import PoliteClient
from scanner.fetch.robots import robots_from_resource
from scanner.models import (
    AgentEndpoints,
    CheckoutProbe,
    CheckResult,
    Evidence,
    FetchedResource,
    ScanContext,
    ScanReport,
    SiteBasics,
)
from scanner.platform.fingerprint import fingerprint
from scanner.sampling.select import sample
from scanner.sampling.sitemap import collect_sitemaps
from scanner.state import RunCheckInput, ScanState

Update = dict[str, Any]


def normalise(url: str) -> str:
    """Return the origin (scheme://host[:port]) for a user-supplied shop URL."""
    raw = url.strip()
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"not a valid http(s) URL: {url!r}")
    host = parts.hostname.lower()
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}"


async def normalise_url(state: ScanState) -> Update:
    # Redirect resolution + final origin happen in fetch_basics once the fetch layer exists.
    return {"origin": normalise(state["url"])}


async def fetch_basics(state: ScanState, runtime: Runtime[ScanDeps]) -> Update:
    """robots.txt -> home (resolves redirects) -> robots.txt of final host if it changed
    -> sitemaps. Robots is registered first so later fetches respect it. A rate-limited
    (429) home page is fetched once more: fingerprinting and home-page checks need it."""
    client = runtime.context.client
    origin = state["origin"]

    robots_res = await _fetch_robots(client, origin)
    home = await client.get(origin + "/")
    if home.status_code == 429:
        # The client already honours Retry-After / backs off before this second attempt.
        home = await client.get(origin + "/")
    final_url = home.final_url or origin + "/"
    final_origin = normalise(final_url)
    if final_origin != origin:
        robots_res = await _fetch_robots(client, final_origin)

    robots = robots_from_resource(robots_res)
    sitemap = await collect_sitemaps(client, final_origin, robots.sitemaps if robots else [])

    return {
        "origin": final_origin,
        "basics": SiteBasics(
            final_url=final_url,
            origin=final_origin,
            https=final_origin.startswith("https://"),
            home=home,
            robots=robots_res,
            sitemap=sitemap,
        ),
    }


async def _fetch_robots(client: PoliteClient, origin: str) -> FetchedResource:
    res = await client.get(origin + "/robots.txt", respect_robots=False)
    robots = robots_from_resource(res)
    host = urlsplit(origin).hostname or ""
    # Network error -> no robots registered: we cannot tell, and the home fetch will
    # most likely fail the same way.
    if robots is not None:
        client.set_robots(host, robots)
    return res


async def fingerprint_platform(state: ScanState) -> Update:
    return {"platform": fingerprint(state["basics"].home)}


async def sample_pages(state: ScanState, runtime: Runtime[ScanDeps]) -> Update:
    opts = state["options"]
    pages = await sample(
        runtime.context.client,
        state["basics"],
        state["platform"],
        max_products=opts.max_products,
        max_categories=opts.max_categories,
        checkout_probe=opts.checkout or opts.checkout_consent,
    )
    return {"pages": pages}


async def fetch_agent_endpoints(state: ScanState, runtime: Runtime[ScanDeps]) -> Update:
    client = runtime.context.client
    origin = state["origin"]
    return {
        "endpoints": AgentEndpoints(
            ucp=await client.get(origin + "/.well-known/ucp"),
            ai_catalog=await client.get(origin + "/.well-known/ai-catalog.json"),
            llms_txt=await client.get(origin + "/llms.txt"),
        )
    }


async def probe_user_agents(state: ScanState, runtime: Runtime[ScanDeps]) -> Update:
    probes = await probe_agents(runtime.context.client, state["basics"])
    return {"agent_probes": probes}


def fan_out_checks(state: ScanState) -> list[Send] | str:
    """Conditional edge: one Send per enabled static check."""
    ids = static_check_ids(state["options"].checks)
    if not ids:
        return route_after_checks(state)
    ctx = ScanContext(
        origin=state["origin"],
        options=state["options"],
        basics=state["basics"],
        platform=state["platform"],
        pages=state["pages"],
        agent_probes=state["agent_probes"],
        endpoints=state["endpoints"],
        checkout=state.get("checkout", CheckoutProbe(skipped_kind="disabled")),
    )
    return [Send("run_check", RunCheckInput(check_id=i, ctx=ctx)) for i in ids]


async def run_check(state: RunCheckInput) -> Update:
    """Run one check. Any exception becomes status="error" and never aborts the graph."""
    spec = REGISTRY[state["check_id"]]
    ctx = state["ctx"]
    try:
        assert spec.func is not None
        result = await spec.func(ctx)
    except Exception as exc:  # deliberate catch-all: isolate check failures
        result = CheckResult(
            id=spec.id,
            category=spec.category,
            label=spec.label,
            status="error",
            weight=spec.weight,
            score_fraction=0.0,
            evidence=[Evidence(url=ctx.origin, detail=f"{type(exc).__name__}: {exc}")],
            guidance=get_guidance(spec.id, ctx.options.lang),
            effort=spec.effort,
        )
    return {"results": [result]}


async def checkout_probe(state: ScanState, runtime: Runtime[ScanDeps]) -> Update:
    """Playwright probe (C1-C4, part of C3, D4 render). Runs before the check fan-out so
    the checks stay pure functions over collected data."""
    opts = state["options"]
    wanted = {i.split(".", 1)[0] for i in static_check_ids(opts.checks)}
    if not (opts.checkout or opts.checkout_consent):
        # Opt-in: the probe adds an item to an anonymous cart (decided 2026-11-08).
        return {
            "checkout": CheckoutProbe(
                skipped_kind="disabled",
                skipped_reason="checkout probe not enabled (opt-in: --checkout when you have "
                "permission to test this shop, --checkout-consent when the merchant asked)",
            )
        }
    if not ({"C1", "C2", "C3", "C4", "D4"} & wanted):
        return {
            "checkout": CheckoutProbe(
                skipped_kind="disabled", skipped_reason="no checkout checks selected"
            )
        }
    probe = await run_probe(
        runtime.context.client,
        state["origin"],
        state["platform"].platform,
        state["pages"],
        consent=opts.checkout_consent,
        artifacts=Path(opts.artifacts_dir) if opts.artifacts_dir else None,
        route_hook=runtime.context.browser_route_hook,
    )
    return {"checkout": probe}


def route_after_checks(state: ScanState) -> str:
    return "visibility" if state["options"].visibility else "score"


async def visibility(state: ScanState) -> Update:
    # STUB (build step 3): V1 subgraph — the only LLM-using code.
    return {}


async def score(state: ScanState) -> Update:
    # STUB (build step 4): weighted, re-normalised score per SPEC.md section 5.
    excluded = sum(r.status in ("not_applicable", "error") for r in state["results"])
    return {"score": None, "excluded_checks": excluded}


async def render_report(state: ScanState, runtime: Runtime[ScanDeps]) -> Update:
    pages = state["pages"]
    # Builds the validated ScanReport; HTML rendering arrives in build step 4.
    report = ScanReport(
        scanner_version=__version__,
        url=state["url"],
        origin=state["origin"],
        started_at=state["started_at"],
        finished_at=datetime.now(UTC),
        platform=state["platform"],
        sampled={
            "products": [p.url for p in pages.products],
            "categories": [p.url for p in pages.categories],
            **{f"policy:{k}": [v.url] for k, v in pages.policies.items()},
        },
        sampling_notes=pages.notes
        + [
            Evidence(detail=f"Host rate-limited us (HTTP 429) {n}x on {h}; slowed down")
            for h, n in runtime.context.client.rate_limited.items()
        ]
        + (
            [Evidence(detail="Fetching stopped early: scan time budget reached")]
            if runtime.context.client.stopped_for_time
            else []
        ),
        requests_made=runtime.context.client.requests_made,
        score=state.get("score"),
        grade=None,
        excluded_checks=state.get("excluded_checks", 0),
        results=sorted(state["results"], key=lambda r: r.id),
    )
    return {"report": report}

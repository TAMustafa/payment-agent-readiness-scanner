"""LangGraph StateGraph for one scan.

START -> normalise_url -> fetch_basics -> fetch_agent_endpoints (UCP, ai-catalog, llms.txt)
      -> fingerprint_platform -> sample_pages -> probe_user_agents (D2 data)
      -> [Send fan-out] run_check -> checkout_probe -> (visibility?) -> score
      -> render_report -> END

API reference (LangGraph 1.2): https://docs.langchain.com/oss/python/langgraph/graph-api
(Send for map-reduce, add_node(..., retry_policy=RetryPolicy(...))).
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy

from scanner import nodes
from scanner.deps import ScanDeps
from scanner.fetch.client import PoliteClient
from scanner.models import ScanOptions, ScanReport
from scanner.state import RunCheckInput, ScanState

# Retries only on network nodes, never on checks (CLAUDE.md).
NETWORK_RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0)
# Time kept back from the scan timeout for checks + report once fetching stops.
RESERVE_S = 10.0


def build_graph() -> CompiledStateGraph[ScanState, ScanDeps, ScanState, ScanState]:
    g = StateGraph(ScanState, context_schema=ScanDeps)

    g.add_node("normalise_url", nodes.normalise_url)
    g.add_node("fetch_basics", nodes.fetch_basics, retry_policy=NETWORK_RETRY)
    g.add_node("fingerprint_platform", nodes.fingerprint_platform)
    g.add_node("sample_pages", nodes.sample_pages, retry_policy=NETWORK_RETRY)
    g.add_node("fetch_agent_endpoints", nodes.fetch_agent_endpoints, retry_policy=NETWORK_RETRY)
    g.add_node("probe_user_agents", nodes.probe_user_agents, retry_policy=NETWORK_RETRY)
    g.add_node("run_check", nodes.run_check, input_schema=RunCheckInput)
    g.add_node("checkout_probe", nodes.checkout_probe)
    g.add_node("visibility", nodes.visibility)
    g.add_node("score", nodes.score)
    g.add_node("render_report", nodes.render_report)

    g.add_edge(START, "normalise_url")
    g.add_edge("normalise_url", "fetch_basics")
    g.add_edge("fetch_basics", "fetch_agent_endpoints")
    g.add_edge("fetch_agent_endpoints", "fingerprint_platform")
    # Sampling first: on rate-limiting shops (Shopify ~12 req/min for our UA) the first
    # requests go to product/policy pages. D2 probes run after, in time the sampler keeps
    # free (PROBE_RESERVE_S), so they cannot be starved either.
    g.add_edge("fingerprint_platform", "sample_pages")
    g.add_edge("sample_pages", "probe_user_agents")
    g.add_conditional_edges(
        "probe_user_agents", nodes.fan_out_checks, ["run_check", "checkout_probe"]
    )
    g.add_edge("run_check", "checkout_probe")
    g.add_conditional_edges("checkout_probe", nodes.route_after_checkout, ["visibility", "score"])
    g.add_edge("visibility", "score")
    g.add_edge("score", "render_report")
    g.add_edge("render_report", END)

    return g.compile()


async def run_scan(
    url: str,
    options: ScanOptions | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    min_interval_s: float = 1.0,
) -> ScanReport:
    opts = options or ScanOptions()
    graph = build_graph()
    initial: ScanState = {
        "url": url,
        "options": opts,
        "started_at": datetime.now(UTC),
        "results": [],
    }
    async with PoliteClient(
        max_requests=opts.max_pages,
        min_interval_s=min_interval_s,
        transport=transport,
        time_budget_s=max(opts.timeout_s - RESERVE_S, 1.0),
    ) as client:
        final = await graph.ainvoke(initial, context=ScanDeps(client=client))
    report: ScanReport = final["report"]
    return report

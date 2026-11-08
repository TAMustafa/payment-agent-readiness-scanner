"""LangGraph StateGraph for one scan.

START -> normalise_url -> fetch_basics -> fingerprint_platform -> sample_pages
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


def build_graph() -> CompiledStateGraph[ScanState, ScanDeps, ScanState, ScanState]:
    g = StateGraph(ScanState, context_schema=ScanDeps)

    g.add_node("normalise_url", nodes.normalise_url)
    g.add_node("fetch_basics", nodes.fetch_basics, retry_policy=NETWORK_RETRY)
    g.add_node("fingerprint_platform", nodes.fingerprint_platform)
    g.add_node("sample_pages", nodes.sample_pages, retry_policy=NETWORK_RETRY)
    g.add_node("run_check", nodes.run_check, input_schema=RunCheckInput)
    g.add_node("checkout_probe", nodes.checkout_probe)
    g.add_node("visibility", nodes.visibility)
    g.add_node("score", nodes.score)
    g.add_node("render_report", nodes.render_report)

    g.add_edge(START, "normalise_url")
    g.add_edge("normalise_url", "fetch_basics")
    g.add_edge("fetch_basics", "fingerprint_platform")
    g.add_edge("fingerprint_platform", "sample_pages")
    g.add_conditional_edges("sample_pages", nodes.fan_out_checks, ["run_check", "checkout_probe"])
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
        max_requests=opts.max_pages, min_interval_s=min_interval_s, transport=transport
    ) as client:
        final = await graph.ainvoke(initial, context=ScanDeps(client=client))
    report: ScanReport = final["report"]
    return report

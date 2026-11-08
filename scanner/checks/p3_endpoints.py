"""P3.mcp_or_feed_endpoint — a public MCP endpoint or agent-readable file is discoverable.

Emerging area: warn, never fail, in v1 (SPEC §4 P). Read-only discovery, no JSON-RPC calls:
- MCP endpoint in the UCP profile (service entry with transport "mcp"),
  https://ucp.dev/2026-08-25/specification/overview/
- /.well-known/ai-catalog.json (MCP Server Cards, SEP-2127, status Final),
  https://modelcontextprotocol.io/seps/2127-mcp-server-cards.md
- /llms.txt (agent-readable site summary; partial credit only).
The MCP spec itself defines no /.well-known/mcp path, so none is probed.
"""

from __future__ import annotations

import json
from typing import Any

from scanner.checks.base import result
from scanner.models import CheckResult, Evidence, FetchedResource, ScanContext

CHECK_ID = "P3.mcp_or_feed_endpoint"


def _json(res: FetchedResource | None) -> Any:
    if res is None or res.status_code != 200 or not res.body:
        return None
    try:
        return json.loads(res.body)
    except json.JSONDecodeError:
        return None


def mcp_endpoints_from_ucp(profile: Any) -> list[str]:
    services = (
        (profile or {}).get("ucp", {}).get("services", {}) if isinstance(profile, dict) else {}
    )
    found: list[str] = []
    for entries in services.values() if isinstance(services, dict) else []:
        for e in entries if isinstance(entries, list) else [entries]:
            if isinstance(e, dict) and e.get("transport") == "mcp" and e.get("endpoint"):
                found.append(str(e["endpoint"]))
    return list(dict.fromkeys(found))


async def check(ctx: ScanContext) -> CheckResult:
    ep = ctx.endpoints
    evidence: list[Evidence] = []

    mcp = mcp_endpoints_from_ucp(_json(ep.ucp))
    if mcp:
        evidence.append(
            Evidence(
                url=ctx.origin + "/.well-known/ucp",
                detail=f"MCP endpoint declared in UCP profile: {mcp[0]}",
            )
        )
    catalog = _json(ep.ai_catalog)
    if catalog is not None:
        evidence.append(
            Evidence(
                url=ctx.origin + "/.well-known/ai-catalog.json",
                detail="AI catalog (MCP Server Cards) published",
            )
        )
    llms = ep.llms_txt
    has_llms = bool(
        llms
        and llms.status_code == 200
        and llms.body
        and not llms.body.lstrip().lower().startswith(("<!doctype", "<html"))
    )
    if has_llms:
        evidence.append(
            Evidence(
                url=ctx.origin + "/llms.txt",
                detail="llms.txt published",
                snippet=(llms.body or "")[:160] if llms else None,
            )
        )

    if mcp or catalog is not None:
        return result(CHECK_ID, ctx, "pass", 1.0, evidence)
    statuses = ", ".join(
        f"{name} {r.status_code if r and r.status_code else (r.error if r else 'not fetched')}"
        for name, r in (
            ("ucp", ep.ucp),
            ("ai-catalog.json", ep.ai_catalog),
            ("llms.txt", ep.llms_txt),
        )
    )
    evidence.append(Evidence(detail=f"No MCP endpoint discoverable ({statuses})"))
    return result(CHECK_ID, ctx, "warn", 0.5 if has_llms else 0.0, evidence)

"""P2.platform_support — the platform offers an agentic channel; is it enabled?

Informational scoring (SPEC §4 P): pass if enabled (a valid UCP profile is live), warn if
a channel is available but not enabled, not_applicable when the platform has no known
channel (nothing for the merchant to switch on). Support table: scanner/platform/support.py.
"""

from __future__ import annotations

import json

from scanner.checks.base import result
from scanner.checks.p1_ucp import validate
from scanner.models import CheckResult, Evidence, ScanContext
from scanner.platform.support import SUPPORT

CHECK_ID = "P2.platform_support"


def ucp_live(ctx: ScanContext) -> bool:
    res = ctx.endpoints.ucp
    if res is None or res.status_code != 200:
        return False
    try:
        errors, _ = validate(json.loads(res.body or ""))
    except json.JSONDecodeError:
        return False
    return not errors


async def check(ctx: ScanContext) -> CheckResult:
    plat = ctx.platform.platform
    row = SUPPORT.get(plat)
    live = ucp_live(ctx)
    if row is None:
        detail = f"Platform '{plat}': no support-table entry (custom or unknown platform)"
        if live:
            return result(
                CHECK_ID,
                ctx,
                "pass",
                1.0,
                [Evidence(detail=f"{detail}, but a valid UCP profile is live")],
            )
        return result(CHECK_ID, ctx, "not_applicable", 0.0, [Evidence(detail=detail)])

    note = row.note_nl if ctx.options.lang == "nl" else row.note_en
    src = Evidence(
        detail=f"{plat}: {row.channel} ({row.level}). {note}",
        snippet=f"Sources (verified {row.verified}): " + (", ".join(row.sources) or "none"),
    )
    if live:
        return result(
            CHECK_ID,
            ctx,
            "pass",
            1.0,
            [
                Evidence(
                    url=ctx.origin + "/.well-known/ucp",
                    detail="Agentic channel enabled: valid UCP profile is live",
                ),
                src,
            ],
        )
    if row.level in ("native", "third_party"):
        return result(
            CHECK_ID,
            ctx,
            "warn",
            0.5,
            [
                Evidence(
                    detail="Channel available for this platform but not enabled "
                    "(no valid UCP profile)"
                ),
                src,
            ],
        )
    return result(CHECK_ID, ctx, "not_applicable", 0.0, [src])

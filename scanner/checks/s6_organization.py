"""S6.organization — Organization / OnlineStore on the home page with name, url, logo,
contact, and KvK/VAT if the page shows one.

Google's Organization properties include contactPoint, telephone, email, vatID, taxID and
iso6523Code; it recommends OnlineStore for e-commerce
(https://developers.google.com/search/docs/appearance/structured-data/organization).
iso6523Code ICD 0106 = Dutch Chamber of Commerce (KvK) number.
"""

from __future__ import annotations

import re
from typing import Any

from scanner.checks.base import result
from scanner.models import CheckResult, CheckStatus, Evidence, ScanContext
from scanner.parse.html import types_of
from scanner.parse.product import organizations, visible_text

CHECK_ID = "S6.organization"
KVK_OR_VAT_SHOWN = re.compile(
    r"\bKvK[\s-]*(?:nummer|nr\.?)?[\s:.]*\d{8}\b|\bNL\s?\d{9}\s?B\s?\d{2}\b|\b(BTW|VAT)[\s-]*"
    r"(?:nummer|nr\.?|id|number)?[\s:.]*NL",
    re.I,
)
ID_PROPS = ("vatID", "taxID", "iso6523Code", "identifier")


def _fields(org: dict[str, Any], need_id: bool) -> dict[str, bool]:
    f = {
        "name": bool(org.get("name")),
        "url": bool(org.get("url")),
        "logo": bool(org.get("logo")),
        "contact": bool(org.get("contactPoint") or org.get("telephone") or org.get("email")),
    }
    if need_id:
        f["KvK/VAT"] = any(org.get(k) for k in ID_PROPS)
    return f


async def check(ctx: ScanContext) -> CheckResult:
    home = ctx.basics.home
    if home is None or not home.ok:
        why = home.unavailable_reason() if home else "not fetched"
        return result(
            CHECK_ID,
            ctx,
            "error",
            0.0,
            [Evidence(url=ctx.origin + "/", detail=f"Home page not available ({why})")],
        )
    html = home.body or ""
    shown = KVK_OR_VAT_SHOWN.search(visible_text(html))
    orgs = organizations(html)
    if not orgs:
        return result(
            CHECK_ID,
            ctx,
            "fail",
            0.0,
            [
                Evidence(
                    url=home.url,
                    detail="No Organization / OnlineStore structured data on the home page",
                )
            ],
        )
    best = max(orgs, key=lambda o: sum(_fields(o, bool(shown)).values()))
    fields = _fields(best, bool(shown))
    fraction = sum(fields.values()) / len(fields)
    missing = [k for k, v in fields.items() if not v]
    kind = "/".join(sorted(types_of(best))) or "Organization"
    evidence = [
        Evidence(
            url=home.url,
            detail=f"{kind} found; "
            + (f"missing: {', '.join(missing)}" if missing else "all expected fields present"),
            snippet=str(best.get("name") or "")[:120] or None,
        )
    ]
    if shown:
        evidence.append(
            Evidence(
                url=home.url,
                detail="Page shows a KvK/VAT number, so the "
                "markup should include vatID / taxID / iso6523Code",
                snippet=shown.group(0),
            )
        )
    status: CheckStatus = "pass" if fraction == 1.0 else "warn"
    return result(CHECK_ID, ctx, status, fraction, evidence)

"""U1-U5, A1, A2: the UCP business profile (/.well-known/ucp) and its AP2 declaration.

Rules from UCP 2026-08-25 (https://ucp.dev/2026-08-25/specification/overview/ #hosting,
#profile-structure; .../payment/extensions/ap2-mandates/; .../signatures/ #key-format-jwk).
"""

from __future__ import annotations

import json
import re
from typing import Any

from ap2check.checks.base import (
    AP2_CAPABILITY,
    CHECKOUT_CAPABILITY,
    UCP_VERSION,
    as_dict,
    entries,
    result,
    ucp_obj,
)
from ap2check.jose import JoseError, ec_key_from_jwk
from ap2check.models import CheckInput, CheckResult, Evidence

MAX_PROFILE_BYTES = 128 * 1024  # consumers MUST accept at least this much (#fetching)
TRANSPORTS = frozenset({"rest", "mcp", "a2a", "embedded"})
NEEDS_ENDPOINT = frozenset({"rest", "mcp", "a2a"})
PRIVATE_JWK_MEMBERS = ("d", "p", "q", "dp", "dq", "qi", "k")


def _no_profile(check_id: str, inp: CheckInput) -> CheckResult:
    return result(
        check_id,
        "not_applicable",
        [Evidence(url=_url(inp), detail="no usable UCP profile (see U1)")],
    )


def _url(inp: CheckInput) -> str:
    return f"{inp.target}/.well-known/ucp"


def profile_usable(inp: CheckInput) -> bool:
    return ucp_obj(inp.profile_json) is not None


def u1_profile_reachable(inp: CheckInput) -> CheckResult:
    res, url = inp.profile, _url(inp)
    cid = "U1.profile_reachable"
    if res is None or res.status_code is None:
        reason = res.error if res else "not fetched"
        # Blocked / unreachable is not proof of absence (CLAUDE.md status conventions).
        return result(cid, "error", [Evidence(url=url, detail=f"could not fetch: {reason}")])
    if 300 <= res.status_code < 400:
        loc = res.headers.get("location", "?")
        return result(
            cid,
            "fail",
            [
                Evidence(
                    url=url,
                    detail=f"HTTP {res.status_code} redirect to {loc}; "
                    "UCP profile endpoints MUST NOT redirect and agents will not follow it",
                )
            ],
        )
    if res.status_code in (401, 403, 429) or res.status_code >= 500:
        return result(
            cid,
            "error",
            [
                Evidence(
                    url=url,
                    detail=f"HTTP {res.status_code}: blocked or unavailable, "
                    "so we cannot tell whether a profile exists",
                )
            ],
        )
    if res.status_code != 200 or not res.body:
        return result(
            cid, "fail", [Evidence(url=url, detail=f"HTTP {res.status_code}: no profile")]
        )
    if inp.profile_json is None:
        return result(
            cid,
            "fail",
            [Evidence(url=url, detail="HTTP 200 but the body is not JSON", snippet=res.body[:200])],
        )
    size = len(res.body.encode("utf-8"))
    ev = [
        Evidence(
            url=url,
            detail=f"HTTP 200, JSON, {size:,} bytes, "
            f"content-type {res.headers.get('content-type', 'missing')}",
        )
    ]
    if res.truncated or size > MAX_PROFILE_BYTES:
        ev.append(Evidence(detail="larger than 128 KiB: some agents may refuse to read it"))
        return result(cid, "warn", ev)
    return result(cid, "pass", ev)


def u2_profile_structure(inp: CheckInput) -> CheckResult:
    cid = "U2.profile_structure"
    if inp.profile_json is None:
        return _no_profile(cid, inp)
    ucp = ucp_obj(inp.profile_json)
    if ucp is None:
        return result(cid, "fail", [Evidence(url=_url(inp), detail="no top-level `ucp` object")])
    errors: list[str] = []
    version = ucp.get("version")
    if not isinstance(version, str) or not version:
        errors.append("`ucp.version` missing")
    for key in ("services", "payment_handlers"):
        if not isinstance(ucp.get(key), dict):
            errors.append(f"`ucp.{key}` missing (required, even when empty)")
    services = as_dict(ucp.get("services"))
    for name, value in services.items():
        for e in entries(value):
            t = e.get("transport")
            ep = e.get("endpoint")
            if t not in TRANSPORTS:
                errors.append(f"service {name}: invalid transport {t!r}")
            elif t in NEEDS_ENDPOINT and not ep:
                errors.append(f"service {name}: {t} transport without endpoint")
            elif ep and not str(ep).startswith("https://"):
                errors.append(f"service {name}: endpoint is not https ({ep})")
    if errors:
        return result(cid, "fail", [Evidence(url=_url(inp), detail=e) for e in errors])
    ev = [Evidence(url=_url(inp), detail=f"ucp.version {version}; {len(services)} service(s)")]
    if isinstance(version, str) and version < UCP_VERSION:
        ev.append(
            Evidence(
                detail=f"profile version {version} is older than {UCP_VERSION}, "
                "the first UCP version with the AP2 mandates extension we checked"
            )
        )
        return result(cid, "warn", ev)
    return result(cid, "pass", ev)


def u3_profile_caching(inp: CheckInput) -> CheckResult:
    cid = "U3.profile_caching"
    res = inp.profile
    if res is None or inp.profile_json is None:
        return _no_profile(cid, inp)
    cc = res.headers.get("cache-control", "")
    directives = {d.strip().split("=", 1)[0].lower(): d.strip() for d in cc.split(",") if d.strip()}
    problems: list[str] = []
    if "public" not in directives:
        problems.append("no `public` directive")
    m = re.search(r"max-age\s*=\s*(\d+)", cc, re.I)
    if not m:
        problems.append("no max-age")
    elif int(m.group(1)) < 60:
        problems.append(f"max-age {m.group(1)} is below 60")
    for bad in ("private", "no-store", "no-cache"):
        if bad in directives:
            problems.append(f"`{bad}` is not allowed")
    ev = [Evidence(url=_url(inp), detail=f"Cache-Control: {cc or '(none)'}")]
    if problems:
        ev += [Evidence(detail=p) for p in problems]
        return result(cid, "fail", ev)
    if not (res.headers.get("etag") or res.headers.get("last-modified")):
        ev.append(Evidence(detail="no ETag or Last-Modified validator (SHOULD)"))
        return result(cid, "warn", ev)
    return result(cid, "pass", ev)


def u4_checkout_capability(inp: CheckInput) -> CheckResult:
    cid = "U4.checkout_capability"
    ucp = ucp_obj(inp.profile_json)
    if ucp is None:
        return _no_profile(cid, inp)
    caps = as_dict(ucp.get("capabilities"))
    services = as_dict(ucp.get("services"))
    callable_eps = [
        f"{name} ({e.get('transport')}: {e.get('endpoint')})"
        for name, value in services.items()
        for e in entries(value)
        if e.get("transport") in {"rest", "mcp", "a2a"} and e.get("endpoint")
    ]
    ev: list[Evidence] = []
    ok = True
    if CHECKOUT_CAPABILITY in caps:
        ev.append(Evidence(url=_url(inp), detail=f"`{CHECKOUT_CAPABILITY}` declared"))
    else:
        ok = False
        ev.append(Evidence(url=_url(inp), detail=f"`{CHECKOUT_CAPABILITY}` not declared"))
    if callable_eps:
        ev.append(Evidence(detail="endpoint(s): " + "; ".join(callable_eps[:4])))
    else:
        ok = False
        ev.append(Evidence(detail="no rest/mcp/a2a service endpoint an agent can call"))
    return result(cid, "pass" if ok else "fail", ev)


def u5_payment_handlers(inp: CheckInput) -> CheckResult:
    cid = "U5.payment_handlers"
    ucp = ucp_obj(inp.profile_json)
    if ucp is None:
        return _no_profile(cid, inp)
    handlers = ucp.get("payment_handlers")
    if isinstance(handlers, dict) and handlers:
        names = ", ".join(sorted(handlers))
        return result(cid, "pass", [Evidence(url=_url(inp), detail=f"handlers: {names}")])
    return result(cid, "fail", [Evidence(url=_url(inp), detail="no payment handler declared")])


def a1_ap2_capability(inp: CheckInput) -> CheckResult:
    cid = "A1.ap2_capability"
    ucp = ucp_obj(inp.profile_json)
    if ucp is None:
        return _no_profile(cid, inp)
    caps = as_dict(ucp.get("capabilities"))
    if AP2_CAPABILITY not in caps:
        return result(
            cid, "fail", [Evidence(url=_url(inp), detail=f"`{AP2_CAPABILITY}` not declared")]
        )
    found = entries(caps[AP2_CAPABILITY])
    entry = found[0] if found else {}
    ev = [Evidence(url=_url(inp), detail=f"`{AP2_CAPABILITY}` declared", snippet=_short(entry))]
    warnings: list[str] = []
    fails: list[str] = []
    version = entry.get("version")
    if not isinstance(version, str):
        warnings.append("no `version` on the capability entry")
    elif version < UCP_VERSION:
        warnings.append(f"version {version} is older than {UCP_VERSION}")
    extends = entry.get("extends")
    if (
        extends is not None
        and extends != CHECKOUT_CAPABILITY
        and (not isinstance(extends, list) or CHECKOUT_CAPABILITY not in extends)
    ):
        warnings.append(f"`extends` is {extends!r}, expected {CHECKOUT_CAPABILITY!r}")
    if CHECKOUT_CAPABILITY not in caps:
        fails.append(f"extends `{CHECKOUT_CAPABILITY}`, which the profile does not declare")
    config = as_dict(entry.get("config"))
    formats = config.get("vp_formats_supported")
    if not (isinstance(formats, dict | list) and "dc+sd-jwt" in formats):
        warnings.append(
            "`config.vp_formats_supported` does not list `dc+sd-jwt` "
            "(the SD-JWT format AP2 mandates use)"
        )
    ev += [Evidence(detail=f) for f in fails] + [Evidence(detail=w) for w in warnings]
    return result(cid, "fail" if fails else "warn" if warnings else "pass", ev)


def a2_signing_keys(inp: CheckInput) -> CheckResult:
    cid = "A2.signing_keys"
    if ucp_obj(inp.profile_json) is None:
        return _no_profile(cid, inp)
    keys = inp.profile_json.get("keys")
    url = _url(inp)
    if keys is None and isinstance(inp.profile_json["ucp"].get("keys"), list):
        return result(
            cid,
            "fail",
            [
                Evidence(
                    url=url, detail="keys are inside `ucp`; UCP requires a top-level `keys` array"
                )
            ],
        )
    if not isinstance(keys, list) or not keys:
        return result(cid, "fail", [Evidence(url=url, detail="no top-level `keys` array")])
    ev: list[Evidence] = []
    fails: list[str] = []
    warnings: list[str] = []
    usable: list[str] = []  # "kid (alg)"
    kids: list[str] = []
    for i, jwk in enumerate(keys):
        label = f"keys[{i}]"
        if not isinstance(jwk, dict):
            fails.append(f"{label} is not a JSON object")
            continue
        kid = jwk.get("kid")
        label = f"key {kid!r}" if kid else label
        leaked = [m for m in PRIVATE_JWK_MEMBERS if m in jwk]
        if leaked:
            fails.append(
                f"{label} contains private key material ({', '.join(leaked)}): "
                "rotate this key now and publish only the public part"
            )
            continue
        if not isinstance(kid, str) or not kid:
            fails.append(f"{label} has no `kid` (required for lookup)")
        else:
            kids.append(kid)
        if jwk.get("kty") == "OKP":
            ev.append(
                Evidence(
                    detail=f"{label}: {jwk.get('crv')} (OKP), fine for HTTP message "
                    "signing; not counted for AP2, which requires ECDSA"
                )
            )
            continue
        try:
            key = ec_key_from_jwk(jwk)
        except JoseError as exc:
            fails.append(f"{label}: {exc}")
            continue
        if jwk.get("use") not in (None, "sig"):
            fails.append(f"{label}: `use` is {jwk.get('use')!r}, must be 'sig'")
            continue
        if jwk.get("alg") not in (None, key.alg):
            fails.append(f"{label}: `alg` {jwk.get('alg')!r} does not match curve {key.crv}")
            continue
        usable.append(f"{kid} ({key.alg})")
    dupes = sorted({k for k in kids if kids.count(k) > 1})
    if dupes:
        fails.append(f"duplicate kid(s): {', '.join(dupes)}")
    if usable:
        ev.insert(0, Evidence(url=url, detail="valid EC signing key(s): " + ", ".join(usable)))
        if not any("ES256" in u for u in usable):
            warnings.append("no P-256 (ES256) key: agents only have to support ES256")
    elif not fails:
        fails.append("no EC (P-256/P-384/P-521) key usable for AP2 signatures")
    ev += [Evidence(detail=f) for f in fails] + [Evidence(detail=w) for w in warnings]
    return result(cid, "fail" if fails else "warn" if warnings else "pass", ev)


def _short(value: Any, limit: int = 300) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"


CHECKS = [
    u1_profile_reachable,
    u2_profile_structure,
    u3_profile_caching,
    u4_checkout_capability,
    u5_payment_handlers,
    a1_ap2_capability,
    a2_signing_keys,
]

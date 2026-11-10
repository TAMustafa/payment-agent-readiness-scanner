"""Self-contained, printable HTML report (SPEC §5). Stdlib only — no template engine.

Focus (decided 2026-11-10): readiness to be found by AI agents and to accept their orders
and payments. Only the in-scope
checks (scanner.report.scoring.STAGES) are shown, grouped as the four steps of an agent
order; each check gets a "why it matters" box and, when not passing, a "how to fix" box.
Full evidence and out-of-scope checks stay in report.json.

Everything shop-derived (evidence, snippets, URLs) goes through `esc` / `_href`; no external
CSS, fonts, images or scripts, so the file opens offline and prints as is.
"""

from __future__ import annotations

import re
from html import escape
from urllib.parse import urlsplit

from scanner.checks.copy import get_guidance
from scanner.checks.registry import REGISTRY
from scanner.models import CheckResult, ScanReport, StageScore
from scanner.report.i18n import (
    EFFORT,
    GRADE,
    PLATFORM_NAME,
    PLATFORM_OTHER,
    STAGE,
    STAGE_QUESTION,
    STATUS,
    UI,
    UNMEASURED,
    WHY,
    Lang,
    label,
    t,
)
from scanner.report.scoring import IN_SCOPE, STAGES

DEFAULT_BRAND = "Agent-Ready Scan"
MAX_EVIDENCE = 3  # per check in HTML; the full list stays in report.json
MAX_SNIPPET = 200
INTERNAL_PREFIXES = ("safety_guard:",)
SCREENSHOT = re.compile(r"^[\w.-]+\.png$")  # probe screenshot file names (artifacts dir)

CSS = """
:root{--ink:#1c2430;--muted:#5b6574;--line:#dde2e8;--bg:#ffffff;--panel:#f5f7f9;
--pass:#1f7a4d;--warn:#a86400;--fail:#b42318;--na:#6b7280;--accent:#1d4ed8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-print-color-adjust:exact;
print-color-adjust:exact}
main{max-width:860px;margin:0 auto;padding:32px 16px 48px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:20px;margin:36px 0 12px;
border-bottom:2px solid var(--line);padding-bottom:6px}
h3{font-size:17px;margin:28px 0 2px}.q{color:var(--muted);margin:0 0 8px}
.meta{color:var(--muted);margin:0}.meta a{color:inherit}
.intro{background:#fff8e6;border:1px solid #f2d48a;border-radius:10px;padding:12px 14px;
margin:20px 0 0}
.summary{display:flex;gap:24px;align-items:center;flex-wrap:wrap;background:var(--panel);
border-radius:12px;padding:20px;margin-top:16px}
.dial{width:132px;height:132px;border-radius:50%;display:grid;place-items:center;
flex:none}.dial div{width:104px;height:104px;border-radius:50%;background:var(--panel);
display:grid;place-items:center;text-align:center}.dial b{font-size:34px;line-height:1}
.dial small{display:block;color:var(--muted);font-size:12px}
.grade{font-size:22px;font-weight:700;margin:0 0 4px}.summary p{margin:2px 0}
.bars{flex:1 1 320px}
.bar{display:grid;grid-template-columns:minmax(0,1fr) 120px 40px 88px;
gap:10px;align-items:center;margin:6px 0}.track{height:10px;background:var(--line);
border-radius:5px;overflow:hidden}.fill{display:block;height:100%;border-radius:5px}
.num{text-align:right;font-variant-numeric:tabular-nums}
ol.fixes{padding-left:0;list-style:none;counter-reset:f}ol.fixes li{counter-increment:f;
border:1px solid var(--line);border-radius:10px;padding:12px 14px 12px 52px;margin:10px 0;
position:relative;break-inside:avoid}ol.fixes li::before{content:counter(f);position:absolute;
left:14px;top:12px;width:26px;height:26px;border-radius:50%;background:var(--accent);
color:#fff;display:grid;place-items:center;font-weight:700;font-size:14px}
.fixhead{font-weight:700}.tags{color:var(--muted);font-size:13px;margin:2px 0 6px}
.check{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0;
break-inside:avoid}.check header{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.check header b{flex:1 1 240px}.badge{font-size:12px;font-weight:700;padding:2px 8px;
border-radius:999px;color:#fff;white-space:nowrap}
.s-pass{background:var(--pass)}.s-warn{background:var(--warn)}.s-fail{background:var(--fail)}
.s-not_applicable,.s-error,.s-not_run{background:var(--na)}
.id{color:var(--muted);font-size:12px;font-family:ui-monospace,Menlo,monospace}
.box{border-radius:8px;padding:8px 10px;margin-top:8px;font-size:14px}
.why{background:var(--panel)}.guide{background:#eef3ff}
.box b{display:block;font-size:13px}
.ev{margin:8px 0 0;font-size:13px;color:#2d3643}.ev b{font-size:13px}
.ev ul{margin:2px 0 0;padding-left:18px}.ev p{margin:2px 0 0}
.ev li{margin:2px 0;overflow-wrap:anywhere}
code{font-family:ui-monospace,Menlo,monospace;font-size:12px;background:var(--panel);
padding:1px 4px;border-radius:4px;overflow-wrap:anywhere}.muted{color:var(--muted)}
footer{margin-top:40px;color:var(--muted);font-size:12px}
@media (max-width:560px){.bar{grid-template-columns:minmax(0,1fr) 40px 84px;
gap:2px 8px}.bar>span:first-child{grid-column:1/-1}}
@media print{main{padding:0;max-width:none}h2,h3{break-after:avoid}a{color:inherit}}
"""


def esc(value: object) -> str:
    return escape(str(value), quote=True)


def _href(url: str | None) -> str:
    """Link only http(s) URLs; anything else is shown as text."""
    if not url:
        return ""
    if urlsplit(url).scheme in ("http", "https"):
        return f'<a href="{esc(url)}" rel="noopener noreferrer">{esc(url)}</a>'
    return esc(url)


def _color(score: float | None) -> str:
    if score is None:
        return "var(--na)"
    return "var(--pass)" if score >= 80 else "var(--warn)" if score >= 60 else "var(--fail)"


def _fmt(n: float) -> str:
    return f"{n:.0f}" if abs(n - round(n)) < 0.05 else f"{n:.1f}"


def _bar(s: StageScore, lang: Lang) -> str:
    value = "&ndash;" if s.score is None else _fmt(s.score)
    total = len(s.check_ids)
    measured = UI["measured"][lang].format(n=total - len(s.excluded), m=total)
    return (
        f"<div class=bar><span>{esc(t(STAGE, s.stage, lang))}</span>"
        f'<span class=track><span class=fill style="width:{s.score or 0.0:.1f}%;'
        f'background:{_color(s.score)}"></span></span><span class=num>{value}</span>'
        f"<span class='num muted'>{esc(measured)}</span></div>"
    )


def _summary(report: ScanReport, lang: Lang) -> str:
    low = report.score is not None and report.grade is None
    if report.score is None:
        dial_inner = "<b>&ndash;</b>"
        grade = esc(UI["no_score"][lang])
    else:
        sub = UI["provisional" if low else "score_of"][lang]
        dial_inner = f"<b>{_fmt(report.score)}</b><small>{esc(sub)}</small>"
        grade = esc(UI["low_coverage"][lang] if low else t(GRADE, report.grade or "", lang))
    pct = report.score or 0.0
    color = "var(--na)" if low else _color(report.score)
    dial_bg = f"conic-gradient({color} {pct * 3.6:.1f}deg, var(--line) 0)"
    unmeasured = report.excluded_checks + len(report.not_run)
    if low:
        text = UI["low_coverage_note"][lang].format(pct=round(100 * report.coverage))
        note = f"<p class=muted>{esc(text)}</p>"
    elif unmeasured:
        text = UI["excluded"][lang].format(n=unmeasured, m=len(IN_SCOPE))
        note = f"<p class=muted>{esc(text)}</p>"
    else:
        note = ""
    bars = "".join(_bar(s, lang) for s in report.stages)
    return (
        "<section class=summary>"
        f'<div class=dial style="background:{dial_bg}"><div>{dial_inner}</div></div>'
        f"<div class=bars><p class=grade>{grade}</p>{note}{bars}</div>"
        "</section>"
    )


def _guidance(r_id: str, stored: str, lang: Lang) -> str:
    return get_guidance(r_id, lang) or stored


def _fixes(report: ScanReport, lang: Lang) -> str:
    head = f"<h2>{esc(UI['top_fixes'][lang])}</h2>"
    if not report.top_fixes:
        return head + f"<p>{esc(UI['no_fixes'][lang])}</p>"
    items = []
    for f in report.top_fixes:
        tags = " · ".join(
            [
                esc(t(STATUS, f.status, lang)),
                esc(UI["gain"][lang].format(n=_fmt(f.score_gain))),
                f"{esc(t(EFFORT, f.effort, lang))} {esc(UI['effort'][lang])}",
            ]
        )
        items.append(
            f"<li><div class=fixhead>{esc(label(f.check_id, f.label, lang))}</div>"
            f"<div class=tags>{tags}</div>"
            f"<div>{esc(_guidance(f.check_id, f.guidance, lang))}</div></li>"
        )
    intro = UI["top_fixes_intro"][lang].format(n=len(report.top_fixes))
    return head + f"<p class=muted>{esc(intro)}</p><ol class=fixes>{''.join(items)}</ol>"


def unmeasured_reason(r: CheckResult, lang: Lang) -> str | None:
    """Plain-language reason for a check we could not measure (None: show the evidence)."""
    text = " ".join(e.detail for e in r.evidence)
    for needle, msg in UNMEASURED:
        if needle.lower() in text.lower():
            return msg[lang]
    return None


def _evidence(r: CheckResult, lang: Lang) -> str:
    if r.status in ("not_applicable", "error"):
        reason = unmeasured_reason(r, lang)
        if reason is not None:
            head = esc(UI["not_measured_why"][lang])
            return f"<div class=ev><b>{head}</b><p>{esc(reason)}</p></div>"
    # Internal probe lines (safety-guard log) stay in report.json only.
    shown = [e for e in r.evidence if not e.detail.startswith(INTERNAL_PREFIXES)]
    # Unmeasured checks: one line saying why is enough.
    limit = 1 if r.status in ("not_applicable", "error") else MAX_EVIDENCE
    rows = []
    for ev in shown[:limit]:
        parts = [esc(ev.detail)]
        if ev.url:
            parts.append(f"<br>{_href(ev.url)}")
        if ev.snippet and not SCREENSHOT.match(ev.snippet):
            snippet = ev.snippet[:MAX_SNIPPET] + ("…" if len(ev.snippet) > MAX_SNIPPET else "")
            parts.append(f"<br><code>{esc(snippet)}</code>")
        rows.append(f"<li>{''.join(parts)}</li>")
    extra = len(shown) - limit
    if extra > 0:
        rows.append(f"<li class=muted>{esc(UI['more_evidence'][lang].format(n=extra))}</li>")
    if not rows:
        return ""
    return f"<div class=ev><b>{esc(UI['found'][lang])}</b><ul>{''.join(rows)}</ul></div>"


def _card(check_id: str, r: CheckResult | None, lang: Lang) -> str:
    spec = REGISTRY[check_id]
    status = r.status if r else "not_run"
    why = WHY.get(check_id, {}).get(lang, "")
    why_box = f"<div class='box why'><b>{esc(UI['why'][lang])}</b>{esc(why)}</div>" if why else ""
    fix_box = ""
    if r is not None and r.status in ("fail", "warn"):
        text = _guidance(r.id, r.guidance, lang)
        if text:
            fix_box = (
                f"<div class='box guide'><b>{esc(UI['how_to_fix'][lang])}</b>{esc(text)}</div>"
            )
    return (
        f"<article class=check><header><span class='badge s-{esc(status)}'>"
        f"{esc(t(STATUS, status, lang))}</span><b>{esc(label(spec.id, spec.label, lang))}</b>"
        f"<span class=id>{esc(spec.id.split('.', 1)[0])}</span></header>"
        f"{why_box}{_evidence(r, lang) if r else ''}{fix_box}</article>"
    )


def _details(report: ScanReport, lang: Lang) -> str:
    by_id = {r.id: r for r in report.results}
    scores = {s.stage: s for s in report.stages}
    out = [f"<h2>{esc(UI['details'][lang])}</h2>"]
    for stage, ids in STAGES:
        s = scores.get(stage)
        value = "" if s is None or s.score is None else f" — {_fmt(s.score)}/100"
        out.append(
            f"<h3>{esc(t(STAGE, stage, lang))}{esc(value)}</h3>"
            f"<p class=q>{esc(t(STAGE_QUESTION, stage, lang))}</p>"
            + "".join(_card(i, by_id.get(i), lang) for i in ids)
        )
    return "".join(out)


def _method(report: ScanReport, lang: Lang) -> str:
    items = [
        UI["m_readonly"][lang].format(products=len(report.sampled.get("products", []))),
        UI["m_checkout_on" if report.checkout_tested else "m_checkout_off"][lang],
        UI["m_d2"][lang],
        UI["m_snapshot"][lang].format(date=report.started_at.strftime("%Y-%m-%d")),
    ]
    body = "".join(f"<li>{esc(i)}</li>" for i in items)
    return f"<h2>{esc(UI['method'][lang])}</h2><ul class=muted>{body}</ul>"


def render_html(report: ScanReport, *, lang: Lang | None = None, brand: str | None = None) -> str:
    lang = lang or report.lang
    brand = brand or DEFAULT_BRAND
    host = urlsplit(report.origin).hostname or report.origin
    when = report.started_at.strftime("%Y-%m-%d")
    title = UI["title"][lang]
    platform = PLATFORM_NAME.get(report.platform.platform, PLATFORM_OTHER[lang])
    return (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{esc(title)} — {esc(host)}</title><style>{CSS}</style></head><body><main>"
        f"<p class=meta>{esc(brand)}</p><h1>{esc(title)}</h1>"
        f"<p class=meta>{_href(report.origin)} · {esc(UI['scanned'][lang])} {esc(when)} · "
        f"{esc(UI['platform'][lang])}: {esc(platform)}</p>"
        f"<p class=intro>{esc(UI['intro'][lang])}</p>"
        f"{_summary(report, lang)}{_fixes(report, lang)}"
        f"{_details(report, lang)}{_method(report, lang)}"
        f"<footer>{esc(UI['footer'][lang].format(brand=brand, version=report.scanner_version))}"
        "</footer></main></body></html>"
    )

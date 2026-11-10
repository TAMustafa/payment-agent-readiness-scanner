"""Self-contained, printable HTML report (SPEC §5). Stdlib only — no template engine.

Everything shop-derived (evidence, snippets, URLs, guidance) goes through `esc` / `_href`;
no external CSS, fonts, images or scripts, so the file opens offline and prints as is.
Sections: summary + score, top 5 fixes, category details with evidence, what's coming
(agent checkout not live in NL), methodology + limitations.
"""

from __future__ import annotations

from html import escape
from urllib.parse import urlsplit

from scanner.checks.copy import get_guidance
from scanner.checks.registry import REGISTRY
from scanner.models import CheckResult, ScanReport
from scanner.platform.support import VERIFIED
from scanner.report.i18n import CATEGORY, EFFORT, GRADE, STATUS, UI, Lang, label, t
from scanner.report.scoring import CATEGORY_ORDER

DEFAULT_BRAND = "Agent-Ready Scan"
MAX_EVIDENCE = 10  # per check in HTML; the full list stays in report.json
MAX_SNIPPET = 400

CSS = """
:root{--ink:#1c2430;--muted:#5b6574;--line:#dde2e8;--bg:#ffffff;--panel:#f5f7f9;
--pass:#1f7a4d;--warn:#a86400;--fail:#b42318;--na:#6b7280;--accent:#1d4ed8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-print-color-adjust:exact;
print-color-adjust:exact}
main{max-width:920px;margin:0 auto;padding:32px 16px 48px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:20px;margin:36px 0 12px;
border-bottom:2px solid var(--line);padding-bottom:6px}h3{font-size:16px;margin:24px 0 8px}
.meta{color:var(--muted);margin:0}.meta a{color:inherit}
.summary{display:flex;gap:24px;align-items:center;flex-wrap:wrap;background:var(--panel);
border-radius:12px;padding:20px;margin-top:20px}
.dial{width:132px;height:132px;border-radius:50%;display:grid;place-items:center;
flex:none}.dial div{width:104px;height:104px;border-radius:50%;background:var(--panel);
display:grid;place-items:center;text-align:center}.dial b{font-size:34px;line-height:1}
.dial small{display:block;color:var(--muted);font-size:12px}
.grade{font-size:20px;font-weight:700;margin:0 0 6px}.summary p{margin:2px 0}
.bars{width:100%;margin-top:8px}
.bar{display:grid;grid-template-columns:minmax(0,1fr) 120px 44px 92px;
gap:10px;align-items:center;margin:6px 0}.track{height:10px;background:var(--line);
border-radius:5px;overflow:hidden}.fill{height:100%;border-radius:5px}
.num{text-align:right;font-variant-numeric:tabular-nums}
ol.fixes{padding-left:0;list-style:none;counter-reset:f}ol.fixes li{counter-increment:f;
border:1px solid var(--line);border-radius:10px;padding:12px 14px 12px 52px;margin:10px 0;
position:relative;break-inside:avoid}ol.fixes li::before{content:counter(f);position:absolute;
left:14px;top:12px;width:26px;height:26px;border-radius:50%;background:var(--accent);
color:#fff;display:grid;place-items:center;font-weight:700;font-size:14px}
.fixhead{font-weight:700}.tags{color:var(--muted);font-size:13px;margin:2px 0 6px}
.check{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0;
break-inside:avoid}.check header{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.check header b{flex:1 1 260px}.badge{font-size:12px;font-weight:700;padding:2px 8px;
border-radius:999px;color:#fff;white-space:nowrap}
.s-pass{background:var(--pass)}.s-warn{background:var(--warn)}.s-fail{background:var(--fail)}
.s-not_applicable,.s-error,.s-not_run{background:var(--na)}
.id{color:var(--muted);font-size:12px;font-family:ui-monospace,Menlo,monospace}
ul.ev{margin:6px 0 0;padding-left:18px;font-size:13px;color:#2d3643}ul.ev li{margin:3px 0;
overflow-wrap:anywhere}code,pre{font-family:ui-monospace,Menlo,monospace;font-size:12px}
pre{background:var(--panel);padding:6px 8px;border-radius:6px;white-space:pre-wrap;
overflow-wrap:anywhere;margin:4px 0}.guide{background:#eef3ff;border-radius:8px;
padding:8px 10px;margin-top:8px;font-size:14px}.muted{color:var(--muted)}
.coming{background:#fff8e6;border:1px solid #f2d48a;border-radius:10px;padding:12px 14px}
footer{margin-top:40px;color:var(--muted);font-size:12px}
@media (max-width:560px){.bar{grid-template-columns:minmax(0,1fr) 40px 84px;
gap:2px 8px}.bar>span:first-child{grid-column:1/-1}}
@media print{main{padding:0;max-width:none}h2{break-after:avoid}a{color:inherit}}
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


def _summary(report: ScanReport, lang: Lang) -> str:
    counted = sum(r.status not in ("not_applicable", "error") for r in report.results)
    if report.score is None:
        dial_inner = "<b>&ndash;</b>"
        grade = esc(UI["no_score"][lang])
    else:
        dial_inner = f"<b>{_fmt(report.score)}</b><small>{esc(UI['score_of'][lang])}</small>"
        grade = esc(t(GRADE, report.grade or "", lang))
    pct = report.score or 0.0
    dial_bg = f"conic-gradient({_color(report.score)} {pct * 3.6:.1f}deg, var(--line) 0)"
    lines = [f"<p>{esc(UI['counted'][lang].format(n=counted))}</p>"]
    if report.excluded_checks:
        lines.append(f"<p>{esc(UI['excluded'][lang].format(n=report.excluded_checks))}</p>")
    if report.not_run:
        ids = ", ".join(i.split(".", 1)[0] for i in report.not_run)
        lines.append(f"<p class=muted>{esc(UI['not_run'][lang].format(ids=ids))}</p>")
    bars = []
    for c in report.categories:
        width = c.score or 0.0
        value = "&ndash;" if c.score is None else _fmt(c.score)
        total = sum(1 for spec in REGISTRY.values() if spec.category == c.category)
        measured = UI["measured"][lang].format(n=total - len(c.excluded), m=total)
        bars.append(
            f"<div class=bar><span>{esc(t(CATEGORY, c.category, lang))}</span>"
            f'<span class=track><span class=fill style="display:block;width:{width:.1f}%;'
            f'background:{_color(c.score)}"></span></span><span class=num>{value}</span>'
            f"<span class='num muted'>{esc(measured)}</span></div>"
        )
    return (
        f"<h2>{esc(UI['summary'][lang])}</h2><section class=summary>"
        f'<div class=dial style="background:{dial_bg}"><div>{dial_inner}</div></div>'
        f"<div><p class=grade>{grade}</p>{''.join(lines)}</div>"
        f"<div class=bars><h3>{esc(UI['by_category'][lang])}</h3>{''.join(bars)}</div>"
        "</section>"
    )


def _guidance(r_id: str, stored: str, lang: Lang) -> str:
    return get_guidance(r_id, lang) or stored


def _fixes(report: ScanReport, lang: Lang) -> str:
    head = f"<h2>{esc(UI['top_fixes'][lang].format(n=len(report.top_fixes) or 5))}</h2>"
    if not report.top_fixes:
        return head + f"<p>{esc(UI['no_fixes'][lang])}</p>"
    items = []
    for f in report.top_fixes:
        tags = " · ".join(
            [
                esc(t(STATUS, f.status, lang)),
                esc(UI["gain"][lang].format(n=_fmt(f.score_gain))),
                f"{esc(UI['effort'][lang])}: {esc(t(EFFORT, f.effort, lang))}",
            ]
        )
        items.append(
            f"<li><div class=fixhead>{esc(label(f.check_id, f.label, lang))} "
            f"<span class=id>{esc(f.check_id)}</span></div><div class=tags>{tags}</div>"
            f"<div>{esc(_guidance(f.check_id, f.guidance, lang))}</div></li>"
        )
    return (
        head
        + f"<p class=muted>{esc(UI['top_fixes_intro'][lang])}</p>"
        + (f"<ol class=fixes>{''.join(items)}</ol>")
    )


def _evidence(r: CheckResult, lang: Lang) -> str:
    rows = []
    for ev in r.evidence[:MAX_EVIDENCE]:
        parts = [esc(ev.detail)]
        if ev.url:
            parts.append(f"<br>{_href(ev.url)}")
        if ev.snippet:
            snippet = ev.snippet[:MAX_SNIPPET] + ("…" if len(ev.snippet) > MAX_SNIPPET else "")
            parts.append(f"<pre>{esc(snippet)}</pre>")
        rows.append(f"<li>{''.join(parts)}</li>")
    extra = len(r.evidence) - MAX_EVIDENCE
    if extra > 0:
        rows.append(f"<li class=muted>{esc(UI['more_evidence'][lang].format(n=extra))}</li>")
    return f"<ul class=ev>{''.join(rows)}</ul>" if rows else ""


def _check(r: CheckResult, lang: Lang) -> str:
    guide = ""
    if r.status != "pass":
        text = _guidance(r.id, r.guidance, lang)
        if text:
            guide = f"<div class=guide><b>{esc(UI['how_to_fix'][lang])}:</b> {esc(text)}</div>"
    return (
        f"<article class=check><header><span class='badge s-{esc(r.status)}'>"
        f"{esc(t(STATUS, r.status, lang))}</span><b>{esc(label(r.id, r.label, lang))}</b>"
        f"<span class=id>{esc(r.id)} · {esc(UI['weight'][lang].format(n=r.weight))} · "
        f"{_fmt(100 * r.score_fraction)}%</span></header>"
        f"{_evidence(r, lang)}{guide}</article>"
    )


def _not_run(check_id: str, lang: Lang) -> str:
    spec = REGISTRY[check_id]
    return (
        f"<article class=check><header><span class='badge s-not_run'>"
        f"{esc(t(STATUS, 'not_run', lang))}</span><b>{esc(label(spec.id, spec.label, lang))}</b>"
        f"<span class=id>{esc(spec.id)} · {esc(UI['weight'][lang].format(n=spec.weight))}"
        "</span></header></article>"
    )


def _details(report: ScanReport, lang: Lang) -> str:
    by_cat: dict[str, list[str]] = {c: [] for c in CATEGORY_ORDER}
    by_id = {r.id: r for r in report.results}
    for spec in REGISTRY.values():
        if spec.id in by_id:
            by_cat[spec.category].append(_check(by_id[spec.id], lang))
        elif spec.id in report.not_run:
            by_cat[spec.category].append(_not_run(spec.id, lang))
    scores = {c.category: c for c in report.categories}
    out = [f"<h2>{esc(UI['details'][lang])}</h2>"]
    if lang == "nl":
        out.append(f"<p class=muted>{esc(UI['evidence_lang'][lang])}</p>")
    for cat in CATEGORY_ORDER:
        c = scores.get(cat)
        value = "" if c is None or c.score is None else f" — {_fmt(c.score)}/100"
        out.append(f"<h3>{esc(t(CATEGORY, cat, lang))}{esc(value)}</h3>{''.join(by_cat[cat])}")
    return "".join(out)


def _method(report: ScanReport, lang: Lang) -> str:
    items = [
        UI["m_readonly"][lang],
        UI["m_sample"][lang].format(
            products=len(report.sampled.get("products", [])),
            categories=len(report.sampled.get("categories", [])),
            requests=report.requests_made,
        ),
        UI["m_d2"][lang],
        UI["m_checkout_on" if report.checkout_tested else "m_checkout_off"][lang],
    ]
    vis = report.visibility
    if vis is not None and vis.ran and vis.calls:
        assistants = sorted({c.assistant for c in vis.calls})
        runs = len({c.run for c in vis.calls})
        joiner = " en " if lang == "nl" else " and "
        items.append(UI["m_v1_on"][lang].format(assistants=joiner.join(assistants), runs=runs))
    else:
        items.append(UI["m_v1_off"][lang])
    items += [UI["m_score"][lang], UI["m_platform"][lang].format(date=VERIFIED)]
    notes = ""
    if report.sampling_notes:
        rows = "".join(f"<li>{esc(n.detail)}</li>" for n in report.sampling_notes[:20])
        notes = f"<h3>{esc(UI['notes'][lang])}</h3><ul class=ev>{rows}</ul>"
    body = "".join(f"<li>{esc(i)}</li>" for i in items)
    return f"<h2>{esc(UI['method'][lang])}</h2><ul>{body}</ul>{notes}"


def render_html(report: ScanReport, *, lang: Lang | None = None, brand: str | None = None) -> str:
    lang = lang or report.lang
    brand = brand or DEFAULT_BRAND
    host = urlsplit(report.origin).hostname or report.origin
    when = report.started_at.strftime("%Y-%m-%d %H:%M UTC")
    title = f"{UI['title'][lang]} — {host}"
    return (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{esc(title)}</title><style>{CSS}</style></head><body><main>"
        f"<p class=meta>{esc(brand)}</p><h1>{esc(title)}</h1>"
        f"<p class=meta>{_href(report.origin)} · {esc(UI['scanned'][lang])} {esc(when)} · "
        f"{esc(UI['platform'][lang])}: {esc(report.platform.platform)}</p>"
        f"{_summary(report, lang)}{_fixes(report, lang)}"
        f"<h2>{esc(UI['coming'][lang])}</h2><p class=coming>{esc(UI['coming_body'][lang])}</p>"
        f"{_details(report, lang)}{_method(report, lang)}"
        f"<footer>{esc(UI['footer'][lang].format(brand=brand, version=report.scanner_version))}"
        "</footer></main></body></html>"
    )

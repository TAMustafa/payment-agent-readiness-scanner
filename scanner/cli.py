"""CLI entry: `scanner scan <url> [--json] [--out dir] [--checks a,b] [--visibility]`."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

import typer

from scanner.graph import build_graph, run_scan
from scanner.models import ScanOptions, ScanReport
from scanner.report.html import DEFAULT_BRAND, render_html
from scanner.report.i18n import Lang
from scanner.report.scoring import summarise

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def main() -> None:
    """Audit a webshop's readiness for AI shopping agents (read-only)."""


@app.command()
def scan(
    url: Annotated[str, typer.Argument(help="Shop URL, e.g. https://example.nl")],
    as_json: Annotated[bool, typer.Option("--json", help="Print report JSON to stdout")] = False,
    out: Annotated[
        Path | None, typer.Option("--out", help="Write report.json under <out>/<host>/<ts>/")
    ] = None,
    checks: Annotated[
        str | None, typer.Option("--checks", help="Comma-separated check ids or prefixes (D1,S2)")
    ] = None,
    visibility: Annotated[
        bool,
        typer.Option(
            "--visibility",
            help="Run V1 AI-visibility check via OpenRouter (costs money; budget in "
            "config/visibility.toml; needs OPENROUTER_API_KEY)",
        ),
    ] = False,
    visibility_prompts: Annotated[
        Path | None,
        typer.Option("--visibility-prompts", help="Own V1 questions: text file, one per line"),
    ] = None,
    timeout: Annotated[
        float | None,
        typer.Option(
            "--timeout",
            help="Hard scan timeout, seconds (default: 120, or 240 when the shop runs on Shopify)",
        ),
    ] = None,
    gmc_active: Annotated[
        bool | None,
        typer.Option("--gmc-active/--gmc-inactive", help="D5 manual input: Merchant Center feed"),
    ] = None,
    gmc_disapproved_pct: Annotated[
        float | None,
        typer.Option("--gmc-disapproved-pct", help="D5 manual input: % products disapproved"),
    ] = None,
    checkout: Annotated[
        bool,
        typer.Option(
            "--checkout",
            help="Run the headless cart/checkout probe (adds 1 item to an anonymous cart). "
            "Only for shops you have permission to test. robots.txt is still respected.",
        ),
    ] = False,
    lang: Annotated[str, typer.Option("--lang", help="Report language: en (default) or nl")] = "en",
    checkout_consent: Annotated[
        bool,
        typer.Option(
            "--checkout-consent",
            help="The merchant asked for this scan: the probe may enter cart/checkout paths "
            "that robots.txt disallows. Never use without the merchant's consent.",
        ),
    ] = False,
) -> None:
    """Scan a shop and print or save the report (report.json + report.html with --out)."""
    report_lang = _lang(lang)
    if os.environ.get("SCANNER_CONTACT_URL") is None:
        typer.echo(
            "Warning: SCANNER_CONTACT_URL is not set; shops see a placeholder contact URL in "
            "our User-Agent. Set it (see .env.example) before scanning real shops.",
            err=True,
        )
    started = datetime.now(UTC)
    artifacts: Path | None = None
    if out is not None:
        host = urlsplit(url if "://" in url else "https://" + url).hostname or "unknown"
        artifacts = out / host / started.strftime("%Y%m%dT%H%M%SZ")
    options = ScanOptions(
        checks=checks.split(",") if checks else None,
        visibility=visibility,
        visibility_prompts_file=str(visibility_prompts) if visibility_prompts else None,
        timeout_s=timeout,
        merchant_center_active=gmc_active,
        merchant_center_disapproved_pct=gmc_disapproved_pct,
        checkout=checkout or checkout_consent,
        checkout_consent=checkout_consent,
        artifacts_dir=str(artifacts) if artifacts else None,
        lang=report_lang,
    )
    try:
        report = asyncio.run(
            asyncio.wait_for(run_scan(url, options), timeout=options.max_timeout_s)
        )
    except TimeoutError:
        typer.echo(f"Scan exceeded hard timeout of {options.max_timeout_s:.0f}s", err=True)
        raise typer.Exit(code=2) from None
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from None

    if artifacts is not None:
        path = _write_report(report, artifacts)
        typer.echo(f"Wrote {path} and report.html", err=True)
    if as_json:
        typer.echo(report.model_dump_json(indent=2))
    else:
        _print_summary(report)


@app.command()
def report(
    report_json: Annotated[Path, typer.Argument(help="A saved report.json")],
    lang: Annotated[
        str | None, typer.Option("--lang", help="en or nl (default: the scan's language)")
    ] = None,
    out: Annotated[
        Path | None, typer.Option("--out", help="HTML file (default: report.html next to it)")
    ] = None,
) -> None:
    """Re-render report.html from a saved report.json (no network access)."""
    saved = ScanReport.model_validate_json(report_json.read_text(encoding="utf-8"))
    if saved.results:
        # Always re-score with the current rules: older reports have no score (before
        # build step 4) or were scored over all checks (before the agent-order scope).
        s = summarise(saved.results)
        saved = saved.model_copy(update=s.report_fields())
    target = out or report_json.with_name("report.html")
    target.write_text(
        render_html(saved, lang=_lang(lang) if lang else None, brand=_brand()), encoding="utf-8"
    )
    typer.echo(f"Wrote {target}", err=True)


@app.command()
def graph() -> None:
    """Print the scan graph as Mermaid."""
    typer.echo(build_graph().get_graph().draw_mermaid())


def _lang(value: str) -> Lang:
    if value not in ("nl", "en"):
        raise typer.BadParameter("--lang must be nl or en")
    return "nl" if value == "nl" else "en"


def _brand() -> str:
    # Service name for the report header is still open (SPEC §9): configurable meanwhile.
    return os.environ.get("SCANNER_BRAND", "").strip() or DEFAULT_BRAND


def _write_report(report: ScanReport, target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    path = target / "report.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (target / "report.html").write_text(render_html(report, brand=_brand()), encoding="utf-8")
    return path


def _print_summary(report: ScanReport) -> None:
    typer.echo(
        f"{report.origin}  platform={report.platform.platform}  score={report.score}  "
        f"grade={report.grade}"
    )
    for sig in report.platform.signals[:3]:
        typer.echo(f"  platform signal: {sig.detail}")
    counts = {k: len(v) for k, v in report.sampled.items()}
    typer.echo(f"  sampled: {counts}  requests: {report.requests_made}")
    for note in report.sampling_notes:
        typer.echo(f"  note: {note.detail}")
    for r in report.results:
        detail = r.evidence[0].detail if r.evidence else ""
        typer.echo(f"  {r.status:<14} {r.id:<26} {detail}")
    typer.echo(f"excluded checks: {report.excluded_checks}  not run: {len(report.not_run)}")
    for f in report.top_fixes:
        typer.echo(f"  fix {f.rank}: {f.check_id:<26} +{f.score_gain} points, effort {f.effort}")

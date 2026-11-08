"""CLI entry: `scanner scan <url> [--json] [--out dir] [--checks a,b] [--visibility]`."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

import typer

from scanner.graph import build_graph, run_scan
from scanner.models import ScanOptions, ScanReport

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
        bool, typer.Option("--visibility", help="Run V1 AI-visibility check (costs money)")
    ] = False,
    timeout: Annotated[float, typer.Option("--timeout", help="Hard scan timeout, seconds")] = 120.0,
    gmc_active: Annotated[
        bool | None,
        typer.Option("--gmc-active/--gmc-inactive", help="D5 manual input: Merchant Center feed"),
    ] = None,
    gmc_disapproved_pct: Annotated[
        float | None,
        typer.Option("--gmc-disapproved-pct", help="D5 manual input: % products disapproved"),
    ] = None,
) -> None:
    """Scan a shop and print or save the report."""
    options = ScanOptions(
        checks=checks.split(",") if checks else None,
        visibility=visibility,
        timeout_s=timeout,
        merchant_center_active=gmc_active,
        merchant_center_disapproved_pct=gmc_disapproved_pct,
    )
    try:
        report = asyncio.run(asyncio.wait_for(run_scan(url, options), timeout=timeout))
    except TimeoutError:
        typer.echo(f"Scan exceeded hard timeout of {timeout:.0f}s", err=True)
        raise typer.Exit(code=2) from None
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from None

    if out is not None:
        path = _write_report(report, out)
        typer.echo(f"Wrote {path}", err=True)
    if as_json:
        typer.echo(report.model_dump_json(indent=2))
    else:
        _print_summary(report)


@app.command()
def graph() -> None:
    """Print the scan graph as Mermaid."""
    typer.echo(build_graph().get_graph().draw_mermaid())


def _write_report(report: ScanReport, out: Path) -> Path:
    host = urlsplit(report.origin).hostname or "unknown"
    ts = report.started_at.strftime("%Y%m%dT%H%M%SZ")
    target = out / host / ts
    target.mkdir(parents=True, exist_ok=True)
    path = target / "report.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def _print_summary(report: ScanReport) -> None:
    typer.echo(f"{report.origin}  platform={report.platform.platform}  score={report.score}")
    for sig in report.platform.signals[:3]:
        typer.echo(f"  platform signal: {sig.detail}")
    counts = {k: len(v) for k, v in report.sampled.items()}
    typer.echo(f"  sampled: {counts}  requests: {report.requests_made}")
    for note in report.sampling_notes:
        typer.echo(f"  note: {note.detail}")
    for r in report.results:
        detail = r.evidence[0].detail if r.evidence else ""
        typer.echo(f"  {r.status:<14} {r.id:<26} {detail}")
    typer.echo(f"excluded checks: {report.excluded_checks}")

"""CLI: `ap2check check <url> [--sample file] [--json]` and `ap2check serve`."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Annotated

import typer

from ap2check.fetch import DEFAULT_CONTACT_URL
from ap2check.runner import InvalidTarget, check_merchant

app = typer.Typer(add_completion=False, help="Check a merchant's readiness for AP2 payments.")

ICON = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "not_applicable": " n/a", "error": " ERR"}


def _warn_contact() -> None:
    if os.environ.get("AP2CHECK_CONTACT_URL", DEFAULT_CONTACT_URL) == DEFAULT_CONTACT_URL:
        typer.echo("warning: AP2CHECK_CONTACT_URL is not set (see .env.example)", err=True)


@app.command()
def check(
    url: str,
    sample: Annotated[
        Path | None,
        typer.Option(help="File with one checkout response (JSON) or a checkout_jwt."),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
) -> None:
    """Check one merchant (GET requests only)."""
    _warn_contact()
    text = sample.read_text(encoding="utf-8") if sample else None
    try:
        report = asyncio.run(check_merchant(url, text))
    except InvalidTarget as exc:
        raise typer.BadParameter(str(exc)) from exc
    if as_json:
        typer.echo(report.model_dump_json(indent=2))
        return
    typer.echo(f"{report.target}  —  {report.verdict.title}")
    typer.echo(report.verdict.summary + "\n")
    for r in report.results:
        typer.echo(f"[{ICON[r.status]}] {r.id:<24} {r.label}")
        for e in r.evidence:
            typer.echo(f"         {e.detail}")
    typer.echo(
        "\nRequests: " + ", ".join(f"{q.url} -> {q.status or q.error}" for q in report.requests)
    )


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    proxy_headers: Annotated[
        bool, typer.Option(help="Trust X-Forwarded-For (only behind your own proxy).")
    ] = False,
) -> None:
    """Run the website."""
    import uvicorn

    _warn_contact()
    uvicorn.run("ap2check.web.app:app", host=host, port=port, proxy_headers=proxy_headers)

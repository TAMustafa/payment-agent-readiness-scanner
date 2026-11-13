"""Guarantees in docs/SAFETY.md, proven by inspecting the code itself."""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "ap2check"
WRITE_METHODS = {"post", "put", "patch", "delete", "request", "send"}


def _modules() -> list[tuple[Path, ast.Module]]:
    return [(p, ast.parse(p.read_text())) for p in PKG.rglob("*.py")]


def test_only_fetch_module_does_network_io() -> None:
    for path, tree in _modules():
        if path.name == "fetch.py":
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"AsyncClient", "Client", "stream"}:
                if path.parts[-2:] == ("web", "app.py") and node.attr != "stream":
                    continue  # type annotations of the injected transport only
                raise AssertionError(f"{path}: network call {node.attr}")


def test_fetcher_sends_get_only_and_never_follows_redirects() -> None:
    src = (PKG / "fetch.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in WRITE_METHODS:
            raise AssertionError(f"fetch.py uses .{node.attr}")
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "stream":
            assert isinstance(node.args[0], ast.Constant) and node.args[0].value == "GET"
    assert "follow_redirects=False" in src


def test_package_never_signs_or_handles_private_keys() -> None:
    for path, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {
                "sign",
                "generate_private_key",
                "private_bytes",
                "load_pem_private_key",
            }:
                raise AssertionError(f"{path}: {node.attr}")


def test_frontend_never_uses_innerhtml() -> None:
    js = (PKG / "web" / "static" / "app.js").read_text()
    assert not re.search(r"\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML|document\.write", js)


def test_no_api_keys_in_tracked_files() -> None:
    files = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    pattern = re.compile(
        r"(sk-or-v1-[0-9a-f]{20,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|"
        r"-----BEGIN (EC |RSA )?PRIVATE KEY-----)"
    )
    for f in files:
        p = ROOT / f
        if p.is_file() and p.suffix not in {".lock", ".png", ".jpg"}:
            assert not pattern.search(p.read_text(errors="ignore")), f

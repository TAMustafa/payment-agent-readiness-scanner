"""Local cost ledger for V1: one JSON line per paid call, in a gitignored file.

Month = UTC calendar month, the same window as OpenRouter's monthly key-limit reset
(1st, 00:00 UTC). The budget check uses the higher of this ledger and OpenRouter's own
`usage_monthly`, so a lost or edited ledger can never let spending exceed the cap.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def month_key(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y-%m")


def month_to_date(path: Path, now: datetime | None = None) -> float:
    if not path.exists():
        return 0.0
    month = month_key(now)
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("month") == month:
            total += float(row.get("cost_usd", 0.0))
    return round(total, 6)


def append(path: Path, rows: list[dict[str, Any]], now: datetime | None = None) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = (now or datetime.now(UTC)).isoformat()
    month = month_key(now)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps({"ts": ts, "month": month, **row}) + "\n")

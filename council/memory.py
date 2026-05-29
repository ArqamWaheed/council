"""Council memory — persist and recall past verdicts.

Every verdict is appended to data/verdicts.jsonl so the council can answer
"what did we decide about auth last week?" from its own history.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STORE = DATA_DIR / "verdicts.jsonl"


def remember(verdict: dict) -> None:
    """Append a verdict to the persistent log."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    record = dict(verdict)
    record.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    with STORE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def recall(query: str | None = None, limit: int = 10) -> list[dict]:
    """Return recent verdicts, optionally filtered by a substring of the question."""
    if not STORE.exists():
        return []
    records: list[dict] = []
    with STORE.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if query:
        q = query.lower()
        records = [r for r in records if q in r.get("question", "").lower()]
    return records[-limit:]


if __name__ == "__main__":
    import sys

    for r in recall(sys.argv[1] if len(sys.argv) > 1 else None):
        print(f"[{r.get('timestamp', '?')}] {r.get('question')!r} -> "
              f"{r.get('verdict')} (confidence {r.get('confidence')})")

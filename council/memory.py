"""Council memory — persist and recall past verdicts.

Every verdict is appended to data/verdicts.jsonl so the council can answer
"what did we decide about auth last week?" from its own history.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Writable on a serverless/read-only deploy (e.g. Vercel) via COUNCIL_DATA_DIR=/tmp/...
DATA_DIR = Path(os.getenv("COUNCIL_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))
STORE = DATA_DIR / "verdicts.jsonl"

HERMES_HOME = Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes")))
HERMES_MEMORY = HERMES_HOME / "MEMORY.md"
_HEADING = "## Council verdicts"


def mirror_to_hermes(verdict: dict, keep: int = 25) -> None:
    """Best-effort: record the verdict in Hermes' built-in MEMORY.md.

    Hermes auto-injects MEMORY.md into context, so after this a plain
    `hermes -z "what did the council decide about X?"` recalls past verdicts —
    real recall through Hermes' own memory, not just our jsonl.
    """
    try:
        if not HERMES_HOME.exists():
            return
        ts = verdict.get("timestamp") or datetime.now(timezone.utc).isoformat()
        line = (
            f'- [{ts[:10]}] "{verdict.get("question", "").strip()}" \u2192 '
            f'{verdict.get("verdict", "").strip()} '
            f'(confidence {verdict.get("confidence")}, split {verdict.get("split")})'
        )
        text = HERMES_MEMORY.read_text(encoding="utf-8") if HERMES_MEMORY.exists() else ""
        if _HEADING not in text:
            text = (text.rstrip() + "\n\n" if text.strip() else "") + _HEADING + "\n"
        head, _, tail = text.partition(_HEADING + "\n")
        bullets = [b for b in tail.splitlines() if b.strip().startswith("- ")]
        bullets.append(line)
        bullets = bullets[-keep:]
        HERMES_MEMORY.write_text(head + _HEADING + "\n" + "\n".join(bullets) + "\n", encoding="utf-8")
    except Exception:
        pass


def remember(verdict: dict) -> None:
    """Append a verdict to the persistent log (and mirror to Hermes memory).

    Best-effort: on a read-only serverless filesystem the write is skipped rather
    than raising, so the verdict still returns (the client keeps weights itself).
    """
    record = dict(verdict)
    record.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with STORE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass
    mirror_to_hermes(record)


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

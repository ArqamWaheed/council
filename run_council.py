"""run_council.py — the judge.

Fan out a question to the jurors (jurors.convene), then synthesize a single
verdict, a confidence score, and a "why they disagreed" summary. Synthesis is
deterministic (so it's testable); juror weighting is read from the learnable
council skill. The verdict is stored in memory.

Usage:
    python run_council.py "Postgres or Mongo for a new SaaS?"
    python run_council.py --learn "Local Juror | security | 1.5"   # append a weighting rule
    python run_council.py --history [query]                         # recall past verdicts

Output: a single JSON object (see README for the schema).
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from council import memory
from jurors import Opinion, convene

SKILL = Path(__file__).resolve().parent / "skills" / "council" / "SKILL.md"

TOPICS = {
    "security": ["security", "auth", "secure", "vulnerab", "encrypt", "password", "token", "exploit"],
    "database": ["database", "postgres", "mongo", "sql", "schema", "query"],
    "architecture": ["microservice", "monolith", "architecture", "scale", "infra"],
}


def classify(question: str) -> str:
    q = question.lower()
    for topic, kws in TOPICS.items():
        if any(k in q for k in kws):
            return topic
    return "general"


def load_weights() -> dict[tuple[str, str], float]:
    """Parse the ```weights``` block of the council skill: 'Juror | topic | multiplier'."""
    weights: dict[tuple[str, str], float] = {}
    if not SKILL.exists():
        return weights
    text = SKILL.read_text(encoding="utf-8")
    m = re.search(r"```weights\s*(.*?)```", text, re.DOTALL)
    if not m:
        return weights
    for line in m.group(1).splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 3:
            try:
                weights[(parts[0].lower(), parts[1].lower())] = float(parts[2])
            except ValueError:
                continue
    return weights


def _norm(position: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", position.lower()).strip()


def judge(question: str, opinions: list[Opinion]) -> dict:
    topic = classify(question)
    weights = load_weights()

    tally: dict[str, float] = defaultdict(float)
    head_count: dict[str, int] = defaultdict(int)
    label: dict[str, str] = {}
    for op in opinions:
        key = _norm(op.position)
        w = weights.get((op.name.lower(), topic), 1.0)
        tally[key] += w
        head_count[key] += 1
        label.setdefault(key, op.position)

    winner = max(tally, key=tally.get)
    total_weight = sum(tally.values()) or 1.0
    confidence = round(tally[winner] / total_weight, 2)

    counts = sorted(head_count.values(), reverse=True)
    split = "-".join(str(c) for c in counts)
    unanimous = len(head_count) == 1

    majority = [op for op in opinions if _norm(op.position) == winner]
    minority = [op for op in opinions if _norm(op.position) != winner]

    agreements = []
    for op in majority:
        agreements.extend(op.reasons[:2])
    agreements = _dedupe(agreements)

    dissents = []
    for op in minority:
        reason = op.reasons[0] if op.reasons else "no reason given"
        dissents.append(f"{op.name} argued '{op.position}': {reason}")

    if unanimous:
        verdict = f"The council is unanimous: {label[winner]}."
    else:
        verdict = (
            f"By a {split} {'weighted ' if weights else ''}majority, the council favors "
            f"{label[winner]} \u2014 but the decision is contested (see dissent)."
        )

    return {
        "question": question,
        "topic": topic,
        "verdict": verdict,
        "confidence": confidence,
        "split": split,
        "unanimous": unanimous,
        "agreements": agreements,
        "dissents": dissents,
        "jurors": [
            {
                "name": op.name,
                "model": op.model,
                "position": op.position,
                "reasons": op.reasons,
                "weight": weights.get((op.name.lower(), topic), 1.0),
                "mocked": op.mocked,
            }
            for op in opinions
        ],
        "weighted": bool(weights),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for it in items:
        k = it.lower()
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def run(question: str) -> dict:
    verdict = judge(question, convene(question))
    memory.remember(verdict)
    return verdict


def learn(rule: str) -> None:
    """Append a juror-weighting rule to the skill's ```weights``` block (the learning loop)."""
    text = SKILL.read_text(encoding="utf-8")
    m = re.search(r"(```weights\s*\n)(.*?)(```)", text, re.DOTALL)
    if not m:
        raise SystemExit("No ```weights``` block found in SKILL.md")
    updated = text[: m.end(2)] + rule.strip() + "\n" + text[m.end(2):]
    SKILL.write_text(updated, encoding="utf-8")
    print(f"Learned: {rule}")


def main(argv: list[str]) -> None:
    if argv and argv[0] == "--learn":
        learn(" ".join(argv[1:]))
        return
    if argv and argv[0] == "--history":
        print(json.dumps(memory.recall(" ".join(argv[1:]) or None), indent=2))
        return
    question = " ".join(argv) or "Should a 3-person startup use microservices?"
    print(json.dumps(run(question), indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])

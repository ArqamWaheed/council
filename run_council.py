"""run_council.py — the judge.

Fan out a question to the jurors (jurors.convene), then synthesize a single
verdict, a confidence score, and a "why they disagreed" summary. Synthesis is
deterministic (so it's testable); juror weighting is read from the learnable
council skill. The verdict is stored in memory.

Usage:
    python run_council.py "Postgres or Mongo for a new SaaS?"
    python run_council.py --learn "Local Juror | security | 1.5"   # append a weighting rule
    python run_council.py --reflect                                # Hermes proposes a rule (you approve)
    python run_council.py --history [query]                         # recall past verdicts

Output: a single JSON object (see README for the schema).
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import hermes_run
from council import memory
from jurors import Opinion, convene, roster

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
    return re.sub(r"[^a-z0-9 ]", " ", position.lower()).strip()


_STOP = {
    "the", "a", "an", "to", "you", "your", "should", "would", "is", "are", "of", "for",
    "it", "be", "this", "that", "do", "does", "with", "and", "or", "in", "on", "we",
    "i", "use", "using", "going", "not", "no", "yes",
}
# Note: "go" is intentionally NOT a stopword — it's a real option ("Python, Go, or
# Rust?"). Two-letter options are matched by exact token only (see _opt_match) so
# "go" never matches inside words like "good" or "google".

# Leading polarity word -> stance bucket. Lets "No" and "No, you should not X" cluster together.
_POLARITY = {
    "no": "neg", "nope": "neg", "never": "neg", "dont": "neg", "avoid": "neg",
    "shouldnt": "neg", "disagree": "neg", "against": "neg", "false": "neg", "cannot": "neg",
    "yes": "pos", "yep": "pos", "agree": "pos", "definitely": "pos", "absolutely": "pos",
    "sure": "pos", "true": "pos",
}

# Negation tokens that flip a yes/no answer negative wherever they appear (e.g.
# "...is not secure", "...is not a good idea"). Used only as a fallback when the
# leading word is neutral, and only for non-option questions, so an "X or Y"
# decision phrased with "not" ("Postgres, not Mongo") is never affected (those are
# clustered by option first).
_NEGATIONS = {
    "not", "no", "never", "dont", "cannot", "cant", "isnt", "arent", "wasnt",
    "werent", "shouldnt", "wont", "nope", "neither", "nor", "without", "insecure",
    "unsafe",
}


def _polarity(position: str) -> str:
    """Stance polarity for a yes/no answer.

    Prefers the leading word (so mid-string 'no-code' doesn't read as negative);
    if that's neutral, a negation anywhere ('...is not secure') marks the stance
    negative so equivalent 'no' answers cluster together instead of fragmenting.
    """
    toks = [t.replace("'", "") for t in re.findall(r"[a-z']+", position.lower())]
    if not toks:
        return ""
    lead = _POLARITY.get(toks[0], "")
    if lead:
        return lead
    if any(t in _NEGATIONS for t in toks):
        return "neg"
    return ""


def _seg_option(segment: str) -> str:
    """The last content word of a comma/connector segment (the option it names),
    e.g. 'Should we use Python' -> 'python', ' Go' -> 'go'."""
    words = [w for w in _norm(segment).split() if w not in _STOP and len(w) > 1]
    return words[-1] if words else ""


def _extract_options(question: str) -> list[str]:
    """Pull the candidate options out of a decision question.

    Handles two-option forms ('Postgres or Mongo for a new SaaS?' -> ['postgres',
    'mongo']) and comma-separated lists ('Python, Go, or Rust for a backend?' ->
    ['python', 'go', 'rust']). Conservative: if it can't find >=2 distinct clean
    options it returns [] and the judge falls back to generic stance clustering.
    """
    q = re.sub(r"[?.!]+$", "", question.strip())
    m = re.search(r"(.+?)\b(?:or|vs\.?|versus)\b(.+)", q, re.IGNORECASE)
    if not m:
        return []
    left_raw, right_raw = m.group(1), m.group(2)
    opts: list[str] = []
    # Left of the connector may be a comma list ("A, B,"); take one option per
    # segment. Otherwise just the single word right before the connector.
    if "," in left_raw:
        opts.extend(o for o in (_seg_option(seg) for seg in left_raw.split(",")) if o)
    else:
        o = _seg_option(left_raw)
        if o:
            opts.append(o)
    # Right of the connector: first content word (the trailing option).
    right = [w for w in _norm(right_raw).split() if w not in _STOP and len(w) > 1]
    if right:
        opts.append(right[0])
    # De-dupe preserving order; only trust the result when >=2 distinct options.
    deduped: list[str] = []
    for o in opts:
        if o not in deduped:
            deduped.append(o)
    return deduped if len(deduped) >= 2 else []


_COMPARE_MARKERS = {
    "than", "over", "vs", "versus", "unlike", "like", "beats", "beat",
    "not", "without", "outperforms", "outperform",
}


def _opt_match(option: str, toks: set[str], norm: str) -> bool:
    """Does an option occur in a position? Short options (<=3 chars, e.g. 'go')
    match on exact token only, so they don't fire inside 'good'/'google'. Longer
    options also match as a substring so 'postgres' catches 'postgresql'."""
    if option in toks:
        return True
    return len(option) >= 4 and option in norm


def _option_occurrences(text: str, option: str) -> list[int]:
    """Start indices of `option` in `text`. Long options (>=4 chars) match as a
    substring ('postgres' in 'postgresql'); short ones are word-bounded so 'go'
    isn't found inside 'good'."""
    if len(option) >= 4:
        out, start = [], 0
        while True:
            i = text.find(option, start)
            if i < 0:
                break
            out.append(i)
            start = i + len(option)
        return out
    return [m.start() for m in re.finditer(rf"\b{re.escape(option)}\b", text)]


def _first_option(text: str, options: list[str]) -> str:
    """The option mentioned earliest in `text`, skipping ones used in a comparison
    ('...better than Mongo', '...other DBs like Mongo' don't count as endorsements)."""
    best, best_i = "", len(text) + 1
    for o in options:
        for i in _option_occurrences(text, o):
            before = text[:i].split()
            if not (before and before[-1] in _COMPARE_MARKERS) and i < best_i:
                best, best_i = o, i
    return best


def _option_of(position: str, options: list[str], reasons: list[str] | None = None) -> str:
    """Which option an opinion endorses. Reads the position first; if that's ambiguous
    (e.g. a small model wrote a vague position), falls back to the reasons text."""
    norm = _norm(position)
    toks = set(norm.split())
    hits = [o for o in options if _opt_match(o, toks, norm)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        return _first_option(norm, options)
    if reasons:
        return _first_option(_norm(" . ".join(reasons)), options)
    return ""


def _content_tokens(position: str) -> set[str]:
    return {w for w in _norm(position).split() if len(w) > 1 and w not in _STOP}


def _same_stance(a: str, b: str) -> bool:
    """True if two position strings express the same stance."""
    pa, pb = _polarity(a), _polarity(b)
    if pa and pb:
        return pa == pb
    na, nb = _norm(a), _norm(b)
    if na and nb and (na in nb or nb in na):
        return True
    ta, tb = _content_tokens(a), _content_tokens(b)
    if ta and tb:
        return len(ta & tb) / len(ta | tb) >= 0.5
    return na == nb


def _stance_changed(
    original: str, current: str, options: list[str], reasons: list[str] | None = None
) -> bool:
    """Did a juror actually change its vote between rounds? Compares stance/option,
    not raw strings, so a mere rewording ('Rust for backends' -> 'Rust') is NOT a
    change while a real flip ('Rust' -> 'Go') is."""
    if not original or not current:
        return False
    if options:
        return _option_of(original, options, reasons) != _option_of(current, options, reasons)
    return not _same_stance(original, current)


def judge(question: str, opinions: list[Opinion], extra_weights: dict | None = None) -> dict:
    topic = classify(question)
    weights = load_weights()
    if extra_weights:
        weights.update(extra_weights)

    def w_of(op: Opinion) -> float:
        return weights.get((op.name.lower(), topic), 1.0)

    # Cluster opinions by stance, not by exact string, so "No" and "No, you should not X" merge.
    # For "X or Y" questions we first map each juror to the option it endorses (robust against
    # wildly different phrasings like "Postgres" vs "Postgres is the better choice for a SaaS").
    options = _extract_options(question)
    clusters: list[dict] = []
    for op in opinions:
        opt = _option_of(op.position, options, op.reasons) if options else ""
        for c in clusters:
            same = (opt and opt == c.get("opt")) or (
                not opt and not c.get("opt") and _same_stance(op.position, c["rep"])
            )
            if same:
                c["ops"].append(op)
                break
        else:
            clusters.append({"rep": op.position, "ops": [op], "opt": opt})

    for c in clusters:
        c["weight"] = sum(w_of(op) for op in c["ops"])
        # Representative label = the most descriptive (longest) phrasing in the cluster.
        c["label"] = max((op.position for op in c["ops"]), key=len)

    clusters.sort(key=lambda c: c["weight"], reverse=True)
    win = clusters[0]
    total_weight = sum(c["weight"] for c in clusters) or 1.0
    confidence = round(win["weight"] / total_weight, 2)

    counts = sorted((len(c["ops"]) for c in clusters), reverse=True)
    split = "-".join(str(c) for c in counts)
    unanimous = len(clusters) == 1

    majority = win["ops"]
    minority = [op for c in clusters[1:] for op in c["ops"]]

    agreements = []
    for op in majority:
        agreements.extend(op.reasons[:2])
    agreements = _dedupe(agreements)

    dissents = []
    for op in minority:
        reason = op.reasons[0] if op.reasons else "no reason given"
        dissents.append(f"{op.name} argued '{op.position}': {reason}")

    if unanimous:
        verdict = f"The council is unanimous: {win['label']}."
    else:
        verdict = (
            f"By a {split} {'weighted ' if weights else ''}majority, the council favors "
            f"{win['label']} \u2014 but the decision is contested (see dissent)."
        )

    debated = any(op.deliberated for op in opinions)
    # Recompute changed_mind by stance/option (jurors.py only had the raw string),
    # so rewordings don't read as mind-changes and real flips still do.
    for op in opinions:
        if op.deliberated:
            op.changed_mind = _stance_changed(
                op.original_position, op.position, options, op.reasons
            )
    shifts = [
        f"{op.name} moved from '{op.original_position}' to '{op.position}' after the debate."
        for op in opinions
        if op.changed_mind
    ]

    return {
        "question": question,
        "topic": topic,
        "verdict": verdict,
        "confidence": confidence,
        "split": split,
        "unanimous": unanimous,
        "debated": debated,
        "shifts": shifts,
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
                "via": op.via,
                "original_position": op.original_position,
                "changed_mind": op.changed_mind,
                "rebuttal": op.rebuttal,
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


def foreman(question: str, verdict: dict) -> str:
    """Have Hermes (grounded in the council skill) speak the verdict as the foreman.

    Returns a short spoken-style summary, or "" if Hermes isn't available so the
    deterministic verdict still stands. The structured fields above stay
    deterministic (and testable); this only adds Hermes' natural-language voice.
    """
    if not hermes_run.available():
        return ""
    provider = "openrouter" if os.getenv("OPENROUTER_API_KEY", "").strip() else ""
    if not provider:
        return ""
    model = os.getenv("JUDGE_MODEL", "").strip() or os.getenv(
        "JUROR_1_MODEL", "openai/gpt-oss-120b:free"
    )
    lines = "\n".join(
        f"- {j['name']} ({j['model']}): {j['position']}" for j in verdict["jurors"]
    )
    prompt = (
        "You are the foreman of a decision council. Using the council skill's judging "
        "rules, read the jurors' positions below and deliver the verdict in 2 short "
        "sentences a person could read aloud. State the majority decision, the "
        f"{verdict['split']} split, and that dissent was noted. Be decisive, no preamble.\n\n"
        f"QUESTION: {question}\nVERDICT: {verdict['verdict']}\nJURORS:\n{lines}"
    )
    try:
        return hermes_run.ask(prompt, provider, model, skills="council").strip()
    except Exception:
        return ""


def run(question: str, extra_weights: dict | None = None) -> dict:
    verdict = judge(question, convene(question), extra_weights)
    verdict["foreman"] = foreman(question, verdict)
    memory.remember(verdict)
    return verdict


def learn(rule: str) -> None:
    """Append a juror-weighting rule to the skill's ```weights``` block (the learning loop).

    Also mirrors the updated skill into the installed Hermes copy so Hermes and the
    deterministic judge read the same learned weights.
    """
    text = SKILL.read_text(encoding="utf-8")
    m = re.search(r"(```weights\s*\n)(.*?)(```)", text, re.DOTALL)
    if not m:
        raise SystemExit("No ```weights``` block found in SKILL.md")
    updated = text[: m.end(2)] + rule.strip() + "\n" + text[m.end(2):]
    SKILL.write_text(updated, encoding="utf-8")
    _sync_hermes_skill(updated)
    print(f"Learned: {rule}")


def _sync_hermes_skill(content: str) -> None:
    """Best-effort: keep the installed Hermes council skill in sync with the repo skill."""
    try:
        home = Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes")))
        dest = home / "skills" / "council" / "SKILL.md"
        if dest.parent.exists() or home.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
    except Exception:
        pass


def _dissenter_names(record: dict) -> set[str]:
    """Pull the dissenting jurors' names out of a stored verdict's `dissents` lines."""
    names = set()
    for line in record.get("dissents", []):
        m = re.match(r"\s*(.+?) argued ", line)
        if m:
            names.add(m.group(1).strip().lower())
    return names


def reflection_evidence(records: list[dict]):
    """Summarize verdicts into (human-readable lines, per (juror, topic) dissent tally).

    tally[(juror_lower, topic)] = [times_dissented, times_appeared]. This is the raw
    signal both Hermes and the offline fallback reason over — kept pure so it's testable.
    """
    lines, tally = [], {}
    for r in records:
        topic = r.get("topic", "general")
        dissenters = _dissenter_names(r)
        for j in r.get("jurors", []):
            key = (j.get("name", "").lower(), topic)
            t = tally.setdefault(key, [0, 0])
            t[1] += 1
            if j.get("name", "").lower() in dissenters:
                t[0] += 1
        lines.append(
            f"- [{topic}] split {r.get('split')}: {(r.get('verdict') or '')[:90]} "
            f"(dissented: {', '.join(sorted(dissenters)) or 'none'})"
        )
    return lines, tally


def _valid_rule(rule: str) -> str:
    """Return a normalized 'Juror | topic | multiplier' rule, or '' if it's not sane."""
    parts = [p.strip() for p in rule.split("|")]
    if len(parts) != 3:
        return ""
    name, topic, mult = parts
    names = {c.name.lower() for c in roster()}
    if name.lower() not in names:
        return ""
    if topic.lower() not in set(TOPICS) | {"general"}:
        return ""
    try:
        m = float(mult)
    except ValueError:
        return ""
    if not 0.25 <= m <= 3.0 or m == 1.0:
        return ""
    return f"{name} | {topic.lower()} | {m:g}"


def _fallback_suggestion(tally: dict):
    """Deterministic proposal when Hermes is unavailable: upweight the juror that has
    repeatedly dissented on one topic (it may be catching what the majority misses)."""
    best, best_d = None, 1
    for (name, topic), (dissents, _appeared) in tally.items():
        if dissents > best_d:
            best, best_d = (name, topic), dissents
    if not best:
        return None
    name, topic = best
    display = next((c.name for c in roster() if c.name.lower() == name), name)
    rule = _valid_rule(f"{display} | {topic} | 1.25")
    if not rule:
        return None
    return {
        "rule": rule,
        "why": (f"{display} dissented {best_d}× on '{topic}' questions — a persistent minority "
                f"view worth surfacing more. Upweight to 1.25 (you decide if that's signal)."),
        "via": "offline-heuristic",
    }


def parse_weights(rules) -> dict:
    """Turn a list of 'Juror | topic | multiplier' strings into a weights dict.

    Used to apply client-side (e.g. browser localStorage) weights per request, so a
    stateless deployment can persist learning without a writable SKILL.md.
    """
    out: dict[tuple[str, str], float] = {}
    for r in rules or []:
        valid = _valid_rule(r if isinstance(r, str) else "")
        if valid:
            name, topic, mult = [p.strip() for p in valid.split("|")]
            out[(name.lower(), topic.lower())] = float(mult)
    return out


def _hermes_suggestion(lines: list[str], tally: dict):
    """Ask Hermes (grounded in the council skill) to propose ONE weight rule, or None.

    The proposal must be backed by the real dissent tally — we reject rules whose
    (juror, topic) lacks repeated evidence so Hermes can't just parrot the skill's
    worked example.
    """
    if not hermes_run.available():
        return None
    provider = "openrouter" if os.getenv("OPENROUTER_API_KEY", "").strip() else ""
    if not provider:
        return None
    model = os.getenv("JUDGE_MODEL", "").strip() or os.getenv(
        "JUROR_1_MODEL", "openai/gpt-oss-120b:free"
    )
    jurors = ", ".join(c.name for c in roster())
    topics = ", ".join(sorted(set(TOPICS) | {"general"}))
    evidence = "\n".join(
        f"  {name} on '{topic}': dissented {d}/{appeared}"
        for (name, topic), (d, appeared) in sorted(tally.items(), key=lambda x: -x[1][0])
        if d > 0
    ) or "  (no dissents recorded)"
    prompt = (
        "You are the council foreman reviewing your own memory to improve future judging. "
        "Below are recent verdicts and a DISSENT TALLY. Decide whether ONE juror has earned a "
        "changed weight on ONE topic — base it ONLY on the tally, not on any example. Only "
        "propose a topic where that juror has dissented at least twice. If nothing qualifies, "
        "say NO_CHANGE.\n\n"
        f"JURORS: {jurors}\nTOPICS: {topics}\n\nDISSENT TALLY:\n{evidence}\n\n"
        "RECENT VERDICTS:\n" + "\n".join(lines) +
        "\n\nReply with EXACTLY one line, nothing else, in one of these two forms:\n"
        "RULE: <Juror> | <topic> | <multiplier between 0.25 and 3.0>\n"
        "NO_CHANGE: <one-line reason>"
    )
    try:
        out = hermes_run.ask(prompt, provider, model, skills="council").strip()
    except Exception:
        return None
    m = re.search(r"RULE:\s*(.+)", out)
    if not m:
        return None
    rule = _valid_rule(m.group(1))
    if not rule:
        return None
    name, topic, _mult = [p.strip() for p in rule.split("|")]
    if tally.get((name.lower(), topic.lower()), [0, 0])[0] < 2:
        return None  # not backed by repeated dissents — likely anchored on the example
    return {"rule": rule, "why": "Hermes reviewed the dissent tally and proposed this rule.",
            "via": "hermes"}


def suggest_weight(records: list[dict] | None = None):
    """Propose a single weight rule from recent verdicts (Hermes first, then offline)."""
    if records is None:
        records = memory.recall(None, limit=25)
    if len(records) < 2:
        return None
    lines, tally = reflection_evidence(records)
    return _hermes_suggestion(lines, tally) or _fallback_suggestion(tally)


def reflect(auto_approve: bool = False, prompt_fn=input) -> None:
    """Have the council reflect on its memory and propose a weighting you approve."""
    suggestion = suggest_weight()
    if not suggestion:
        print("Not enough signal yet — run a few more verdicts (need a repeated pattern).")
        return
    print(f"\nProposed weighting ({suggestion['via']}):\n  {suggestion['rule']}")
    print(f"  Why: {suggestion['why']}\n")
    if auto_approve:
        learn(suggestion["rule"])
        return
    try:
        answer = prompt_fn("Apply this weighting? [y/N] ").strip().lower()
    except EOFError:
        answer = ""
    if answer in ("y", "yes"):
        learn(suggestion["rule"])
    else:
        print("Skipped — no change made.")


def main(argv: list[str]) -> None:
    if argv and argv[0] == "--learn":
        learn(" ".join(argv[1:]))
        return
    if argv and argv[0] == "--reflect":
        reflect(auto_approve="--yes" in argv[1:])
        return
    if argv and argv[0] == "--history":
        print(json.dumps(memory.recall(" ".join(argv[1:]) or None), indent=2))
        return
    question = " ".join(argv) or "Should a 3-person startup use microservices?"
    print(json.dumps(run(question), indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])

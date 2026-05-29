"""jurors.py — the fan-out.

Ask each juror (a different LLM) the same question over the OpenAI-compatible
OpenRouter API (plus an optional local Ollama juror). Each juror takes a clear
position and gives reasons. Runs back through Hermes' execute_code path.

If OPENROUTER_API_KEY is not set, jurors fall back to deterministic MOCK
responses so the whole demo runs offline at $0 with no credentials.
"""
from __future__ import annotations

import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import hermes_run

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional
    pass


@dataclass
class JurorConfig:
    name: str
    model: str
    base_url: str = "https://openrouter.ai/api/v1"
    api_key_env: str = "OPENROUTER_API_KEY"
    local: bool = False
    provider: str = ""          # Hermes provider; empty ⇒ don't route through Hermes


@dataclass
class Opinion:
    name: str
    model: str
    position: str          # short stance, e.g. "Postgres"
    reasons: list[str] = field(default_factory=list)
    raw: str = ""
    mocked: bool = False
    via: str = ""          # orchestrator that produced it: "hermes" | "openrouter" | "mock"


PROMPT = (
    "You are juror {n}, an experienced engineer on a decision council. "
    "Answer the question below. Take ONE clear position in the FIRST line "
    "(prefix it with 'POSITION:'), then give exactly 3 short reasons as a "
    "numbered list. Be decisive; do not hedge.\n\nQUESTION: {q}"
)


def roster() -> list[JurorConfig]:
    """Build the juror roster from environment configuration.

    When a key is present we route the hosted jurors through Hermes' `openrouter`
    provider; the local juror routes through a named Hermes custom provider
    (default `ollama-local`) so a hosted and an on-device model run through the
    *same* model-agnostic interface — Council's whole bet.
    """
    have_key = bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    hosted_provider = "openrouter" if have_key else ""
    jurors = [
        JurorConfig("Juror 1", os.getenv("JUROR_1_MODEL", "openai/gpt-oss-120b:free"),
                    provider=hosted_provider),
        JurorConfig("Juror 2", os.getenv("JUROR_2_MODEL", "z-ai/glm-4.5-air:free"),
                    provider=hosted_provider),
    ]
    ollama_model = os.getenv("OLLAMA_MODEL", "").strip()
    if ollama_model:
        jurors.append(
            JurorConfig(
                "Local Juror",
                ollama_model,
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                api_key_env="",
                local=True,
                provider=os.getenv("HERMES_OLLAMA_PROVIDER", "ollama-local"),
            )
        )
    elif not have_key:
        # Offline mock mode: include a third "on-device" juror so the demo shows the
        # full 3-model experience (and the signature 2-1 split) with zero credentials.
        jurors.append(JurorConfig("Local Juror", "qwen2.5 (local)", api_key_env="", local=False))
    return jurors


def _strip_md(s: str) -> str:
    """Remove markdown emphasis/code/heading/bullet markers so stances cluster cleanly."""
    s = re.sub(r"\*\*|__|`+|#+", "", s)
    s = re.sub(r"^[\s>]*[-*\u2022]\s+", "", s)
    return s.strip()


# Matches a leading stance label, with optional markdown, e.g. "**POSITION:**", "Answer -", "Verdict:"
_LABEL_RE = re.compile(
    r"^[\s>*_#-]*(?:position|answer|verdict|stance|recommendation|conclusion)[\s*_]*[:\-\u2014]\s*",
    re.IGNORECASE,
)
_POS_RE = re.compile(
    r"^[\s>*_#-]*(?:position|answer|verdict|stance|recommendation|conclusion)[\s*_]*[:\-\u2014]\s*(.+)$",
    re.IGNORECASE,
)
_NUM_RE = re.compile(r"^[\s>*_#-]*\d+[.)]\s*(.+)$")
_BULLET_RE = re.compile(r"^[\s>]*[-*\u2022]\s+(.+)$")


def _parse(text: str) -> tuple[str, list[str]]:
    position = ""
    reasons: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _POS_RE.match(line)
        if m and not position:
            position = _strip_md(m.group(1))
            continue
        m = _NUM_RE.match(line) or _BULLET_RE.match(line)
        if m:
            reasons.append(_strip_md(m.group(1)))
    if not position:
        # No explicit label: use the first non-empty line, dropping any stray label prefix.
        first_line = _strip_md(text.strip().split("\n", 1)[0])
        position = _LABEL_RE.sub("", first_line)
    return _condense(position), reasons[:3]


def _condense(position: str, max_words: int = 14) -> str:
    """Keep stances short: take the first clause/sentence and cap length.

    Small models sometimes write a paragraph after 'POSITION:'; a verdict reads better
    (and clusters more reliably) when the stance is concise.
    """
    position = _strip_md(position).strip("\"'")
    position = _LABEL_RE.sub("", position)  # drop any residual "Position:" label
    first = re.split(r"(?<=[.!?])\s|[\u2014;\u2013]| - | because | since ", position, maxsplit=1)[0]
    first = first.strip().rstrip(".,")
    words = first.split()
    if len(words) > max_words:
        first = " ".join(words[:max_words]).rstrip(".,") + "\u2026"
    return first or position[:60]


def _ask_real(cfg: JurorConfig, question: str, n: int, retries: int = 2) -> Opinion:
    import time

    from openai import OpenAI

    api_key = os.getenv(cfg.api_key_env, "") if cfg.api_key_env else "ollama"
    client = OpenAI(base_url=cfg.base_url, api_key=api_key or "ollama")
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = client.chat.completions.create(
                model=cfg.model,
                messages=[{"role": "user", "content": PROMPT.format(n=n, q=question)}],
                temperature=0.7,
            )
            text = resp.choices[0].message.content or ""
            position, reasons = _parse(text)
            return Opinion(cfg.name, cfg.model, position, reasons, raw=text)
        except Exception as exc:  # retry transient upstream rate limits (429)
            last_exc = exc
            if "429" in str(exc) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise last_exc  # pragma: no cover


# --- Mock juror (offline mode) -------------------------------------------------

_STANCES = ["Yes", "No", "It depends"]


def _mock(cfg: JurorConfig, question: str, n: int) -> Opinion:
    """Deterministic, distinct opinions so offline demos still show real disagreement."""
    seed = int(hashlib.sha256(f"{n}:{question}".encode()).hexdigest(), 16)
    options = _extract_options(question) or _STANCES
    position = options[seed % len(options)]
    reason_bank = [
        f"It best fits the stated constraints in: '{_short(question)}'.",
        "It minimizes long-term operational and maintenance cost.",
        "It is the lower-risk, well-understood choice for a small team.",
        "It keeps the door open to change direction later.",
        "The ecosystem and tooling are more mature here.",
        "It optimizes for the team's current skills over hypothetical scale.",
    ]
    reasons = [reason_bank[(seed >> (i * 3)) % len(reason_bank)] for i in range(3)]
    raw = f"POSITION: {position}\n" + "\n".join(f"{i+1}. {r}" for i, r in enumerate(reasons))
    return Opinion(cfg.name, cfg.model + " (mock)", position, reasons, raw=raw, mocked=True, via="mock")


def _extract_options(question: str) -> list[str]:
    """Pull 'A or B' style options out of the question for richer mock disagreement."""
    m = re.search(
        r"(?:a |an |the )?([\w.+#-]+)\s+(?:or|vs\.?)\s+(?:a |an |the )?([\w.+#-]+)",
        question,
        re.IGNORECASE,
    )
    if m:
        return [m.group(1).capitalize(), m.group(2).capitalize()]
    return []


def _short(text: str, n: int = 60) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "\u2026"


def ask_juror(cfg: JurorConfig, question: str, n: int) -> Opinion:
    prompt = PROMPT.format(n=n, q=question)
    fallback_note = ""
    # Preferred path: Hermes orchestrates the inference (model-agnostic, hosted or local).
    if cfg.provider and hermes_run.available():
        try:
            text = hermes_run.ask(prompt, cfg.provider, cfg.model)
            position, reasons = _parse(text)
            return Opinion(cfg.name, cfg.model, position, reasons, raw=text, via="hermes")
        except Exception as exc:  # Hermes unavailable/rate-limited -> direct or mock
            fallback_note = f"[hermes failed, fell back: {exc}]\n"

    have_key = bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    if cfg.local or have_key:
        try:
            op = _ask_real(cfg, question, n)
            op.via = "openrouter"
            op.raw = fallback_note + op.raw
            return op
        except Exception as exc:  # network/credentials/model errors -> graceful mock
            op = _mock(cfg, question, n)
            op.raw = f"{fallback_note}[fell back to mock: {exc}]\n" + op.raw
            return op
    op = _mock(cfg, question, n)
    op.raw = fallback_note + op.raw
    return op


def convene(question: str) -> list[Opinion]:
    """Fan out the question to every juror (in parallel) and collect their opinions.

    Each juror is an independent Hermes run, so they execute concurrently — genuine
    parallel delegation rather than a serial loop.
    """
    jurors = roster()
    with ThreadPoolExecutor(max_workers=len(jurors) or 1) as pool:
        return list(pool.map(lambda ic: ask_juror(ic[1], question, ic[0] + 1), enumerate(jurors)))


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "Should a 3-person startup use microservices?"
    for op in convene(q):
        print(f"\n## {op.name} ({op.model})\nPOSITION: {op.position}")
        for r in op.reasons:
            print(f"  - {r}")

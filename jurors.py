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
from dataclasses import dataclass, field

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


@dataclass
class Opinion:
    name: str
    model: str
    position: str          # short stance, e.g. "Postgres"
    reasons: list[str] = field(default_factory=list)
    raw: str = ""
    mocked: bool = False


PROMPT = (
    "You are juror {n}, an experienced engineer on a decision council. "
    "Answer the question below. Take ONE clear position in the FIRST line "
    "(prefix it with 'POSITION:'), then give exactly 3 short reasons as a "
    "numbered list. Be decisive; do not hedge.\n\nQUESTION: {q}"
)


def roster() -> list[JurorConfig]:
    """Build the juror roster from environment configuration."""
    jurors = [
        JurorConfig("Juror 1", os.getenv("JUROR_1_MODEL", "meta-llama/llama-3.3-70b-instruct:free")),
        JurorConfig("Juror 2", os.getenv("JUROR_2_MODEL", "deepseek/deepseek-chat-v3-0324:free")),
    ]
    ollama_model = os.getenv("OLLAMA_MODEL", "").strip()
    have_key = bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    if ollama_model:
        jurors.append(
            JurorConfig(
                "Local Juror",
                ollama_model,
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                api_key_env="",
                local=True,
            )
        )
    elif not have_key:
        # Offline mock mode: include a third "on-device" juror so the demo shows the
        # full 3-model experience (and the signature 2-1 split) with zero credentials.
        jurors.append(JurorConfig("Local Juror", "qwen2.5 (local)", api_key_env="", local=False))
    return jurors


def _parse(text: str) -> tuple[str, list[str]]:
    position = ""
    reasons: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"(?i)^position[:\-]\s*(.+)$", line)
        if m and not position:
            position = m.group(1).strip().rstrip(".")
            continue
        m = re.match(r"^\d+[.)]\s*(.+)$", line)
        if m:
            reasons.append(m.group(1).strip())
    if not position:
        position = text.strip().split("\n", 1)[0][:60]
    return position, reasons[:3]


def _ask_real(cfg: JurorConfig, question: str, n: int) -> Opinion:
    from openai import OpenAI

    api_key = os.getenv(cfg.api_key_env, "") if cfg.api_key_env else "ollama"
    client = OpenAI(base_url=cfg.base_url, api_key=api_key or "ollama")
    resp = client.chat.completions.create(
        model=cfg.model,
        messages=[{"role": "user", "content": PROMPT.format(n=n, q=question)}],
        temperature=0.7,
    )
    text = resp.choices[0].message.content or ""
    position, reasons = _parse(text)
    return Opinion(cfg.name, cfg.model, position, reasons, raw=text)


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
    return Opinion(cfg.name, cfg.model + " (mock)", position, reasons, raw=raw, mocked=True)


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
    have_key = bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    if cfg.local or have_key:
        try:
            return _ask_real(cfg, question, n)
        except Exception as exc:  # network/credentials/model errors -> graceful mock
            op = _mock(cfg, question, n)
            op.raw = f"[fell back to mock: {exc}]\n" + op.raw
            return op
    return _mock(cfg, question, n)


def convene(question: str) -> list[Opinion]:
    """Fan out the question to every juror and collect their opinions."""
    return [ask_juror(cfg, question, i + 1) for i, cfg in enumerate(roster())]


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "Should a 3-person startup use microservices?"
    for op in convene(q):
        print(f"\n## {op.name} ({op.model})\nPOSITION: {op.position}")
        for r in op.reasons:
            print(f"  - {r}")

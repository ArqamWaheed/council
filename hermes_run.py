"""hermes_run.py — drive the Hermes Agent CLI as Council's orchestrator.

Each juror and the judge are real Hermes runs: Hermes (model-agnostic) does the
inference over whichever provider/model it's pointed at — a hosted OpenRouter
model or a local Ollama model through the *same* interface. This is the core of
Criterion A: Hermes doing real work at the heart of the project, not in prose.

`ask()` shells out to a scripted one-shot (`hermes -z`) which prints only the
final answer on stdout, so it pipes cleanly back into the judge.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

DEFAULT_TIMEOUT = int(os.getenv("HERMES_TIMEOUT", "180"))


def binary() -> str | None:
    """Locate the hermes executable (PATH, then the default install location)."""
    found = shutil.which("hermes")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "hermes"
    return str(local) if local.exists() else None


def available() -> bool:
    """True when Council should orchestrate through Hermes (binary present + opted in)."""
    if os.getenv("HERMES_ORCHESTRATION", "1").strip().lower() in {"0", "false", "no"}:
        return False
    return binary() is not None


def ask(prompt: str, provider: str, model: str, timeout: int = DEFAULT_TIMEOUT,
        skills: str = "") -> str:
    """Run one scripted Hermes one-shot and return its stdout answer.

    `skills` optionally preloads a Hermes skill (e.g. "council") so the run is
    grounded in that skill's instructions. Raises RuntimeError on failure or
    empty output so callers can fall back.
    """
    exe = binary()
    if not exe:
        raise RuntimeError("hermes binary not found")
    cmd = [exe]
    if provider:
        cmd += ["--provider", provider]
    if model:
        cmd += ["--model", model]
    if skills:
        cmd += ["--skills", skills]
    cmd += ["-z", prompt]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "PYTHONPATH": "", "PYTHONHOME": ""},
    )
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 or not out:
        err = (proc.stderr or "").strip() or f"exit {proc.returncode}, empty output"
        raise RuntimeError(f"hermes run failed: {err[:300]}")
    return out

# memory.md — Council brain

> Agent: read this FIRST every task, UPDATE it LAST (keep terse, minimize tokens).

## What this is
Council: a $0 multi-model decision agent. Ask a judgment call, three "jurors" (LLMs from
different families) take positions, a Hermes-style judge synthesizes one verdict + a confidence
score + a "why they disagreed" panel. Verdicts are remembered; a skill learns which juror to trust.

## Stack
- Orchestrator/judge: Hermes Agent (model-agnostic; the whole bet)
- Jurors: 2 free OpenRouter models (different families) + optional local Ollama
- Fan-out path: Python script over OpenAI-compatible API (`jurors.py`) — the reliable $0 path
- UI: designed single-page `index.html` + Flask `server.py`; Streamlit `app.py` fallback
- License: MIT

## Status snapshot
- Bootstrap, jurors, judge, skill, UI, blog draft: built.
- Runs offline in mock mode (no API key needed) for a deterministic demo.
- Verified live with real models: defaults are `openai/gpt-oss-120b:free` + `z-ai/glm-4.5-air:free`
  (different families, responsive). Free tier is heavily 429-rate-limited; jurors retry w/ backoff
  then fall back to mock. Optional 3rd juror = local Ollama (set OLLAMA_MODEL) — best model-agnostic proof.

## Key decisions
- Path B (execute_code-style Python fan-out) over delegate_task subagents: reliable, no
  un-verifiable Hermes internals. Judging + learning still live in Hermes.
- Confidence = agreement among jurors (high when aligned, low on a 2-1 split).
- Mock fallback so `setup.sh` → demo works with zero credentials.
- Max 3 jurors in the demo (clarity + latency + cost).

## Open questions / TODO
- Round 2 "true debate" (jurors see each other's first answers) — future.
- When is self-learned juror weighting signal vs. overfitting? (open, also the blog's closing Q)

## File map
- `jurors.py`       — fan-out: query each juror (OpenRouter/Ollama) or mock
- `run_council.py`  — judge: cluster stances, synthesize verdict/confidence/dissent, store memory
- `tests/test_judge.py` — unit tests for stance clustering (run: python -m unittest discover -s tests)
- `council/memory.py` — append/query past verdicts (data/verdicts.jsonl)
- `skills/council/SKILL.md` — juror-weighting brain Hermes edits (learning loop)
- `server.py`       — Flask endpoint serving index.html + /api/convene
- `index.html`      — designed verdict UI
- `app.py`          — Streamlit fallback UI
- `setup.sh`        — one-command setup

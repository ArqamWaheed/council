# memory.md — Council brain

> Agent: read this FIRST every task, UPDATE it LAST (keep terse, minimize tokens).

## What this is
Council: a $0 multi-model decision agent. Ask a judgment call, three "jurors" (LLMs from
different families) take positions, a Hermes-style judge synthesizes one verdict + a confidence
score + a "why they disagreed" panel. Verdicts are remembered; a skill learns which juror to trust.

## Stack
- Orchestrator/judge: **Hermes Agent (Nous Research), actually installed & in the loop** (the whole bet)
- Jurors: 2 free OpenRouter models (different families) + local Ollama, **all run through Hermes**
- Fan-out path: `jurors.py` shells out to `hermes -z` per juror (parallel); falls back to direct
  OpenAI-compatible API then deterministic mock so it always runs at $0
- UI: designed single-page `index.html` + Flask `server.py`; Streamlit `app.py` fallback
- License: MIT

## Status snapshot
- **Tier 0 (real Hermes) DONE.** Hermes orchestrates end to end:
  - Each juror = a real `hermes -z --provider P --model M` run; hosted jurors use `openrouter`,
    local juror uses a Hermes custom provider `ollama-local` → hosted + on-device through ONE
    model-agnostic interface. Verdict JSON tags each juror `"via":"hermes"`.
  - Judge "foreman" prose routed through `hermes -z --skills council` (grounded in the skill).
  - `council` skill installed into `~/.hermes/skills/council`; `--learn` edits weights & syncs the
    installed copy (self-improving). Verdicts mirrored into Hermes `MEMORY.md`; recall via `hermes -z`.
  - Reproducible via `setup_hermes.sh` (idempotent). Proof in `docs/hermes-proof/`.
- **Tier 1 polish DONE (most):** foreman **TTS** readout in `index.html` (browser SpeechSynthesis;
  button "the foreman reads the verdict"); **CI** at `.github/workflows/tests.yml` (unittest, py3.10-12,
  mock mode) + badge in README; README has a Hermes-centered architecture diagram + setup_hermes section;
  `docs/BLOG_POST.md` (dev.to) rewritten to match real Hermes orchestration. Remaining: t1-demo gif (optional).
- Hermes facts: requires >=64K ctx (set `model.ollama_num_ctx: 65536` + custom_providers
  `context_length`); `-z` prints final answer only; key lives in `~/.hermes/.env`.
- Runs offline in mock mode (no key / no hermes) for a deterministic demo. Free tier is 429-heavy.
- Stance clustering is option-aware: for "X or Y" questions each juror is mapped to the option it
  endorses (robust to phrasing); else leading-polarity (yes/no) then fuzzy token overlap. Parser strips
  markdown + leading labels ("POSITION:") so a stance isn't misread. UI renders **bold** and shows a
  progress-bar loading screen (asymptotic %, elapsed timer, staged status). Tests: tests/test_judge.py.

## Key decisions
- Hermes is the orchestrator for real (Criterion A): one Hermes run per juror on a different model.
  Direct API + mock remain as graceful fallbacks (toggle with `HERMES_ORCHESTRATION=0`).
- Confidence = agreement among jurors (high when aligned, low on a 2-1 split).
- Mock fallback so `setup.sh` → demo works with zero credentials.
- Max 3 jurors in the demo (clarity + latency + cost).

## Open questions / TODO
- Round 2 "true debate" (jurors see each other's first answers) — future.
- When is self-learned juror weighting signal vs. overfitting? (open, also the blog's closing Q)

## File map
- `hermes_run.py`   — drive Hermes CLI (`hermes -z`) per juror/judge; availability + fallback
- `setup_hermes.sh` — idempotent: install Hermes, wire key, register `ollama-local`, install skill
- `docs/hermes-proof/` — Criterion-A evidence (subagents, skill learning, memory recall, verdict)
- `jurors.py`       — fan-out: query each juror (OpenRouter/Ollama) or mock
- `run_council.py`  — judge: cluster stances, synthesize verdict/confidence/dissent, store memory
- `tests/test_judge.py` — unit tests for stance clustering (run: python -m unittest discover -s tests)
- `council/memory.py` — append/query past verdicts (data/verdicts.jsonl)
- `skills/council/SKILL.md` — juror-weighting brain Hermes edits (learning loop)
- `server.py`       — Flask endpoint serving index.html + /api/convene
- `index.html`      — designed verdict UI (with foreman TTS readout)
- `.github/workflows/tests.yml` — CI: unittest in offline mock mode
- `docs/BLOG_POST.md` — dev.to submission post (tie-break asset; screenshots docs/*.png)
- `app.py`          — Streamlit fallback UI
- `setup.sh`        — one-command setup

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
- **Round 2 "true debate" DONE.** After round 1, if the jurors disagree, `jurors.deliberate()` runs a
  second round: each juror is shown its peers' positions+lead reasons and either HOLDs or CHANGEs its mind
  (real jurors reconsider via the same Hermes/OpenRouter path; mock jurors reconsider deterministically so
  offline stays reproducible). The judge synthesizes the verdict from the **deliberated** opinions, so a
  talked-round juror actually shifts the outcome. Verdict gains `debated`, `shifts`, and per-juror
  `original_position`/`changed_mind`/`rebuttal`. UI shows a "⇄ changed" badge + struck round-1 stance +
  round-2 rebuttal + a "the debate changed minds" panel. Toggle off with `COUNCIL_DEBATE=0`. Tests:
  tests/test_judge.py TestDebate (32 tests total).
- **Clustering logic audit (5 live questions) DONE.** Fixed two real bugs found by running diverse
  questions through the live council: (1) `changed_mind`/`shifts` were raw-string compares in jurors.py,
  so a reword ("Rust for backends" → "Rust") falsely read as a mind-change — now `judge()` recomputes
  `changed_mind` by stance/option via `_stance_changed` (option diff, else `_same_stance`). (2) "go" was a
  stopword and `_extract_options` only ever returned 2 options, so a Go endorsement was invisible —
  removed "go" from `_STOP`, rewrote `_extract_options` to parse comma lists ("A, B, or C" → 3 options),
  and made option matching length-aware (`_opt_match`/`_option_occurrences`: short options like "go" match
  exact-token only so they don't fire inside "good"/"google"; long options keep substring match so
  "postgres" catches "postgresql"). Known limitation (not fixed, too risky for the deterministic
  clusterer): open-ended questions where two jurors agree but word it very differently
  (e.g. "task-queue system" vs "job-queue with workers") can still read as a split, and a positively-phrased
  agreement to a yes/no question ("CSRF protection is important" vs "No, don't disable CSRF") may not cluster.
- Hermes facts: requires >=64K ctx (set `model.ollama_num_ctx: 65536` + custom_providers
  `context_length`); `-z` prints final answer only; key lives in `~/.hermes/.env`.
- Runs offline in mock mode (no key / no hermes) for a deterministic demo. Free tier is 429-heavy.
- Stance clustering is option-aware: for "X or Y" questions each juror is mapped to the option it
  endorses (robust to phrasing); else leading-polarity (yes/no) then fuzzy token overlap. Polarity is
  **negation-aware**: if the leading word is neutral, a negation anywhere ("...is not secure") marks the
  stance negative, so equivalent "no/insecure" answers to a yes/no question cluster into one verdict
  instead of a false 1-1-1 split. If a juror's position is vague/option-less, `_option_of` falls back to scanning its REASONS (first-mentioned option
  wins, skipping comparison contexts like "better than Mongo"/"like Mongo") so an agreeing juror isn't
  mis-clustered as a dissenter. Parser strips markdown + leading labels ("POSITION:") so a stance isn't
  misread. UI renders **bold** and shows a progress-bar loading screen (asymptotic %, elapsed timer,
  staged status). Tests: tests/test_judge.py (32 tests).

## Key decisions
- Hermes is the orchestrator for real (Criterion A): one Hermes run per juror on a different model.
  Direct API + mock remain as graceful fallbacks (toggle with `HERMES_ORCHESTRATION=0`).
- Learning loop has two paths: `--learn "Juror | topic | mult"` (manual) and `--reflect` (agentic:
  Hermes reviews its own verdict memory, proposes ONE weight rule, human approves; offline =
  deterministic heuristic over repeated dissents). Rules validated (known juror/topic, 0.25–3.0, ≠1.0).
  Web UI exposes both: `/api/reflect` (propose) + `/api/learn` (apply) behind a "reweight itself" button.
  Reflect is evidence-grounded: rejects any proposed rule not backed by ≥2 real dissents in the tally
  (prevents Hermes parroting the skill's example). Web learning also persists in browser localStorage and
  is re-sent per convene (`run(question, extra_weights)` / `parse_weights`) so stateless deploys keep it.
- Confidence = agreement among jurors (high when aligned, low on a 2-1 split).
- Mock fallback so `setup.sh` → demo works with zero credentials.
- Max 3 jurors in the demo (clarity + latency + cost).

## Open questions / TODO
- Round 2 "true debate" **DONE** (jurors see each other's first answers and may change their minds).
  Future: a round 3, or letting a juror cite a *specific* peer reason in its rebuttal.
- When is self-learned juror weighting signal vs. overfitting? (open, also the blog's closing Q)

## File map
- `hermes_run.py`   — drive Hermes CLI (`hermes -z`) per juror/judge; availability + fallback
- `setup_hermes.sh` — idempotent: install Hermes, wire key, register `ollama-local`, install skill
- `docs/hermes-proof/` — Criterion-A evidence (subagents, skill learning, memory recall, verdict)
- `jurors.py`       — fan-out: query each juror (OpenRouter/Ollama) or mock; round-2 `deliberate()`
- `run_council.py`  — judge: cluster stances, synthesize verdict/confidence/dissent, store memory
- `tests/test_judge.py` — unit tests for stance clustering (run: python -m unittest discover -s tests)
- `council/memory.py` — append/query past verdicts (data/verdicts.jsonl)
- `skills/council/SKILL.md` — juror-weighting brain Hermes edits (learning loop)
- `server.py`       — Flask endpoint serving index.html + /api/convene
- `index.html`      — designed verdict UI (with foreman TTS readout)
- `.github/workflows/tests.yml` — CI: unittest in offline mock mode
- `docs/BLOG_POST.md` — dev.to submission post (kept local / gitignored; screenshots docs/*.png)
- `app.py`          — Streamlit fallback UI
- `setup.sh`        — one-command setup

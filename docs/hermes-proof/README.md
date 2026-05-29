# Hermes proof — Hermes Agent doing real work at the heart of Council

This folder is evidence for **Criterion A**: Council does not merely *mention* Hermes,
it is **orchestrated by Hermes Agent** (Nous Research) end to end.

| # | Artifact | What it proves |
|---|----------|----------------|
| 01 | [`01-environment.txt`](01-environment.txt) | Hermes Agent installed; the `council` skill is installed & enabled in Hermes. |
| 02 | [`02-juror-subagents.txt`](02-juror-subagents.txt) | Each juror is a **real Hermes run** (`via=hermes`) on a **different model** — two hosted OpenRouter families **and** a local Ollama model through the *same* model-agnostic interface. They run **in parallel** (one Hermes agent per juror). |
| 03 | [`03-skill-learning.txt`](03-skill-learning.txt) | The **self-improving skill**: `--learn` edits the council skill's `weights` block and syncs it into the installed Hermes skill, changing future judging. |
| 04 | [`04-memory-recall.txt`](04-memory-recall.txt) | Verdicts are written into Hermes' built-in `MEMORY.md`; a plain `hermes -z` question **recalls** them from Hermes' own memory. |
| 05 | [`05-verdict.json`](05-verdict.json) | A full verdict where every juror shows `"via": "hermes"`, plus the Hermes-authored `foreman` summary. |

## How Hermes is in the loop (code)

- **`hermes_run.py`** — shells out to scripted one-shots (`hermes -z`), with the council skill preloaded for the judge.
- **`jurors.py`** — `convene()` fans out one Hermes run per juror **concurrently**; each juror's `provider`/`model` points Hermes at a different model (`openrouter` for hosted, `ollama-local` for the on-device juror).
- **`run_council.py`** — `foreman()` routes the spoken verdict through Hermes **grounded in the `council` skill**; `learn()` edits + syncs that skill.
- **`council/memory.py`** — `mirror_to_hermes()` records each verdict into Hermes `MEMORY.md` for recall.

Hermes orchestration is the default; if the `hermes` binary is absent or a free
model rate-limits, Council falls back to a direct API call and finally to a
deterministic offline mock, so the demo always runs at **$0**.

## Reproduce

```bash
# Hosted jurors (free OpenRouter) + local juror (Ollama) all via Hermes:
python run_council.py "Should a small team choose microservices or a monolith?"

# Recall a past verdict straight from Hermes' memory:
hermes -z "Check your memory. What has the council decided about Postgres vs Mongo?"
```

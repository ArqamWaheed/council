# ⚖️ Council

> **Don't trust one model. Convene a jury.**
> Make your AI models argue, then let Hermes be the judge.

Council takes any judgment call — *"Postgres or Mongo?"*, *"is this PR safe to merge?"*,
*"microservices or a monolith?"* — and asks **three different models**. They each take a
position with reasons. Then a Hermes-style judge delivers **one verdict**, a **confidence
score**, and exactly **why they disagreed**. Three models, one verdict, **$0**.

The whole idea rides on Hermes' defining property: it's **model-agnostic** — swap providers
with `hermes model`, no code change. The jurors are *different* models from *different*
families, and that's the point.

![Council verdict card: a 2-1 split with a confidence dial and colour-coded juror chips](docs/verdict.png)

---

## Why

Single-model overconfidence is the villain: you ask one model, get one smooth, authoritative
answer, and the disagreement that should have warned you is invisible. Council makes the
**dissent the product**. A contested 2-1 split is *more* useful than a confident single answer.

---

## Quickstart (runs at $0, no API key required)

```bash
git clone https://github.com/YOU/council && cd council
./setup.sh
python server.py          # designed web UI -> http://localhost:8000
```

Without an API key, Council runs in **offline mock mode** — deterministic, distinct opinions so
the full 3-juror experience works with zero credentials. Add a free key to convene real models:

```bash
cp .env.example .env       # then paste your free OpenRouter key into OPENROUTER_API_KEY
```

Other entry points:

```bash
python run_council.py "Should we use Postgres or Mongo for a new SaaS?"   # CLI -> JSON
streamlit run app.py                                                       # plainer fallback UI
```

---

## How it works

```
question ──▶ jurors.py (fan-out)         ──▶ run_council.py (judge)        ──▶ verdict JSON
              • Juror 1  (OpenRouter free)     • tally positions by weight       + stored in memory
              • Juror 2  (OpenRouter free)     • confidence = agreement
              • Local Juror (Ollama, opt.)     • surface the dissent
```

- **Fan-out (`jurors.py`)** — each juror is a different model, queried over the
  OpenAI-compatible API (Hermes' `execute_code` path). Each takes one clear position + 3 reasons.
- **Judge (`run_council.py`)** — deterministic synthesis into a single verdict, a confidence
  score (high when jurors agree, low on a split), agreements, and dissents.
- **Skill (`skills/council/SKILL.md`)** — the juror-weighting *brain*. Hermes appends learned
  rules over time (e.g. "upweight the local model on `security`"). A static prompt can't improve;
  this can.
- **Memory (`council/memory.py`)** — every verdict is logged to `data/verdicts.jsonl`, so you can
  ask `python run_council.py --history auth` for what the council decided before.

### The learning loop

```bash
python run_council.py --learn "Local Juror | security | 1.5"
```

This appends a rule to the skill's `weights` block; on the next security question that juror's
vote counts 1.5×. The weighting is read back by the judge automatically.

### Verdict JSON schema

```jsonc
{
  "question": "...", "topic": "database",
  "verdict": "By a 2-1 majority, the council favors Postgres — but the decision is contested.",
  "confidence": 0.67, "split": "2-1", "unanimous": false,
  "agreements": ["..."], "dissents": ["Juror 2 argued 'Mongo': ..."],
  "jurors": [{ "name": "Juror 1", "model": "...", "position": "Postgres",
               "reasons": ["..."], "weight": 1.0, "mocked": false }],
  "weighted": false, "timestamp": "..."
}
```

---

## Configuration

All optional — see [`.env.example`](.env.example).

| Var | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | *(empty)* | Free OpenRouter key. Empty ⇒ offline mock mode. |
| `JUROR_1_MODEL` | `meta-llama/llama-3.3-70b-instruct:free` | First juror (≥64K ctx). |
| `JUROR_2_MODEL` | `deepseek/deepseek-chat-v3-0324:free` | Second juror, different family. |
| `OLLAMA_MODEL` | *(empty)* | Optional local "on-device" juror. |
| `JUDGE_MODEL` | `JUROR_1_MODEL` | Model Hermes uses to synthesize. |

> Hermes rejects models under 64K context at startup — pick `:free` models that clear that bar.

---

## Project layout

| File | Role |
|---|---|
| `jurors.py` | Fan-out: query each juror, or deterministic mock offline |
| `run_council.py` | Judge: synthesize verdict/confidence/dissent, store memory |
| `council/memory.py` | Persist + recall past verdicts |
| `skills/council/SKILL.md` | Learnable juror-weighting brain |
| `server.py` + `index.html` | Designed single-page verdict UI |
| `app.py` | Streamlit fallback UI |

Agent workflow notes live in [`AGENTS.md`](AGENTS.md) and [`memory.md`](memory.md).

---

## Built for the Hermes Agent Challenge · MIT licensed

Fork it, add your own jurors. The verdict UI was built with the **frontend-design** skill;
the repo's commit history and `AGENTS.md` show the agent-run process.

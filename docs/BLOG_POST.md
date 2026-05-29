---
title: "I Made My AI Models Argue, Then Let Hermes Be the Judge"
published: false
description: "A $0 multi-model decision agent: three LLMs debate, Hermes judges, and it learns who to trust."
tags: hermesagentchallenge, devchallenge, agents, showdev
cover_image: https://YOUR_COVER_URL
---

*This is a submission for the [Hermes Agent Challenge](https://dev.to/challenges/hermes-agent-2026-05-15): Build With Hermes Agent*

An LLM once talked me into the wrong database with total confidence. One smooth, authoritative answer. I shipped it. It cost me a weekend and a migration I'm still not over.

The villain here is **single-model overconfidence** — you get one polished reply, and the disagreement that should have warned you is invisible. You never see the other opinions, because you only asked one model.

**So I stopped trusting one model. I convened a jury.**

Council takes any judgment call — "Postgres or Mongo?", "is this PR safe to merge?", "is this clause risky?" — and asks **three different models**, lets them disagree, then has Hermes deliver one verdict, a confidence score, and exactly *why* they split. Three models, one verdict, $0.

{% youtube YOUR_VIDEO_ID %}

**Repo:** https://github.com/YOU/council *(MIT)* · **Live demo:** https://YOUR_DEMO

---

## What I Built

You ask a question. Council fans it out to three jurors — two free OpenRouter models from different families and one local model via Ollama — each takes a position with reasons. Hermes then judges: a single verdict, a **confidence score** (high when they agree, low when they split 2–1), and a "why they disagreed" panel. Every verdict is remembered, and a `council.md` skill learns which juror to trust for which kind of question.

![A contested 2-1 split: confidence 67%, with colour-coded juror chips and an expandable dissent panel](https://YOUR_SCREENSHOT_2-1_SPLIT)

---

## Demo

Live: https://YOUR_DEMO — try "Should a 3-person startup use microservices?" and open the dissent panel.
Local, one command (runs at $0 in offline mock mode, no key needed):

```
git clone https://github.com/YOU/council && cd council && ./setup.sh && python server.py
```

---

## Code

Repo: https://github.com/YOU/council. Interesting files: `run_council.py` (orchestration + the deterministic judge), `skills/council/SKILL.md` (the juror-weighting brain Hermes edits), `index.html` (the designed verdict UI).

```python
# jurors.py — the fan-out, one model per juror (OpenAI-compatible API)
def convene(question: str) -> list[Opinion]:
    return [ask_juror(cfg, question, i + 1) for i, cfg in enumerate(roster())]

# run_council.py — confidence = winning weight / total weight
winner = max(tally, key=tally.get)
confidence = round(tally[winner] / (sum(tally.values()) or 1.0), 2)
```

---

## How I Used Hermes Agent

**Why Hermes at all — the model-agnostic core.** Hermes lets you point at any provider and swap with `hermes model`, no code change. Council is built *on top of that one property*: the jurors are different models, and Hermes is the only piece that makes "different models" cheap. I genuinely didn't see another entry in this challenge exploit model-agnosticism — everyone picked one model and moved on. That's the whole bet.

**Why subagents (and the gotcha).** I wanted each juror in isolated context so one model's reasoning couldn't anchor another's. My first plan was one `delegate_task` subagent per juror. The gotcha I hit: making each subagent run on a *different* provider per call isn't the clean, guaranteed path I wanted to bet a submission on. So I fell back to Hermes' **`execute_code`** tool — it runs a small Python script (`jurors.py`) that calls each model over the OpenAI-compatible API and hands the results straight back to Hermes to judge. Either way the *judging and learning* stays in Hermes; the fan-out is just plumbing.

**Why a skill, not a prompt, for judging.** The weighting logic lives in `skills/council/SKILL.md`, in a machine-readable `weights` block. After a string of security questions, Hermes appended a rule to upweight the local model on that topic — because it had caught issues the hosted models missed:

```
python run_council.py --learn "Local Juror | security | 1.5"
```

On the next security question that juror's vote counts 1.5×, read straight back by the judge. Counterfactual: a static synthesis prompt can't get better; this does.

**Why memory.** Each verdict is appended to a log, so I can run `run_council.py --history auth` and ask "what did the council decide about auth last week?" — answered from its own history.

**The build itself was agent-run.** I kept a `memory.md` the coding agent read before each task and updated after (so context stayed cheap), committed every increment with Conventional Commits, and built the verdict UI with the **frontend-design** skill — which is why the confidence dial and colour-coded juror chips read as *designed*, not default-template AI slop. The repo's `AGENTS.md` + commit history show the process, not just the result.

**Why these models, and the concession.** Two free OpenRouter models (≥64K context — Hermes rejects smaller at startup) plus a local Ollama juror. Concession: free models are slower and three calls add latency (~10–20s/verdict). For a once-a-decision tool, I'll take it. Cost: $0.

**License.** MIT — fork it, add your own jurors.

---

## What I learned (and what's next)

- The disagreement is the product. A 2–1 split is *more* useful than a confident single answer.
- Hermes' 64K-context floor caught a model that would've quietly underperformed.
- Next: let jurors see each other's first answers for a real second round (true debate).

One question for you: **I weight a *local* model higher on security after it out-caught the hosted ones — but that's one user's anecdote turning into a rule. How would you decide when an agent's self-learned weighting is signal vs. overfitting?**

---

*Built for the Hermes Agent Challenge. MIT licensed. Repo, live demo, and the self-written skill diff are all in the README.*

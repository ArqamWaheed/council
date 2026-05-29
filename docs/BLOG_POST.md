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

**Repo:** https://github.com/ArqamWaheed/council *(MIT)* · **Live demo:** https://YOUR_DEMO

---

## What I Built

You ask a question. Council fans it out to three jurors — two free OpenRouter models from different families and one local model via Ollama — each takes a position with reasons. Hermes then judges: a single verdict, a **confidence score** (high when they agree, low when they split 2–1), and a "why they disagreed" panel. Every verdict is remembered, and a `council.md` skill learns which juror to trust for which kind of question.

![A contested 2-1 split: confidence 67%, with colour-coded juror chips and an expandable dissent panel](https://YOUR_SCREENSHOT_2-1_SPLIT)

---

## Demo

Live: https://YOUR_DEMO — try "Should a 3-person startup use microservices?" and open the dissent panel.
Local, one command (runs at $0 in offline mock mode, no key needed):

```
git clone https://github.com/ArqamWaheed/council && cd council && ./setup_hermes.sh && python server.py
```

---

## Code

Repo: https://github.com/ArqamWaheed/council. Interesting files: `hermes_run.py` (the Hermes CLI driver every juror/judge call goes through), `run_council.py` (orchestration + the deterministic judge + Hermes foreman), `skills/council/SKILL.md` (the juror-weighting brain Hermes edits), `index.html` (the designed verdict UI with the foreman TTS readout). Proof that Hermes is genuinely in the loop — subagent transcripts, skill diff, memory recall — is in [`docs/hermes-proof/`](https://github.com/ArqamWaheed/council/tree/main/docs/hermes-proof).

```python
# hermes_run.py — every juror/judge call is a real Hermes run
def ask(prompt, provider, model, skills=None, timeout=120):
    cmd = [binary(), "--provider", provider, "--model", model]
    if skills: cmd += ["--skills", skills]
    cmd += ["-z", prompt]                       # -z = one-shot, final answer on stdout
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout

# jurors.py — fan out one Hermes subagent per juror, in parallel
with ThreadPoolExecutor(max_workers=len(roster())) as pool:
    opinions = list(pool.map(lambda c: ask_juror(*c), enumerate(roster())))
```

---

## How I Used Hermes Agent

**Why Hermes at all — the model-agnostic core.** Hermes lets you point at any provider and swap with a flag, no code change. Council is built *on top of that one property*: the jurors are different models, and Hermes is the only piece that makes "different models" cheap. The clearest proof is the third juror — it runs **locally** via Ollama while the other two are **hosted** on OpenRouter, and all three answer through the exact same `hermes -z` interface. A hosted model and an on-device model, sitting on the same jury, no code change: that's model-agnosticism you can see. I genuinely didn't see another entry in this challenge exploit it — everyone picked one model and moved on. That's the whole bet.

**Subagents — one real Hermes run per juror.** Each juror is a genuine, isolated Hermes invocation on a *different* provider+model (`hermes -z --provider openrouter --model …` for the two hosted jurors, `--provider ollama-local …` for the on-device one), fanned out **in parallel** so no model's reasoning anchors another's. Hermes does the inference; my Python (`jurors.py` → `hermes_run.py`) is just the fan-out plumbing, and every juror in the output JSON is tagged `"via": "hermes"`. The gotcha worth flagging: Hermes enforces a **64K-context floor**, which for the local model meant setting both `ollama_num_ctx` *and* a named `custom_providers` entry — without the named provider, `--provider ollama` silently routed to the wrong base URL. `setup_hermes.sh` encodes the working config so a judge can reproduce it in one command.

**Why a skill, not a prompt, for judging.** The foreman's verdict is itself a Hermes run — `hermes -z --skills council` — grounded in `skills/council/SKILL.md`, which is **installed into Hermes** (`hermes skills list` shows it). The weighting logic lives in a machine-readable `weights` block. After a string of security questions, `--learn` appended a rule to upweight the local model on that topic — *and synced the installed Hermes copy* — because it had caught issues the hosted models missed:

```
python run_council.py --learn "Local Juror | security | 1.5"
```

On the next security question that juror's vote counts 1.5×, read straight back by the judge. Counterfactual: a static synthesis prompt can't get better; this does. (The before/after skill diff is in [`docs/hermes-proof/03-skill-learning.txt`](https://github.com/ArqamWaheed/council/blob/main/docs/hermes-proof/03-skill-learning.txt).)

**Why memory.** Each verdict is appended to a log *and mirrored into Hermes' own `MEMORY.md`*, so I can ask `hermes -z "what did the council decide about auth?"` and Hermes recalls it from its memory — not from my code. Proof: [`docs/hermes-proof/04-memory-recall.txt`](https://github.com/ArqamWaheed/council/blob/main/docs/hermes-proof/04-memory-recall.txt).

**The foreman reads the verdict aloud.** The verdict card has a "the foreman reads the verdict" button (browser SpeechSynthesis, $0); Hermes also ships native TTS via `hermes setup tts`. On-theme and memorable — a jury foreman *announcing* the decision.

**The build itself was agent-run.** I kept a `memory.md` the coding agent read before each task and updated after (so context stayed cheap), committed every increment with Conventional Commits, and built the verdict UI with the **frontend-design** skill — which is why the confidence dial and colour-coded juror chips read as *designed*, not default-template AI slop. The repo's `AGENTS.md` + commit history show the process, not just the result.

**Why these models, and the concession.** Two free OpenRouter models from different families (≥64K context — Hermes rejects smaller at startup) plus a local Ollama juror. Two honest concessions: (1) free models are slower and three calls add latency (~10–20s/verdict); (2) the free tier is *aggressively* rate-limited — I hit 429s constantly while building, so Council retries and, if a juror still won't answer, falls back (Hermes → direct API → deterministic stand-in) rather than crashing the verdict, which also means the demo runs **fully offline at $0**. For a once-a-decision tool, I'll take it. Cost: $0.

**License.** MIT — fork it, add your own jurors.

---

## What I learned (and what's next)

- The disagreement is the product. A 2–1 split is *more* useful than a confident single answer.
- Hermes' 64K-context floor caught a model that would've quietly underperformed.
- Next: let jurors see each other's first answers for a real second round (true debate).

One question for you: **I weight a *local* model higher on security after it out-caught the hosted ones — but that's one user's anecdote turning into a rule. How would you decide when an agent's self-learned weighting is signal vs. overfitting?**

---

*Built for the Hermes Agent Challenge. MIT licensed. Repo, live demo, and the self-written skill diff are all in the README.*

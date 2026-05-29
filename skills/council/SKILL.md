---
name: council
description: "Use when synthesizing a multi-juror Council verdict: classify the question's topic, weigh each juror per the learned weights block, tally positions, set confidence from agreement, and always surface the dissent."
version: 1.0.0
author: Council
license: MIT
metadata:
  hermes:
    tags: [council, jury, decision, multi-model, verdict, judging]
    category: autonomous-ai-agents
---

# Council Skill — how to weigh the jurors

This skill is the council's **judging brain**. Hermes reads it before synthesizing a
verdict and **appends to it over time** as it learns which juror to trust for which kind
of question. That learning loop is the point: a static synthesis prompt can't improve;
this can.

## How the judge uses this file
1. Classify the question's **topic** (security, database, architecture, general).
2. Look up per-juror **weights** for that topic in the `weights` block below.
3. Tally each position by its juror's weight; the highest-weighted position is the verdict.
4. Confidence = winning weight / total weight (high when jurors agree, low on a split).

## Judging rules
- A contested split is **information, not noise** — always surface the dissent.
- Never claim consensus equals truth. Report the split honestly.
- Default every juror to weight `1.0` unless a learned rule below says otherwise.
- Prefer the lower-risk, reversible option when jurors are evenly split.

## Learned weights (Hermes edits this block)
Format: `Juror Name | topic | multiplier`. Higher = more trusted for that topic.
Only add a rule that is backed by a repeated pattern in the verdict history.

```weights
```

## Learnings log (human-readable; Hermes appends)
<!-- Append a dated note ONLY when the dissent tally shows a repeated pattern across
several verdicts. Base the rule on the data, not on this comment. -->

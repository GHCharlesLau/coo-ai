---
name: coo-critique
description: Scores the campaign proposal on a fixed rubric, rewrites proposal.md and slides.json when notes exist, and writes review.json. Use during the COO AI critique stage. Soft-gated; retries then escalates to a human.
---

# Critique

## When to use

When `proposal.md`, `slides.json`, and all upstream artifacts exist and the orchestrator is on stage `critique`.

## Required inputs

- `brief.json`
- `situation.md`
- `evidence.json`
- `strategy.json`
- `plan.json`
- `measurement.json`
- `proposal.md`
- `slides.json`

## Procedure (do not skip)

1. Run this stage as an independent reviewer. Open a fresh subagent or a cold re-read with no memory of drafting the proposal, and judge only the artifacts on disk. Do not defend earlier choices. Hunt defects. Do not award a uniform sheet of any score.
2. Score each criterion 1–5. Criteria (use these `criterion` strings exactly):
   - `brief_fidelity`
   - `insight_quality`
   - `message_distinctiveness`
   - `plan_kpi_coherence`
   - `budget_clarity`
   - `measurability`
   - `proposal_completeness`
   - For evidence-v2 campaigns, also score `budget_evidence_quality` and `visual_communication`.
3. `overall` is the unweighted mean of those scores.
4. `passed` is true only if `overall >= pass_threshold` (default 3.5).
5. Requirements-v3 campaigns need at least one substantive `revision_notes` entry of 40+ characters that names a concrete defect and the fix. "Tighten copy" or "improve flow" does not count. A high score is not a reason to skip review; find the weakest section and strengthen it.
6. If any criterion is below 4, rewrite `proposal.md` and `slides.json` to fix the issues. Preserve required headings, `<!-- coo:... -->` markers, APA cites, and slide layout variety. Marker numbers must still match plan and measurement.
7. When `revision_notes` is non-empty, the proposal and slides files **must** differ from the write/slides-stage versions. Make a real edit, not a whitespace change.
8. Emit `review.json`, `proposal.md`, and `slides.json`. The orchestrator re-assembles References and re-renders `proposal.pptx`.

## Output schema (`review.json`)

```
campaign_id: string
scores: [{criterion, score 1-5, comment}]
overall: number
pass_threshold: number
passed: boolean
revision_notes: string[]
human_override: false
```

## Self-check

- All seven legacy criteria present; evidence-v2 also includes budget evidence quality and visual communication
- `overall` equals the mean of scores
- `passed` matches the threshold
- Scores differ across criteria
- At least one substantive revision note (40+ characters) for requirements-v3 campaigns
- Revised proposal still passes the write and slides gates

## Must not do

- Do not set `human_override` to true. Only a human can do that.
- Do not inflate scores to pass a thin proposal.
- Do not leave revision notes while emitting an unchanged proposal.
- Do not remove markers, required headings, or the References section while editing.

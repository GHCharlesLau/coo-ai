---
name: coo-strategy
description: Writes strategy.json (insight, positioning, message house, big idea) that answers the brief. Use during the COO AI strategy stage only. Must not include tactics or budget.
---

# Strategy

## When to use

When `brief.json`, `situation.md`, and `evidence.json` exist and the orchestrator is on stage `strategy`.

## Required inputs

- `brief.json`
- `situation.md`
- `evidence.json`

## Procedure (do not skip)

1. Derive one insight from the situation (what is true and useful about the audience or category).
2. Write positioning that names who it is for and why this offer wins.
3. Build a message house: headline, at least two pillars, proof points that do not contradict evidence.
4. Write a big idea: the organizing thought, not a media plan.
5. Set `objective_links` to **every** brief objective id.
6. Forbid extra keys: no `channels`, `tactics`, `budget`, `media`, `media_mix`.
7. Emit `strategy.json` only.

## Output schema (`strategy.json`)

```
campaign_id: string
insight: string
positioning: string
message_house: {headline, pillars[], proof_points[]}
big_idea: string
objective_links: string[]  # brief objective ids
```

## Self-check

- Every brief objective id appears in `objective_links`
- No tactic or budget fields
- Insight is a sentence, not a slogan stuffed with channel names
- Big idea could be executed in more than one channel

## Must not do

- Do not invent a media mix.
- Do not assign owners, dates, or dollar amounts.
- Do not ignore an objective.

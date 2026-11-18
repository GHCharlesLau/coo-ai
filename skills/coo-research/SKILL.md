---
name: coo-research
description: Builds situation.md and evidence.json from live lookup, not from the brief restated. Use during the COO AI research stage only.
---

# Research

## When to use

When `brief.json` exists and the orchestrator is on stage `research`.

## Required inputs

- `brief.json`

## Procedure (do not skip)

1. Search live sources before writing. Look up host economy / market geography, published calendar or timing, and at least one comparable campaign (summit/host-year or a PRSA Silver Anvil-style case). Start with `references/websites.md` when that file is in the workspace (`marketing-interactive.com`, PRSA Silver Anvil cases, Digital Marketing Institute, istylemarketing).
   For evidence-v2 campaigns, prioritize sources current to the decision date. Record `checked_at` (ISO date), `geography`, and `applicable_period` for every sourced item; distinguish current facts from historical comparisons. Support every material fact, numeric claim, rate, and benchmark with a traceable source. For numeric evidence, record `numeric_value` and `numeric_unit` when applicable.
2. Write `situation.md` with these headings exactly: Category, Audience, Competitors, Opportunity, plus Host or Geography or Market. Name the host/geography if it is public. If it is truly unknown, add an evidence item whose claim says "host unknown" or "geography unknown" and `is_assumption: true`.
3. Every material claim in the situation must appear in `evidence.json`.
4. Do not treat the brief as an external source. `brief.json`, "this brief", and "the campaign brief" are not citations.
5. For each sourced item fill APA fields: `author` (person or organization), `year` (YYYY or n.d.), `title`, `container` (site/publisher), and an `http` `source_url`. Assumptions omit those fields and set `is_assumption: true`.
   Client quotes and internal records may use `source_kind: client_quote|internal` and a `source_reference`; public evidence uses `source_kind: public` and a URL.
6. Keep assumptions at or below half of all items. Prefer fewer honest assumptions over a wall of unsourced claims.
7. Do not recommend channels or write the big idea.
8. Emit both `situation.md` and `evidence.json`.

## Output schema

`situation.md` — markdown with at least: Category, Audience, Competitors, Opportunity, and Host/Geography/Market.

`evidence.json`:

```
campaign_id: string
items: [{id, claim, source?, source_url?, source_kind, source_reference?, checked_at?, geography?, applicable_period?, numeric_value?, numeric_unit?, numeric_currency?, cost_scope?, is_assumption, confidence, author?, year?, title?, container?}]
```

Sourced items require author, year, title, and http source_url.

## Self-check

- At least three distinct http `source_url` values
- No item cites the brief
- Assumptions ≤ 50% of items
- `campaign_id` matches context
- No media mix, budget, or tagline

## Must not do

- Do not fabricate citations, URLs, or statistics.
- Do not jump to positioning or tactics.
- Do not skip live lookup because the brief already sounds complete.

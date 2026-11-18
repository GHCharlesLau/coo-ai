---
name: coo-write
description: Assembles a client-ready proposal.md from upstream artifacts with APA citations, required sections, and machine-readable number markers. Use during the COO AI write stage only.
---

# Write

Legacy eight-stage path only. New campaigns use `coo-deliver`, which merges proposal and deck work.

## When to use

When brief, situation, evidence, strategy, plan, and measurement artifacts exist and the orchestrator is on stage `write`.

## Required inputs

- `brief.json`
- `situation.md`
- `evidence.json`
- `strategy.json`
- `plan.json`
- `measurement.json`
- `operations.json` (evidence-v2)

## Procedure (do not skip)

1. Open the proposal template structure. Use the nine numbered headings exactly, including the `## N. ` prefix. After Next Steps the orchestrator will write `## References` from evidence; you may include a stub References heading.
2. Fill each section from artifacts as client copy. Do not invent new KPIs, tactics, or budget numbers. Do not tell the reader to open `evidence.json` or any other artifact.
   Write at client depth: the default floors are 150 characters per numbered section and 900 words across the nine numbered sections (References excluded). These are minimums, not targets; use the space for evidence, trade-offs, sequencing, and decisions. Operators can raise them with `COO_MIN_SECTION_CHARS` and `COO_MIN_PROPOSAL_WORDS`.
3. Keep tactic, objective, KPI, budget-line, question, and evidence ids out of the prose. They belong only in the HTML markers at the top.
4. Situation must name geography or language mix. Strategy must include 2–3 sample lines from the message house, written as spoken copy.
5. Every factual sentence drawn from a sourced evidence item gets an APA parenthetical or a cite marker `<!-- cite:ev_id -->`. Do not give assumptions a fake year; label them as assumptions.
6. For evidence-v2 campaigns, present low/base/high budget ranges in the requested currency, show whether the estimate is complete or a priced subtotal, and label assumptions and outstanding quotes plainly. Use calculated plan amounts only; never create a precise total for unpriced components.
7. Emit machine-readable markers at the top of the document:

```
<!-- coo:budget_total=NUMBER -->
<!-- coo:budget_currency=CODE -->
<!-- coo:budget_range=LOW,BASE,HIGH -->
<!-- coo:budget_complete=true|false -->
<!-- coo:kpi_ids=id1,id2 -->
<!-- coo:tactic_ids=id1,id2 -->
```

`kpi_ids` must be the full set from `measurement.json`. `tactic_ids` must be the full set from `plan.json`. No spaces in the lists.

8. Budget section must also state the human-readable total and line items.
9. For evidence-v2 campaigns, also emit `campaign_assets.json` with a tailored media pitch, press release, issue FAQ with anticipated hard questions, social calendar, estimated-versus-actual budget ledger (leave actuals blank), and post-campaign evaluation outline covering every objective and KPI. Keep quotes, FAQ answers, and claims provisional until an approver is named; do not invent spokespeople, approvals, results, or actual spend.
10. Emit `proposal.md`; evidence-v2 campaigns also emit `campaign_assets.json`. The orchestrator expands cite markers and overwrites `## References` from `evidence.json`.

`campaign_assets.json` follows `coo.schemas.operations.CampaignAssets`:

```
campaign_id: string
media_pitch: {subject, recipient_personalization, hook, body, call_to_action}
press_release: {headline, subheadline, dateline, body, quote, quote_attribution, boilerplate, approval_note}
issue_faq: [{question, answer, approval_status: draft|needs_client_review|approved, approved_by?}]
social_calendar: [{date_or_phase, platform, copy, visual_cue, hashtags[]}]
budget_ledger: [{budget_line_id, category, estimate_low, estimate_base, estimate_high, actual?, currency, status}]
post_campaign_evaluation: [{objective_id, kpi_id, evaluation_method, data_source, timing}]
```

Its budget ledger must reconcile to `plan.json`; actual spend remains null until campaign delivery. Evaluation rows collectively cover every objective and KPI. Label unapproved press quotes, FAQ answers, and claims as needing client review. Use client-approved boilerplate and named spokespeople only.

## Required headings (verbatim)

```
## 1. Executive Summary
## 2. Brief and Objectives
## 3. Situation
## 4. Strategy
## 5. Channel and Tactics Plan
## 6. Budget
## 7. Measurement
## 8. Risks and Constraints
## 9. Next Steps
## References
```

## Self-check

- All required headings present and each section is substantive
- Nine numbered sections clear the depth floor; the proposal reads like client copy, not a summary
- Markers match plan totals, currency, range, completeness, KPI ids, and tactic ids
- No new numbers that are not in upstream artifacts
- Sourced claims are cited; URLs will match evidence

## Must not do

- Do not drop a tactic or KPI.
- Do not round the budget to a different total.
- Do not skip markers because the prose already mentions the numbers.
- Do not leak `tac_`, `obj_`, `kpi_`, `bl_`, `q_`, or `ev` ids into client copy.
- Do not point at `evidence.json`.

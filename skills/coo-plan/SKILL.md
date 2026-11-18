---
name: coo-plan
description: Turns approved strategy into plan.json and, on the lean pipeline, measurement.json. Use during the COO AI plan stage only.
---

# Plan

## When to use

When `brief.json` and `strategy.json` exist and the orchestrator is on stage `plan`.

## Required inputs

- `brief.json`
- `strategy.json`
- `evidence.json`

## Procedure (do not skip)

1. Choose channels that can carry the big idea. List them in `channels`.
2. Define tactics. Each tactic has `id`, `name`, `channel` (must be in `channels`), `description`, `kpi_id`, `budget_line_id`, `owner`, `start`, `end`. Use real `YYYY-MM` dates. Compare them to today's date: mark elapsed work `completed` or `in_progress`, or explicitly rebaseline the schedule; do not present elapsed work as upcoming.
3. For evidence-v2 campaigns, build each budget line from `components`: quantity, unit, low/base/high rate, rate currency, geography, pricing date, and basis (`published_rate`, `benchmark`, `client_quote`, `assumption`, or `unpriced`). Cite sourced rates through `evidence_id`; each priced evidence item must match the rate/unit/geography and identify when it was checked. For foreign currency, give `fx_to_budget`, `fx_date`, and a sourced `fx_evidence_id` that identifies the currency pair. Use USD unless the brief requests another currency. Mark assumptions with rationale and confidence. If no defensible price exists, leave rates empty, set `basis: unpriced`, and state the quote needed. Never invent a subtotal.
4. Set each line's `amount`, `low_amount`, and `high_amount` to the calculated sum of its components in the budget currency. Mark `estimate_status` complete, assumption, partial, or unpriced as appropriate; disclose any unpriced item. Set `estimate_as_of`.
5. Every tactic must point at an existing budget line and a KPI id you intend measurement to define (stable `kpi_...` ids).
6. If the brief has a budget cap, set `budget_cap` and compare the high-case total against it. A partial subtotal cannot confirm cap compliance; call that out and identify outstanding quotes.
7. Timeline must cover all tactics.
8. For evidence-v2 campaigns, also emit `operations.json` with a ROPES plan covering stakeholder analysis; impact/output/outcome objectives; programming theme and message strategy; pretesting, monitoring, evaluation, and stewardship; media/KOL profiles scored for relevance, reach, resonance, and risk/ethics; five countdown phases; run-of-show rows; campaign risks with immediate PR response; and a jurisdiction-aware compliance checklist. Categorize outlet tiers as `tier_1_mainstream` (mainstream business/financial impact), `tier_2_vertical` (trade/industry depth), or `tier_3_niche` (niche digital creators), and explain the tier fit. Use evidence ids for sourced assessments; mark unknown scores and pending legal checks plainly. If no current media shortlist is available, set `media_coverage_status` to `pending_client_list` or `pending_research` and state the dependency. If RSVPs or attendee data are involved, flag applicable local privacy obligations and GDPR where relevant for client/legal review. Do not provide legal advice.
9. Emit `plan.json`; evidence-v2 campaigns also emit `operations.json`.
10. Lean pipeline only: also emit `measurement.json` in the same response, using the measurement procedure below. The two files ship together and are gated together.

## Measurement procedure (lean pipeline)

1. Collect every `kpi_id` referenced by plan tactics. Each must appear in `kpis`.
2. For every KPI give name, operational `definition`, `unit`, `target`, `polarity` (`leading` or `lagging`), `communication_tier` (`output`, `outtake`, or `outcome`), `data_source`, and `cadence`. Evidence-v2 runs need at least one KPI at each tier. Set `measurable: true` only when a real data source is named.
3. An `established` target needs an explicit baseline or comparison value plus source evidence ids. Otherwise mark it `provisional` and give a concrete `calibration_method` such as a pre-launch baseline or pilot test.
4. Include at least one leading and one lagging KPI, link every campaign objective to at least one KPI, and keep KPI ids unique.
5. Add `reporting_cadence` and 1-3 `decision_rules` (if X by date Y, then do Z).
6. Emit `measurement.json`:

```
campaign_id: string
kpis: [{id, name, definition, unit, target, polarity, communication_tier, objective_ids: [], data_source, cadence, formula?, measurable, target_status: established|provisional, target_evidence_ids: [], baseline?, calibration_method?}]
reporting_cadence: string
decision_rules: string[]
```

## Output schema (`plan.json`)

```
campaign_id: string
channels: string[]
tactics: [{id, name, channel, description, kpi_id, budget_line_id, owner, start, end, status: planned|in_progress|completed}]
timeline_start: string
timeline_end: string
budget_currency: string
budget_cap: number | null
budget_lines: [{id, label, amount?, low_amount?, high_amount?, estimate_status, components: [{label, quantity, unit, basis, rate_currency, rate_low?, rate_base?, rate_high?, range_rationale?, geography, priced_on?, evidence_id?, fx_to_budget?, fx_evidence_id?, fx_date?, assumption_rationale?, confidence?, quote_needed?}], quote_needed?}]
estimate_as_of: ISO date
notes: string
```

For evidence-v2 runs, `operations.json` follows `coo.schemas.operations.OperationsPlan`. Its countdown covers month 6, month 3, week 1, day 1, and post-event. The run of show uses time, duration, activity, on-stage talent, A/V cues, and responsible party. If an event schedule is not yet available, state that in `run_of_show_note` and identify the client input needed. Each compliance item names a jurisdiction, status, and review note; pending legal checks stay pending until the client or qualified reviewer confirms them.

The new-run structure is:

```
ropes: {research, stakeholder_analysis[], objectives[], impact_objectives[], output_objectives[], outcome_objectives[], programming[], programming_theme, message_strategy[], pretesting[], monitoring[], evaluation[], stewardship[]}
media_klos: [{name, kind, tier, tier_category, tier_rationale, audience, relevance, reach, resonance, risk_ethics, disclosure_required?, disclosure_notes, selection_rationale}]
media_coverage_status: assessed|pending_client_list|pending_research|not_applicable
countdown: [{phase: month_6|month_3|week_1|day_1|post_event, tasks[], owner}]
run_of_show: [{time, duration, activity, on_stage_talent, av_cues, responsible_party}]
risks: [{risk, likelihood, impact, mitigation, immediate_pr_response, owner}]
compliance: [{area, status, jurisdiction, notes, reviewer?}]
```

## Self-check

- Every tactic has `kpi_id` and `budget_line_id`
- Lean runs emit `measurement.json` whose KPI ids cover every plan tactic
- Every `budget_line_id` exists
- Low/base/high totals are calculated from line items and reconcile exactly
- Every priced rate is evidenced or explicitly labeled as a reasoned assumption
- High-case total is within cap, or cap compliance is explicitly unresolved due to unpriced quotes
- Tactic channels are a subset of `channels`
- Tactic ids and budget line ids are unique
- For evidence-v2 runs, all five countdown phases and all six compliance review areas are present
- Never use the DOCX's sample budget ratios as market-rate evidence

## Must not do

- Do not rewrite strategy.
- Do not leave a tactic without a KPI or a budget line.
- Do not invent a total that is not the sum of lines.

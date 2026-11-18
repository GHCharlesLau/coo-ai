---
name: coo-measure
description: Writes measurement.json so every plan tactic has a measurable KPI with leading and lagging measures. Use during the COO AI measure stage only.
---

# Measure

Legacy eight-stage path only. New campaigns receive `measurement.json` from the merged `coo-plan` stage.

## When to use

When `brief.json`, `strategy.json`, and `plan.json` exist and the orchestrator is on stage `measure`.

## Required inputs

- `brief.json`
- `strategy.json`
- `plan.json`

## Procedure (do not skip)

1. Collect every `kpi_id` referenced by plan tactics. Each must appear in `kpis`.
2. For every KPI: name, operational `definition`, `unit`, `target`, `polarity` (`leading` or `lagging`), `communication_tier` (`output`, `outtake`, or `outcome`), `data_source`, and `cadence`. Evidence-v2 campaigns need at least one KPI at each communication tier. Set `measurable: true` only if a real data source is named. An `established` target needs an explicit baseline/comparison value and source evidence ids. Otherwise mark it `provisional` and state a concrete `calibration_method` (for example, a pre-launch baseline survey or an initial media test). Do not present an uncalibrated target as established.
3. Include at least one leading and one lagging KPI.
4. Add `reporting_cadence` and 1–3 `decision_rules` (if X by date Y, do Z).
5. Emit `measurement.json` only.

## Output schema (`measurement.json`)

```
campaign_id: string
kpis: [{id, name, definition, unit, target, polarity, communication_tier: output|outtake|outcome, objective_ids: [], data_source, cadence, formula?, measurable, target_status: established|provisional, target_evidence_ids: [], baseline?, calibration_method?}]
reporting_cadence: string
decision_rules: string[]
```

## Self-check

- All plan tactic `kpi_id`s exist
- No KPI with empty definition, unit, target, or data_source
- Each established target has a traceable evidence source and explicit baseline/comparison value; each provisional target has a calibration method
- `measurable` is true for every KPI
- Both polarities present
- Evidence-v2 runs include all three communication tiers and link every objective to at least one KPI
- KPI ids unique

## Must not do

- Do not add vanity metrics with no data source.
- Do not drop a KPI a tactic depends on.
- Do not rewrite the plan.

---
name: coo-deliver
description: Writes the client proposal.md and the slides.json deck in one stage. Use during the COO AI deliver stage only.
---

# Deliver

## When to use

When `brief.json`, `situation.md`, `evidence.json`, `strategy.json`, `plan.json`, and `measurement.json` exist and the orchestrator is on stage `deliver`.

## Required inputs

- `brief.json`
- `situation.md`
- `evidence.json`
- `strategy.json`
- `plan.json`
- `measurement.json`
- `operations.json` (evidence-v2)

## Required outputs

- `proposal.md`
- `slides.json`
- `campaign_assets.json` (evidence-v2 only)

The CLI expands cite markers, regenerates `## References` from `evidence.json`, renders `proposal.html`, and builds a native editable `proposal.pptx` from `slides.json` with real text, shapes, tables, charts, and picture frames. Never hand-edit `proposal.pptx` and never emit OOXML.

## Content abundance

A client-ready deliverable is not a summary. Aim for 1,800-2,800 words across the nine numbered sections. The hard floors are 200 characters per numbered section and 1,400 words total (References excluded); operators can raise them with `COO_MIN_SECTION_CHARS` and `COO_MIN_PROPOSAL_WORDS`. Floor compliance is not the target. Use the space for evidence, audience nuance, channel logic, sequencing, trade-offs, ownership, and decisions.

The deck must contain 14-26 slides (18-26 when the deck is image- or diagram-led). Use the coverage checklist below, not a fixed slide sequence:

- situation and category pressure
- audience and insight
- strategy, positioning, and big idea
- message house and sample copy
- one slide per tactic or workstream, each with owner, timing, channel, cost link, and KPI
- campaign calendar or sequence
- budget with low/base/high treatment when evidence-v2
- measurement and reporting
- risks, constraints, and mitigation
- next steps and decisions requested
- references

At least one data or diagram slide must appear in each major section (situation, strategy, tactics, budget, measurement). Never compress several tactics into one bullet slide.

## Proposal procedure (do not skip)

1. Use the nine numbered headings exactly, with the `## N. ` prefix. After Next Steps the orchestrator writes `## References`; a stub heading is allowed.
2. Fill each section from artifacts as client copy. Do not invent KPIs, tactics, or budget numbers. Never tell the reader to open `evidence.json` or any artifact.
3. Keep tactic, objective, KPI, budget-line, question, and evidence ids out of prose. They belong only in the HTML markers and schema fields.
4. Situation must name geography or language mix. Strategy must include 2-3 sample lines from the message house written as spoken copy.
5. Every tactic in the Channel and Tactics section must name its human name, owner, channel, start and end timing, and budget-line label. One paragraph or bullet block per tactic; no summary sweep.
6. Every factual sentence drawn from sourced evidence gets an APA parenthetical or a `<!-- cite:ev_id -->` marker. Label assumptions as assumptions; never attach a fake year or source.
7. For evidence-v2 campaigns present low/base/high budget ranges, state whether the estimate is complete or a priced subtotal, and label assumptions and outstanding quotes plainly. Use calculated plan amounts only.
8. Emit machine-readable markers at the top:

```
<!-- coo:budget_total=NUMBER -->
<!-- coo:budget_currency=CODE -->
<!-- coo:budget_range=LOW,BASE,HIGH -->
<!-- coo:budget_complete=true|false -->
<!-- coo:kpi_ids=id1,id2 -->
<!-- coo:tactic_ids=id1,id2 -->
```

`kpi_ids` is the full measurement set; `tactic_ids` is the full plan set. No spaces.
9. Budget section restates the human-readable total and line items. Measurement restates each KPI target and data source.
10. For evidence-v2, also emit `campaign_assets.json` with a tailored media pitch, press release, issue FAQ, social calendar, estimated-versus-actual budget ledger (actuals blank), and post-campaign evaluation covering every objective and KPI. Keep quotes, FAQ answers, and claims provisional until an approver is named.

## Required proposal headings (verbatim)

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

## Deck procedure (do not skip)

1. Emit `slides.json` only. The HTML deck and the native PPTX are two presentations of the same source. The PPTX carries editable text, shapes, tables, charts, and picture frames, and must not contain speaker notes or full-slide screenshots; edit `slides.json` and re-render.
2. Build 14-26 slides with a campaign-specific mix of text, data, and diagram compositions. Do not repeat one template across the deck.
3. Use the layout variants: alternate split-image, full-bleed photo with scrim, left-rail stat band, offset two-column, horizontal timeline, and ruled editorial table. Drive rotation with `design.variant` and per-slide `variant`, not new layout types. Image-led decks may also use `board` (pinned evidence wall), `evidence` (one photograph with numbered annotations), and the `hub` / `route` diagram kinds.
4. Set `design.style` (`editorial`, `brief`, `report`, `briefing`), `design.accent_mode` (`contrast`, `warm`, `mono`), `density`, and `visual_ratio` to fit the campaign. `briefing` is the Lemo-Opuscar Engineering Briefing Board: enamel-paper ground, pinned prints, marker annotations and stamps; use it when photographs and diagrams carry the argument. Mix light and dark slides within one deck, except `briefing`, whose sections stay light so the wall reads as one surface. Never use more than two consecutive slides with the same composition variant.
5. Required coverage: title, situation with citations, strategy/message house, one slide per tactic, calendar or timeline, budget, KPIs, risks, next steps, references. Insert a section divider only when it helps navigation.
6. Copy `budget_total`, `budget_currency`, `kpi_ids`, and `tactic_ids` from plan and measurement. These fields are gated.
7. Speaker `notes` are internal source material only. Never rely on them for client-facing content: no deliverable (HTML, PPTX, PDF, DOCX) may contain notes, process commentary, or tool attribution. Put anything the client needs on the slide itself.
8. Photos are optional and only when supplied or rights-cleared. Store campaign images under `assets/images/` and reference them as `assets/images/<file>`; named deliverables stay at the artifacts root. Include path, alt text, caption, rights status, usage statement, and source/creator/license. Prefer diagrams over decorative stock imagery.
9. Every `cite_id` must exist in `evidence.json`. Table and chart slides need a source note.

## Output schema (`slides.json`)

```
campaign_id: string
theme: editorial|navy_gold
budget_total: number
budget_low?: number
budget_high?: number
budget_complete: boolean
budget_currency: string
kpi_ids: [string]
tactic_ids: [string]
palette?: {background, text, muted, accent, card, rule, navy, white, olive}
font_heading?: string
font_body?: string
design?: {density: airy|balanced|dense, visual_ratio: 0-1, style: editorial|brief|report|briefing, accent_mode: contrast|warm|mono, variant: auto|hint}
slides: [{
  layout: title|section|bullets|two_column|kpis|budget|quote|references|next_steps|diagram|timeline|chart|photo|table|stats|gallery|comparison|map|matrix|board|evidence
  title, subtitle?, body?, bullets?, left?, right?, notes?, cite_ids?, stamp?,
  variant?: auto|cover|split|bleed|ledger|rail|offset|steps|editorial|timeline|grid|dense|gallery|mosaic|data|framework|flow|matrix|wall|annotated,
  diagram?: {kind: flow|framework|timeline|hub|route, nodes, edges}, chart?: {kind, categories, series, unit?, axis_label?},
  image?: {path, alt_text, caption?, rights_status, usage, source_url?, creator?, license?, placement},
  table?: {columns, rows, align?, column_widths?, highlight_rows?, source_note?},
  stats?: [{value, label, detail?, source_note?}], images?: [image], source_note?: string
}]
```

`template_path` is tolerated for stored decks and ignored. Brand theming lives in `palette`, `font_heading`, `font_body`, and `design`.

## Self-check

- Nine numbered sections clear the depth floor and each tactic carries owner, timing, channel, and cost link
- Markers match plan totals, currency, range, completeness, KPI ids, and tactic ids
- 14-26 slides, one per tactic, title/references/KPI-or-budget present
- No more than two consecutive slides share a composition variant
- At least one data or diagram slide in each major section
- Budget, KPI, and tactic ids match upstream artifacts; no invented numbers
- Cite ids exist; sourced claims carry citations; images carry rights metadata

## Must not do

- Do not drop a tactic, KPI, or objective
- Do not round the budget to a different total
- Do not skip markers because the prose mentions the numbers
- Do not leak `tac_`, `obj_`, `kpi_`, `bl_`, `q_`, or `ev` ids into client copy
- Do not point the reader at `evidence.json`
- Do not dump the proposal as bullet walls or repeat one slide template

---
name: coo-slides
description: Maps the approved proposal into typed slides.json. The orchestrator renders proposal.pptx. Use during the COO AI slides stage only.
---

# Slides

Legacy eight-stage path only. New campaigns use `coo-deliver`, which merges proposal and deck work.

## When to use

When `proposal.md` and upstream artifacts exist and the orchestrator is on stage `slides`.

## Required inputs

- `brief.json`
- `situation.md`
- `evidence.json`
- `strategy.json`
- `plan.json`
- `measurement.json`
- `proposal.md`
- `operations.json` and `campaign_assets.json` for evidence-v2 campaigns

## Procedure (do not skip)

1. Emit `slides.json` only. Do not emit OOXML or a binary deck. The CLI renders `proposal.html`, a native editable `proposal.pptx` (real text, shapes, tables, charts, and picture frames), and a deck PDF from the same source.
2. Build 10–16 slides for a standard deck, or 18–26 for a deliberately visual, image-led proposal. Use a supplied brand template/palette when available; preserve its theme, typography, colors, and brand marks. Otherwise use a warm, restrained editorial theme with strong type hierarchy and generous whitespace. Favor legible editable diagrams for campaign flow, relationships, and timelines, plus readable tables, stat bands, image galleries, maps, and charts where data supports them. `design.style: briefing` selects the Lemo-Opuscar Engineering Briefing Board (enamel paper, pinned prints, marker annotations, stamps) for photo- and diagram-led decks. Alternate concise text, diagrams, data views, and optional image-led slides; avoid repeated card grids and bullet walls. Set `design.visual_ratio` when the deck should be gated for visual density. Use the attached reference deck only for flexible cues such as warm canvas, bold hierarchy, and varied composition. Never reuse its brand marks, campaign copy/claims, or images.
   Photos are optional and only allowed when supplied or rights-cleared. Store campaign images under `assets/images/` and reference them as `assets/images/<file>`; named deliverables stay at the artifacts root. Include image path, descriptive alt text, caption, rights status, a usage-rights statement, and source/creator/license metadata for licensed images. If no suitable cleared image exists, rely on diagrams; do not use decorative stock imagery.
3. Required sequence (you may insert extras):
   - `title` — campaign title, brand, window
   - `section` — agenda
   - situation with citations (`bullets` or `two_column`, `cite_ids` set)
   - strategy / big idea (`diagram`, `two_column`, or `quote`)
   - tactics (`bullets`) using human names, not ids
   - `budget` table whose total matches plan
   - `kpis` cards whose targets match measurement
   - risks
   - `next_steps`
   - `references` — APA lines from sourced evidence
4. Copy `budget_total`, `budget_currency`, `kpi_ids`, and `tactic_ids` from the proposal markers / plan / measurement. These fields are gated.
5. Speaker `notes` are internal source material only. No deliverable may contain notes, process commentary, or tool attribution; put anything the client needs on the slide itself.
6. Every `cite_id` must exist in `evidence.json`.

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
template_path?: string
palette?: {navy?, accent?, background?, text?, muted?, card?, white?}
font_heading?: string
font_body?: string
design?: {density?: airy|balanced|dense, visual_ratio?: number, reference_style?: string, style?: editorial|brief|report|briefing, accent_mode?: contrast|warm|mono, variant?: string}
slides: [{
  layout: title|section|bullets|two_column|kpis|budget|quote|references|next_steps|diagram|timeline|chart|photo|table|stats|gallery|comparison|map|matrix|board|evidence
  title: string
  subtitle?: string
  body?: string
  bullets?: [string]
  left?: [string]
  right?: [string]
  notes?: string  # internal only; never written to a deliverable
  cite_ids?: [string]
  stamp?: string
  rows?: [[string]]
  quote?: string
  attribution?: string
  diagram?: {kind: flow|framework|timeline|hub|route, nodes: [{id, label, detail?, date?}], edges: [{source, target, label?}]}
  chart?: {kind: bar|line|donut|horizontal_bar|stacked_bar, categories: [string], series: [{label, values: [number]}], unit?, axis_label?}
  image?: {path, alt_text, caption?, rights_status: supplied|licensed, usage, source_url?, creator?, license?, placement: right|left|full_bleed|inset}
  table?: {columns: [string], rows: [[string]], align?, column_widths?, highlight_rows?, source_note?}
  stats?: [{value, label, detail?, source_note?}]
  images?: [image]
  source_note?: string
}]
```

## Self-check

- At least 10 slides
- Layouts include title, references, and kpis or budget
- Budget total and KPI/tactic ids match plan and measurement
- No invented numbers
- Diagram/chart fields contain the data they visualize; image assets live under `assets/images/` and document rights metadata
- Table and chart slides carry a source note
- No slide depends on speaker notes, and no deliverable contains notes, generator metadata, or tool attribution
- When `design.visual_ratio` is set, enough visual/data slides are present, there are at least two data slides, and no more than two consecutive text-heavy slides
- Use the plan's low/base/high range and label incomplete subtotals

## Must not do

- Do not emit `proposal.pptx` yourself.
- Do not dump the full proposal as bullet walls.
- Do not cite evidence ids that do not exist.

---
name: coo-ai
description: Constructs a campaign proposal through the COO AI CLI (gated intake, research, strategy, plan, deliver, critique). Use when the user asks for a campaign proposal, marketing campaign, PR campaign, brand campaign, campaign brief, COO AI, or to advance/resume/approve a campaign.
compatibility: Requires Python 3.11+ and the coo-ai CLI (pip install -e coo-ai)
---

# COO AI

Drive campaign proposals with the **COO AI CLI**. Do not paste a finished proposal into chat.

The orchestrator owns stage order, schemas, gates, traces, and human checkpoints. Stage skills under `coo-ai/skills/` are loaded through CLI prompts, not as your independent workflow.

## Setup

From `coo-ai/`:

```
python -m pip install -e ".[dev]"
```

**Default model:** the coding agent's own model. An API key is optional.

- No `COO_LLM_API_KEY` / `OPENAI_API_KEY`: CLI pauses at `awaiting_agent`. You read `prompts/<stage>.md`, write the required files under `artifacts/`, then `resume`.
- Key set: CLI calls that OpenAI-compatible API.
- `--stub`: test fixture only. Do not use it for a real campaign.

## Commands

```
python -m coo new --demand "USER DEMAND TEXT" --run
python -m coo new --revision-of <campaign-id> --run
python -m coo status <campaign-id>
python -m coo prompt <campaign-id>
python -m coo resume <campaign-id>
python -m coo resume <campaign-id> --approve
python -m coo answer <campaign-id> --question <id> --text "..."
python -m coo answer <campaign-id> --question <id> --defer-reason "..."
python -m coo resume <campaign-id> --override
python -m coo export <campaign-id>              # proposal.docx + proposal.pdf
python -m coo export <campaign-id> --format pdf
python -m coo export <campaign-id> --format html
python -m coo export <campaign-id> --format pptx
python -m coo export <campaign-id> --format deck-pdf
python -m coo export <campaign-id> --format all  # DOCX + PDF + HTML + PPTX + deck PDF
```

Default store: `coo-ai/store/campaigns/<id>/`. Artifacts: `artifacts/`. Prompts: `prompts/`. Traces: `traces/events.ndjson`.

## Agent-fill loop (no API key)

1. `new --run` (or `resume`) until status is `awaiting_agent`.
2. Read `prompts/<stage>.md`. Write each required file into `artifacts/`.
3. `python -m coo resume <id>` so gates run.
4. If the gate fails, fix files from the updated prompt and resume again.
5. When status is `awaiting_human`, stop. Show the artifact. Wait. `--approve` only after the user agrees.

Human checkpoints: after **intake**, **strategy**, and **critique**.

New campaigns use `requirements_version: 3` and the six-stage lean pipeline: `intake → research → strategy → plan → deliver → critique`. The `plan` stage emits `plan.json` and `measurement.json`; `deliver` emits `proposal.md`, `slides.json`, and all campaign materials in `campaign_assets.json`. The plan includes structured ROPES, media/KOL tiering, event run of show, countdown, risks, and jurisdiction-specific compliance review; measurement links objectives to output/outtake/outcome KPIs with calibrated targets. Old stored records keep their original eight-stage graph and gate set.

On `agent_fill:research`, search the live web (or workspace `references/websites.md`) before writing `situation.md` and `evidence.json`. Do not cite the brief. Sourced items need APA fields: author, year, title, http `source_url`.
For new evidence-v2 runs, record when sources were checked, their geography and applicable period, and support material facts and numeric claims with traceable sources. Budgets must be built from quantities and low/base/high rates, include currency and pricing date, and cite public rates/client quotes or label reasoned assumptions. Leave unsupported prices unpriced and state which quote is needed. Include dated FX evidence when converting currencies; compare the high case against the cap.
New plans must use current `YYYY-MM` dates and mark elapsed work completed/in progress or rebaseline it. KPI targets need a sourced baseline or must be labeled provisional with a calibration method.

On `agent_fill:deliver`, emit `proposal.md`, `slides.json`, and (evidence-v2) `campaign_assets.json`. The CLI overwrites `## References` from evidence, renders `proposal.html`, then builds a native editable `proposal.pptx` from `slides.json`. Lean depth floors are 200 characters per numbered section and 1,400 words across the nine numbered sections (`COO_MIN_SECTION_CHARS`, `COO_MIN_PROPOSAL_WORDS`). Every tactic must name its owner, channel, timing, and budget-line cost link. Thin sections and summary-only tactics fail the gate.

Lean decks need 14-20 slides, one slide per tactic, at least one data or diagram slide per major section, and no more than two consecutive slides with the same composition variant. Use the HTML and PPTX renderers' variants (split, bleed, rail, offset, timeline, ruled table), a per-campaign `palette`, and `design.style` / `design.accent_mode`; `template_path` is ignored. Photos must be supplied or rights-cleared with source/usage metadata and descriptive alt text, stored under `assets/images/`. The PPTX is native and editable, with real text, shapes, tables, charts, and picture frames; it contains no speaker notes and no full-slide screenshots. Edit `slides.json` and re-render.

On `agent_fill:critique`, run the review as an independent reviewer: use a fresh subagent or a cold re-read and do not defend the draft. Do not score every criterion the same. Requirements-v3 campaigns need at least one substantive revision note (40+ characters) naming a defect and its fix; if you list notes, rewrite `proposal.md` and `slides.json` with real edits.

After the campaign is `complete`, render client deliverables with `python -m coo export <campaign-id>`. The CLI writes `artifacts/proposal.docx` and `artifacts/proposal.pdf` from `proposal.md`, and `artifacts/proposal.html`, `artifacts/proposal.pptx`, and `artifacts/proposal-deck.pdf` from `slides.json`. The HTML deck is a single self-contained file with inline CSS/JavaScript and embedded images. The PPTX is written directly with `python-pptx` as a native 16:9 editable deck; the deck PDF prints from the same HTML with headless Chrome/Edge and is checked for page count and non-empty pages. Set `COO_BROWSER` to an explicit executable if auto-detection fails. PowerPoint and LibreOffice are not part of the deck path. Do not hand-edit any output; re-export from `proposal.md` or `slides.json`.

## Plugin hosts and MCP tools

The `plugin/` bundle ships this same loop to Claude Code, Codex, Cursor, OpenCode, and DeepSeek Harness. MCP hosts expose `coo_new`, `coo_list`, `coo_status`, `coo_prompt`, `coo_artifact_write`, `coo_artifact_read`, `coo_artifact_list`, `coo_resume`, `coo_answer`, and `coo_export`. Use those tools when they are present; they call the same store, runner, and gates as the CLI. The OpenCode and DeepSeek Harness adapters call the same CLI directly.

Before using a plugin build, run `python -m coo doctor` and `python -m coo plugin validate`. Install a host copy with `python -m coo plugin install --host <claude|codex|cursor|opencode|dsh> --scope project`.

## Must not do

- Do not draft `proposal.md` (or other artifacts) as chat copy instead of files on disk.
- Do not skip a stage or a checkpoint.
- Do not use `--stub` for a live user demand.
- Do not set `human_override` except via `resume --override` after the user asks.

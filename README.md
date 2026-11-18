# COO AI

**A gated campaign-proposal orchestrator for coding agents.**

COO AI turns a one-line demand into a client-ready campaign proposal and deck. Six stages, typed artifacts, deterministic gates, and human checkpoints keep the work reviewable; one export command produces DOCX, PDF, an interactive HTML deck, an editable PowerPoint deck, and a deck PDF.

It runs with any coding agent out of the box (no API key), or with an OpenAI-compatible model if you configure one.

## Install

Requires Python 3.11+.

```bash
python -m pip install -e ".[dev]"
python -m coo doctor
```

`doctor` checks Python, the store, the stage skills, the plugin bundle, and model configuration. Only deck-PDF export needs Chrome, Chromium, or Edge; PowerPoint generation is native and needs no Office install.

## Quick start

```bash
python -m coo new --demand "Launch a 12-week brand campaign for Acme widgets." --run
```

With no model key, the CLI pauses at `awaiting_agent` and writes `prompts/<stage>.md`. The coding agent writes that stage's files into `artifacts/`, then you continue:

```bash
python -m coo resume <campaign-id>
```

Repeat at each pause. At a human checkpoint, review the artifact and approve it:

```bash
python -m coo resume <campaign-id> --approve
```

Chat is not a brief, and hand-written proposal files are not a campaign: the CLI reads `artifacts/` from disk and gates the result.

## Pipeline

| Stage | Writes |
| --- | --- |
| `intake` | `brief.json` |
| `research` | `situation.md`, `evidence.json` |
| `strategy` | `strategy.json` |
| `plan` | `plan.json`, `measurement.json` |
| `deliver` | `proposal.md`, `slides.json` |
| `critique` | `review.json`, revised `proposal.md` and `slides.json` |

Evidence-v2 campaigns (the default) also write `operations.json` during `plan` and `campaign_assets.json` during `deliver`.

Human checkpoints follow intake, strategy, and critique. A failed gate rewrites the stage prompt with the exact errors. Campaign state lives in `store/campaigns/<campaign-id>/` (`campaign.json`, `artifacts/`, `prompts/`, `notes/`, `traces/`); it is user data, not fixture data.

## Deliverables

`proposal.md` is the source of truth for DOCX/PDF; `slides.json` is the source of truth for the HTML deck, PowerPoint deck, and deck PDF. Edit the sources, then re-export — never hand-edit an output.

```bash
python -m coo export <campaign-id>              # proposal.docx + proposal.pdf
python -m coo export <campaign-id> --format all # DOCX, PDF, HTML, PPTX, deck PDF
python -m coo export <campaign-id> --format pptx
```

- `proposal.docx` / `proposal.pdf` — cover, contents, page numbers, styled tables, References.
- `proposal.html` — a single self-contained 1920×1080 deck; no build step, server, or external dependencies.
- `proposal.pptx` — native 16:9 OOXML: real text, shapes, tables, charts, and picture frames, fully editable in PowerPoint.
- `proposal-deck.pdf` — the HTML deck printed with headless Chrome/Edge.

Deliverables carry no speaker notes, generator metadata, or tool attribution. Internal `notes` stay in `slides.json`.

## Plugin hosts

`plugin/` is a portable bundle for Claude Code, Codex, Cursor, OpenCode, and DeepSeek Harness. Every action calls the installed runtime or its MCP server, so stage order and gates stay in Python.

```bash
python -m coo plugin install --host codex --scope project
python -m coo plugin install --host all  --scope project
python -m coo plugin validate
```

The MCP server is `python -m coo mcp` (newline-delimited JSON-RPC over stdio). It exposes `coo_new`, `coo_list`, `coo_status`, `coo_prompt`, `coo_artifact_list`, `coo_artifact_read`, `coo_artifact_write`, `coo_resume`, `coo_answer`, and `coo_export`.

See [plugin/README.md](plugin/README.md) for per-host activation and MCP details.

## Commands

| Command | Purpose |
| --- | --- |
| `coo new --demand "..." --run` | Create a campaign and advance to the first pause |
| `coo status <id>` | Show stage status and the next action |
| `coo prompt <id>` | Print the pending agent-fill prompt |
| `coo resume <id> [--approve\|--override]` | Continue, approve a checkpoint, or override a critique |
| `coo answer <id> --question q_budget --text "..."` | Answer or defer an intake question |
| `coo export <id> --format all` | Render every deliverable |
| `coo artifact read\|write <id> <name>` | Read or write a campaign artifact |
| `coo doctor` | Check the environment |
| `coo plugin validate\|sync\|install` | Manage the plugin bundle |
| `coo mcp` | Run the MCP stdio server |

`--store DIR` and `--stub` are top-level flags, before the subcommand. `--stub` is a deterministic test fixture, not a real campaign.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `COO_STORE_DIR` | `coo-ai/store/campaigns` | Campaign workspace root |
| `COO_LLM_API_KEY` | unset | Enables the external LLM; unset means agent-fill |
| `COO_LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible endpoint |
| `COO_LLM_MODEL` | `gpt-4o-mini` | Model for external runs |
| `COO_RUBRIC_THRESHOLD` | `3.5` | Critique pass threshold |
| `COO_BROWSER` | auto-detect | Chrome/Edge executable for deck PDF |

## Layout

```
coo/            Python package: schemas, store, gates, orchestrator, export, CLI, MCP
skills/         stage playbooks loaded by the orchestrator (not agent skills)
agent-pack/     canonical conductor skill, copied to agent hosts
plugin/         shareable bundle: manifests, commands, adapters, MCP config
templates/      proposal outline
schemas/        JSON Schema exports of the Pydantic contracts
tests/          offline pytest suite
store/          campaign workspace, created at runtime
```

## Development

```bash
python -m pytest
python -m coo plugin validate
```

Tests run offline against the stub client. Refresh generated files after changing their sources:

```bash
python -m coo.schemas.export      # schemas/*.json
python -m coo.agent_install       # .agents/skills/ and .claude/skills/
python -m coo plugin sync         # plugin/skills/coo-ai/SKILL.md
```

`REQUIREMENTS_AUDIT.md` maps the source checklist to implemented gates.

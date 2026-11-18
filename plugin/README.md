# COO AI plugin bundle

One plugin, five hosts. The bundle carries host manifests, the conductor skill, commands, and thin adapters. Every action calls the installed COO AI runtime or its MCP server; stage order and gates stay in the Python orchestrator.

```
plugin/
  plugin.json              Agent Plugins 1.0.0 manifest (Codex, Cursor)
  mcp.json                 portable MCP server definition
  .mcp.json                Claude Code MCP definition
  skills/coo-ai/SKILL.md   conductor skill (synced from agent-pack)
  commands/coo.md          /coo command
  .claude-plugin/          Claude Code manifest
  .codex-plugin/           Codex compatibility manifest
  .cursor-plugin/          Cursor manifest
  hosts/opencode/          OpenCode server plugin (TypeScript)
  hosts/dsh/               DeepSeek Harness Cordis plugin (JavaScript)
```

## Prerequisite

The plugin is a shell. Install the runtime once:

```
cd coo-ai
python -m pip install -e ".[dev]"
python -m coo doctor
python -m coo plugin validate
```

`coo doctor` checks Python, the store, stage skills, the plugin bundle, and whether a model key is configured. Without a key the orchestrator uses agent-fill: it pauses at `awaiting_agent` and the host writes artifacts from the prompt.

## Install per host

```
python -m coo plugin install --host claude   --scope project
python -m coo plugin install --host codex    --scope project
python -m coo plugin install --host cursor   --scope project
python -m coo plugin install --host opencode --scope project
python -m coo plugin install --host dsh      --scope project
```

Add `--scope user` for a user-level copy, `--dest DIR` for an explicit location, or `--force` to replace a non-COO directory.

- **Claude Code** reads `.claude-plugin/plugin.json`, `skills/`, `commands/`, and `.mcp.json`. The repo root also carries a marketplace at `.claude-plugin/marketplace.json`; add it with `claude plugin marketplace add <path-to-coo-ai>` then `claude plugin install coo-ai@coo-ai`. A local copy can be loaded directly with `claude --plugin-dir <dest>`. The command is namespaced as `/coo-ai:coo`.
- **Codex** reads the Agent Plugins `plugin.json` and `.codex-plugin/plugin.json`, plus `skills/` and `.mcp.json`.
- **Cursor** reads the Agent Plugins `plugin.json` and `.cursor-plugin/plugin.json`, plus `skills/`, `commands/`, and `mcp.json`.
- **OpenCode** auto-loads the installed `.opencode/plugins/coo-ai/index.ts`; the adapter registers the `coo_*` tools, the `/coo` command, and the skill.
- **DeepSeek Harness** installs the Cordis bundle from `hosts/dsh/`; the adapter registers the same tools through `ctx.tools.register`.

## MCP tools

`python -m coo mcp` speaks newline-delimited JSON-RPC over stdio. It exposes:

`coo_new`, `coo_list`, `coo_status`, `coo_prompt`, `coo_artifact_list`, `coo_artifact_read`, `coo_artifact_write`, `coo_resume`, `coo_answer`, `coo_export`.

The MCP server is the common runtime for Claude Code, Codex, Cursor, and any other MCP host. OpenCode and DeepSeek Harness call the CLI directly through their adapters.

`coo_export` accepts `format: "both"` (DOCX+PDF), `"all"` (DOCX, PDF, HTML, PPTX, deck PDF), or one of `docx`, `pdf`, `html`, `pptx`, `deck-pdf`. The HTML deck is a self-contained interactive file; the PPTX is a native 16:9 editable deck rendered directly from `slides.json`; the deck PDF prints the HTML with headless Chrome/Edge. Set `COO_BROWSER` to an explicit executable if auto-detection fails. PowerPoint and LibreOffice are not part of the deck path.

## Keeping the skill in sync

The skill copy is generated. Edit `agent-pack/coo-ai/SKILL.md`, then:

```
python -m coo plugin sync
python -m coo plugin validate
```

`coo plugin validate` fails if the bundle's skill copy drifts from the source. It also checks the closed Agent Plugins manifest fields, MCP command, host manifests, adapter files, and marketplace entries.

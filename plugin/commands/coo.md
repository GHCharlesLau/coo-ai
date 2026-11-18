---
description: Start, resume, or review a COO AI campaign proposal
argument-hint: [demand or campaign id]
---

Drive this request with the COO AI orchestrator. Do not draft the proposal in chat.

Use the text the user supplied with this command:

- If the argument is a campaign id (`cmp-YYYYMMDD-xxxxxxxx`), call `coo_status` for it.
- If the argument is a demand, call `coo_new` with that demand and `run: true`.
- If there is no argument, ask for the demand before creating anything.
- When the status is `awaiting_agent`, call `coo_prompt`, write each required file with `coo_artifact_write`, then call `coo_resume`.
- When the status is `awaiting_human`, show the named artifact and stop. Call `coo_resume` with `approve: true` only after the user agrees.
- When the campaign is complete, call `coo_export` for `proposal.docx`, `proposal.pdf`, `proposal.html`, `proposal.pptx`, and `proposal-deck.pdf`. Use `format: "all"` for every deliverable, or `format: "html"` / `"pptx"` / `"deck-pdf"` for one.

If the MCP tools are unavailable, run the same commands through `coo` in the shell. Never skip a checkpoint and never use `--stub` for a real demand.

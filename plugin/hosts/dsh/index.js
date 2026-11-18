import { execFile } from "node:child_process"
import { defineTool } from "@deepseek-ai/dsh-tools"

export const name = "coo-ai"
export const inject = ["tools"]

const CONFIGURED = (process.env.COO_BIN || "").trim()
const BIN = CONFIGURED || process.env.COO_PYTHON || "python"
const PREFIX = CONFIGURED ? [] : ["-m", "coo"]
const STORE = process.env.COO_STORE_DIR

function run(args, stdin) {
  return new Promise((resolve, reject) => {
    const argv = [...PREFIX, ...(STORE ? ["--store", STORE] : []), ...args]
    const child = execFile(
      BIN,
      argv,
      {
        encoding: "utf8",
        windowsHide: true,
        maxBuffer: 16 * 1024 * 1024,
        env: { ...process.env, PYTHONIOENCODING: "utf-8" },
      },
      (error, stdout, stderr) => {
        const output = [stdout, stderr].filter(Boolean).join("\n").trim()
        if (error) reject(new Error(output || error.message))
        else resolve(output || "(no output)")
      },
    )
    child.stdin?.end(stdin ?? "")
  })
}

function required(args, key) {
  const value = args[key]
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`Missing required argument: ${key}`)
  }
  return value
}

function tool(toolName, description, parameters, execute) {
  return defineTool({
    name: toolName,
    description,
    parameters,
    output: {
      schema: { type: "string" },
      render: (_args, value) => [{ type: "text", text: String(value) }],
    },
    execute,
  })
}

export function apply(ctx) {
  ctx.tools.register(
    tool(
      "coo_new",
      "Create a campaign from the user's demand and advance it to the first pause. Set run=false to create only.",
      {
        demand: { type: "string", required: true, description: "The client's demand in their own words." },
        run: { type: "boolean", required: false, description: "Advance immediately (default true)." },
        revision_of: { type: "string", required: false, description: "Parent campaign id for a revision." },
      },
      async (args) => {
        const argv = ["new", "--demand", required(args, "demand")]
        if (args.run !== false) argv.push("--run")
        if (typeof args.revision_of === "string" && args.revision_of) {
          argv.push("--revision-of", args.revision_of)
        }
        return run(argv)
      },
    ),
  )

  ctx.tools.register(
    tool("coo_list", "List stored campaigns with status and current stage.", {}, async () => run(["list"])),
  )

  ctx.tools.register(
    tool(
      "coo_status",
      "Show pipeline status, pause reason, open questions, and the exact next action.",
      { campaign_id: { type: "string", required: true, description: "Campaign id." } },
      async (args) => run(["status", required(args, "campaign_id")]),
    ),
  )

  ctx.tools.register(
    tool(
      "coo_prompt",
      "Return the agent-fill prompt for the current stage or a named stage.",
      {
        campaign_id: { type: "string", required: true, description: "Campaign id." },
        stage: { type: "string", required: false, description: "Optional stage name." },
      },
      async (args) => {
        const argv = ["prompt", required(args, "campaign_id")]
        if (typeof args.stage === "string" && args.stage) argv.push("--stage", args.stage)
        return run(argv)
      },
    ),
  )

  ctx.tools.register(
    tool(
      "coo_resume",
      "Continue the campaign through the gates. Set approve=true only after the user approves a checkpoint.",
      {
        campaign_id: { type: "string", required: true, description: "Campaign id." },
        approve: { type: "boolean", required: false, description: "Approve the pending checkpoint." },
        override: { type: "boolean", required: false, description: "Override a failed critique rubric." },
      },
      async (args) => {
        const argv = ["resume", required(args, "campaign_id")]
        if (args.approve === true) argv.push("--approve")
        if (args.override === true) argv.push("--override")
        return run(argv)
      },
    ),
  )

  ctx.tools.register(
    tool(
      "coo_answer",
      "Answer or defer one intake question in brief.json.",
      {
        campaign_id: { type: "string", required: true, description: "Campaign id." },
        question_id: { type: "string", required: true, description: "Question id such as q_budget." },
        text: { type: "string", required: false, description: "Answer text." },
        defer_reason: { type: "string", required: false, description: "Reason to defer." },
      },
      async (args) => {
        const argv = ["answer", required(args, "campaign_id"), "--question", required(args, "question_id")]
        if (typeof args.text === "string" && args.text) argv.push("--text", args.text)
        else if (typeof args.defer_reason === "string" && args.defer_reason) {
          argv.push("--defer-reason", args.defer_reason)
        } else {
          throw new Error("Provide text or defer_reason.")
        }
        return run(argv)
      },
    ),
  )

  ctx.tools.register(
    tool(
      "coo_artifact_list",
      "List files in a campaign's artifacts directory.",
      { campaign_id: { type: "string", required: true, description: "Campaign id." } },
      async (args) => run(["artifact", "list", required(args, "campaign_id")]),
    ),
  )

  ctx.tools.register(
    tool(
      "coo_artifact_read",
      "Read one UTF-8 artifact from a campaign, such as brief.json or proposal.md.",
      {
        campaign_id: { type: "string", required: true, description: "Campaign id." },
        name: { type: "string", required: true, description: "Artifact filename inside artifacts/." },
      },
      async (args) =>
        run(["artifact", "read", required(args, "campaign_id"), required(args, "name")]),
    ),
  )

  ctx.tools.register(
    tool(
      "coo_artifact_write",
      "Write one artifact into a campaign's artifacts directory.",
      {
        campaign_id: { type: "string", required: true, description: "Campaign id." },
        name: { type: "string", required: true, description: "Artifact filename inside artifacts/." },
        content: { type: "string", required: true, description: "Full file content." },
      },
      async (args) =>
        run(
          ["artifact", "write", required(args, "campaign_id"), required(args, "name"), "--stdin"],
          required(args, "content"),
        ),
    ),
  )

  ctx.tools.register(
    tool(
      "coo_export",
      "Render proposal docs and campaign deck deliverables for a completed campaign.",
      {
        campaign_id: { type: "string", required: true, description: "Campaign id." },
        format: {
          type: "string",
          required: false,
          description: "both (DOCX+PDF, default), all (every deliverable), docx, pdf, html, pptx, or deck-pdf.",
        },
      },
      async (args) => {
        const argv = ["export", required(args, "campaign_id")]
        if (typeof args.format === "string" && args.format) argv.push("--format", args.format)
        return run(argv)
      },
    ),
  )
}

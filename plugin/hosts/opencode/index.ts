import { Plugin, Skill } from "@opencode/plugin"
import { execFile } from "node:child_process"
import { access, readFile } from "node:fs/promises"
import { fileURLToPath } from "node:url"

type Options = {
  command?: string
  store?: string
}

type Runner = {
  bin: string
  prefix: string[]
}

type ToolInput = Record<string, unknown>

const SKILL_DESCRIPTION =
  "Constructs a campaign proposal through COO AI: gated intake, research, strategy, plan, measurement, draft, slides, critique, and export. Use for campaign proposals, marketing campaigns, PR campaigns, brand campaigns, campaign briefs, or advancing a COO AI campaign."

function required(input: ToolInput, key: string): string {
  const value = input[key]
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`Missing required argument: ${key}`)
  }
  return value
}

function makeRunner(runner: Runner, store?: string) {
  return (args: string[], stdin?: string): Promise<string> =>
    new Promise((resolve, reject) => {
      const argv = [...runner.prefix, ...(store ? ["--store", store] : []), ...args]
      const child = execFile(
        runner.bin,
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

async function findSkill(): Promise<URL | undefined> {
  const candidates = [
    new URL("./skills/coo-ai/SKILL.md", import.meta.url),
    new URL("../../skills/coo-ai/SKILL.md", import.meta.url),
  ]
  for (const candidate of candidates) {
    try {
      await access(candidate)
      return candidate
    } catch {
      // try the next layout
    }
  }
  return undefined
}

export default Plugin.define({
  id: "coo-ai",
  async setup(ctx) {
    const options = (ctx.options ?? {}) as Options
    const configured = (options.command || process.env.COO_BIN || "").trim()
    const runner: Runner = configured
      ? { bin: configured, prefix: [] }
      : { bin: process.env.COO_PYTHON || "python", prefix: ["-m", "coo"] }
    const store = options.store || process.env.COO_STORE_DIR
    const run = makeRunner(runner, store)

    await ctx.tool.transform((editor) => {
      editor.namespace({ name: "coo", description: "COO AI campaign proposals" })

      editor.add({
        name: "new",
        description:
          "Create a campaign from the user's demand and advance it to the first pause. Set run=false to create only.",
        input: {
          type: "object",
          properties: {
            demand: { type: "string", description: "The client's demand in their own words." },
            run: { type: "boolean", description: "Advance immediately (default true)." },
            revision_of: { type: "string", description: "Parent campaign id for a revision." },
          },
          required: ["demand"],
          additionalProperties: false,
        },
        execute: async (input: ToolInput) => {
          const args = ["new", "--demand", required(input, "demand")]
          if (input.run !== false) args.push("--run")
          if (typeof input.revision_of === "string" && input.revision_of) {
            args.push("--revision-of", input.revision_of)
          }
          return { content: await run(args) }
        },
      })

      editor.add({
        name: "list",
        description: "List stored campaigns with status and current stage.",
        input: { type: "object", properties: {}, additionalProperties: false },
        execute: async () => ({ content: await run(["list"]) }),
      })

      editor.add({
        name: "status",
        description: "Show pipeline status, pause reason, open questions, and the exact next action.",
        input: {
          type: "object",
          properties: { campaign_id: { type: "string", description: "Campaign id." } },
          required: ["campaign_id"],
          additionalProperties: false,
        },
        execute: async (input: ToolInput) => ({ content: await run(["status", required(input, "campaign_id")]) }),
      })

      editor.add({
        name: "prompt",
        description: "Return the agent-fill prompt for the current stage or a named stage.",
        input: {
          type: "object",
          properties: {
            campaign_id: { type: "string", description: "Campaign id." },
            stage: { type: "string", description: "Optional stage name." },
          },
          required: ["campaign_id"],
          additionalProperties: false,
        },
        execute: async (input: ToolInput) => {
          const args = ["prompt", required(input, "campaign_id")]
          if (typeof input.stage === "string" && input.stage) args.push("--stage", input.stage)
          return { content: await run(args) }
        },
      })

      editor.add({
        name: "resume",
        description:
          "Continue the campaign through the gates. Set approve=true only after the user approves a checkpoint.",
        input: {
          type: "object",
          properties: {
            campaign_id: { type: "string", description: "Campaign id." },
            approve: { type: "boolean", description: "Approve the pending human checkpoint." },
            override: { type: "boolean", description: "Human-override a failed critique rubric." },
          },
          required: ["campaign_id"],
          additionalProperties: false,
        },
        execute: async (input: ToolInput) => {
          const args = ["resume", required(input, "campaign_id")]
          if (input.approve === true) args.push("--approve")
          if (input.override === true) args.push("--override")
          return { content: await run(args) }
        },
      })

      editor.add({
        name: "answer",
        description: "Answer or defer one intake question in brief.json.",
        input: {
          type: "object",
          properties: {
            campaign_id: { type: "string", description: "Campaign id." },
            question_id: { type: "string", description: "Question id such as q_budget." },
            text: { type: "string", description: "Answer text." },
            defer_reason: { type: "string", description: "Reason to defer." },
          },
          required: ["campaign_id", "question_id"],
          additionalProperties: false,
        },
        execute: async (input: ToolInput) => {
          const args = ["answer", required(input, "campaign_id"), "--question", required(input, "question_id")]
          if (typeof input.text === "string" && input.text) args.push("--text", input.text)
          else if (typeof input.defer_reason === "string" && input.defer_reason) {
            args.push("--defer-reason", input.defer_reason)
          } else {
            throw new Error("Provide text or defer_reason.")
          }
          return { content: await run(args) }
        },
      })

      editor.add({
        name: "artifact_list",
        description: "List files in a campaign's artifacts directory.",
        input: {
          type: "object",
          properties: { campaign_id: { type: "string", description: "Campaign id." } },
          required: ["campaign_id"],
          additionalProperties: false,
        },
        execute: async (input: ToolInput) => ({
          content: await run(["artifact", "list", required(input, "campaign_id")]),
        }),
      })

      editor.add({
        name: "artifact_read",
        description: "Read one UTF-8 artifact from a campaign, such as brief.json or proposal.md.",
        input: {
          type: "object",
          properties: {
            campaign_id: { type: "string", description: "Campaign id." },
            name: { type: "string", description: "Artifact filename inside artifacts/." },
          },
          required: ["campaign_id", "name"],
          additionalProperties: false,
        },
        execute: async (input: ToolInput) => ({
          content: await run([
            "artifact",
            "read",
            required(input, "campaign_id"),
            required(input, "name"),
          ]),
        }),
      })

      editor.add({
        name: "artifact_write",
        description: "Write one artifact into a campaign's artifacts directory.",
        input: {
          type: "object",
          properties: {
            campaign_id: { type: "string", description: "Campaign id." },
            name: { type: "string", description: "Artifact filename inside artifacts/." },
            content: { type: "string", description: "Full file content." },
          },
          required: ["campaign_id", "name", "content"],
          additionalProperties: false,
        },
        execute: async (input: ToolInput) => {
          const args = [
            "artifact",
            "write",
            required(input, "campaign_id"),
            required(input, "name"),
            "--stdin",
          ]
          return { content: await run(args, required(input, "content")) }
        },
      })

      editor.add({
        name: "export",
        description: "Render proposal docs and campaign deck deliverables for a completed campaign.",
        input: {
          type: "object",
          properties: {
            campaign_id: { type: "string", description: "Campaign id." },
            format: {
              type: "string",
              enum: ["both", "all", "docx", "pdf", "html", "pptx", "deck-pdf"],
              description: "both=DOCX+PDF (default), all=every deliverable, or one named format.",
            },
          },
          required: ["campaign_id"],
          additionalProperties: false,
        },
        execute: async (input: ToolInput) => {
          const args = ["export", required(input, "campaign_id")]
          if (typeof input.format === "string" && input.format) args.push("--format", input.format)
          return { content: await run(args) }
        },
      })
    })

    await ctx.command.transform((editor) => {
      editor.add({
        name: "coo",
        description: "Start, resume, or review a COO AI campaign proposal",
        execute: async ({ sessionID, prompt, delivery }) => {
          const demand = prompt.text.trim()
          const text = demand
            ? `Use the coo_new tool with this demand, then follow the COO AI loop: coo_prompt, coo_artifact_write, coo_resume. Stop at awaiting_human and ask before approving.\n\nDemand:\n${demand}`
            : "Ask the user for the campaign demand. Then use the COO AI tools to run it."
          await ctx.session.prompt({ ...prompt, sessionID, text, delivery })
        },
      })
    })

    const skill = await findSkill()
    if (skill) {
      const content = await readFile(skill, "utf8")
      await ctx.skill.transform((editor) => {
        editor.add({
          id: Skill.ID.make("coo-ai"),
          name: Skill.Name.make("coo-ai"),
          description: SKILL_DESCRIPTION,
          path: Skill.Info.fields.path.make(fileURLToPath(skill)),
          content,
        })
      })
    }
  },
})

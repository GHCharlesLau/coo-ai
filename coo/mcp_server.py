"""MCP stdio server: expose the COO AI orchestrator to any MCP-capable host.

The server is a thin protocol shell over the same store, runner, gates, and export
code the CLI uses. It never decides stage order or bypasses a gate.
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import sys
import traceback
from typing import Any, Callable

from coo import __version__
from coo.campaign_ops import answer_question, format_status
from coo.config import Settings, load_settings
from coo.export import EXPORT_FORMATS, export_campaign
from coo.llm import LLMClient, build_client
from coo.orchestrator.graph import stages_for
from coo.orchestrator.runner import advance
from coo.store import CampaignStore

SERVER_NAME = "coo-ai"
# Newest first. The client's requested revision is echoed when supported.
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
LATEST_PROTOCOL = PROTOCOL_VERSIONS[0]

INSTRUCTIONS = """Drive campaign proposals with the COO AI orchestrator.

Start with coo_new, then read coo_prompt. In agent-fill mode the orchestrator
pauses at awaiting_agent: write every required file with coo_artifact_write, then
call coo_resume so the deterministic gates run. If a gate fails, re-read
coo_prompt and fix the named files. Stop at awaiting_human: show the artifact and
ask the user before calling coo_resume with approve=true. Never paste a finished
proposal into chat, never skip a checkpoint, and never use stub mode for a real
demand.
"""


def _schema(properties: dict[str, dict[str, Any]], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


CAMPAIGN_ID = {"type": "string", "description": "Campaign id, for example cmp-20260101-abcd1234."}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "coo_new",
        "description": (
            "Create a campaign from the user's demand and advance it to the first pause. "
            "Use run=false to create without advancing."
        ),
        "inputSchema": _schema(
            {
                "demand": {"type": "string", "description": "The client's demand in their own words."},
                "run": {"type": "boolean", "description": "Advance immediately (default true)."},
                "revision_of": {"type": "string", "description": "Parent campaign id for a revision."},
            }
        ),
    },
    {
        "name": "coo_list",
        "description": "List stored campaigns with status and current stage.",
        "inputSchema": _schema({}),
    },
    {
        "name": "coo_status",
        "description": "Show pipeline status, pause reason, open questions, and the exact next action.",
        "inputSchema": _schema({"campaign_id": CAMPAIGN_ID}, ["campaign_id"]),
    },
    {
        "name": "coo_prompt",
        "description": "Return the agent-fill prompt for the current stage (or a named stage).",
        "inputSchema": _schema(
            {
                "campaign_id": CAMPAIGN_ID,
                "stage": {"type": "string", "description": "Optional stage name; defaults to the current stage."},
            },
            ["campaign_id"],
        ),
    },
    {
        "name": "coo_resume",
        "description": (
            "Continue the campaign. Runs gates and pauses at the next human checkpoint or agent fill. "
            "Set approve=true only after the user has approved the checkpoint."
        ),
        "inputSchema": _schema(
            {
                "campaign_id": CAMPAIGN_ID,
                "approve": {"type": "boolean", "description": "Approve the pending human checkpoint."},
                "override": {"type": "boolean", "description": "Human-override a failed critique rubric."},
            },
            ["campaign_id"],
        ),
    },
    {
        "name": "coo_answer",
        "description": "Answer or defer one intake question in brief.json.",
        "inputSchema": _schema(
            {
                "campaign_id": CAMPAIGN_ID,
                "question_id": {"type": "string", "description": "Question id such as q_budget."},
                "text": {"type": "string", "description": "Answer text."},
                "defer_reason": {"type": "string", "description": "Reason to defer instead of answering."},
            },
            ["campaign_id", "question_id"],
        ),
    },
    {
        "name": "coo_artifact_list",
        "description": "List files in a campaign's artifacts directory.",
        "inputSchema": _schema({"campaign_id": CAMPAIGN_ID}, ["campaign_id"]),
    },
    {
        "name": "coo_artifact_read",
        "description": "Read a UTF-8 artifact from a campaign, such as brief.json or proposal.md.",
        "inputSchema": _schema(
            {
                "campaign_id": CAMPAIGN_ID,
                "name": {"type": "string", "description": "Artifact filename inside artifacts/."},
            },
            ["campaign_id", "name"],
        ),
    },
    {
        "name": "coo_artifact_write",
        "description": (
            "Write one artifact into a campaign's artifacts directory. Use this in agent-fill mode "
            "for every file the prompt requires."
        ),
        "inputSchema": _schema(
            {
                "campaign_id": CAMPAIGN_ID,
                "name": {"type": "string", "description": "Artifact filename inside artifacts/."},
                "content": {"type": "string", "description": "Full file content."},
            },
            ["campaign_id", "name", "content"],
        ),
    },
    {
        "name": "coo_export",
        "description": "Render proposal.docx, proposal.pdf, proposal.html, proposal.pptx, and/or proposal-deck.pdf.",
        "inputSchema": _schema(
            {
                "campaign_id": CAMPAIGN_ID,
                "format": {
                    "type": "string",
                    "enum": ["both", "all", "docx", "pdf", "html", "pptx", "deck-pdf"],
                    "description": "both=DOCX+PDF (default), all=every deliverable, or one named format.",
                },
            },
            ["campaign_id"],
        ),
    },
]


def _text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _ok(text: str, structured: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"content": [_text_block(text)], "isError": False}
    if structured is not None:
        result["structuredContent"] = structured
    return result


def _error(text: str) -> dict[str, Any]:
    return {"content": [_text_block(text)], "isError": True}


def _meta_payload(meta, store: CampaignStore) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "campaign_id": meta.id,
        "status": meta.status,
        "stage": meta.current_stage,
        "pause_reason": meta.pause_reason,
        "revision_of": meta.revision_of,
        "model": meta.model,
    }
    if meta.status == "awaiting_agent":
        payload["prompt_path"] = str(store.prompt_path(meta.id, meta.current_stage))
    return payload


class CooMCPServer:
    """One JSON-RPC request handler over an explicit store and settings."""

    def __init__(self, store: CampaignStore, settings: Settings, llm: LLMClient) -> None:
        self.store = store
        self.settings = settings
        self.llm = llm
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "coo_new": self._new,
            "coo_list": self._list,
            "coo_status": self._status,
            "coo_prompt": self._prompt,
            "coo_resume": self._resume,
            "coo_answer": self._answer,
            "coo_artifact_list": self._artifact_list,
            "coo_artifact_read": self._artifact_read,
            "coo_artifact_write": self._artifact_write,
            "coo_export": self._export,
        }

    # -- protocol ---------------------------------------------------------

    def handle(self, request: Any) -> dict[str, Any] | None:
        if not isinstance(request, dict):
            return self._rpc_error(None, -32600, "Invalid Request")
        method = request.get("method")
        request_id = request.get("id")
        is_notification = "id" not in request
        params = request.get("params") or {}
        if not isinstance(params, dict):
            return None if is_notification else self._rpc_error(request_id, -32602, "params must be an object")

        if method == "initialize":
            result = self._initialize(params)
        elif method in {"notifications/initialized", "notifications/cancelled"}:
            return None
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            result = self._tools_call(params)
        else:
            return None if is_notification else self._rpc_error(request_id, -32601, f"Method not found: {method}")

        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        version = requested if requested in PROTOCOL_VERSIONS else LATEST_PROTOCOL
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": __version__},
            "instructions": INSTRUCTIONS,
        }

    @staticmethod
    def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    def _tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        handler = self._handlers.get(name) if isinstance(name, str) else None
        if handler is None:
            return _error(f"Unknown tool: {name}")
        if not isinstance(arguments, dict):
            return _error("Tool arguments must be an object.")
        try:
            # A stray print in a library must not corrupt the protocol stream.
            with contextlib.redirect_stdout(io.StringIO()):
                return handler(arguments)
        except (FileNotFoundError, ValueError, KeyError, RuntimeError) as exc:
            return _error(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            traceback.print_exc(file=sys.stderr)
            return _error(f"{type(exc).__name__}: {exc}")

    # -- tools ------------------------------------------------------------

    def _require(self, args: dict[str, Any], key: str) -> str:
        value = args.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing required argument: {key}")
        return value

    def _new(self, args: dict[str, Any]) -> dict[str, Any]:
        demand = args.get("demand") or ""
        revision_of = args.get("revision_of")
        if not isinstance(demand, str):
            raise ValueError("demand must be a string")
        if not demand.strip() and not revision_of:
            raise ValueError("Provide demand or revision_of.")
        if self.settings.stub:
            model = "stub"
        elif self.settings.agent_fill:
            model = "coding-agent"
        else:
            model = self.settings.model
        meta = self.store.create(
            demand,
            stub=self.settings.stub,
            model=model,
            revision_of=revision_of if isinstance(revision_of, str) else None,
        )
        message = f"Created {meta.id}."
        if args.get("run", True):
            result = advance(self.store, meta.id, self.llm, self.settings)
            message = result.message
        meta = self.store.load_meta(meta.id)
        text = format_status(meta, self.store)
        return _ok(f"{message}\n{text}" if message else text, _meta_payload(meta, self.store))

    def _list(self, args: dict[str, Any]) -> dict[str, Any]:
        del args
        campaigns = self.store.list_campaigns()
        if not campaigns:
            return _ok("No campaigns.", {"campaigns": []})
        rows = [
            {
                "campaign_id": meta.id,
                "status": meta.status,
                "stage": meta.current_stage,
                "pause_reason": meta.pause_reason,
            }
            for meta in campaigns
        ]
        text = "\n".join(f"{row['campaign_id']}\t{row['status']}\t{row['stage']}" for row in rows)
        return _ok(text, {"campaigns": rows})

    def _status(self, args: dict[str, Any]) -> dict[str, Any]:
        campaign_id = self._require(args, "campaign_id")
        meta = self.store.load_meta(campaign_id)
        return _ok(format_status(meta, self.store), _meta_payload(meta, self.store))

    def _prompt(self, args: dict[str, Any]) -> dict[str, Any]:
        campaign_id = self._require(args, "campaign_id")
        meta = self.store.load_meta(campaign_id)
        stage = args.get("stage") or meta.current_stage
        known_stages = stages_for(meta)
        if stage not in known_stages:
            raise ValueError(f"Unknown stage {stage!r}. Known: {', '.join(known_stages)}")
        content = self.store.read_prompt(campaign_id, stage)
        return _ok(content, {"campaign_id": campaign_id, "stage": stage, "prompt": content})

    def _resume(self, args: dict[str, Any]) -> dict[str, Any]:
        campaign_id = self._require(args, "campaign_id")
        result = advance(
            self.store,
            campaign_id,
            self.llm,
            self.settings,
            approve=bool(args.get("approve", False)),
            human_override=bool(args.get("override", False)),
        )
        meta = self.store.load_meta(campaign_id)
        text = format_status(meta, self.store)
        if result.message:
            text = f"{result.message}\n{text}"
        if result.gate_errors:
            text += "Gate errors:\n" + "\n".join(f"  - {err}" for err in result.gate_errors) + "\n"
        payload = _meta_payload(meta, self.store)
        payload["message"] = result.message
        payload["gate_errors"] = list(result.gate_errors)
        return _ok(text, payload)

    def _answer(self, args: dict[str, Any]) -> dict[str, Any]:
        campaign_id = self._require(args, "campaign_id")
        question_id = self._require(args, "question_id")
        text = args.get("text")
        defer_reason = args.get("defer_reason")
        brief = answer_question(
            self.store,
            campaign_id,
            question_id,
            text=text if isinstance(text, str) else None,
            defer_reason=defer_reason if isinstance(defer_reason, str) else None,
        )
        self.store.append_user_notes(
            campaign_id,
            f"Answered {question_id}: text={text!r} defer={defer_reason!r}",
        )
        remaining = [q.id for q in brief.open_questions if q.status == "unanswered"]
        message = f"Updated {question_id}. Remaining unanswered: {', '.join(remaining) or '(none)'}"
        return _ok(message, {"campaign_id": campaign_id, "remaining": remaining})

    def _artifact_list(self, args: dict[str, Any]) -> dict[str, Any]:
        campaign_id = self._require(args, "campaign_id")
        root = self.store.artifacts_dir(campaign_id)
        if not root.is_dir():
            raise FileNotFoundError(f"Campaign not found: {campaign_id}")
        files = sorted(path for path in root.rglob("*") if path.is_file())
        rows = [
            {"name": path.relative_to(root).as_posix(), "bytes": path.stat().st_size}
            for path in files
        ]
        if not rows:
            return _ok("No artifacts.", {"campaign_id": campaign_id, "artifacts": []})
        text = "\n".join(f"{row['name']}\t{row['bytes']}" for row in rows)
        return _ok(text, {"campaign_id": campaign_id, "artifacts": rows})

    def _artifact_read(self, args: dict[str, Any]) -> dict[str, Any]:
        campaign_id = self._require(args, "campaign_id")
        name = self._require(args, "name")
        path = self.store.artifact_path(campaign_id, name)
        if not path.is_file():
            raise FileNotFoundError(f"Missing artifact {name} for {campaign_id}")
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            data = path.read_bytes()
            encoded = base64.b64encode(data).decode("ascii")
            return _ok(
                f"{name} is binary ({len(data)} bytes). Base64 follows.\n{encoded}",
                {"campaign_id": campaign_id, "name": name, "encoding": "base64", "content": encoded},
            )
        return _ok(content, {"campaign_id": campaign_id, "name": name, "encoding": "utf-8", "content": content})

    def _artifact_write(self, args: dict[str, Any]) -> dict[str, Any]:
        campaign_id = self._require(args, "campaign_id")
        name = self._require(args, "name")
        content = args.get("content")
        if not isinstance(content, str):
            raise ValueError("content must be a string")
        if len(content.encode("utf-8")) > 8 * 1024 * 1024:
            raise ValueError("content exceeds the 8 MB artifact limit")
        path = self.store.write_artifact(campaign_id, name, content)
        return _ok(
            f"Wrote {path} ({path.stat().st_size} bytes).",
            {"campaign_id": campaign_id, "name": name, "path": str(path), "bytes": path.stat().st_size},
        )

    def _export(self, args: dict[str, Any]) -> dict[str, Any]:
        campaign_id = self._require(args, "campaign_id")
        fmt = args.get("format") or "both"
        if fmt not in {"both", "all", *EXPORT_FORMATS}:
            raise ValueError(f"Unsupported format: {fmt}")
        if fmt == "both":
            formats = ("docx", "pdf")
        elif fmt == "all":
            formats = EXPORT_FORMATS
        else:
            formats = (fmt,)
        outputs = export_campaign(self.store, campaign_id, formats=formats)
        text = "\n".join(f"{kind.upper()}: {path}" for kind, path in outputs.items())
        return _ok(text, {"campaign_id": campaign_id, "outputs": {k: str(v) for k, v in outputs.items()}})


def _configure_stdio() -> None:
    """MCP stdio is UTF-8 even when the Windows console code page is not."""
    for stream, options in (
        (sys.stdin, {"encoding": "utf-8"}),
        (sys.stdout, {"encoding": "utf-8", "newline": "\n"}),
    ):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(**options)
        except (OSError, ValueError):
            pass


def serve(store: CampaignStore | None = None, settings: Settings | None = None, llm: LLMClient | None = None) -> int:
    """Run the newline-delimited JSON-RPC loop on stdin/stdout until EOF."""
    _configure_stdio()
    settings = settings or load_settings()
    store = store or CampaignStore(settings.store_dir)
    server = CooMCPServer(store, settings, llm or build_client(settings))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            response = CooMCPServer._rpc_error(None, -32700, "Parse error")
        else:
            response = server.handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> None:
    del argv
    raise SystemExit(serve())


if __name__ == "__main__":
    main()

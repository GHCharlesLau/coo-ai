"""CLI: campaigns, artifacts, exports, MCP, doctor, and the plugin bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from coo.campaign_ops import answer_question, format_status
from coo.config import load_settings
from coo.export import EXPORT_FORMATS, export_campaign
from coo.llm import build_client
from coo.orchestrator.runner import advance
from coo.paths import default_store_dir
from coo.store import CampaignStore


def _store(args: argparse.Namespace) -> CampaignStore:
    return CampaignStore(args.store or default_store_dir())


def _client(args: argparse.Namespace):
    settings = load_settings(stub=True if args.stub else None)
    if args.stub:
        settings = load_settings(stub=True)
    return settings, build_client(settings)


def cmd_new(args: argparse.Namespace) -> int:
    demand = args.demand
    if args.demand_file:
        demand = args.demand_file.read_text(encoding="utf-8")
    if not demand and not args.revision_of:
        print("Provide --demand or --demand-file.", file=sys.stderr)
        return 2
    settings = load_settings(stub=True if args.stub else None)
    store = _store(args)
    if settings.stub:
        model_name = "stub"
    elif settings.agent_fill:
        model_name = "coding-agent"
    else:
        model_name = settings.model
    meta = store.create(
        demand,
        stub=settings.stub,
        model=model_name,
        revision_of=args.revision_of,
    )
    print(meta.id)
    print(format_status(meta, store), end="")
    if args.run:
        return cmd_run(argparse.Namespace(**{**vars(args), "campaign_id": meta.id, "approve": False, "override": False}))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    settings, client = _client(args)
    store = _store(args)
    result = advance(
        store,
        args.campaign_id,
        client,
        settings,
        approve=args.approve,
        human_override=args.override,
    )
    print(format_status(store.load_meta(args.campaign_id), store), end="")
    print(result.message)
    if result.gate_errors:
        print("Gate errors:")
        for err in result.gate_errors:
            print(f"  - {err}")
    return 0 if result.status in {"ready", "awaiting_human", "awaiting_agent", "complete"} else 1


def cmd_status(args: argparse.Namespace) -> int:
    store = _store(args)
    print(format_status(store.load_meta(args.campaign_id), store), end="")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    store = _store(args)
    campaigns = store.list_campaigns()
    if not campaigns:
        print("No campaigns.")
        return 0
    for meta in campaigns:
        print(f"{meta.id}\t{meta.status}\t{meta.current_stage}")
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    store = _store(args)
    meta = store.load_meta(args.campaign_id)
    stage = args.stage or meta.current_stage
    print(store.read_prompt(args.campaign_id, stage), end="")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    store = _store(args)
    if args.format == "both":
        formats = ("docx", "pdf")
    elif args.format == "all":
        formats = EXPORT_FORMATS
    else:
        formats = (args.format,)
    outputs = export_campaign(store, args.campaign_id, formats=formats)
    for fmt, path in outputs.items():
        print(f"{fmt.upper()}: {path}")
    return 0


def cmd_answer(args: argparse.Namespace) -> int:
    store = _store(args)
    brief = answer_question(
        store,
        args.campaign_id,
        args.question,
        text=args.text,
        defer_reason=args.defer_reason,
    )
    store.append_user_notes(
        args.campaign_id,
        f"Answered {args.question}: text={args.text!r} defer={args.defer_reason!r}",
    )
    remaining = [q.id for q in brief.open_questions if q.status == "unanswered"]
    print(f"Updated {args.question}. Remaining unanswered: {', '.join(remaining) or '(none)'}")
    return 0


def cmd_artifact(args: argparse.Namespace) -> int:
    store = _store(args)
    action = args.artifact_cmd
    if action == "list":
        root = store.artifacts_dir(args.campaign_id)
        if not root.is_dir():
            raise FileNotFoundError(f"Campaign not found: {args.campaign_id}")
        files = sorted(path for path in root.rglob("*") if path.is_file())
        for path in files:
            print(f"{path.relative_to(root).as_posix()}\t{path.stat().st_size}")
        return 0

    if action == "read":
        path = store.artifact_path(args.campaign_id, args.name)
        if not path.is_file():
            raise FileNotFoundError(f"Missing artifact {args.name} for {args.campaign_id}")
        data = path.read_bytes()
        if args.out:
            args.out.write_bytes(data)
            print(args.out)
            return 0
        try:
            print(data.decode("utf-8"), end="" if data.endswith(b"\n") else "\n")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{args.name} is binary; use --out to write it to a file") from exc
        return 0

    if args.file:
        content = args.file.read_text(encoding="utf-8")
    elif args.stdin:
        content = sys.stdin.read()
    elif args.text is not None:
        content = args.text
    else:
        raise ValueError("Provide --file, --stdin, or --text.")
    path = store.write_artifact(args.campaign_id, args.name, content)
    print(path)
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    from coo.mcp_server import serve

    settings = load_settings(stub=True if args.stub else None)
    return serve(_store(args), settings)


def cmd_doctor(args: argparse.Namespace) -> int:
    from coo.doctor import run_doctor

    return run_doctor(json_output=args.json, quiet=args.quiet)


def cmd_plugin(args: argparse.Namespace) -> int:
    from coo.plugin import HOSTS, install_plugin, next_steps, plugin_dir, sync_plugin_skill, validate_plugin

    action = args.plugin_cmd
    if action == "path":
        print(plugin_dir())
        return 0

    if action == "sync":
        print(sync_plugin_skill())
        return 0

    if action == "validate":
        issues = validate_plugin()
        failed = any(issue.level == "fail" for issue in issues)
        if args.json:
            payload = {
                "ok": not failed,
                "issues": [{"level": issue.level, "message": issue.message} for issue in issues],
            }
            print(json.dumps(payload, indent=2))
        else:
            for issue in issues:
                print(f"{issue.level.upper():4}  {issue.message}")
        return 1 if failed else 0

    hosts = list(HOSTS) if args.host == "all" else [args.host]
    if args.host == "all" and args.dest:
        raise ValueError("--dest requires a single --host; omit --dest to use each host's default directory.")
    for host in hosts:
        destination = install_plugin(
            host,
            scope=args.scope,
            root=args.root,
            destination=args.dest,
            force=args.force,
        )
        print(f"Installed {host}: {destination}")
        for line in next_steps(host, destination):
            print(f"  {line}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    from coo.plugin import HOSTS as HOSTS_FOR_CLI

    parser = argparse.ArgumentParser(prog="coo", description="COO AI campaign-proposal orchestrator")
    parser.add_argument("--store", help="Campaign store directory (default: store/campaigns or COO_STORE_DIR)")
    parser.add_argument("--stub", action="store_true", help="Use the deterministic stub LLM")
    sub = parser.add_subparsers(dest="cmd", required=True)

    new = sub.add_parser("new", help="Create a campaign from a demand")
    new.add_argument("--demand", default="", help="User demand text")
    new.add_argument("--demand-file", type=lambda p: __import__("pathlib").Path(p), help="Read demand from a file")
    new.add_argument("--revision-of", help="Create a linked successor campaign and reuse its demand when omitted")
    new.add_argument("--run", action="store_true", help="Advance immediately after create")
    new.set_defaults(func=cmd_new)

    run = sub.add_parser("run", help="Advance the campaign until the next pause")
    run.add_argument("campaign_id")
    run.add_argument("--approve", action="store_true", help="Approve the current human checkpoint, then continue")
    run.add_argument("--override", action="store_true", help="Human-override a failed critique rubric")
    run.set_defaults(func=cmd_run)

    resume = sub.add_parser("resume", help="Same as run (continue from last passed gate)")
    resume.add_argument("campaign_id")
    resume.add_argument("--approve", action="store_true")
    resume.add_argument("--override", action="store_true")
    resume.set_defaults(func=cmd_run)

    status = sub.add_parser("status", help="Show campaign pipeline status")
    status.add_argument("campaign_id")
    status.set_defaults(func=cmd_status)

    listing = sub.add_parser("list", help="List campaigns")
    listing.set_defaults(func=cmd_list)

    answer = sub.add_parser("answer", help="Answer or defer an intake question")
    answer.add_argument("campaign_id")
    answer.add_argument("--question", required=True)
    answer.add_argument("--text", help="Answer text")
    answer.add_argument("--defer-reason", help="Defer instead of answering")
    answer.set_defaults(func=cmd_answer)

    prompt = sub.add_parser("prompt", help="Print the current agent-fill prompt")
    prompt.add_argument("campaign_id")
    prompt.add_argument("--stage", help="Optional stage name (default: current stage)")
    prompt.set_defaults(func=cmd_prompt)

    export = sub.add_parser("export", help="Render proposal docs and/or campaign deck deliverables")
    export.add_argument("campaign_id")
    export.add_argument(
        "--format",
        choices=("both", "all", "docx", "pdf", "html", "pptx", "deck-pdf"),
        default="both",
        help="both=DOCX+PDF; all=DOCX+PDF+HTML+PPTX+deck PDF; or one format (default: both)",
    )
    export.set_defaults(func=cmd_export)

    artifact = sub.add_parser("artifact", help="Read or write campaign artifacts")
    artifact_sub = artifact.add_subparsers(dest="artifact_cmd", required=True)
    artifact_list = artifact_sub.add_parser("list", help="List artifact files")
    artifact_list.add_argument("campaign_id")
    artifact_list.set_defaults(func=cmd_artifact)
    artifact_read = artifact_sub.add_parser("read", help="Print or save one artifact")
    artifact_read.add_argument("campaign_id")
    artifact_read.add_argument("name")
    artifact_read.add_argument("--out", type=Path, help="Write bytes to this file instead of stdout")
    artifact_read.set_defaults(func=cmd_artifact)
    artifact_write = artifact_sub.add_parser("write", help="Write one artifact from a file, stdin, or text")
    artifact_write.add_argument("campaign_id")
    artifact_write.add_argument("name")
    source = artifact_write.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="Read content from a UTF-8 file")
    source.add_argument("--stdin", action="store_true", help="Read content from stdin")
    source.add_argument("--text", help="Inline content")
    artifact_write.set_defaults(func=cmd_artifact)

    mcp = sub.add_parser("mcp", help="Run the MCP stdio server for Claude Code, Cursor, Codex, and other hosts")
    mcp.set_defaults(func=cmd_mcp)

    doctor = sub.add_parser("doctor", help="Check Python, store, skills, plugin, and model configuration")
    doctor.add_argument("--json", action="store_true", help="Emit a JSON report")
    doctor.add_argument("--quiet", action="store_true", help="Print only warnings and failures")
    doctor.set_defaults(func=cmd_doctor)

    plugin = sub.add_parser("plugin", help="Inspect, validate, sync, or install the shareable plugin bundle")
    plugin_sub = plugin.add_subparsers(dest="plugin_cmd", required=True)
    plugin_path = plugin_sub.add_parser("path", help="Print the plugin bundle path")
    plugin_path.set_defaults(func=cmd_plugin)
    plugin_validate = plugin_sub.add_parser("validate", help="Validate manifests, skill copy, and host adapters")
    plugin_validate.add_argument("--json", action="store_true")
    plugin_validate.set_defaults(func=cmd_plugin)
    plugin_sync = plugin_sub.add_parser("sync", help="Copy the canonical conductor skill into the bundle")
    plugin_sync.set_defaults(func=cmd_plugin)
    plugin_install = plugin_sub.add_parser("install", help="Install the bundle for one host")
    plugin_install.add_argument("--host", choices=(*HOSTS_FOR_CLI, "all"), required=True)
    plugin_install.add_argument("--scope", choices=("project", "user"), default="project")
    plugin_install.add_argument("--root", type=Path, help="Workspace root for project scope (default: cwd)")
    plugin_install.add_argument("--dest", type=Path, help="Explicit destination directory")
    plugin_install.add_argument("--force", action="store_true", help="Replace a non-COO directory")
    plugin_install.set_defaults(func=cmd_plugin)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        code = args.func(args)
    except (FileNotFoundError, FileExistsError, OSError, ValueError, KeyError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    raise SystemExit(code)

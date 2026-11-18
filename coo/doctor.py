"""Environment checks behind `coo doctor`."""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import asdict, dataclass
from typing import TextIO

from coo import __version__
from coo.config import load_settings
from coo.orchestrator.graph import STAGES
from coo.paths import default_store_dir, skills_dir, templates_dir
from coo.plugin import validate_plugin
from coo.store import CampaignStore


@dataclass(frozen=True)
class Check:
    name: str
    level: str
    detail: str


def _check_python() -> Check:
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info >= (3, 11):
        return Check("python", "pass", version)
    return Check("python", "fail", f"{version}; COO AI requires 3.11+")


def _check_package() -> Check:
    return Check("package", "pass", f"coo-ai {__version__}")


def _check_cli() -> Check:
    found = shutil.which("coo")
    if found:
        return Check("cli", "pass", found)
    python = shutil.which("python")
    if python:
        return Check("cli", "pass", f"{python} -m coo (console script not on PATH)")
    return Check(
        "cli",
        "warn",
        f"neither `coo` nor `python` is on PATH; point MCP hosts at {sys.executable} -m coo mcp",
    )


def _check_store() -> tuple[Check, CampaignStore | None]:
    path = default_store_dir()
    try:
        store = CampaignStore(path)
        probe = store.root / ".doctor-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return Check("store", "fail", f"{path} is not writable ({exc})"), None
    count = len(store.list_campaigns())
    return Check("store", "pass", f"{path} ({count} campaign{'s' if count != 1 else ''})"), store


def _check_skills() -> Check:
    missing = [
        stage.skill
        for stage in STAGES.values()
        if not (skills_dir() / stage.skill / "SKILL.md").is_file()
    ]
    if missing:
        return Check("stage skills", "fail", f"missing: {', '.join(missing)}")
    return Check("stage skills", "pass", f"{len(STAGES)} playbooks in {skills_dir()}")


def _check_templates() -> Check:
    path = templates_dir() / "proposal.md"
    if path.is_file():
        return Check("templates", "pass", str(path))
    return Check("templates", "fail", f"missing {path}")


def _check_conductor() -> Check:
    from coo.agent_install import agent_pack_dir

    path = agent_pack_dir() / "SKILL.md"
    if path.is_file():
        return Check("conductor skill", "pass", str(path))
    return Check("conductor skill", "fail", f"missing {path}")


def _check_plugin() -> Check:
    try:
        issues = validate_plugin()
    except (FileNotFoundError, OSError) as exc:
        return Check("plugin", "fail", str(exc))
    failures = [issue.message for issue in issues if issue.level == "fail"]
    if failures:
        return Check("plugin", "fail", failures[0])
    warnings = [issue.message for issue in issues if issue.level == "warn"]
    if warnings:
        return Check("plugin", "warn", warnings[0])
    return Check("plugin", "pass", "bundle is installable")


def _check_llm() -> Check:
    settings = load_settings()
    if settings.stub:
        return Check("llm", "warn", "stub mode is a test fixture; unset COO_LLM_STUB for a real campaign")
    if settings.api_key:
        return Check("llm", "pass", f"external model {settings.model}")
    return Check("llm", "pass", "agent-fill (coding agent writes artifacts, no API key)")


def _check_node() -> Check:
    found = shutil.which("node")
    if found:
        return Check("node", "pass", found)
    return Check("node", "warn", "Node.js not found; needed only for the OpenCode and DSH adapters")


def run_checks() -> list[Check]:
    checks = [
        _check_python(),
        _check_package(),
        _check_cli(),
        _check_store()[0],
        _check_skills(),
        _check_templates(),
        _check_conductor(),
        _check_plugin(),
        _check_llm(),
        _check_node(),
    ]
    return checks


def run_doctor(*, json_output: bool = False, quiet: bool = False, stream: TextIO | None = None) -> int:
    out = stream or sys.stdout
    checks = run_checks()
    failed = any(check.level == "fail" for check in checks)
    if json_output:
        payload = {
            "ok": not failed,
            "checks": [asdict(check) for check in checks],
        }
        print(json.dumps(payload, indent=2), file=out)
        return 1 if failed else 0
    visible = [check for check in checks if not quiet or check.level != "pass"]
    for check in visible:
        print(f"{check.level.upper():4}  {check.name:<16} {check.detail}", file=out)
    if not visible:
        return 0
    if failed:
        print("Fix the failures above, then re-run `coo doctor`.", file=out)
    return 1 if failed else 0

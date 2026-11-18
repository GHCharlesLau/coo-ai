"""Validate, sync, and install the shareable COO AI plugin bundle.

The bundle is a distribution shell. It carries host manifests, the conductor
skill, and host adapters; every command ultimately calls the Python orchestrator.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from coo.agent_install import agent_pack_dir
from coo.paths import project_root

PLUGIN_NAME = "coo-ai"
PLUGIN_VERSION = "0.1.0"
PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
ROOT_FIELDS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}
NAME_RE = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
HOSTS = ("claude", "codex", "cursor", "opencode", "dsh")
HOST_DIRS = {
    "claude": Path(".claude") / "plugins" / PLUGIN_NAME,
    "codex": Path(".codex") / "plugins" / PLUGIN_NAME,
    "cursor": Path(".cursor") / "plugins" / PLUGIN_NAME,
    "opencode": Path(".opencode") / "plugins" / PLUGIN_NAME,
    "dsh": Path(".dsh") / "plugins" / PLUGIN_NAME,
}
HOST_USER_DIRS = {
    **HOST_DIRS,
    "opencode": Path(".config") / "opencode" / "plugins" / PLUGIN_NAME,
}
MARKER = "install.json"

Level = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class Issue:
    level: Level
    message: str


def plugin_dir() -> Path:
    override = os.environ.get("COO_PLUGIN_DIR")
    path = Path(override) if override else project_root() / "plugin"
    if not path.is_dir():
        raise FileNotFoundError(f"Plugin bundle not found: {path}")
    return path


def _load(path: Path, issues: list[Issue], label: str) -> dict[str, Any] | None:
    if not path.is_file():
        issues.append(Issue("fail", f"{label}: missing {path}"))
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(Issue("fail", f"{label}: invalid JSON ({exc})"))
        return None
    if not isinstance(data, dict):
        issues.append(Issue("fail", f"{label}: expected a JSON object"))
        return None
    return data


def _check_name(data: dict[str, Any], issues: list[Issue], label: str) -> None:
    name = data.get("name")
    if not isinstance(name, str) or not 1 <= len(name) <= 64 or not NAME_RE.match(name):
        issues.append(Issue("fail", f"{label}: name must be 1-64 lowercase letters, digits, single hyphens, or single periods"))
    elif name != PLUGIN_NAME:
        issues.append(Issue("fail", f"{label}: name must be {PLUGIN_NAME!r}, got {name!r}"))


def _check_rel_path(root: Path, value: Any, issues: list[Issue], label: str) -> None:
    if not isinstance(value, str) or not value.startswith("./"):
        issues.append(Issue("fail", f"{label}: path must start with './'"))
        return
    resolved = (root / value).resolve()
    if resolved != root.resolve() and root.resolve() not in resolved.parents:
        issues.append(Issue("fail", f"{label}: path escapes the plugin root"))
    elif not resolved.exists():
        issues.append(Issue("fail", f"{label}: path does not exist: {value}"))


def _frontmatter(path: Path, issues: list[Issue], label: str) -> dict[str, str]:
    if not path.is_file():
        issues.append(Issue("fail", f"{label}: missing {path}"))
        return {}
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        issues.append(Issue("fail", f"{label}: missing YAML frontmatter"))
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        field = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if field:
            fields[field.group(1)] = field.group(2).strip()
    return fields


def validate_plugin(root: Path | None = None) -> list[Issue]:
    """Return pass/warn/fail checks for the bundle. Fails block install."""
    root = root or plugin_dir()
    issues: list[Issue] = []
    if not root.is_dir():
        return [Issue("fail", f"plugin root not found: {root}")]

    manifest = _load(root / "plugin.json", issues, "plugin.json")
    if manifest is not None:
        issues.append(Issue("pass", "plugin.json parses"))
        if manifest.get("$schema") != PLUGIN_SCHEMA:
            issues.append(Issue("fail", f"plugin.json: $schema must be {PLUGIN_SCHEMA}"))
        extra = set(manifest) - ROOT_FIELDS
        if extra:
            issues.append(Issue("fail", f"plugin.json: unknown fields: {', '.join(sorted(extra))}"))
        _check_name(manifest, issues, "plugin.json")
        if not str(manifest.get("version", "")).strip():
            issues.append(Issue("fail", "plugin.json: version is required"))
        description = manifest.get("description")
        if not isinstance(description, str) or not description.strip():
            issues.append(Issue("warn", "plugin.json: description is empty"))

    mcp = _load(root / "mcp.json", issues, "mcp.json")
    if mcp is not None:
        issues.append(Issue("pass", "mcp.json parses"))
        extra = set(mcp) - {"$schema", "mcpServers"}
        if extra:
            issues.append(Issue("fail", f"mcp.json: unknown fields: {', '.join(sorted(extra))}"))
        servers = mcp.get("mcpServers")
        server_key = PLUGIN_NAME if isinstance(servers, dict) and PLUGIN_NAME in servers else "coo"
        coo = servers.get(server_key) if isinstance(servers, dict) else None
        if not isinstance(coo, dict):
            issues.append(Issue("fail", f"mcp.json: mcpServers.{server_key} is missing"))
        else:
            if coo.get("type") != "stdio":
                issues.append(Issue("fail", f"mcp.json: mcpServers.{server_key}.type must be 'stdio'"))
            if not str(coo.get("command", "")).strip():
                issues.append(Issue("fail", f"mcp.json: mcpServers.{server_key}.command is empty"))
            if coo.get("args") != ["-m", "coo", "mcp"]:
                issues.append(Issue("warn", "mcp.json: expected args ['-m', 'coo', 'mcp']"))
            else:
                issues.append(Issue("pass", "MCP server runs `python -m coo mcp`"))

    claude_mcp = _load(root / ".mcp.json", issues, ".mcp.json")
    if claude_mcp is not None and not isinstance(claude_mcp.get("mcpServers"), dict):
        issues.append(Issue("fail", ".mcp.json: mcpServers is missing"))

    skill = root / "skills" / PLUGIN_NAME / "SKILL.md"
    fields = _frontmatter(skill, issues, "skills")
    if fields:
        if fields.get("name") != PLUGIN_NAME:
            issues.append(Issue("fail", f"skills: name must be {PLUGIN_NAME!r}"))
        description = fields.get("description", "")
        if not 1 <= len(description) <= 1024:
            issues.append(Issue("fail", "skills: description must be 1-1024 characters"))
        canonical = agent_pack_dir() / "SKILL.md"
        if canonical.is_file():
            if skill.read_text(encoding="utf-8") != canonical.read_text(encoding="utf-8"):
                issues.append(
                    Issue("fail", "skills: copy drifted from agent-pack/coo-ai; run `python -m coo plugin sync`")
                )
            else:
                issues.append(Issue("pass", "conductor skill matches agent-pack"))
        else:
            issues.append(Issue("warn", "agent-pack source not found; skipped skill drift check"))

    command = root / "commands" / "coo.md"
    command_fields = _frontmatter(command, issues, "commands")
    if command_fields and not command_fields.get("description"):
        issues.append(Issue("fail", "commands/coo.md: description is required"))

    host_manifests = {
        "claude": (root / ".claude-plugin" / "plugin.json", ("skills", "commands", "hooks", "mcpServers")),
        "codex": (root / ".codex-plugin" / "plugin.json", ("skills", "mcpServers")),
        "cursor": (root / ".cursor-plugin" / "plugin.json", ("skills", "commands", "hooks", "mcpServers")),
    }
    for host, (path, path_fields) in host_manifests.items():
        data = _load(path, issues, f"{host} manifest")
        if data is None:
            continue
        issues.append(Issue("pass", f"{host} manifest parses"))
        _check_name(data, issues, f"{host} manifest")
        for field in path_fields:
            if field in data:
                _check_rel_path(root, data[field], issues, f"{host} manifest.{field}")

    opencode_pkg = _load(root / "hosts" / "opencode" / "package.json", issues, "opencode package")
    if opencode_pkg is not None:
        issues.append(Issue("pass", "opencode package parses"))
        if opencode_pkg.get("type") != "module":
            issues.append(Issue("fail", "opencode package: type must be 'module'"))
        if not (root / "hosts" / "opencode" / "index.ts").is_file():
            issues.append(Issue("fail", "opencode: hosts/opencode/index.ts is missing"))

    dsh_pkg = _load(root / "hosts" / "dsh" / "package.json", issues, "dsh package")
    if dsh_pkg is not None:
        issues.append(Issue("pass", "dsh package parses"))
        if dsh_pkg.get("type") != "module":
            issues.append(Issue("fail", "dsh package: type must be 'module'"))
        files = dsh_pkg.get("files")
        if not isinstance(files, list) or "cordis.patch.yml" not in files:
            issues.append(Issue("fail", "dsh package: files must include cordis.patch.yml"))
        bundle = dsh_pkg.get("dsh", {}).get("bundle", {}) if isinstance(dsh_pkg.get("dsh"), dict) else {}
        if bundle.get("patch") != "./cordis.patch.yml":
            issues.append(Issue("fail", "dsh package: dsh.bundle.patch must be './cordis.patch.yml'"))
        if not (root / "hosts" / "dsh" / "index.js").is_file():
            issues.append(Issue("fail", "dsh: hosts/dsh/index.js is missing"))
        if not (root / "hosts" / "dsh" / "cordis.patch.yml").is_file():
            issues.append(Issue("fail", "dsh: hosts/dsh/cordis.patch.yml is missing"))

    repo = root.parent
    allowed_sources = {
        "claude": {f"./{root.name}"},
        "cursor": {root.name, f"./{root.name}"},
    }
    for name, host in ((".claude-plugin", "claude"), (".cursor-plugin", "cursor")):
        data = _load(repo / name / "marketplace.json", issues, f"{host} marketplace")
        if data is None:
            continue
        plugins = data.get("plugins")
        entry = next((p for p in plugins if isinstance(p, dict) and p.get("name") == PLUGIN_NAME), None) if isinstance(plugins, list) else None
        if entry is None:
            issues.append(Issue("fail", f"{host} marketplace: no {PLUGIN_NAME} entry"))
        elif entry.get("source") not in allowed_sources[host]:
            issues.append(Issue("warn", f"{host} marketplace: source should point at {root.name}"))
        else:
            issues.append(Issue("pass", f"{host} marketplace points at {root.name}"))

    if not any(issue.level == "fail" for issue in issues):
        issues.append(Issue("pass", "bundle is installable"))
    return issues


def sync_plugin_skill(root: Path | None = None) -> Path:
    """Copy the canonical conductor skill into the bundle."""
    root = root or plugin_dir()
    source = agent_pack_dir()
    if not (source / "SKILL.md").is_file():
        raise FileNotFoundError(f"Conductor skill missing: {source / 'SKILL.md'}")
    destination = root / "skills" / PLUGIN_NAME
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    return destination


def _copy_for_host(host: str, source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if host == "opencode":
        shutil.copy2(source / "hosts" / "opencode" / "index.ts", destination / "index.ts")
        shutil.copy2(source / "hosts" / "opencode" / "package.json", destination / "package.json")
        shutil.copytree(source / "skills", destination / "skills", dirs_exist_ok=True)
        shutil.copy2(source / "plugin.json", destination / "plugin.json")
        return
    if host == "dsh":
        for name in ("index.js", "package.json", "cordis.patch.yml"):
            shutil.copy2(source / "hosts" / "dsh" / name, destination / name)
        shutil.copytree(source / "skills", destination / "skills", dirs_exist_ok=True)
        shutil.copy2(source / "plugin.json", destination / "plugin.json")
        return
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("hosts", "__pycache__", "*.pyc"),
    )


def _bind_mcp_command(destination: Path) -> None:
    """Point an installed copy at the interpreter that can import coo."""
    for name in ("mcp.json", ".mcp.json"):
        path = destination / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            continue
        for server in servers.values():
            if isinstance(server, dict) and server.get("command") in {"python", "python3"}:
                server["command"] = sys.executable
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def install_plugin(
    host: str,
    *,
    scope: Literal["project", "user"] = "project",
    root: Path | None = None,
    destination: Path | None = None,
    force: bool = False,
) -> Path:
    """Copy the bundle (or a host adapter) into a host discovery directory."""
    if host not in HOSTS:
        raise ValueError(f"Unknown host {host!r}. Choose from: {', '.join(HOSTS)}")
    if scope not in {"project", "user"}:
        raise ValueError("scope must be 'project' or 'user'")
    failures = [issue.message for issue in validate_plugin() if issue.level == "fail"]
    if failures:
        raise ValueError("Plugin validation failed: " + "; ".join(failures[:3]))

    source = plugin_dir()
    base_dir = (root or Path.cwd()) if scope == "project" else Path.home()
    host_dir = HOST_DIRS[host] if scope == "project" else HOST_USER_DIRS[host]
    base = destination or base_dir / host_dir
    target = Path(base)
    if target.exists():
        marker = target / MARKER
        if not force and not marker.is_file():
            raise FileExistsError(
                f"{target} already exists and is not a COO AI install; pass --force to replace it"
            )
        shutil.rmtree(target)
    _copy_for_host(host, source, target)
    _bind_mcp_command(target)
    marker = {
        "plugin": PLUGIN_NAME,
        "version": PLUGIN_VERSION,
        "host": host,
        "scope": scope,
        "source": str(source),
        "installed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    (target / MARKER).write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    return target


def next_steps(host: str, destination: Path) -> list[str]:
    source = plugin_dir()
    if host == "claude":
        return [
            f'claude plugin marketplace add "{source.parent}"',
            f"claude plugin install {PLUGIN_NAME}@{PLUGIN_NAME}",
            f'# or load this copy directly: claude --plugin-dir "{destination}"',
        ]
    if host == "codex":
        return [
            f"# add a local marketplace entry for {destination} in .agents/plugins/marketplace.json",
            f'# {{"name": "{PLUGIN_NAME}", "source": {{"source": "local", "path": "{destination.as_posix()}"}}, "policy": {{"installation": "AVAILABLE", "authentication": "ON_INSTALL"}}, "category": "Productivity"}}',
            "# then run `codex /plugins` and install coo-ai",
        ]
    if host == "cursor":
        return [
            f"# Cursor reads the Agent Plugin at {destination}",
            f'# or add the local plugin from "{source}" in Cursor settings',
        ]
    if host == "opencode":
        return [
            f"# OpenCode auto-loads {destination / 'index.ts'}",
            "# restart OpenCode, then ask for a campaign proposal",
        ]
    return [
        f'dsh plugin --profile <profile> add "link:{destination}"',
        "# restart the profile and confirm the coo_* tools are listed",
    ]

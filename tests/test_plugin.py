from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from coo.agent_install import agent_pack_dir
from coo.plugin import (
    HOSTS,
    PLUGIN_NAME,
    PLUGIN_SCHEMA,
    install_plugin,
    next_steps,
    plugin_dir,
    validate_plugin,
)


def test_bundle_validates_without_failures():
    issues = validate_plugin()
    failures = [issue.message for issue in issues if issue.level == "fail"]
    assert failures == []
    assert any(issue.message == "bundle is installable" for issue in issues)


def test_root_manifest_is_closed_and_named():
    manifest = json.loads((plugin_dir() / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["$schema"] == PLUGIN_SCHEMA
    assert manifest["name"] == PLUGIN_NAME
    allowed = {
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
    assert set(manifest) <= allowed


def test_portable_mcp_launches_the_cli():
    mcp = json.loads((plugin_dir() / "mcp.json").read_text(encoding="utf-8"))
    server = mcp["mcpServers"]["coo"]
    assert server["type"] == "stdio"
    assert server["command"] == "python"
    assert server["args"] == ["-m", "coo", "mcp"]


def test_claude_mcp_file_matches():
    mcp = json.loads((plugin_dir() / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["coo"]["command"] == "python"
    assert mcp["mcpServers"]["coo"]["args"] == ["-m", "coo", "mcp"]


def test_skill_copy_matches_canonical_source():
    bundled = plugin_dir() / "skills" / PLUGIN_NAME / "SKILL.md"
    canonical = agent_pack_dir() / "SKILL.md"
    assert bundled.read_text(encoding="utf-8") == canonical.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "relative",
    [
        ".claude-plugin/plugin.json",
        ".codex-plugin/plugin.json",
        ".cursor-plugin/plugin.json",
        "commands/coo.md",
        "hosts/opencode/index.ts",
        "hosts/opencode/package.json",
        "hosts/dsh/index.js",
        "hosts/dsh/package.json",
        "hosts/dsh/cordis.patch.yml",
    ],
)
def test_bundle_contains_host_components(relative: str):
    assert (plugin_dir() / relative).is_file()


@pytest.mark.parametrize("host", HOSTS)
def test_every_host_has_a_destination_and_steps(host: str):
    steps = next_steps(host, Path("/tmp/coo-ai"))
    assert steps
    assert any("coo" in step.lower() or "dsh" in step.lower() for step in steps)


def test_install_opencode_copies_adapter_skill_and_marker(tmp_path: Path):
    destination = install_plugin("opencode", root=tmp_path)
    assert destination == tmp_path / ".opencode" / "plugins" / PLUGIN_NAME
    assert (destination / "index.ts").is_file()
    assert (destination / "skills" / PLUGIN_NAME / "SKILL.md").is_file()
    marker = json.loads((destination / "install.json").read_text(encoding="utf-8"))
    assert marker["host"] == "opencode"
    assert marker["plugin"] == PLUGIN_NAME


def test_install_is_idempotent_with_marker(tmp_path: Path):
    first = install_plugin("opencode", root=tmp_path)
    second = install_plugin("opencode", root=tmp_path)
    assert first == second
    assert (second / "install.json").is_file()


def test_install_claude_copies_bundle_without_hosts(tmp_path: Path):
    destination = install_plugin("claude", root=tmp_path)
    assert (destination / ".claude-plugin" / "plugin.json").is_file()
    assert (destination / ".mcp.json").is_file()
    assert (destination / "skills" / PLUGIN_NAME / "SKILL.md").is_file()
    assert not (destination / "hosts").exists()


def test_install_binds_mcp_to_the_current_interpreter(tmp_path: Path):
    destination = install_plugin("claude", root=tmp_path)
    for name in (".mcp.json", "mcp.json"):
        data = json.loads((destination / name).read_text(encoding="utf-8"))
        assert data["mcpServers"]["coo"]["command"] == sys.executable
        assert data["mcpServers"]["coo"]["args"] == ["-m", "coo", "mcp"]


def test_opencode_user_scope_uses_the_global_config_dir(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    destination = install_plugin("opencode", scope="user")
    assert destination == tmp_path / ".config" / "opencode" / "plugins" / PLUGIN_NAME


def test_install_refuses_foreign_directory_without_force(tmp_path: Path):
    target = tmp_path / ".opencode" / "plugins" / PLUGIN_NAME
    target.mkdir(parents=True)
    (target / "foreign.txt").write_text("keep me", encoding="utf-8")
    with pytest.raises(FileExistsError):
        install_plugin("opencode", root=tmp_path)
    destination = install_plugin("opencode", root=tmp_path, force=True)
    assert not (destination / "foreign.txt").exists()


def test_install_rejects_unknown_host(tmp_path: Path):
    with pytest.raises(ValueError):
        install_plugin("unknown", root=tmp_path)


def test_marketplaces_point_at_the_bundle():
    repo = plugin_dir().parent
    for name, expected in ((".claude-plugin", f"./plugin"), (".cursor-plugin", "plugin")):
        data = json.loads((repo / name / "marketplace.json").read_text(encoding="utf-8"))
        entry = next(item for item in data["plugins"] if item["name"] == PLUGIN_NAME)
        assert entry["source"] == expected


def test_cli_plugin_install(tmp_path: Path):
    from coo.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["plugin", "install", "--host", "opencode", "--scope", "project", "--root", str(tmp_path)])
    assert exc.value.code == 0
    assert (tmp_path / ".opencode" / "plugins" / PLUGIN_NAME / "index.ts").is_file()


def test_cli_plugin_rejects_dest_for_all(tmp_path: Path):
    from coo.cli import main

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "plugin",
                "install",
                "--host",
                "all",
                "--scope",
                "project",
                "--root",
                str(tmp_path),
                "--dest",
                str(tmp_path / "one"),
            ]
        )
    assert exc.value.code == 2

from __future__ import annotations

import re
from pathlib import Path

from coo.agent_install import SKILL_NAME, agent_pack_dir, install_pack

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_FIELD = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$", re.MULTILINE)


def _frontmatter(text: str) -> dict[str, str]:
    match = _FRONTMATTER.match(text)
    assert match, "SKILL.md must start with YAML frontmatter"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        field = _FIELD.match(line)
        if field:
            fields[field.group(1)] = field.group(2).strip()
    return fields


def test_conductor_skill_frontmatter():
    path = agent_pack_dir() / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    fields = _frontmatter(text)
    assert fields.get("name") == SKILL_NAME
    assert agent_pack_dir().name == SKILL_NAME
    description = fields.get("description", "")
    assert 1 <= len(description) <= 1024
    for token in ("campaign proposal", "COO AI", "brief", "marketing campaign"):
        assert token.lower() in description.lower()
    assert "python -m coo" in text
    assert "awaiting_agent" in text or "artifacts/" in text
    assert text.count("\n") < 200


def test_install_pack_writes_both_discovery_paths(tmp_path: Path):
    written = install_pack(workspace=tmp_path)
    agents = tmp_path / ".agents" / "skills" / SKILL_NAME / "SKILL.md"
    claude = tmp_path / ".claude" / "skills" / SKILL_NAME / "SKILL.md"
    assert agents.is_file()
    assert claude.is_file()
    assert agents.read_text(encoding="utf-8") == claude.read_text(encoding="utf-8")
    source = (agent_pack_dir() / "SKILL.md").read_text(encoding="utf-8")
    assert agents.read_text(encoding="utf-8") == source
    assert {path.resolve() for path in written} == {agents.parent.resolve(), claude.parent.resolve()}


def test_install_pack_user_home(tmp_path: Path):
    workspace = tmp_path / "ws"
    home = tmp_path / "home"
    workspace.mkdir()
    written = install_pack(workspace=workspace, user=True, home=home)
    user_agents = home / ".agents" / "skills" / SKILL_NAME / "SKILL.md"
    user_claude = home / ".claude" / "skills" / SKILL_NAME / "SKILL.md"
    assert user_agents.is_file()
    assert user_claude.is_file()
    assert user_agents.parent in written
    assert user_claude.parent in written

"""Load portable SKILL.md files. Frontmatter is stripped; body is the stage prompt."""

from __future__ import annotations

import re
from pathlib import Path

from coo.paths import skills_dir

_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


def skill_path(name: str, root: Path | None = None) -> Path:
    return (root or skills_dir()) / name / "SKILL.md"


def load_skill(name: str, root: Path | None = None) -> str:
    path = skill_path(name, root)
    if not path.is_file():
        raise FileNotFoundError(f"Skill not found: {path}")
    text = path.read_text(encoding="utf-8")
    return _FRONTMATTER.sub("", text, count=1).strip() + "\n"


def constitution() -> str:
    return load_skill("coo-constitution")

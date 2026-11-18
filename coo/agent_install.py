"""Copy the COO AI conductor skill into coding-agent discovery paths."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from coo.paths import project_root

SKILL_NAME = "coo-ai"
PROJECT_TARGETS = (
    Path(".agents") / "skills" / SKILL_NAME,
    Path(".claude") / "skills" / SKILL_NAME,
)
USER_TARGETS = (
    Path(".agents") / "skills" / SKILL_NAME,
    Path(".claude") / "skills" / SKILL_NAME,
)


def agent_pack_dir() -> Path:
    override = os.environ.get("COO_AGENT_PACK_DIR")
    if override:
        return Path(override)
    return project_root() / "agent-pack" / SKILL_NAME


def default_workspace_root() -> Path:
    override = os.environ.get("COO_WORKSPACE_ROOT")
    if override:
        return Path(override)
    here = project_root()
    parent = here.parent
    markers = ("references", "AGENTS.md", ".agents")
    if here.name == "coo-ai" and any((parent / marker).exists() for marker in markers):
        return parent
    return here


def copy_skill(src: Path, dest: Path) -> Path:
    if not (src / "SKILL.md").is_file():
        raise FileNotFoundError(f"Conductor skill missing: {src / 'SKILL.md'}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return dest


def install_pack(
    *,
    workspace: Path | None = None,
    user: bool = False,
    home: Path | None = None,
    pack: Path | None = None,
) -> list[Path]:
    src = pack or agent_pack_dir()
    written: list[Path] = []
    root = (workspace or default_workspace_root()).resolve()
    for rel in PROJECT_TARGETS:
        written.append(copy_skill(src, root / rel))
    if user:
        user_home = (home or Path.home()).resolve()
        for rel in USER_TARGETS:
            written.append(copy_skill(src, user_home / rel))
    return written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m coo.agent_install",
        description="Install the COO AI conductor skill for Cursor, Claude Code, Codex, and Zcode.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Workspace root that receives .agents/skills and .claude/skills (default: detected)",
    )
    parser.add_argument(
        "--user",
        action="store_true",
        help="Also copy to ~/.agents/skills/coo-ai and ~/.claude/skills/coo-ai",
    )
    args = parser.parse_args(argv)
    try:
        paths = install_pack(workspace=args.root, user=args.user)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    for path in paths:
        print(path)
    raise SystemExit(0)


if __name__ == "__main__":
    main()

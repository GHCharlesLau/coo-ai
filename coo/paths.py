"""Resolve repo-relative locations for skills, templates, and the default store."""

from __future__ import annotations

import os
from pathlib import Path


def package_dir() -> Path:
    return Path(__file__).resolve().parent


def project_root() -> Path:
    return package_dir().parent


def skills_dir() -> Path:
    override = os.environ.get("COO_SKILLS_DIR")
    if override:
        return Path(override)
    return project_root() / "skills"


def templates_dir() -> Path:
    override = os.environ.get("COO_TEMPLATES_DIR")
    if override:
        return Path(override)
    return project_root() / "templates"


def default_store_dir() -> Path:
    override = os.environ.get("COO_STORE_DIR")
    if override:
        return Path(override)
    return project_root() / "store" / "campaigns"

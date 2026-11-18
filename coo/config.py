"""Runtime configuration. Orchestrator policy lives here; marketing doctrine does not."""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_RUBRIC_THRESHOLD = 3.5
DEFAULT_MAX_RETRIES = 2


@dataclass(frozen=True)
class Settings:
    store_dir: str | None
    api_key: str | None
    base_url: str
    model: str
    stub: bool
    agent_fill: bool
    max_retries: int
    rubric_threshold: float
    timeout_s: float


def load_settings(*, stub: bool | None = None) -> Settings:
    env_stub = os.environ.get("COO_LLM_STUB", "").strip().lower() in {"1", "true", "yes"}
    use_stub = env_stub if stub is None else stub
    api_key = os.environ.get("COO_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    agent_fill = not use_stub and not api_key
    return Settings(
        store_dir=os.environ.get("COO_STORE_DIR"),
        api_key=api_key,
        base_url=os.environ.get("COO_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        model="coding-agent" if agent_fill else os.environ.get("COO_LLM_MODEL", DEFAULT_MODEL),
        stub=use_stub,
        agent_fill=agent_fill,
        max_retries=int(os.environ.get("COO_MAX_RETRIES", DEFAULT_MAX_RETRIES)),
        rubric_threshold=float(os.environ.get("COO_RUBRIC_THRESHOLD", DEFAULT_RUBRIC_THRESHOLD)),
        timeout_s=float(os.environ.get("COO_LLM_TIMEOUT", "90")),
    )

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

STAGE_NAMES: tuple[str, ...] = (
    "intake",
    "research",
    "strategy",
    "plan",
    "deliver",
    "critique",
)

LEGACY_STAGE_NAMES: tuple[str, ...] = (
    "intake",
    "research",
    "strategy",
    "plan",
    "measure",
    "write",
    "slides",
    "critique",
)

StageName = Literal[
    "intake",
    "research",
    "strategy",
    "plan",
    "deliver",
    "measure",
    "write",
    "slides",
    "critique",
]

StageStatus = Literal[
    "pending",
    "running",
    "passed",
    "failed",
    "needs_human",
    "needs_agent",
    "escalated",
]

CampaignStatus = Literal[
    "ready",
    "running",
    "awaiting_human",
    "awaiting_agent",
    "escalated",
    "failed",
    "complete",
]


class StageState(BaseModel):
    name: str
    status: StageStatus = "pending"
    attempts: int = 0
    gate_passed: bool = False
    last_errors: list[str] = Field(default_factory=list)


class CampaignMeta(BaseModel):
    id: str
    revision_of: str | None = None
    quality_profile: Literal["legacy", "evidence_v2"] = "legacy"
    # Missing on all pre-lean records; those campaigns keep the eight-stage graph.
    pipeline_version: Literal["legacy", "lean"] = "legacy"
    # Older stored runs omit this field and remain on their original gate set.
    requirements_version: int = Field(
        default=2,
        ge=1,
        description="Gate set version; older records default to 2 and new runs are created at 3.",
    )
    created_at: str
    updated_at: str
    status: CampaignStatus = "ready"
    current_stage: str = "intake"
    stages: dict[str, StageState]
    approvals: list[str] = Field(default_factory=list)
    model: str | None = None
    stub: bool = False
    pause_reason: str | None = None
    proposal_hash_at_write: str | None = None
    slides_hash_at_slides: str | None = None


def initial_stage_states(*, legacy: bool = False) -> dict[str, StageState]:
    names = LEGACY_STAGE_NAMES if legacy else STAGE_NAMES
    return {name: StageState(name=name) for name in names}

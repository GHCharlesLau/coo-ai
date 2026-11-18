"""Linear stage graph. The orchestrator owns order; skills do not."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from coo.schemas.campaign import LEGACY_STAGE_NAMES, STAGE_NAMES, CampaignMeta, StageState

RetryKind = Literal["hard", "soft"]


@dataclass(frozen=True)
class StageDef:
    name: str
    skill: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    gate: str
    checkpoint_after: bool = False
    retry_kind: RetryKind = "hard"


LEGACY_PIPELINE: tuple[StageDef, ...] = (
    StageDef(
        name="intake",
        skill="coo-intake",
        inputs=(),
        outputs=("brief.json",),
        gate="intake",
        checkpoint_after=True,
    ),
    StageDef(
        name="research",
        skill="coo-research",
        inputs=("brief.json",),
        outputs=("situation.md", "evidence.json"),
        gate="research",
    ),
    StageDef(
        name="strategy",
        skill="coo-strategy",
        inputs=("brief.json", "situation.md", "evidence.json"),
        outputs=("strategy.json",),
        gate="strategy",
        checkpoint_after=True,
    ),
    StageDef(
        name="plan",
        skill="coo-plan",
        inputs=("brief.json", "strategy.json", "evidence.json"),
        outputs=("plan.json",),
        gate="plan",
    ),
    StageDef(
        name="measure",
        skill="coo-measure",
        inputs=("brief.json", "strategy.json", "plan.json"),
        outputs=("measurement.json",),
        gate="measure",
    ),
    StageDef(
        name="write",
        skill="coo-write",
        inputs=(
            "brief.json",
            "situation.md",
            "evidence.json",
            "strategy.json",
            "plan.json",
            "measurement.json",
        ),
        outputs=("proposal.md",),
        gate="write",
    ),
    StageDef(
        name="slides",
        skill="coo-slides",
        inputs=(
            "brief.json",
            "situation.md",
            "evidence.json",
            "strategy.json",
            "plan.json",
            "measurement.json",
            "proposal.md",
        ),
        outputs=("slides.json",),
        gate="slides",
    ),
    StageDef(
        name="critique",
        skill="coo-critique",
        inputs=(
            "brief.json",
            "situation.md",
            "evidence.json",
            "strategy.json",
            "plan.json",
            "measurement.json",
            "proposal.md",
            "slides.json",
        ),
        outputs=("review.json", "proposal.md", "slides.json"),
        gate="critique",
        checkpoint_after=True,
        retry_kind="soft",
    ),
)


PIPELINE: tuple[StageDef, ...] = (
    LEGACY_PIPELINE[0],
    LEGACY_PIPELINE[1],
    LEGACY_PIPELINE[2],
    StageDef(
        name="plan",
        skill="coo-plan",
        inputs=("brief.json", "strategy.json", "evidence.json"),
        outputs=("plan.json", "measurement.json"),
        gate="plan_lean",
    ),
    StageDef(
        name="deliver",
        skill="coo-deliver",
        inputs=(
            "brief.json",
            "situation.md",
            "evidence.json",
            "strategy.json",
            "plan.json",
            "measurement.json",
        ),
        outputs=("proposal.md", "slides.json"),
        gate="deliver",
    ),
    StageDef(
        name="critique",
        skill="coo-critique",
        inputs=(
            "brief.json",
            "situation.md",
            "evidence.json",
            "strategy.json",
            "plan.json",
            "measurement.json",
            "proposal.md",
            "slides.json",
        ),
        outputs=("review.json", "proposal.md", "slides.json"),
        gate="critique",
        checkpoint_after=True,
        retry_kind="soft",
    ),
)

STAGE_ORDER: tuple[str, ...] = tuple(stage.name for stage in PIPELINE)
STAGES: dict[str, StageDef] = {stage.name: stage for stage in PIPELINE}
LEGACY_STAGES: dict[str, StageDef] = {stage.name: stage for stage in LEGACY_PIPELINE}

if STAGE_ORDER != STAGE_NAMES:
    raise RuntimeError("PIPELINE names drifted from schemas.campaign.STAGE_NAMES")
if tuple(stage.name for stage in LEGACY_PIPELINE) != LEGACY_STAGE_NAMES:
    raise RuntimeError("LEGACY_PIPELINE names drifted from LEGACY_STAGE_NAMES")


def stage_index(name: str) -> int:
    return STAGE_ORDER.index(name)


def pipeline_for(meta: CampaignMeta) -> tuple[StageDef, ...]:
    return LEGACY_PIPELINE if meta.pipeline_version == "legacy" else PIPELINE


def stages_for(meta: CampaignMeta) -> dict[str, StageDef]:
    return LEGACY_STAGES if meta.pipeline_version == "legacy" else STAGES


def next_stage(name: str, pipeline: tuple[StageDef, ...] = PIPELINE) -> StageDef | None:
    names = tuple(stage.name for stage in pipeline)
    idx = names.index(name)
    if idx + 1 >= len(pipeline):
        return None
    return pipeline[idx + 1]


def first_unpassed(
    states: dict[str, StageState], pipeline: tuple[StageDef, ...] = PIPELINE
) -> StageDef | None:
    for stage in pipeline:
        status = states[stage.name].status
        if status != "passed":
            return stage
    return None


V2_EXTRA_OUTPUTS = {
    "plan": ("operations.json",),
    "write": ("campaign_assets.json",),
    "deliver": ("campaign_assets.json",),
}
V2_EXTRA_INPUTS = {
    "write": ("operations.json",),
    "deliver": ("operations.json",),
    "slides": ("operations.json", "campaign_assets.json"),
    "critique": ("operations.json", "campaign_assets.json"),
}


def stage_outputs(stage: StageDef, quality_profile: str) -> tuple[str, ...]:
    extras = V2_EXTRA_OUTPUTS.get(stage.name, ()) if quality_profile == "evidence_v2" else ()
    return stage.outputs + extras


def stage_inputs(stage: StageDef, quality_profile: str) -> tuple[str, ...]:
    extras = V2_EXTRA_INPUTS.get(stage.name, ()) if quality_profile == "evidence_v2" else ()
    return stage.inputs + extras

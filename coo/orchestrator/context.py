"""Assemble only the artifacts a stage is allowed to see."""

from __future__ import annotations

import json

from coo.orchestrator.graph import StageDef
from coo.store import CampaignStore


def assemble_context(store: CampaignStore, campaign_id: str, stage: StageDef) -> str:
    from coo.orchestrator.graph import stage_inputs

    meta = store.load_meta(campaign_id)
    profile = meta.quality_profile
    inputs = stage_inputs(stage, profile)
    if meta.pipeline_version == "lean" and stage.name == "critique":
        inputs = tuple(
            name for name in inputs if name in {"brief.json", "proposal.md", "slides.json"}
        )
    parts: list[str] = [
        f"campaign_id: {campaign_id}",
        f"quality_profile: {profile}",
        f"requirements_version: {meta.requirements_version}",
        f"pipeline_version: {meta.pipeline_version}",
        "",
        "## User demand",
        store.demand(campaign_id),
    ]
    notes = store.user_notes(campaign_id)
    if notes:
        parts.extend(["", "## User notes", notes])
    for name in inputs:
        if not store.has_artifact(campaign_id, name):
            raise FileNotFoundError(
                f"Stage {stage.name} cannot start: missing required artifact {name}"
            )
        body = store.read_artifact(campaign_id, name).rstrip()
        if meta.pipeline_version == "lean" and name.endswith(".json"):
            body = json.dumps(json.loads(body), ensure_ascii=False, separators=(",", ":"))
        parts.extend(["", f"## Artifact: {name}", body])
    return "\n".join(parts) + "\n"

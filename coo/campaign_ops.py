"""Mutations that a human performs on campaign artifacts between stages."""

from __future__ import annotations

from coo.orchestrator.graph import stages_for, stage_outputs
from coo.schemas.brief import Brief
from coo.store import CampaignStore

CHECKPOINT_ARTIFACTS = {
    "intake": "brief.json",
    "strategy": "strategy.json",
    "critique": "proposal.md and proposal.pptx",
}


def answer_question(
    store: CampaignStore,
    campaign_id: str,
    question_id: str,
    *,
    text: str | None = None,
    defer_reason: str | None = None,
) -> Brief:
    if not text and not defer_reason:
        raise ValueError("Provide --text or --defer-reason.")
    brief = Brief.model_validate_json(store.read_artifact(campaign_id, "brief.json"))
    target = next((q for q in brief.open_questions if q.id == question_id), None)
    if target is None:
        known = ", ".join(q.id for q in brief.open_questions) or "(none)"
        raise KeyError(f"No question {question_id!r}. Known: {known}")
    if defer_reason:
        target.status = "deferred"
        target.defer_reason = defer_reason
        target.answer = None
    else:
        target.status = "answered"
        target.answer = text
        target.defer_reason = None
    store.write_artifact(campaign_id, "brief.json", brief.model_dump_json(indent=2))
    return brief


def format_status(meta, store: CampaignStore) -> str:
    lines = [
        f"Campaign: {meta.id}",
        *( [f"Revision of: {meta.revision_of}"] if meta.revision_of else [] ),
        f"Status:   {meta.status}",
        f"Stage:    {meta.current_stage}",
        f"Model:    {meta.model or '-'}",
    ]
    if meta.pause_reason:
        lines.append(f"Pause:    {meta.pause_reason}")
    if meta.status == "awaiting_agent":
        prompt = store.prompt_path(meta.id, meta.current_stage)
        lines.append(f"Prompt:   {prompt}")
    lines.append("Pipeline:")
    for name, state in meta.stages.items():
        extra = f"  attempts={state.attempts}"
        if state.last_errors:
            extra += f"  errors={state.last_errors[0]}"
        lines.append(f"  {name:<10} {state.status:<14}{extra}")
    if store.has_artifact(meta.id, "brief.json"):
        brief = Brief.model_validate_json(store.read_artifact(meta.id, "brief.json"))
        open_qs = [q for q in brief.open_questions if q.status == "unanswered"]
        if open_qs:
            lines.append("Open questions:")
            for q in open_qs:
                lines.append(f"  {q.id}: {q.question}")
    lines.extend(_next_action(meta, store))
    return "\n".join(lines) + "\n"


def _next_action(meta, store: CampaignStore) -> list[str]:
    """State the exact command that unblocks a paused campaign."""
    resume = f'python -m coo --store "{store.root}" resume {meta.id}'
    if meta.status == "awaiting_agent":
        stage = stages_for(meta).get(meta.current_stage)
        outputs = stage_outputs(stage, meta.quality_profile) if stage else ()
        return [
            "Next:",
            f"  write {', '.join(outputs)} to {store.artifacts_dir(meta.id)}",
            f"  {resume}",
        ]
    if meta.status == "awaiting_human":
        reason = meta.pause_reason or ""
        if reason.startswith("checkpoint:"):
            stage = reason.split(":", 1)[1]
            return [
                "Next:",
                f"  review {CHECKPOINT_ARTIFACTS.get(stage, 'the stage artifacts')} in {store.artifacts_dir(meta.id)}",
                f"  {resume} --approve",
            ]
        if reason.startswith("questions"):
            return ["Next:", f"  answer open questions, then {resume}"]
        return ["Next:", f"  resolve {reason or 'the open dependency'}, then {resume}"]
    if meta.status in {"failed", "escalated"}:
        retry = f"{resume} --override" if meta.status == "escalated" else resume
        return [
            "Next:",
            f"  fix {meta.current_stage} using prompts/{meta.current_stage}.md",
            f"  {retry}",
        ]
    if meta.status == "complete":
        missing = [
            name for name in ("proposal.docx", "proposal.pdf") if not store.has_artifact(meta.id, name)
        ]
        if missing:
            return [
                "Next:",
                f'  python -m coo --store "{store.root}" export {meta.id}',
                f"  (missing {', '.join(missing)})",
            ]
    return []

"""Stage runner: load skill, call LLM, write artifacts, enforce gates, pause for humans."""

from __future__ import annotations

from dataclasses import dataclass

from coo.citations.apa import assemble_proposal_file
from coo.config import Settings
from coo.gates.hard import GATES
from coo.llm import LLMClient, parse_files
from coo.orchestrator.context import assemble_context
from coo.orchestrator.graph import (
    StageDef,
    first_unpassed,
    next_stage,
    pipeline_for,
    stage_inputs,
    stage_outputs,
    stages_for,
)
from coo.orchestrator.handoff import merge_research_facts
from coo.paths import project_root
from coo.schemas.campaign import CampaignMeta
from coo.schemas.common import GateResult, fail
from coo.skill_loader import constitution, load_skill
from coo.slides.pptx import render_campaign_deck
from coo.store import CampaignStore, utc_now
import json

OUTPUT_PROTOCOL = """## Output protocol
Emit every required file in this exact form, with no commentary outside the blocks:

<<<FILE:filename>>>
file body
<<<END:filename>>>

Required files: {files}
If the file is JSON, emit valid JSON only inside the block.
"""


@dataclass
class RunResult:
    campaign_id: str
    status: str
    current_stage: str
    message: str
    gate_errors: list[str]


def _pretty(name: str, body: str) -> str:
    if name.endswith(".json"):
        parsed = json.loads(body)
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    return body


def _apply_stage_effects(store: CampaignStore, campaign_id: str, stage: StageDef) -> GateResult:
    try:
        if stage.name in {"write", "deliver", "critique"} and store.has_artifact(campaign_id, "proposal.md"):
            assemble_proposal_file(store, campaign_id)
        if stage.name in {"slides", "deliver", "critique"} and store.has_artifact(campaign_id, "slides.json"):
            render_campaign_deck(store, campaign_id)
    except Exception as exc:
        return fail(f"{stage.name} post-process failed: {exc}")
    return GateResult(passed=True)


def _gate(stage: StageDef, store: CampaignStore, campaign_id: str, settings: Settings) -> GateResult:
    fn = GATES[stage.gate]
    if stage.gate == "critique":
        return fn(store, campaign_id, threshold=settings.rubric_threshold)
    return fn(store, campaign_id)


def _save(store: CampaignStore, meta: CampaignMeta) -> None:
    store.save_meta(meta)


def _trace(store: CampaignStore, campaign_id: str, **event) -> None:
    event.setdefault("ts", utc_now())
    event.setdefault("campaign_id", campaign_id)
    store.append_trace(campaign_id, event)


def _hashes(store: CampaignStore, campaign_id: str, names: tuple[str, ...]) -> dict[str, str]:
    return {name: store.artifact_hash(campaign_id, name) for name in names if store.has_artifact(campaign_id, name)}


def _consume_checkpoint(meta: CampaignMeta) -> str:
    """Mark the completed checkpoint stage as approved and point at the next stage."""
    completed = meta.current_stage
    if completed not in meta.approvals:
        meta.approvals.append(completed)
    meta.pause_reason = None
    nxt = next_stage(completed, pipeline_for(meta))
    if nxt is None:
        meta.status = "complete"
        return "Campaign complete."
    meta.status = "ready"
    meta.current_stage = nxt.name
    return f"Approved {completed}; next stage is {nxt.name}."


def _result(meta: CampaignMeta, message: str, errors: list[str] | None = None) -> RunResult:
    return RunResult(
        campaign_id=meta.id,
        status=meta.status,
        current_stage=meta.current_stage,
        message=message,
        gate_errors=errors or [],
    )


def _workspace_block(store: CampaignStore, campaign_id: str, outputs: tuple[str, ...]) -> str:
    """Absolute paths and contracts for a coding agent that cannot guess the store root."""
    schema_dir = project_root() / "schemas"
    schemas = [
        schema_dir / f"{name.removesuffix('.json')}.json"
        for name in outputs
        if name.endswith(".json") and (schema_dir / f"{name.removesuffix('.json')}.json").is_file()
    ]
    lines = [
        "## Campaign workspace",
        f"Campaign directory: {store.campaign_dir(campaign_id)}",
        f"Write the required files here: {store.artifacts_dir(campaign_id)}",
    ]
    if schemas:
        lines.append("JSON Schema contracts (read before writing JSON):")
        lines.extend(f"- {path}" for path in schemas)
    lines.append(f'After writing, run: python -m coo --store "{store.root}" resume {campaign_id}')
    return "\n".join(lines)


def compose_prompt(store: CampaignStore, campaign_id: str, stage: StageDef, prior_errors: list[str] | None = None) -> str:
    outputs = stage_outputs(stage, store.load_meta(campaign_id).quality_profile)
    parts = [
        constitution(),
        f"Stage skill: {stage.skill}",
        f"Stage name: {stage.name}",
        "",
        load_skill(stage.skill),
        OUTPUT_PROTOCOL.format(files=", ".join(outputs)),
        "## Write these files",
        f"Save each required file under the campaign `artifacts/` directory: {', '.join(outputs)}",
        "Do not wrap the files in chat. The CLI will gate whatever is on disk.",
        "",
        _workspace_block(store, campaign_id, outputs),
        "",
        "## Context",
        assemble_context(store, campaign_id, stage),
    ]
    if prior_errors:
        parts.extend(
            [
                "## Previous gate errors",
                "Fix these issues. Do not skip required fields.",
                *[f"- {err}" for err in prior_errors],
            ]
        )
    return "\n".join(parts).rstrip() + "\n"


def _execute_agent_fill(
    store: CampaignStore,
    meta: CampaignMeta,
    stage: StageDef,
    llm: LLMClient,
    settings: Settings,
) -> GateResult:
    outputs = stage_outputs(stage, meta.quality_profile)
    inputs = stage_inputs(stage, meta.quality_profile)
    state = meta.stages[stage.name]
    state.attempts = max(state.attempts, 1)
    have_outputs = all(store.has_artifact(meta.id, name) for name in outputs)
    _save(store, meta)
    if have_outputs:
        effects = _apply_stage_effects(store, meta.id, stage)
        if not effects.passed:
            store.write_prompt(meta.id, stage.name, compose_prompt(store, meta.id, stage, effects.errors))
            return GateResult(passed=False, errors=effects.errors, needs_agent=True)
        result = _gate(stage, store, meta.id, settings)
        _trace(
            store,
            meta.id,
            stage=stage.name,
            skill=stage.skill,
            model=llm.model,
            action="agent_gate",
            attempts=state.attempts,
            gate_verdict="pass" if result.passed else "fail",
            needs_human=result.needs_human,
            errors=result.errors,
            input_hashes=_hashes(store, meta.id, inputs),
            output_paths=list(outputs),
        )
        if result.passed or result.needs_human:
            return result
        store.write_prompt(meta.id, stage.name, compose_prompt(store, meta.id, stage, result.errors))
        return GateResult(passed=False, errors=result.errors, needs_agent=True)

    store.write_prompt(meta.id, stage.name, compose_prompt(store, meta.id, stage))
    _trace(
        store,
        meta.id,
        stage=stage.name,
        skill=stage.skill,
        model=llm.model,
        action="agent_prompt",
        attempts=state.attempts,
        gate_verdict="wait",
        input_hashes=_hashes(store, meta.id, inputs),
        output_paths=list(outputs),
    )
    return GateResult(
        passed=False,
        errors=[f"Write {', '.join(outputs)} from prompts/{stage.name}.md then run resume."],
        needs_agent=True,
    )


def execute_stage(
    store: CampaignStore,
    meta: CampaignMeta,
    stage: StageDef,
    llm: LLMClient,
    settings: Settings,
    *,
    revalidate_only: bool = False,
) -> GateResult:
    outputs = stage_outputs(stage, meta.quality_profile)
    inputs = stage_inputs(stage, meta.quality_profile)
    state = meta.stages[stage.name]
    meta.model = llm.model
    meta.stub = settings.stub
    meta.status = "running"
    meta.current_stage = stage.name
    state.status = "running"
    _save(store, meta)

    if settings.agent_fill:
        return _execute_agent_fill(store, meta, stage, llm, settings)

    prior_errors: list[str] = []
    result = GateResult(passed=False, errors=["stage did not run"])

    if revalidate_only and all(store.has_artifact(meta.id, name) for name in outputs):
        effects = _apply_stage_effects(store, meta.id, stage)
        if not effects.passed:
            return effects
        result = _gate(stage, store, meta.id, settings)
        state.attempts = max(state.attempts, 1)
        _trace(
            store,
            meta.id,
            stage=stage.name,
            skill=stage.skill,
            model=llm.model,
            action="revalidate",
            attempts=state.attempts,
            gate_verdict="pass" if result.passed else "fail",
            needs_human=result.needs_human,
            errors=result.errors,
            input_hashes=_hashes(store, meta.id, inputs),
            output_paths=list(outputs),
        )
        if result.passed or result.needs_human:
            return result
        prior_errors = list(result.errors)

    constitution_text = constitution()
    skill_text = load_skill(stage.skill)

    for attempt in range(1, settings.max_retries + 1):
        state.attempts = attempt
        _save(store, meta)
        context = assemble_context(store, meta.id, stage)
        user_parts = [
            f"Stage skill: {stage.skill}",
            f"Stage name: {stage.name}",
            "",
            skill_text,
            OUTPUT_PROTOCOL.format(files=", ".join(outputs)),
            "## Context",
            context,
        ]
        if prior_errors:
            user_parts.extend(
                [
                    "## Previous gate errors",
                    "Fix these issues. Do not skip required fields.",
                    *[f"- {err}" for err in prior_errors],
                ]
            )
        raw = llm.complete(system=constitution_text, user="\n".join(user_parts))
        try:
            files = parse_files(raw, outputs)
            written = []
            for name, body in files.items():
                try:
                    body = _pretty(name, body)
                except json.JSONDecodeError:
                    pass
                store.write_artifact(meta.id, name, body)
                written.append(name)
        except ValueError as exc:
            result = GateResult(passed=False, errors=[str(exc)])
            prior_errors = result.errors
            _trace(
                store,
                meta.id,
                stage=stage.name,
                skill=stage.skill,
                model=llm.model,
                action="parse",
                attempts=attempt,
                gate_verdict="fail",
                errors=result.errors,
                input_hashes=_hashes(store, meta.id, inputs),
            )
            continue

        effects = _apply_stage_effects(store, meta.id, stage)
        if not effects.passed:
            result = effects
            prior_errors = result.errors
            _trace(
                store,
                meta.id,
                stage=stage.name,
                skill=stage.skill,
                model=llm.model,
                action="postprocess",
                attempts=attempt,
                gate_verdict="fail",
                errors=result.errors,
                input_hashes=_hashes(store, meta.id, inputs),
            )
            continue

        result = _gate(stage, store, meta.id, settings)
        _trace(
            store,
            meta.id,
            stage=stage.name,
            skill=stage.skill,
            model=llm.model,
            action="gate",
            attempts=attempt,
            gate_verdict="pass" if result.passed else "fail",
            needs_human=result.needs_human,
            errors=result.errors,
            warnings=result.warnings,
            input_hashes=_hashes(store, meta.id, inputs),
            output_paths=written,
        )
        if result.passed or result.needs_human:
            return result
        prior_errors = result.errors

    return result


def _mark_passed_and_maybe_checkpoint(store: CampaignStore, meta: CampaignMeta, stage: StageDef) -> RunResult:
    state = meta.stages[stage.name]
    state.status = "passed"
    state.gate_passed = True
    state.last_errors = []
    meta.current_stage = stage.name
    if stage.name == "research":
        merge_research_facts(store, meta.id)
    if stage.name in {"write", "deliver"} and store.has_artifact(meta.id, "proposal.md"):
        meta.proposal_hash_at_write = store.artifact_hash(meta.id, "proposal.md")
    if stage.name in {"slides", "deliver"} and store.has_artifact(meta.id, "slides.json"):
        meta.slides_hash_at_slides = store.artifact_hash(meta.id, "slides.json")
    if stage.checkpoint_after:
        meta.status = "awaiting_human"
        meta.pause_reason = f"checkpoint:{stage.name}"
        _save(store, meta)
        return _result(meta, f"Stage {stage.name} passed. Paused for human approval.")
    nxt = next_stage(stage.name, pipeline_for(meta))
    meta.status = "ready"
    if nxt is not None:
        meta.current_stage = nxt.name
    _save(store, meta)
    return _result(meta, f"Stage {stage.name} passed.")


def advance(
    store: CampaignStore,
    campaign_id: str,
    llm: LLMClient,
    settings: Settings,
    *,
    approve: bool = False,
    human_override: bool = False,
) -> RunResult:
    meta = store.load_meta(campaign_id)
    meta.model = llm.model
    meta.stub = settings.stub

    if meta.status == "complete":
        return _result(meta, "Campaign already complete.")

    if human_override:
        if not store.has_artifact(meta.id, "review.json"):
            return _result(meta, "Cannot override: review.json missing.")
        raw = json.loads(store.read_artifact(meta.id, "review.json"))
        raw["human_override"] = True
        raw["passed"] = True
        store.write_artifact(meta.id, "review.json", json.dumps(raw, indent=2))
        critique = stages_for(meta)["critique"]
        result = _gate(critique, store, meta.id, settings)
        _trace(store, meta.id, stage="critique", action="human_override", errors=result.errors)
        if result.passed:
            return _mark_passed_and_maybe_checkpoint(store, meta, critique)
        return _result(meta, "Human override set but critique gate still failed.", result.errors)

    if meta.status in {"failed", "escalated"}:
        meta.status = "ready"
        meta.pause_reason = None
        _save(store, meta)

    if meta.status == "awaiting_agent":
        meta.status = "ready"
        meta.pause_reason = None
        _save(store, meta)

    if meta.status == "awaiting_human":
        reason = meta.pause_reason or ""
        if reason.startswith("checkpoint:"):
            if not approve:
                return _result(meta, f"Paused for human approval after {meta.current_stage}. Re-run with --approve.")
            message = _consume_checkpoint(meta)
            _save(store, meta)
            _trace(store, meta.id, stage=meta.current_stage, action="approve", message=message)
            if meta.status == "complete":
                return _result(meta, message)
        elif reason.startswith("questions"):
            meta.status = "ready"
            meta.pause_reason = None
            _save(store, meta)
        elif not approve:
            return _result(meta, f"Paused: {reason or 'human input required'}.")

    while True:
        meta = store.load_meta(campaign_id)
        meta.model = llm.model
        meta.stub = settings.stub
        if meta.status in {"complete", "failed", "escalated", "awaiting_human"}:
            return _result(meta, meta.pause_reason or meta.status)

        stage = first_unpassed(meta.stages, pipeline_for(meta))
        if stage is None:
            meta.status = "complete"
            _save(store, meta)
            return _result(meta, "Campaign complete.")

        inputs = stage_inputs(stage, meta.quality_profile)
        outputs = stage_outputs(stage, meta.quality_profile)
        missing = [name for name in inputs if not store.has_artifact(meta.id, name)]
        if missing:
            meta.status = "failed"
            meta.pause_reason = f"missing inputs for {stage.name}: {', '.join(missing)}"
            _save(store, meta)
            return _result(meta, meta.pause_reason)

        revalidate = meta.stages[stage.name].status == "needs_human" and all(
            store.has_artifact(meta.id, name) for name in outputs
        )
        result = execute_stage(store, meta, stage, llm, settings, revalidate_only=revalidate)
        meta = store.load_meta(campaign_id)
        state = meta.stages[stage.name]
        state.last_errors = result.errors

        if result.needs_human:
            state.status = "needs_human"
            meta.status = "awaiting_human"
            meta.current_stage = stage.name
            meta.pause_reason = "questions: unanswered items in brief.json"
            _save(store, meta)
            return _result(meta, meta.pause_reason, result.errors)

        if result.needs_agent:
            state.status = "needs_agent"
            meta.status = "awaiting_agent"
            meta.current_stage = stage.name
            prompt = store.prompt_path(meta.id, stage.name)
            meta.pause_reason = f"agent_fill:{stage.name}"
            _save(store, meta)
            return _result(
                meta,
                f"Paused for coding-agent fill of {stage.name}. Write {', '.join(outputs)} using {prompt}, then run resume.",
                result.errors,
            )

        if not result.passed:
            if stage.retry_kind == "soft":
                state.status = "escalated"
                meta.status = "escalated"
                meta.pause_reason = "escalate: rubric did not pass after retries"
            else:
                state.status = "failed"
                meta.status = "failed"
                meta.pause_reason = f"failed: {stage.name} gate"
            _save(store, meta)
            return _result(meta, meta.pause_reason, result.errors)

        marked = _mark_passed_and_maybe_checkpoint(store, meta, stage)
        if marked.status == "awaiting_human":
            return marked

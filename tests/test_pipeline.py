from __future__ import annotations

import json

from coo.campaign_ops import answer_question
from coo.gates.rubric import DEFAULT_CRITERIA
from coo.llm import StubClient, _wrap
from coo.orchestrator.context import assemble_context
from coo.orchestrator.graph import LEGACY_STAGES, STAGES, stage_inputs, stage_outputs
from coo.orchestrator.runner import advance
from tests.factories import valid_measurement, valid_plan, valid_proposal


def _legacy_campaign(store, demand):
    meta = store.create(demand, stub=True, pipeline_version="legacy")
    meta.quality_profile = "legacy"
    store.save_meta(meta)
    return meta


def test_full_stub_pipeline_with_checkpoints(store, settings, stub_llm):
    meta = _legacy_campaign(store, "Launch Acme widgets to urban professionals in 12 weeks with a 100000 USD cap.")
    first = advance(store, meta.id, stub_llm, settings)
    assert first.status == "awaiting_human"
    assert store.load_meta(meta.id).pause_reason == "checkpoint:intake"
    assert store.has_artifact(meta.id, "brief.json")
    assert not store.has_artifact(meta.id, "strategy.json")

    blocked = advance(store, meta.id, stub_llm, settings)
    assert blocked.status == "awaiting_human"
    assert not store.has_artifact(meta.id, "situation.md")

    second = advance(store, meta.id, stub_llm, settings, approve=True)
    assert second.status == "awaiting_human"
    assert store.load_meta(meta.id).pause_reason == "checkpoint:strategy"
    assert store.has_artifact(meta.id, "strategy.json")
    assert not store.has_artifact(meta.id, "proposal.md")
    brief = json.loads(store.read_artifact(meta.id, "brief.json"))
    assert "coo:research_facts" in brief.get("notes", "")

    third = advance(store, meta.id, stub_llm, settings, approve=True)
    assert third.status == "awaiting_human"
    assert store.load_meta(meta.id).pause_reason == "checkpoint:critique"
    assert store.has_artifact(meta.id, "proposal.md")
    assert store.has_artifact(meta.id, "review.json")
    assert store.has_artifact(meta.id, "slides.json")
    assert store.has_artifact(meta.id, "proposal.pptx")
    proposal = store.read_artifact(meta.id, "proposal.md")
    assert "## References" in proposal
    assert "https://www.ama.org/marketing-news/" in proposal

    done = advance(store, meta.id, stub_llm, settings, approve=True)
    assert done.status == "complete"
    again = advance(store, meta.id, stub_llm, settings)
    assert again.status == "complete"
    traces = (store.campaign_dir(meta.id) / "traces" / "events.ndjson").read_text(encoding="utf-8").strip().splitlines()
    assert traces


def test_proposal_template_carries_current_budget_markers():
    from coo.paths import templates_dir

    text = (templates_dir() / "proposal.md").read_text(encoding="utf-8")
    assert "coo:budget_range" in text
    assert "coo:budget_complete" in text


def test_new_artifacts_are_required_only_for_evidence_v2_campaigns():
    assert stage_outputs(STAGES["plan"], "legacy") == ("plan.json", "measurement.json")
    assert stage_outputs(STAGES["plan"], "evidence_v2") == (
        "plan.json",
        "measurement.json",
        "operations.json",
    )
    assert stage_outputs(STAGES["deliver"], "evidence_v2") == (
        "proposal.md",
        "slides.json",
        "campaign_assets.json",
    )
    assert "operations.json" in stage_inputs(STAGES["deliver"], "evidence_v2")
    assert stage_outputs(LEGACY_STAGES["write"], "legacy") == ("proposal.md",)
    assert stage_outputs(LEGACY_STAGES["measure"], "legacy") == ("measurement.json",)
    assert "campaign_assets.json" not in stage_outputs(LEGACY_STAGES["write"], "legacy")


def test_evidence_v2_stub_pipeline_emits_operations_and_campaign_assets(store, settings, stub_llm):
    meta = store.create("Launch an evidence-led Acme campaign in Hong Kong.", stub=True)
    first = advance(store, meta.id, stub_llm, settings)
    assert first.status == "awaiting_human"
    assert advance(store, meta.id, stub_llm, settings, approve=True).status == "awaiting_human"
    final_review = advance(store, meta.id, stub_llm, settings, approve=True)
    assert final_review.status == "awaiting_human"
    assert store.has_artifact(meta.id, "operations.json")
    assert store.has_artifact(meta.id, "campaign_assets.json")
    assert store.has_artifact(meta.id, "proposal.pptx")
    completed = advance(store, meta.id, stub_llm, settings, approve=True)
    assert completed.status == "complete"


def test_open_question_then_answer(store, settings, stub_llm):
    meta = _legacy_campaign(store, "LEAVE_QUESTION Launch Acme to cities.")
    paused = advance(store, meta.id, stub_llm, settings)
    assert paused.status == "awaiting_human"
    assert "questions" in (store.load_meta(meta.id).pause_reason or "")
    answer_question(store, meta.id, "q_budget", defer_reason="Use the default 100000 cap")
    resumed = advance(store, meta.id, stub_llm, settings)
    assert resumed.status == "awaiting_human"
    assert store.load_meta(meta.id).pause_reason == "checkpoint:intake"


def test_context_hides_downstream_artifacts(store, settings, stub_llm):
    meta = _legacy_campaign(store, "Launch Acme.")
    advance(store, meta.id, stub_llm, settings)
    advance(store, meta.id, stub_llm, settings, approve=True)
    store.write_artifact(meta.id, "proposal.md", "secret downstream")
    text = assemble_context(store, meta.id, STAGES["plan"])
    assert "brief.json" in text
    assert "strategy.json" in text
    assert "secret downstream" not in text
    assert "proposal.md" not in text


def test_critique_retries_then_passes(store, settings):
    meta = _legacy_campaign(store, "Launch Acme widgets.")
    inner = StubClient()
    critique_calls = {"n": 0}

    class FlakyCritique:
        model = "flaky"

        def complete(self, *, system: str, user: str) -> str:
            if "Stage skill: coo-critique" in user:
                critique_calls["n"] += 1
                campaign_id = meta.id
                plan = valid_plan(campaign_id)
                measurement = valid_measurement(campaign_id)
                # Prefer artifacts already on disk once write has run.
                if store.has_artifact(campaign_id, "proposal.md"):
                    proposal = store.read_artifact(campaign_id, "proposal.md")
                else:
                    proposal = valid_proposal(plan, measurement)
                pattern = (
                    [2] * len(DEFAULT_CRITERIA)
                    if critique_calls["n"] == 1
                    else [5, 4, 5, 4, 5, 4, 4]
                )
                overall = sum(pattern) / len(pattern)
                review = {
                    "campaign_id": campaign_id,
                    "scores": [
                        {"criterion": name, "score": pattern[index], "comment": "test"}
                        for index, name in enumerate(DEFAULT_CRITERIA)
                    ],
                    "overall": overall,
                    "pass_threshold": 3.5,
                    "passed": overall >= 3.5,
                    "revision_notes": ["raise distinctiveness"] if critique_calls["n"] == 1 else [],
                    "human_override": False,
                }
                slides = store.read_artifact(campaign_id, "slides.json")
                return _wrap(
                    {
                        "review.json": json.dumps(review, indent=2),
                        "proposal.md": proposal,
                        "slides.json": slides,
                    }
                )
            return inner.complete(system=system, user=user)

    llm = FlakyCritique()
    advance(store, meta.id, llm, settings)
    advance(store, meta.id, llm, settings, approve=True)
    result = advance(store, meta.id, llm, settings, approve=True)
    assert result.status == "awaiting_human"
    assert store.load_meta(meta.id).pause_reason == "checkpoint:critique"
    assert critique_calls["n"] == 2
    review = json.loads(store.read_artifact(meta.id, "review.json"))
    assert review["overall"] > 3.5


def test_critique_escalates_then_human_override(store, settings):
    meta = _legacy_campaign(store, "Launch Acme widgets.")
    inner = StubClient()

    class AlwaysLow:
        model = "low"

        def complete(self, *, system: str, user: str) -> str:
            if "Stage skill: coo-critique" in user:
                proposal = store.read_artifact(meta.id, "proposal.md")
                review = {
                    "campaign_id": meta.id,
                    "scores": [
                        {"criterion": name, "score": 2, "comment": "thin"}
                        for name in DEFAULT_CRITERIA
                    ],
                    "overall": 2.0,
                    "pass_threshold": 3.5,
                    "passed": False,
                    "revision_notes": ["rewrite"],
                    "human_override": False,
                }
                slides = store.read_artifact(meta.id, "slides.json")
                return _wrap(
                    {
                        "review.json": json.dumps(review, indent=2),
                        "proposal.md": proposal,
                        "slides.json": slides,
                    }
                )
            return inner.complete(system=system, user=user)

    llm = AlwaysLow()
    advance(store, meta.id, llm, settings)
    advance(store, meta.id, llm, settings, approve=True)
    result = advance(store, meta.id, llm, settings, approve=True)
    assert result.status == "escalated"
    overridden = advance(store, meta.id, llm, settings, human_override=True)
    assert overridden.status == "awaiting_human"
    assert store.load_meta(meta.id).pause_reason == "checkpoint:critique"
    review = json.loads(store.read_artifact(meta.id, "review.json"))
    assert review["human_override"] is True

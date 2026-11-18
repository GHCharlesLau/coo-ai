from __future__ import annotations

from coo.gates.hard import (
    gate_critique,
    gate_intake,
    gate_measure,
    gate_plan,
    gate_research,
    gate_slides,
    gate_strategy,
    gate_write,
)
from coo.slides.pptx import render_campaign_deck
from tests.factories import (
    valid_brief,
    valid_deck,
    valid_evidence,
    valid_measurement,
    valid_plan,
    valid_proposal,
    valid_situation,
    valid_strategy,
    write_json,
)


def _seed_brief(store, demand="Launch Acme."):
    meta = store.create(demand, stub=True)
    # This suite captures compatibility behavior for pre-v2 campaign records.
    meta.quality_profile = "legacy"
    store.save_meta(meta)
    return meta


def _seed_write(store, meta):
    plan = valid_plan(meta.id)
    measurement = valid_measurement(meta.id)
    evidence = valid_evidence(meta.id)
    write_json(store, meta.id, "plan.json", plan)
    write_json(store, meta.id, "measurement.json", measurement)
    write_json(store, meta.id, "evidence.json", evidence)
    return plan, measurement, evidence


def test_intake_pauses_on_unanswered_questions(store):
    meta = _seed_brief(store)
    brief = valid_brief(meta.id)
    brief["open_questions"] = [
        {
            "id": "q_budget",
            "question": "Budget cap?",
            "status": "unanswered",
            "answer": None,
            "defer_reason": None,
        }
    ]
    write_json(store, meta.id, "brief.json", brief)
    result = gate_intake(store, meta.id)
    assert not result.passed
    assert result.needs_human


def test_intake_accepts_deferred_questions(store):
    meta = _seed_brief(store)
    brief = valid_brief(meta.id)
    brief["open_questions"] = [
        {
            "id": "q_budget",
            "question": "Budget cap?",
            "status": "deferred",
            "answer": None,
            "defer_reason": "Use default cap",
        }
    ]
    write_json(store, meta.id, "brief.json", brief)
    result = gate_intake(store, meta.id)
    assert result.passed


def test_intake_rejects_deferred_public_facts(store):
    meta = _seed_brief(store)
    brief = valid_brief(meta.id)
    brief["open_questions"] = [
        {
            "id": "q_host",
            "question": "Who is the 2026 host economy?",
            "status": "deferred",
            "answer": None,
            "defer_reason": "Look up later",
        }
    ]
    write_json(store, meta.id, "brief.json", brief)
    result = gate_intake(store, meta.id)
    assert not result.passed
    assert any("public look-uppable" in err for err in result.errors)


def test_research_requires_source_or_assumption(store):
    meta = _seed_brief(store)
    store.write_artifact(meta.id, "situation.md", valid_situation())
    evidence = valid_evidence(meta.id)
    evidence["items"][0]["source"] = None
    evidence["items"][0]["source_url"] = None
    evidence["items"][0]["author"] = None
    evidence["items"][0]["is_assumption"] = False
    write_json(store, meta.id, "evidence.json", evidence)
    result = gate_research(store, meta.id)
    assert not result.passed


def test_research_rejects_brief_as_source(store):
    meta = _seed_brief(store)
    store.write_artifact(meta.id, "situation.md", valid_situation())
    evidence = valid_evidence(meta.id)
    evidence["items"][0]["source"] = "this brief"
    evidence["items"][0]["source_url"] = "https://example.com/a"
    write_json(store, meta.id, "evidence.json", evidence)
    result = gate_research(store, meta.id)
    assert not result.passed
    assert any("brief is not an external source" in err for err in result.errors)


def test_research_rejects_too_many_assumptions(store):
    meta = _seed_brief(store)
    store.write_artifact(meta.id, "situation.md", valid_situation())
    evidence = valid_evidence(meta.id)
    for item in evidence["items"]:
        item["is_assumption"] = True
        item["source_url"] = None
    write_json(store, meta.id, "evidence.json", evidence)
    result = gate_research(store, meta.id)
    assert not result.passed
    assert any("assumptions" in err for err in result.errors)


def test_research_rejects_zero_urls(store):
    meta = _seed_brief(store)
    store.write_artifact(meta.id, "situation.md", valid_situation())
    evidence = valid_evidence(meta.id)
    for item in evidence["items"]:
        if not item["is_assumption"]:
            item["source_url"] = None
    write_json(store, meta.id, "evidence.json", evidence)
    result = gate_research(store, meta.id)
    assert not result.passed
    assert any("http source_url" in err for err in result.errors)


def test_research_rejects_sourced_item_missing_author(store):
    meta = _seed_brief(store)
    store.write_artifact(meta.id, "situation.md", valid_situation())
    evidence = valid_evidence(meta.id)
    evidence["items"][0]["author"] = None
    write_json(store, meta.id, "evidence.json", evidence)
    result = gate_research(store, meta.id)
    assert not result.passed
    assert any("missing author" in err for err in result.errors)


def test_research_accepts_valid_log(store):
    meta = _seed_brief(store)
    store.write_artifact(meta.id, "situation.md", valid_situation())
    write_json(store, meta.id, "evidence.json", valid_evidence(meta.id))
    result = gate_research(store, meta.id)
    assert result.passed


def test_strategy_must_link_all_objectives(store):
    meta = _seed_brief(store)
    write_json(store, meta.id, "brief.json", valid_brief(meta.id))
    strategy = valid_strategy(meta.id)
    strategy["objective_links"] = []
    write_json(store, meta.id, "strategy.json", strategy)
    result = gate_strategy(store, meta.id)
    assert not result.passed
    assert any("obj_awareness" in err for err in result.errors)


def test_strategy_rejects_leaked_channels(store):
    meta = _seed_brief(store)
    write_json(store, meta.id, "brief.json", valid_brief(meta.id))
    strategy = valid_strategy(meta.id)
    strategy["channels"] = ["tv"]
    write_json(store, meta.id, "strategy.json", strategy)
    result = gate_strategy(store, meta.id)
    assert not result.passed
    assert any("leaked" in err for err in result.errors)


def test_plan_requires_kpi_and_budget_line(store):
    meta = _seed_brief(store)
    plan = valid_plan(meta.id)
    plan["tactics"][0]["kpi_id"] = ""
    write_json(store, meta.id, "plan.json", plan)
    result = gate_plan(store, meta.id)
    assert not result.passed


def test_plan_budget_cannot_exceed_cap(store):
    meta = _seed_brief(store)
    plan = valid_plan(meta.id, cap=100000, extra_line=1)
    write_json(store, meta.id, "plan.json", plan)
    result = gate_plan(store, meta.id)
    assert not result.passed
    assert any("exceeds cap" in err for err in result.errors)


def test_plan_totals_pass_when_under_cap(store):
    meta = _seed_brief(store)
    write_json(store, meta.id, "plan.json", valid_plan(meta.id))
    result = gate_plan(store, meta.id)
    assert result.passed


def test_measure_requires_plan_kpi_ids_and_both_polarities(store):
    meta = _seed_brief(store)
    write_json(store, meta.id, "plan.json", valid_plan(meta.id))
    measurement = valid_measurement(meta.id)
    measurement["kpis"] = [k for k in measurement["kpis"] if k["id"] != "kpi_action"]
    write_json(store, meta.id, "measurement.json", measurement)
    result = gate_measure(store, meta.id)
    assert not result.passed
    assert any("kpi_action" in err for err in result.errors)


def test_write_requires_sections_and_matching_numbers(store):
    meta = _seed_brief(store)
    plan, measurement, evidence = _seed_write(store, meta)
    store.write_artifact(meta.id, "proposal.md", "# Hello\n")
    result = gate_write(store, meta.id)
    assert not result.passed

    store.write_artifact(meta.id, "proposal.md", valid_proposal(plan, measurement, evidence=evidence))
    result = gate_write(store, meta.id)
    assert result.passed, result.errors


def test_write_detects_budget_mismatch(store):
    meta = _seed_brief(store)
    plan, measurement, evidence = _seed_write(store, meta)
    text = valid_proposal(plan, measurement, evidence=evidence).replace(
        "coo:budget_total=100000", "coo:budget_total=1"
    )
    store.write_artifact(meta.id, "proposal.md", text)
    result = gate_write(store, meta.id)
    assert not result.passed
    assert any("budget_total" in err for err in result.errors)


def test_write_rejects_missing_references(store):
    meta = _seed_brief(store)
    plan, measurement, evidence = _seed_write(store, meta)
    text = valid_proposal(plan, measurement, evidence=evidence).split("## References")[0]
    store.write_artifact(meta.id, "proposal.md", text)
    result = gate_write(store, meta.id)
    assert not result.passed
    assert any("References" in err for err in result.errors)


def test_write_rejects_url_not_in_evidence(store):
    meta = _seed_brief(store)
    plan, measurement, evidence = _seed_write(store, meta)
    text = valid_proposal(plan, measurement, evidence=evidence) + "\nhttps://example.com/not-in-log\n"
    store.write_artifact(meta.id, "proposal.md", text)
    result = gate_write(store, meta.id)
    assert not result.passed
    assert any("not in evidence.json" in err for err in result.errors)


def test_write_rejects_in_text_without_evidence(store):
    meta = _seed_brief(store)
    plan, measurement, evidence = _seed_write(store, meta)
    text = valid_proposal(plan, measurement, evidence=evidence).replace(
        "(American Marketing Association, 2024)", "(Nobody, 1999)", 1
    )
    store.write_artifact(meta.id, "proposal.md", text)
    result = gate_write(store, meta.id)
    assert not result.passed
    assert any("in-text cite" in err for err in result.errors)


def test_slides_rejects_missing_pptx(store):
    meta = _seed_brief(store)
    plan, measurement, evidence = _seed_write(store, meta)
    write_json(store, meta.id, "slides.json", valid_deck(meta.id, plan, measurement, evidence))
    result = gate_slides(store, meta.id)
    assert not result.passed
    assert any("proposal.pptx" in err for err in result.errors)


def test_slides_rejects_too_few_slides(store):
    meta = _seed_brief(store)
    plan, measurement, evidence = _seed_write(store, meta)
    deck = valid_deck(meta.id, plan, measurement, evidence)
    deck["slides"] = deck["slides"][:3]
    write_json(store, meta.id, "slides.json", deck)
    render_campaign_deck(store, meta.id)
    result = gate_slides(store, meta.id)
    assert not result.passed
    assert any("at least 14 slides" in err for err in result.errors)


def test_slides_rejects_unknown_cite_id(store):
    meta = _seed_brief(store)
    plan, measurement, evidence = _seed_write(store, meta)
    deck = valid_deck(meta.id, plan, measurement, evidence)
    deck["slides"][2]["cite_ids"] = ["ev_missing"]
    write_json(store, meta.id, "slides.json", deck)
    render_campaign_deck(store, meta.id)
    result = gate_slides(store, meta.id)
    assert not result.passed
    assert any("unknown cite_ids" in err for err in result.errors)


def test_slides_rejects_budget_mismatch(store):
    meta = _seed_brief(store)
    plan, measurement, evidence = _seed_write(store, meta)
    deck = valid_deck(meta.id, plan, measurement, evidence)
    deck["budget_total"] = 1
    write_json(store, meta.id, "slides.json", deck)
    render_campaign_deck(store, meta.id)
    result = gate_slides(store, meta.id)
    assert not result.passed
    assert any("budget_total" in err for err in result.errors)


def test_slides_accepts_valid_deck(store):
    meta = _seed_brief(store)
    plan, measurement, evidence = _seed_write(store, meta)
    write_json(store, meta.id, "slides.json", valid_deck(meta.id, plan, measurement, evidence))
    render_campaign_deck(store, meta.id)
    result = gate_slides(store, meta.id)
    assert result.passed, result.errors


def test_lean_deck_requires_a_slide_per_tactic(store):
    meta = _seed_brief(store)
    plan, measurement, evidence = _seed_write(store, meta)
    deck = valid_deck(meta.id, plan, measurement, evidence)
    missing = plan["tactics"][-1]["name"]
    deck["slides"] = [slide for slide in deck["slides"] if slide["title"] != missing]
    write_json(store, meta.id, "slides.json", deck)
    render_campaign_deck(store, meta.id)
    result = gate_slides(store, meta.id)
    assert not result.passed
    assert any(f"slide for tactic" in error and missing in error for error in result.errors)


def test_lean_deck_rejects_three_consecutive_same_variant(store):
    meta = _seed_brief(store)
    plan, measurement, evidence = _seed_write(store, meta)
    deck = valid_deck(meta.id, plan, measurement, evidence)
    for slide in deck["slides"][2:5]:
        slide["variant"] = "rail"
    write_json(store, meta.id, "slides.json", deck)
    render_campaign_deck(store, meta.id)
    result = gate_slides(store, meta.id)
    assert not result.passed
    assert any("more than two consecutive slides" in error for error in result.errors)


def _seed_critique(store, meta, *, notes=None, scores=None):
    from coo.gates.rubric import DEFAULT_CRITERIA

    plan, measurement, evidence = _seed_write(store, meta)
    proposal = valid_proposal(plan, measurement, evidence=evidence)
    store.write_artifact(meta.id, "proposal.md", proposal)
    write_json(store, meta.id, "slides.json", valid_deck(meta.id, plan, measurement, evidence))
    render_campaign_deck(store, meta.id)
    meta.proposal_hash_at_write = store.artifact_hash(meta.id, "proposal.md")
    meta.slides_hash_at_slides = store.artifact_hash(meta.id, "slides.json")
    store.save_meta(meta)
    pattern = scores or [5, 4, 5, 4, 5, 4, 4]
    review = {
        "campaign_id": meta.id,
        "scores": [
            {"criterion": name, "score": pattern[index], "comment": "test"}
            for index, name in enumerate(DEFAULT_CRITERIA)
        ],
        "overall": sum(pattern) / len(pattern),
        "pass_threshold": 3.5,
        "passed": True,
        "revision_notes": notes or [],
        "human_override": False,
    }
    write_json(store, meta.id, "review.json", review)
    return proposal


def test_critique_rejects_uniform_scores(store):
    meta = _seed_brief(store)
    _seed_critique(store, meta, scores=[5, 5, 5, 5, 5, 5, 5])
    result = gate_critique(store, meta.id, threshold=3.5)
    assert not result.passed
    assert any("uniform" in err for err in result.errors)


def test_critique_rejects_unchanged_proposal_when_notes_exist(store):
    meta = _seed_brief(store)
    _seed_critique(store, meta, notes=["tighten the insight"], scores=[5, 3, 5, 4, 5, 4, 4])
    result = gate_critique(store, meta.id, threshold=3.5)
    assert not result.passed
    assert any("unchanged from write" in err for err in result.errors)

from __future__ import annotations

import io
import json

from pptx import Presentation
from pptx.util import Emu, Inches, Pt

from coo.gates.hard import (
    _deck_layout_errors,
    _proposal_depth_errors,
    gate_critique,
    gate_intake,
    gate_slides,
    gate_write,
)
from coo.gates.rubric import V2_CRITERIA
from coo.schemas.proposal import REQUIRED_SECTIONS
from coo.slides.pptx import render_campaign_deck
from tests.factories import (
    valid_brief,
    valid_campaign_assets,
    valid_deck,
    valid_evidence,
    valid_measurement,
    valid_operations,
    valid_plan,
    valid_proposal,
    write_json,
)


def _deep_proposal() -> str:
    body = " ".join(["Client evidence and decision detail."] * 20)
    sections = "\n\n".join(f"{heading}\n\n{body}" for heading in REQUIRED_SECTIONS)
    return f"# Campaign Proposal: Depth test\n\n{sections}\n"


def _seed_v3_write(
    store,
    *,
    stub: bool = False,
    proposal: str | None = None,
    pipeline_version: str = "legacy",
):
    meta = store.create("Launch Acme campaign", stub=True, pipeline_version=pipeline_version)
    meta.stub = stub
    store.save_meta(meta)
    plan = valid_plan(meta.id)
    measurement = valid_measurement(meta.id)
    evidence = valid_evidence(meta.id)
    write_json(store, meta.id, "brief.json", valid_brief(meta.id))
    write_json(store, meta.id, "plan.json", plan)
    write_json(store, meta.id, "measurement.json", measurement)
    write_json(store, meta.id, "evidence.json", evidence)
    write_json(store, meta.id, "operations.json", valid_operations(meta.id))
    write_json(store, meta.id, "campaign_assets.json", valid_campaign_assets(meta.id, plan))
    store.write_artifact(
        meta.id, "proposal.md", proposal or valid_proposal(plan, measurement, evidence=evidence)
    )
    return meta, plan, measurement, evidence


def _seed_v3_deck(store):
    meta = store.create("Launch Acme campaign", stub=True, pipeline_version="legacy")
    meta.stub = False
    store.save_meta(meta)
    plan = valid_plan(meta.id)
    for line in plan["budget_lines"]:
        line.update(
            {
                "low_amount": line["amount"],
                "high_amount": line["amount"],
                "estimate_status": "complete",
            }
        )
    measurement = valid_measurement(meta.id)
    evidence = valid_evidence(meta.id)
    write_json(store, meta.id, "plan.json", plan)
    write_json(store, meta.id, "measurement.json", measurement)
    write_json(store, meta.id, "evidence.json", evidence)
    deck = valid_deck(meta.id, plan, measurement, evidence)
    total = sum(line["amount"] for line in plan["budget_lines"])
    deck.update({"budget_low": total, "budget_high": total, "budget_complete": True})
    deck["slides"].insert(
        5,
        {
            "layout": "timeline",
            "title": "Timeline",
            "diagram": {
                "kind": "timeline",
                "nodes": [{"id": "n1", "label": "Start"}, {"id": "n2", "label": "End"}],
            },
        },
    )
    write_json(store, meta.id, "slides.json", deck)
    render_campaign_deck(store, meta.id)
    return meta


def _seed_review(store, meta, *, notes):
    pattern = [5, 4, 5, 4, 5, 4, 4, 4, 4]
    write_json(
        store,
        meta.id,
        "review.json",
        {
            "campaign_id": meta.id,
            "scores": [
                {"criterion": name, "score": pattern[index], "comment": "test"}
                for index, name in enumerate(V2_CRITERIA)
            ],
            "overall": sum(pattern) / len(pattern),
            "pass_threshold": 3.5,
            "passed": True,
            "revision_notes": notes,
            "human_override": False,
        },
    )


def test_proposal_depth_helper_uses_section_and_word_floors():
    assert _proposal_depth_errors(_deep_proposal(), min_section_chars=150, min_words=900) == []

    thin = "# Campaign Proposal: Thin\n\n" + "\n\n".join(
        f"{heading}\n\nOne short line." for heading in REQUIRED_SECTIONS
    )
    errors = _proposal_depth_errors(thin, min_section_chars=150, min_words=900)
    assert any("minimum 150" in error for error in errors)
    assert any("minimum 900" in error for error in errors)


def test_v3_write_gate_rejects_thin_proposal(store):
    meta, _, _, _ = _seed_v3_write(store)
    result = gate_write(store, meta.id)
    assert not result.passed
    assert any("minimum 150" in error for error in result.errors)
    assert any("minimum 900" in error for error in result.errors)


def test_v3_depth_floors_are_env_configurable(store, monkeypatch):
    monkeypatch.setenv("COO_MIN_SECTION_CHARS", "5000")
    monkeypatch.setenv("COO_MIN_PROPOSAL_WORDS", "0")
    meta, _, _, _ = _seed_v3_write(store)
    result = gate_write(store, meta.id)
    assert any("minimum 5000" in error for error in result.errors)


def test_stub_campaigns_keep_the_legacy_depth_floor(store):
    meta, _, _, _ = _seed_v3_write(store, stub=True)
    result = gate_write(store, meta.id)
    assert not any("minimum 150" in error for error in result.errors)
    assert not any("minimum 900" in error for error in result.errors)


def test_lean_pipeline_raises_depth_floors(store):
    meta, _, _, _ = _seed_v3_write(
        store, proposal=_deep_proposal(), pipeline_version="lean"
    )
    result = gate_write(store, meta.id)
    assert any("minimum 1400" in error for error in result.errors)


def test_lean_write_requires_per_tactic_detail(store):
    body = " ".join(["Client evidence and decision detail."] * 20)
    sections = []
    for heading in REQUIRED_SECTIONS:
        if "Tactic" in heading:
            sections.append(
                f"{heading}\n\n" + "\n".join([f"- Summary line {index}." for index in range(20)])
            )
        else:
            sections.append(f"{heading}\n\n{body}")
    proposal = "# Campaign Proposal: Tactic depth\n\n" + "\n\n".join(sections) + "\n"
    meta, _, _, _ = _seed_v3_write(store, proposal=proposal, pipeline_version="lean")
    result = gate_write(store, meta.id)
    assert any("cost link" in error and "tactic" in error for error in result.errors)


def test_v3_critique_requires_a_substantive_revision_note(store):
    meta = store.create("Launch Acme campaign", stub=True)
    meta.stub = False
    store.save_meta(meta)
    _seed_review(store, meta, notes=[])
    result = gate_critique(store, meta.id, threshold=3.5)
    assert any("substantive revision note" in error for error in result.errors)

    _seed_review(store, meta, notes=["tighten it"])
    result = gate_critique(store, meta.id, threshold=3.5)
    assert any("substantive revision note" in error for error in result.errors)


def test_stub_critique_is_exempt_from_the_note_requirement(store):
    meta = store.create("Launch Acme campaign", stub=True)
    _seed_review(store, meta, notes=[])
    result = gate_critique(store, meta.id, threshold=3.5)
    assert not any("substantive revision note" in error for error in result.errors)


def test_v3_slides_gate_rejects_layout_diagnostics(store, monkeypatch):
    meta = _seed_v3_deck(store)
    assert gate_slides(store, meta.id).passed, gate_slides(store, meta.id).errors
    monkeypatch.setattr(
        "coo.gates.hard._deck_layout_errors", lambda store, campaign_id: ["slide 1: test overflow"]
    )
    result = gate_slides(store, meta.id)
    assert not result.passed
    assert any("deck layout: slide 1: test overflow" in error for error in result.errors)


def test_design_visual_ratio_is_enforced(store):
    meta = _seed_v3_deck(store)
    deck = json.loads(store.read_artifact(meta.id, "slides.json"))
    deck["design"] = {"visual_ratio": 1.0}
    write_json(store, meta.id, "slides.json", deck)
    result = gate_slides(store, meta.id)
    assert not result.passed
    assert any("visual/data slides" in error for error in result.errors)


def test_deck_layout_helper_requires_editable_text(store):
    meta = store.create("Launch Acme campaign", stub=True)
    presentation = Presentation()
    presentation.slide_width = Emu(int(13.333 * 914400))
    presentation.slide_height = Emu(int(7.5 * 914400))
    presentation.slides.add_slide(presentation.slide_layouts[6])
    buffer = io.BytesIO()
    presentation.save(buffer)
    store.write_bytes(meta.id, "proposal.pptx", buffer.getvalue())

    diagnostics = _deck_layout_errors(store, meta.id)
    assert any("no editable text" in item for item in diagnostics)


def test_deck_layout_helper_accepts_native_text_slides(store):
    meta = store.create("Launch Acme campaign", stub=True)
    presentation = Presentation()
    presentation.slide_width = Emu(int(13.333 * 914400))
    presentation.slide_height = Emu(int(7.5 * 914400))
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(9), Inches(1))
    box.text_frame.text = "A real editable title"
    for paragraph in box.text_frame.paragraphs:
        for run in paragraph.runs:
            run.font.size = Pt(30)
    buffer = io.BytesIO()
    presentation.save(buffer)
    store.write_bytes(meta.id, "proposal.pptx", buffer.getvalue())

    assert _deck_layout_errors(store, meta.id) == []


def test_event_date_is_optional_for_brand_campaigns(store):
    meta = store.create("Launch Acme widgets to urban professionals.", stub=True)
    brief = valid_brief(meta.id)
    brief["intake_topics"].pop("event_date")
    write_json(store, meta.id, "brief.json", brief)
    assert gate_intake(store, meta.id).passed


def test_event_campaigns_must_name_a_date(store):
    meta = store.create("Host a summit launch event for Acme.", stub=True)
    brief = valid_brief(meta.id)
    brief["intake_topics"]["event_date"] = "not_applicable"
    write_json(store, meta.id, "brief.json", brief)
    result = gate_intake(store, meta.id)
    assert not result.passed
    assert any("event_date cannot be not_applicable" in error for error in result.errors)

    brief["intake_topics"].pop("event_date")
    write_json(store, meta.id, "brief.json", brief)
    result = gate_intake(store, meta.id)
    assert any("intake_topics.event_date" in error for error in result.errors)

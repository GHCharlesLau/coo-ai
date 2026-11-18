from __future__ import annotations

import json

from coo.budget import plan_range
from coo.gates.hard import gate_measure, gate_plan, gate_research
from coo.schemas.plan import Plan
from tests.factories import valid_operations, valid_situation


def _evidence(campaign_id: str, *, fx_value: float = 1.2) -> dict:
    items = []
    for index in range(1, 4):
        items.append({
            "id": f"ev{index}", "claim": f"Current market fact {index}.",
            "source": "Example Research", "source_url": f"https://example.com/{index}",
            "author": "Example Research", "year": "2026", "title": f"Fact {index}",
            "container": "Example", "is_assumption": False, "confidence": "high",
            "source_kind": "public", "checked_at": "2026-10-12", "geography": "Hong Kong",
            "applicable_period": "2026 campaign planning", "numeric_value": 100,
            "numeric_unit": "production day", "numeric_currency": "EUR",
        })
    items.append({
        "id": "fx_eur_usd", "claim": "EUR/USD daily reference rate.",
        "source": "Example FX source", "source_url": "https://example.com/fx",
        "author": "Example FX source", "year": "2026", "title": "FX reference",
        "container": "Example", "is_assumption": False, "confidence": "high",
        "source_kind": "public", "checked_at": "2026-10-12", "geography": "EUR/USD",
        "applicable_period": "2026-10-12", "numeric_value": fx_value,
        "numeric_unit": "EUR/USD",
    })
    return {"campaign_id": campaign_id, "items": items}


def _plan(campaign_id: str, *, cap: float = 3000) -> dict:
    return {
        "campaign_id": campaign_id, "channels": ["production"],
        "tactics": [{"id": "tac_a", "name": "Production", "channel": "production",
                     "description": "Create campaign assets", "kpi_id": "kpi_a",
                     "budget_line_id": "bl_a", "owner": "Team", "start": "2026-11",
                     "end": "2026-12"}],
        "timeline_start": "2026-11", "timeline_end": "2026-12", "budget_currency": "USD",
        "budget_cap": cap, "estimate_as_of": "2026-10-12",
        "budget_lines": [{"id": "bl_a", "label": "Production", "amount": 2400,
                          "low_amount": 2160, "high_amount": 2640, "estimate_status": "complete",
                          "components": [{"label": "Production days", "quantity": 20, "unit": "production day",
                                          "basis": "benchmark", "rate_currency": "EUR", "rate_low": 90,
                                          "rate_base": 100, "rate_high": 110, "range_rationale": "Supplier quotes vary by crew size.",
                                          "geography": "Hong Kong", "priced_on": "2026-10-12", "evidence_id": "ev1",
                                          "fx_to_budget": 1.2, "fx_evidence_id": "fx_eur_usd", "fx_date": "2026-10-12"}]}],
    }


def test_component_ranges_and_foreign_currency_provenance(store):
    meta = store.create("APEC campaign", stub=True)
    plan_data = _plan(meta.id)
    plan = Plan.model_validate(plan_data)
    result = plan_range(plan)
    assert (result.low, result.base, result.high, result.complete) == (2160, 2400, 2640, True)
    store.write_artifact(meta.id, "evidence.json", json.dumps(_evidence(meta.id)))
    store.write_artifact(meta.id, "operations.json", json.dumps(valid_operations(meta.id)))
    store.write_artifact(meta.id, "plan.json", json.dumps(plan_data))
    gate = gate_plan(store, meta.id)
    assert gate.passed, gate.errors


def test_budget_high_case_is_checked_against_cap(store):
    meta = store.create("APEC campaign", stub=True)
    plan = _plan(meta.id, cap=2500)
    store.write_artifact(meta.id, "evidence.json", json.dumps(_evidence(meta.id)))
    store.write_artifact(meta.id, "operations.json", json.dumps(valid_operations(meta.id)))
    store.write_artifact(meta.id, "plan.json", json.dumps(plan))
    gate = gate_plan(store, meta.id)
    assert not gate.passed
    assert any("high-case budget 2640.0 exceeds cap" in error for error in gate.errors)


def test_fx_rate_must_match_cited_source(store):
    meta = store.create("APEC campaign", stub=True)
    store.write_artifact(meta.id, "evidence.json", json.dumps(_evidence(meta.id, fx_value=1.15)))
    store.write_artifact(meta.id, "operations.json", json.dumps(valid_operations(meta.id)))
    store.write_artifact(meta.id, "plan.json", json.dumps(_plan(meta.id)))
    gate = gate_plan(store, meta.id)
    assert not gate.passed
    assert any("fx rate does not match" in error for error in gate.errors)


def test_assumption_rates_require_rationale_and_unpriced_items_name_quote():
    from pydantic import ValidationError
    from coo.schemas.plan import CostComponent

    base = {"label": "Media", "quantity": 1, "unit": "package", "basis": "assumption",
            "geography": "Hong Kong", "rate_low": 10, "rate_base": 20, "rate_high": 30,
            "range_rationale": "Assumes small pilot versus full launch."}
    try:
        CostComponent.model_validate(base)
    except ValidationError as exc:
        assert "assumption_rationale" in str(exc)
    else:
        raise AssertionError("assumption-only rate without a rationale was accepted")
    try:
        CostComponent.model_validate({"label": "Venue", "quantity": 1, "unit": "day",
                                     "basis": "unpriced", "geography": "Hong Kong"})
    except ValidationError as exc:
        assert "quote_needed" in str(exc)
    else:
        raise AssertionError("unpriced cost without a quote request was accepted")


def test_provisional_kpis_need_calibration_method(store):
    meta = store.create("APEC campaign", stub=True)
    plan = _plan(meta.id)
    from tests.factories import valid_brief, write_json
    write_json(store, meta.id, "brief.json", valid_brief(meta.id))
    store.write_artifact(meta.id, "plan.json", json.dumps(plan))
    measurement = {"campaign_id": meta.id, "reporting_cadence": "weekly",
                   "kpis": [{"id": "kpi_a", "name": "Qualified interest", "definition": "Qualified requests.",
                             "unit": "count", "target": "100", "polarity": "leading", "data_source": "CRM",
                             "cadence": "weekly", "target_status": "provisional"},
                            {"id": "kpi_b", "name": "Conversion", "definition": "Completed registrations.",
                             "unit": "count", "target": "50", "polarity": "lagging", "data_source": "CRM",
                             "cadence": "weekly", "target_status": "provisional", "calibration_method": "Set after a two-week baseline."}]}
    store.write_artifact(meta.id, "measurement.json", json.dumps(measurement))
    gate = gate_measure(store, meta.id)
    assert not gate.passed
    assert any("kpi_a: provisional target needs a calibration_method" in error for error in gate.errors)


def test_new_research_requires_dates_and_rejects_elapsed_work(store):
    meta = store.create("APEC campaign", stub=True)
    store.write_artifact(meta.id, "situation.md", valid_situation())
    evidence = _evidence(meta.id)
    evidence["items"][0]["checked_at"] = "not-a-date"
    store.write_artifact(meta.id, "evidence.json", json.dumps(evidence))
    gate = gate_research(store, meta.id)
    assert not gate.passed
    assert any("checked_at must be an ISO date" in error for error in gate.errors)

    plan = _plan(meta.id)
    plan["tactics"][0]["start"] = "2026-09"
    plan["tactics"][0]["end"] = "2026-12"
    store.write_artifact(meta.id, "evidence.json", json.dumps(_evidence(meta.id)))
    store.write_artifact(meta.id, "operations.json", json.dumps(valid_operations(meta.id)))
    store.write_artifact(meta.id, "plan.json", json.dumps(plan))
    plan_gate = gate_plan(store, meta.id)
    assert not plan_gate.passed
    assert any("elapsed start date" in error for error in plan_gate.errors)


def test_operations_gate_requires_compliance_and_countdown_coverage(store):
    meta = store.create("APEC event campaign", stub=True)
    store.write_artifact(meta.id, "evidence.json", json.dumps(_evidence(meta.id)))
    store.write_artifact(meta.id, "plan.json", json.dumps(_plan(meta.id)))
    operations = valid_operations(meta.id)
    operations["countdown"] = operations["countdown"][:-1]
    operations["compliance"] = [row for row in operations["compliance"] if row["area"] != "media_consent"]
    store.write_artifact(meta.id, "operations.json", json.dumps(operations))
    gate = gate_plan(store, meta.id)
    assert not gate.passed
    assert any("countdown must cover" in error for error in gate.errors)
    assert any("operations.compliance must include" in error for error in gate.errors)


def test_intake_requires_explicit_acknowledgement_of_unknown_topics(store):
    from coo.gates.hard import gate_intake
    from tests.factories import valid_brief, write_json

    meta = store.create("A campaign with a date yet to be set", stub=True)
    brief = valid_brief(meta.id)
    brief["intake_topics"]["event_date"] = "Not set; client to confirm before schedule approval."
    write_json(store, meta.id, "brief.json", brief)
    assert gate_intake(store, meta.id).passed
    brief["intake_topics"].pop("budget")
    write_json(store, meta.id, "brief.json", brief)
    gate = gate_intake(store, meta.id)
    assert not gate.passed
    assert any("intake_topics.budget" in error for error in gate.errors)


def test_media_scores_require_source_or_explicit_assumption():
    import pytest
    from pydantic import ValidationError
    from coo.schemas.operations import MediaDimension

    with pytest.raises(ValidationError, match="evidence_ids"):
        MediaDimension.model_validate({"score": 4, "basis": "High relevance", "basis_kind": "evidence"})
    assumed = MediaDimension.model_validate({
        "score": 3, "basis": "Small sample and provisional audience match.",
        "basis_kind": "assumption", "confidence": "low",
    })
    assert assumed.score == 3


def test_successor_run_reuses_demand_and_has_independent_trace(store):
    parent = store.create("Build an APEC campaign with realistic costs.", stub=True)
    parent_trace = store.campaign_dir(parent.id) / "traces" / "events.ndjson"
    parent_trace.write_text("parent event\n", encoding="utf-8")
    child = store.create(revision_of=parent.id, stub=True)
    assert child.revision_of == parent.id
    assert store.demand(child.id) == store.demand(parent.id)
    assert store.load_meta(parent.id).revision_of is None
    assert (store.campaign_dir(child.id) / "traces" / "events.ndjson").read_text(encoding="utf-8") == ""
    assert parent_trace.read_text(encoding="utf-8") == "parent event\n"


def test_new_requirements_do_not_change_stored_v2_records(store):
    from coo.schemas.campaign import CampaignMeta
    from coo.gates.hard import gate_intake
    from tests.factories import valid_brief, write_json

    meta = store.create("Legacy evidence-v2 brief", stub=True)
    old_record = meta.model_dump()
    old_record.pop("requirements_version")
    migrated = CampaignMeta.model_validate(old_record)
    assert migrated.requirements_version == 2
    migrated.requirements_version = 2
    store.save_meta(migrated)

    brief = valid_brief(meta.id)
    brief["intake_topics"].pop("blacklisted_terms")
    write_json(store, meta.id, "brief.json", brief)
    assert gate_intake(store, meta.id).passed


def test_v3_plan_gate_requires_complete_ropes_and_media_tier_classification(store):
    meta = store.create("APEC campaign", stub=True)
    operations = valid_operations(meta.id)
    operations["ropes"]["outcome_objectives"] = []
    store.write_artifact(meta.id, "evidence.json", json.dumps(_evidence(meta.id)))
    store.write_artifact(meta.id, "plan.json", json.dumps(_plan(meta.id)))
    store.write_artifact(meta.id, "operations.json", json.dumps(operations))
    gate = gate_plan(store, meta.id)
    assert not gate.passed
    assert any("ropes.outcome_objectives" in error for error in gate.errors)

    operations = valid_operations(meta.id)
    dimension = {"score": 4, "basis_kind": "evidence", "basis": "Current audience fit.", "evidence_ids": ["ev1"], "confidence": "high"}
    operations["media_coverage_status"] = "assessed"
    operations["media_klos"] = [{
        "name": "Sample business outlet", "kind": "media_outlet", "tier": "Tier 1", "audience": "Business readers",
        "tier_category": "unclassified", "tier_rationale": "",
        "relevance": dimension, "reach": dimension, "resonance": dimension, "risk_ethics": dimension,
        "selection_rationale": "Current reader fit.",
    }]
    store.write_artifact(meta.id, "operations.json", json.dumps(operations))
    gate = gate_plan(store, meta.id)
    assert not gate.passed
    assert any("needs a tier category and rationale" in error for error in gate.errors)


def test_v3_established_kpi_target_requires_explicit_baseline(store):
    meta = store.create("APEC campaign", stub=True)
    from tests.factories import valid_brief, valid_measurement, write_json

    brief = valid_brief(meta.id)
    measurement = valid_measurement(meta.id)
    for index, kpi in enumerate(measurement["kpis"]):
        kpi.update({
            "communication_tier": ("output", "outtake", "outcome")[index],
            "objective_ids": ["obj_awareness"],
            "target_status": "established",
            "target_evidence_ids": ["ev1"],
        })
    write_json(store, meta.id, "brief.json", brief)
    write_json(store, meta.id, "plan.json", _plan(meta.id))
    write_json(store, meta.id, "evidence.json", _evidence(meta.id))
    write_json(store, meta.id, "measurement.json", measurement)
    gate = gate_measure(store, meta.id)
    assert not gate.passed
    assert any("established target needs an explicit baseline" in error for error in gate.errors)


def test_v3_operations_requires_crisis_response_and_compliance_note(store):
    meta = store.create("APEC campaign", stub=True)
    operations = valid_operations(meta.id)
    operations["risks"][0]["immediate_pr_response"] = ""
    operations["compliance"][0]["notes"] = ""
    store.write_artifact(meta.id, "evidence.json", json.dumps(_evidence(meta.id)))
    store.write_artifact(meta.id, "plan.json", json.dumps(_plan(meta.id)))
    store.write_artifact(meta.id, "operations.json", json.dumps(operations))
    gate = gate_plan(store, meta.id)
    assert not gate.passed
    assert any("campaign risk is missing immediate_pr_response" in error for error in gate.errors)
    assert any("needs a jurisdiction and client/legal review note" in error for error in gate.errors)

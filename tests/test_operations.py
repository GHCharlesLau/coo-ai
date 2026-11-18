from __future__ import annotations

from coo.gates.hard import gate_write
from coo.schemas.operations import CampaignAssets
from tests.factories import (
    valid_brief,
    valid_campaign_assets,
    valid_evidence,
    valid_measurement,
    valid_operations,
    valid_plan,
    valid_proposal,
    write_json,
)

_campaign_assets = valid_campaign_assets


def test_campaign_assets_have_all_requested_structured_deliverables():
    plan = valid_plan("cmp-20261012-a1b2c3d4")
    assets = CampaignAssets.model_validate(_campaign_assets("cmp-20261012-a1b2c3d4", plan))
    assert len(assets.budget_ledger) == len(plan["budget_lines"])
    assert assets.social_calendar[0].post_copy.startswith("See the proof")


def test_write_gate_checks_campaign_ledger_reconciles_to_plan(store):
    meta = store.create("Launch Acme campaign", stub=True)
    plan = valid_plan(meta.id)
    measurement = valid_measurement(meta.id)
    evidence = valid_evidence(meta.id)
    brief = valid_brief(meta.id)
    assets = _campaign_assets(meta.id, plan)
    assets["budget_ledger"][0]["estimate_base"] = 39999
    write_json(store, meta.id, "brief.json", brief)
    write_json(store, meta.id, "plan.json", plan)
    write_json(store, meta.id, "measurement.json", measurement)
    write_json(store, meta.id, "evidence.json", evidence)
    write_json(store, meta.id, "operations.json", valid_operations(meta.id))
    write_json(store, meta.id, "campaign_assets.json", assets)
    store.write_artifact(meta.id, "proposal.md", valid_proposal(plan, measurement, evidence=evidence))

    result = gate_write(store, meta.id)
    assert not result.passed
    assert any("campaign budget ledger bl_content does not match plan estimates" in error for error in result.errors)


def test_v3_write_gate_requires_reviewed_faq_and_evaluation_coverage(store):
    meta = store.create("Launch Acme campaign", stub=True)
    plan = valid_plan(meta.id)
    measurement = valid_measurement(meta.id)
    evidence = valid_evidence(meta.id)
    brief = valid_brief(meta.id)
    assets = _campaign_assets(meta.id, plan)
    assets["issue_faq"][0]["approval_status"] = "draft"
    assets["post_campaign_evaluation"].pop()
    write_json(store, meta.id, "brief.json", brief)
    write_json(store, meta.id, "plan.json", plan)
    write_json(store, meta.id, "measurement.json", measurement)
    write_json(store, meta.id, "evidence.json", evidence)
    write_json(store, meta.id, "operations.json", valid_operations(meta.id))
    write_json(store, meta.id, "campaign_assets.json", assets)
    store.write_artifact(meta.id, "proposal.md", valid_proposal(plan, measurement, evidence=evidence))

    result = gate_write(store, meta.id)
    assert not result.passed
    assert any("must be labeled needs_client_review" in error for error in result.errors)
    assert any("must cover every campaign KPI" in error for error in result.errors)


def test_v3_forbidden_phrases_are_checked_across_campaign_copy(store):
    meta = store.create("Launch Acme campaign", stub=True)
    plan = valid_plan(meta.id)
    measurement = valid_measurement(meta.id)
    evidence = valid_evidence(meta.id)
    brief = valid_brief(meta.id)
    brief["forbidden_phrases"] = ["revolutionary"]
    assets = _campaign_assets(meta.id, plan)
    assets["social_calendar"][0]["copy"] = "A revolutionary way to choose."
    write_json(store, meta.id, "brief.json", brief)
    write_json(store, meta.id, "plan.json", plan)
    write_json(store, meta.id, "measurement.json", measurement)
    write_json(store, meta.id, "evidence.json", evidence)
    write_json(store, meta.id, "operations.json", valid_operations(meta.id))
    write_json(store, meta.id, "campaign_assets.json", assets)
    store.write_artifact(meta.id, "proposal.md", valid_proposal(plan, measurement, evidence=evidence))

    result = gate_write(store, meta.id)
    assert not result.passed
    assert any("forbidden brand association appears" in error for error in result.errors)


def test_docx_budget_ratios_are_not_market_rate_evidence():
    from coo.skill_loader import load_skill

    assert "Never use the DOCX's sample budget ratios as market-rate evidence" in load_skill("coo-plan")

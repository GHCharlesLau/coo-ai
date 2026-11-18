"""Deterministic quality gates. No LLM calls."""

from __future__ import annotations

import io
import json
import os
import re
from datetime import date
from math import ceil
from typing import Any

from pydantic import ValidationError

from coo.citations.apa import authors_match, extract_in_text_pairs, extract_reference_urls, sourced_items
from coo.budget import line_range, plan_range
from coo.schemas.brief import Brief
from coo.schemas.common import GateResult, fail, ok
from coo.schemas.evidence import EvidenceLog
from coo.schemas.measurement import Measurement
from coo.schemas.operations import CampaignAssets, OperationsPlan
from coo.schemas.plan import Plan
from coo.schemas.proposal import PROPOSAL_MARKERS, REQUIRED_SECTIONS
from coo.schemas.review import Review
from coo.schemas.slides import Deck
from coo.schemas.strategy import Strategy
from coo.store import CampaignStore
from coo.gates.rubric import V2_CRITERIA

FORBIDDEN_STRATEGY_KEYS = {
    "channels",
    "tactics",
    "budget",
    "budget_lines",
    "budget_cap",
    "media_mix",
    "media",
}

PUBLIC_FACT_RE = re.compile(
    r"\b(host economy|host city|host venue|summit host|meeting calendar|published calendar)\b",
    re.IGNORECASE,
)
BRIEF_AS_SOURCE_RE = re.compile(r"\b(brief\.json|the brief|this brief|campaign brief)\b", re.IGNORECASE)
SITUATION_HEADINGS = ("## category", "## audience", "## competitors", "## opportunity")
ID_LEAK_RE = re.compile(r"\b(?:tac_|obj_|kpi_|bl_|q_|ev_)[A-Za-z0-9_]+")
EVENT_SIGNAL_RE = re.compile(
    r"\b(?:event|summit|conference|convention|congress|festival|forum|expo|exhibition|trade show|"
    r"ceremony|awards?|gala|activation|roadshow|symposium|leaders'? week|host[- ]year|apec)\b",
    re.IGNORECASE,
)
EVENT_NOT_APPLICABLE = {"not_applicable", "not applicable", "n/a", "na", "none", "no event", "not an event"}
MIN_HTTP_SOURCES = 3
MIN_SECTION_CHARS = 40
MIN_V3_SECTION_CHARS = 150
MIN_V3_PROPOSAL_WORDS = 900
MIN_REVISION_NOTE_CHARS = 40
MIN_SLIDES = 10
MIN_LEAN_SECTION_CHARS = 200
MIN_LEAN_PROPOSAL_WORDS = 1400
MIN_LEAN_SLIDES = 14
ZIP_MAGIC = b"PK"


def _load_json(store: CampaignStore, campaign_id: str, name: str) -> Any:
    return json.loads(store.read_artifact(campaign_id, name))


def _validation_errors(exc: ValidationError) -> list[str]:
    return [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()]


def _requirements_v3(store: CampaignStore, campaign_id: str) -> bool:
    meta = store.load_meta(campaign_id)
    return meta.quality_profile == "evidence_v2" and meta.requirements_version >= 3


def _v3_quality_checks(store: CampaignStore, campaign_id: str) -> bool:
    """New quality floors apply to real requirements-v3 campaigns, not stub fixtures."""
    meta = store.load_meta(campaign_id)
    return _requirements_v3(store, campaign_id) and not meta.stub


def _is_lean(store: CampaignStore, campaign_id: str) -> bool:
    return store.load_meta(campaign_id).pipeline_version == "lean"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _is_event_campaign(store: CampaignStore, campaign_id: str, brief: Brief) -> bool:
    blob = " ".join(
        [store.demand(campaign_id), brief.title, brief.offer, brief.success_definition]
    )
    return bool(EVENT_SIGNAL_RE.search(blob))


def gate_intake(store: CampaignStore, campaign_id: str) -> GateResult:
    try:
        brief = Brief.model_validate(_load_json(store, campaign_id, "brief.json"))
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        return fail(f"brief.json is unreadable: {exc}")
    except ValidationError as exc:
        return fail(*_validation_errors(exc))

    errors: list[str] = []
    strict = store.load_meta(campaign_id).quality_profile == "evidence_v2"
    if brief.campaign_id != campaign_id:
        errors.append(f"brief.campaign_id {brief.campaign_id!r} != {campaign_id!r}")
    if not brief.title.strip():
        errors.append("title is empty")
    if not brief.brand.strip():
        errors.append("brand is empty")
    if not brief.offer.strip():
        errors.append("offer is empty")
    if not brief.success_definition.strip():
        errors.append("success_definition is empty")
    if not brief.audience.primary.strip():
        errors.append("audience.primary is empty")
    if not brief.objectives:
        errors.append("at least one objective is required")
    for obj in brief.objectives:
        if not obj.statement.strip():
            errors.append(f"objective {obj.id} has empty statement")
    if strict:
        event_like = _is_event_campaign(store, campaign_id, brief)
        required_topics = ["budget", "brand_guardrails", "key_competitors", "key_challenges"]
        if event_like:
            required_topics.insert(0, "event_date")
        if _requirements_v3(store, campaign_id):
            required_topics.append("blacklisted_terms")
        for topic in required_topics:
            if not (brief.intake_topics.get(topic) or "").strip():
                errors.append(f"intake_topics.{topic} must contain an answer or an explicit unknown/not-set response")
        event_date = (brief.intake_topics.get("event_date") or "").strip()
        if event_like and event_date.casefold() in EVENT_NOT_APPLICABLE:
            errors.append(
                "intake_topics.event_date cannot be not_applicable: the demand describes an event; "
                "give the date, a rebaseline, or an explicit unknown"
            )
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", event_date):
            try:
                if date.fromisoformat(event_date) < date.today() and not re.search(r"completed|rebaseline", brief.intake_topics.get("event_date", ""), re.IGNORECASE):
                    errors.append("campaign event date has elapsed; mark it completed or provide a rebaseline date")
            except ValueError:
                errors.append("intake_topics.event_date must be a valid ISO date when supplied as YYYY-MM-DD")

    unanswered = [q for q in brief.open_questions if q.status == "unanswered"]
    if unanswered:
        ids = ", ".join(q.id for q in unanswered)
        return GateResult(
            passed=False,
            errors=[*errors, f"unanswered questions must be answered or deferred: {ids}"],
            needs_human=True,
        )
    for question in brief.open_questions:
        if question.status == "answered" and not (question.answer or "").strip():
            errors.append(f"question {question.id} is answered but has no answer text")
        if question.status == "deferred" and not (question.defer_reason or "").strip():
            errors.append(f"question {question.id} is deferred but has no defer_reason")
        if question.status == "deferred" and PUBLIC_FACT_RE.search(question.question):
            errors.append(
                f"{question.id}: public look-uppable facts must not be deferred; leave them for research"
            )
    if errors:
        return fail(*errors)
    return ok()


def gate_research(store: CampaignStore, campaign_id: str) -> GateResult:
    if not store.has_artifact(campaign_id, "situation.md"):
        return fail("situation.md is missing")
    situation = store.read_artifact(campaign_id, "situation.md").strip()
    if len(situation) < 80:
        return fail("situation.md is too thin to count as a situation analysis")
    try:
        evidence = EvidenceLog.model_validate(_load_json(store, campaign_id, "evidence.json"))
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        return fail(f"evidence.json is unreadable: {exc}")
    except ValidationError as exc:
        return fail(*_validation_errors(exc))
    if evidence.campaign_id != campaign_id:
        return fail("evidence.campaign_id does not match campaign")
    if not evidence.items:
        return fail("evidence.json has no claims")
    errors: list[str] = []
    strict = store.load_meta(campaign_id).quality_profile == "evidence_v2"
    lower = situation.lower()
    for heading in SITUATION_HEADINGS:
        if heading not in lower:
            errors.append(f"situation.md missing {heading} heading")
    has_geo = bool(re.search(r"^##\s+(host|geography|market)\b", situation, re.IGNORECASE | re.MULTILINE))
    has_host_assumption = any(
        item.is_assumption
        and re.search(r"host unknown|geography unknown|market unknown", item.claim, re.IGNORECASE)
        for item in evidence.items
    )
    if not has_geo and not has_host_assumption:
        errors.append(
            "situation.md must name Host/Geography/Market or include an assumption that host/geography is unknown"
        )
    http_count = 0
    assumption_count = 0
    for item in evidence.items:
        if not item.claim.strip():
            errors.append(f"{item.id}: empty claim")
        if item.is_assumption:
            assumption_count += 1
            continue
        blob = " ".join(filter(None, [item.source, item.source_url, item.source_reference, item.container, item.title]))
        if BRIEF_AS_SOURCE_RE.search(blob):
            errors.append(f"{item.id}: brief is not an external source")
        if not (item.author or "").strip():
            errors.append(f"{item.id}: sourced claim missing author")
        if not (item.year or "").strip():
            errors.append(f"{item.id}: sourced claim missing year")
        if not (item.title or "").strip():
            errors.append(f"{item.id}: sourced claim missing title")
        url = (item.source_url or "").strip()
        if item.source_kind == "public":
            if not url.lower().startswith("http"):
                errors.append(f"{item.id}: sourced claim missing http source_url")
            else:
                http_count += 1
        elif not (item.source_reference or "").strip():
            errors.append(f"{item.id}: non-public evidence needs source_reference")
        if strict:
            if not (item.checked_at or "").strip():
                errors.append(f"{item.id}: missing checked_at")
            else:
                try:
                    checked = date.fromisoformat(item.checked_at)
                    if checked > date.today():
                        errors.append(f"{item.id}: checked_at is in the future")
                except ValueError:
                    errors.append(f"{item.id}: checked_at must be an ISO date")
            if not (item.geography or "").strip():
                errors.append(f"{item.id}: missing evidence geography")
            if not (item.applicable_period or "").strip():
                errors.append(f"{item.id}: missing applicable_period")
    if http_count < MIN_HTTP_SOURCES:
        errors.append(f"need at least {MIN_HTTP_SOURCES} http source_url values, found {http_count}")
    if evidence.items and assumption_count / len(evidence.items) > 0.5:
        errors.append(
            f"assumptions are {assumption_count}/{len(evidence.items)} of evidence; cap is 50%"
        )
    if errors:
        return fail(*errors)
    return ok()


def gate_strategy(store: CampaignStore, campaign_id: str) -> GateResult:
    raw = _load_json(store, campaign_id, "strategy.json")
    if not isinstance(raw, dict):
        return fail("strategy.json must be an object")
    leaked = sorted(FORBIDDEN_STRATEGY_KEYS.intersection(raw.keys()))
    if leaked:
        return fail(f"strategy leaked tactic fields: {', '.join(leaked)}")
    try:
        strategy = Strategy.model_validate(raw)
        brief = Brief.model_validate(_load_json(store, campaign_id, "brief.json"))
    except ValidationError as exc:
        return fail(*_validation_errors(exc))
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        return fail(str(exc))

    errors: list[str] = []
    if strategy.campaign_id != campaign_id:
        errors.append("strategy.campaign_id mismatch")
    if not strategy.insight.strip():
        errors.append("insight is empty")
    if not strategy.positioning.strip():
        errors.append("positioning is empty")
    if not strategy.big_idea.strip():
        errors.append("big_idea is empty")
    if len(strategy.message_house.pillars) < 2:
        errors.append("message_house needs at least two pillars")
    brief_ids = {obj.id for obj in brief.objectives}
    linked = set(strategy.objective_links)
    missing = sorted(brief_ids - linked)
    if missing:
        errors.append(f"strategy does not answer brief objectives: {', '.join(missing)}")
    unknown = sorted(linked - brief_ids)
    if unknown:
        errors.append(f"objective_links reference unknown ids: {', '.join(unknown)}")
    if errors:
        return fail(*errors)
    return ok()


def gate_plan(store: CampaignStore, campaign_id: str) -> GateResult:
    try:
        plan = Plan.model_validate(_load_json(store, campaign_id, "plan.json"))
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        return fail(f"plan.json is unreadable: {exc}")
    except ValidationError as exc:
        return fail(*_validation_errors(exc))

    errors: list[str] = []
    if plan.campaign_id != campaign_id:
        errors.append("plan.campaign_id mismatch")
    if not plan.tactics:
        errors.append("plan has no tactics")
    if not plan.budget_lines:
        errors.append("plan has no budget_lines")
    if not plan.channels:
        errors.append("plan has no channels")

    line_ids = {line.id for line in plan.budget_lines}
    if len(line_ids) != len(plan.budget_lines):
        errors.append("budget_line ids are not unique")
    tactic_ids = [t.id for t in plan.tactics]
    if len(set(tactic_ids)) != len(tactic_ids):
        errors.append("tactic ids are not unique")

    for tactic in plan.tactics:
        if not tactic.kpi_id.strip():
            errors.append(f"tactic {tactic.id} missing kpi_id")
        if not tactic.budget_line_id.strip():
            errors.append(f"tactic {tactic.id} missing budget_line_id")
        elif tactic.budget_line_id not in line_ids:
            errors.append(f"tactic {tactic.id} budget_line_id {tactic.budget_line_id} does not exist")
        if tactic.channel and tactic.channel not in plan.channels:
            errors.append(f"tactic {tactic.id} channel {tactic.channel!r} not in plan.channels")

    strict = store.load_meta(campaign_id).quality_profile == "evidence_v2"
    if strict:
        try:
            operations = OperationsPlan.model_validate(_load_json(store, campaign_id, "operations.json"))
        except (json.JSONDecodeError, FileNotFoundError) as exc:
            return fail(f"operations.json is unreadable: {exc}")
        except ValidationError as exc:
            return fail(*_validation_errors(exc))
        if operations.campaign_id != campaign_id:
            errors.append("operations.campaign_id mismatch")
        expected_phases = {"month_6", "month_3", "week_1", "day_1", "post_event"}
        actual_phases = {item.phase for item in operations.countdown}
        if actual_phases != expected_phases:
            errors.append("operations.countdown must cover month_6, month_3, week_1, day_1, and post_event")
        compliance_areas = {item.area for item in operations.compliance}
        expected_areas = {"local_law", "data_privacy", "media_consent", "influencer_disclosure", "claims_and_brand_safety", "event_safety"}
        if compliance_areas != expected_areas:
            errors.append("operations.compliance must include each required local-law, privacy, consent, disclosure, brand-safety, and event-safety check")
        if len(operations.compliance) != len(expected_areas):
            errors.append("operations.compliance must not duplicate review areas")
        for item in operations.compliance:
            if item.status == "confirmed_by_client" and not item.reviewer.strip():
                errors.append(f"compliance {item.area}: client-confirmed status needs a named reviewer")
        if not operations.run_of_show and not operations.run_of_show_note.strip():
            errors.append("operations must include a run of show or explain why timing is pending/not applicable")
        for row_index, row in enumerate(operations.run_of_show, start=1):
            for field in ("time", "duration", "activity", "on_stage_talent", "av_cues", "responsible_party"):
                if not getattr(row, field).strip():
                    errors.append(f"run_of_show row {row_index} is missing {field}")
        for person in operations.media_klos:
            if person.kind == "kol" and person.disclosure_required is None:
                errors.append(f"media/KOL profile {person.name}: disclosure_required must be assessed or explicitly marked unknown in notes")
        if _requirements_v3(store, campaign_id):
            ropes = operations.ropes
            for field in ("stakeholder_analysis", "objectives", "impact_objectives", "output_objectives", "outcome_objectives", "programming", "message_strategy", "pretesting", "monitoring", "evaluation", "stewardship"):
                if not any(item.strip() for item in getattr(ropes, field)):
                    errors.append(f"operations.ropes.{field} must describe the corresponding ROPES work or its pending calibration")
            for field in ("research", "programming_theme"):
                if not getattr(ropes, field).strip():
                    errors.append(f"operations.ropes.{field} must state the work or a pending client decision")
            if not operations.media_coverage_note.strip():
                errors.append("operations.media_coverage_note must explain the assessment or the outstanding client/research input")
            if not operations.media_klos and operations.media_coverage_status == "assessed":
                errors.append("media_coverage_status assessed requires at least one scored media/KOL profile")
            if operations.media_klos and operations.media_coverage_status != "assessed":
                errors.append("scored media/KOL profiles require media_coverage_status assessed")
            for person in operations.media_klos:
                if person.tier_category == "unclassified" or not person.tier_rationale.strip():
                    errors.append(f"media/KOL profile {person.name} needs a tier category and rationale")
                if not person.selection_rationale.strip():
                    errors.append(f"media/KOL profile {person.name} needs a selection rationale")
                for dimension_name in ("relevance", "reach", "resonance", "risk_ethics"):
                    dimension = getattr(person, dimension_name)
                    if not dimension.basis.strip():
                        errors.append(f"media/KOL profile {person.name}.{dimension_name} needs an evidence basis or an explicit not-assessed reason")
                if person.kind == "kol" and not person.disclosure_notes.strip():
                    errors.append(f"KOL profile {person.name} needs disclosure/risk notes")
            for index, milestone in enumerate(operations.countdown, start=1):
                if not milestone.owner.strip() or not any(task.strip() for task in milestone.tasks):
                    errors.append(f"countdown phase {milestone.phase} needs a named owner and at least one task")
            for item in operations.risks:
                for field in ("risk", "mitigation", "immediate_pr_response", "owner"):
                    if not getattr(item, field).strip():
                        errors.append(f"campaign risk is missing {field}")
            for item in operations.compliance:
                if not item.jurisdiction.strip() or not item.notes.strip():
                    errors.append(f"compliance {item.area} needs a jurisdiction and client/legal review note")
        try:
            evidence = EvidenceLog.model_validate(_load_json(store, campaign_id, "evidence.json"))
            evidence_ids = {item.id for item in evidence.items}
            evidence_by_id = {item.id: item for item in evidence.items}
            for person in operations.media_klos:
                for dimension_name in ("relevance", "reach", "resonance", "risk_ethics"):
                    dimension = getattr(person, dimension_name)
                    unknown = sorted(set(dimension.evidence_ids) - evidence_ids)
                    if unknown:
                        errors.append(f"media/KOL profile {person.name}.{dimension_name} cites unknown evidence: {', '.join(unknown)}")
                    if dimension.basis_kind == "evidence" and any(evidence_by_id[eid].is_assumption for eid in dimension.evidence_ids if eid in evidence_by_id):
                        errors.append(f"media/KOL profile {person.name}.{dimension_name} must not treat an assumption as sourced evidence")
        except (json.JSONDecodeError, FileNotFoundError, ValidationError):
            errors.append("operations media evidence could not be checked")
    total = sum(line.amount or 0 for line in plan.budget_lines)
    if any(line.amount is not None and line.amount < 0 for line in plan.budget_lines):
        errors.append("budget line amounts must be >= 0")
    warnings: list[str] = []
    if strict:
        try:
            evidence = EvidenceLog.model_validate(_load_json(store, campaign_id, "evidence.json"))
        except (json.JSONDecodeError, FileNotFoundError, ValidationError) as exc:
            return fail(f"budget evidence is unreadable: {exc}")
        evidence_by_id = {item.id: item for item in evidence.items}
        for line in plan.budget_lines:
            if not line.components:
                errors.append(f"{line.id}: new campaigns need a cost build-up or an explicit unpriced component")
                continue
            for component in line.components:
                if component.basis == "unpriced":
                    continue
                if not component.priced_on:
                    errors.append(f"{line.id}/{component.label}: priced component needs priced_on")
                if component.rate_currency != plan.budget_currency:
                    if component.fx_to_budget is None or component.fx_evidence_id not in evidence_by_id:
                        errors.append(f"{line.id}/{component.label}: foreign-currency rate needs a sourced FX rate")
                    if not component.fx_date:
                        errors.append(f"{line.id}/{component.label}: FX rate needs fx_date")
                elif component.fx_to_budget not in (None, 1, 1.0):
                    errors.append(f"{line.id}/{component.label}: same-currency component must use FX 1")
                if component.basis in {"published_rate", "benchmark", "client_quote"}:
                    source = evidence_by_id.get(component.evidence_id or "")
                    if source is None or source.is_assumption:
                        errors.append(f"{line.id}/{component.label}: pricing evidence_id must refer to a sourced evidence item")
                    elif component.basis == "client_quote" and source.source_kind != "client_quote":
                        errors.append(f"{line.id}/{component.label}: client_quote must use client_quote evidence")
                    elif component.basis != "client_quote" and source.source_kind != "public":
                        errors.append(f"{line.id}/{component.label}: public rate or benchmark must use public evidence")
                    elif source.numeric_value is None or source.numeric_unit != component.unit:
                        errors.append(f"{line.id}/{component.label}: pricing evidence must state the comparable numeric rate and unit")
                    elif abs(source.numeric_value - component.rate_base) > 0.01:
                        errors.append(f"{line.id}/{component.label}: base rate does not match its cited evidence")
                    elif source.numeric_currency != component.rate_currency:
                        errors.append(f"{line.id}/{component.label}: pricing evidence currency does not match the component")
                    if source and source.geography and source.geography.casefold() != component.geography.casefold():
                        errors.append(f"{line.id}/{component.label}: pricing geography differs from evidence")
                if component.fx_evidence_id:
                    fx_source = evidence_by_id.get(component.fx_evidence_id)
                    if fx_source is None or fx_source.is_assumption:
                        errors.append(f"{line.id}/{component.label}: fx_evidence_id must refer to sourced evidence")
                    elif fx_source.numeric_value is None or abs(fx_source.numeric_value - component.fx_to_budget) > 1e-8:
                        errors.append(f"{line.id}/{component.label}: fx rate does not match its cited evidence")
                    elif fx_source.numeric_unit not in {"FX", f"{component.rate_currency}/{plan.budget_currency}"}:
                        errors.append(f"{line.id}/{component.label}: FX evidence unit must identify the currency pair")
            expected = line_range(line, plan.budget_currency)
            if expected.base is None:
                if line.estimate_status != "unpriced":
                    errors.append(f"{line.id}: wholly unpriced line must be marked unpriced")
                if not (line.quote_needed or "").strip():
                    errors.append(f"{line.id}: unpriced line needs quote_needed")
                continue
            if line.amount is None or abs(line.amount - expected.base) > 0.01:
                errors.append(f"{line.id}: amount does not equal its base cost build-up ({expected.base})")
            if line.low_amount is None or abs(line.low_amount - expected.low) > 0.01:
                errors.append(f"{line.id}: low_amount does not equal its cost build-up ({expected.low})")
            if line.high_amount is None or abs(line.high_amount - expected.high) > 0.01:
                errors.append(f"{line.id}: high_amount does not equal its cost build-up ({expected.high})")
            has_unpriced = any(c.basis == "unpriced" for c in line.components)
            has_assumptions = any(c.basis == "assumption" for c in line.components)
            expected_status = "partial" if has_unpriced else ("assumption" if has_assumptions else "complete")
            if line.estimate_status != expected_status:
                errors.append(f"{line.id}: estimate_status should be {expected_status}")
            if has_unpriced and not (line.quote_needed or "").strip():
                errors.append(f"{line.id}: partial line must identify the quote needed")
        totals = plan_range(plan)
        if plan.budget_cap is not None:
            if not totals.complete:
                warnings.append("budget cap cannot be confirmed while one or more cost items remain unpriced")
            elif totals.high is not None and totals.high > plan.budget_cap + 1e-6:
                errors.append(f"high-case budget {totals.high} exceeds cap {plan.budget_cap}")
        if not totals.complete:
            warnings.append("budget totals are a priced subtotal; at least one quote remains outstanding")
    else:
        if any(line.amount is None for line in plan.budget_lines):
            errors.append("legacy budget lines require numeric amount")
        if plan.budget_cap is not None and total - plan.budget_cap > 1e-6:
            errors.append(f"budget lines total {total} exceeds cap {plan.budget_cap}")

    today = date.today().strftime("%Y-%m")
    for tactic in plan.tactics:
        if strict and (not re.fullmatch(r"\d{4}-\d{2}", tactic.start) or not re.fullmatch(r"\d{4}-\d{2}", tactic.end)):
            errors.append(f"{tactic.id}: tactic dates must use YYYY-MM")
        elif strict and tactic.end < tactic.start:
            errors.append(f"{tactic.id}: tactic end precedes start")
        elif strict and tactic.start < today and tactic.status == "planned":
            errors.append(f"{tactic.id}: elapsed start date must be marked in_progress/completed or rebaselined")
    if strict:
        for field, value in (("timeline_start", plan.timeline_start), ("timeline_end", plan.timeline_end)):
            if not re.fullmatch(r"\d{4}-\d{2}", value):
                errors.append(f"plan.{field} must use YYYY-MM")
        if plan.timeline_end < plan.timeline_start:
            errors.append("plan.timeline_end precedes timeline_start")
        if not plan.estimate_as_of:
            errors.append("plan.estimate_as_of is required for evidence-v2 budgets")
        else:
            try:
                if date.fromisoformat(plan.estimate_as_of) > date.today():
                    errors.append("plan.estimate_as_of cannot be in the future")
            except ValueError:
                errors.append("plan.estimate_as_of must be an ISO date")
        for line in plan.budget_lines:
            for component in line.components:
                if component.priced_on:
                    try:
                        if date.fromisoformat(component.priced_on) > date.today():
                            errors.append(f"{line.id}/{component.label}: priced_on cannot be in the future")
                    except ValueError:
                        errors.append(f"{line.id}/{component.label}: priced_on must be an ISO date")

    used_lines = {t.budget_line_id for t in plan.tactics if t.budget_line_id}
    unused = sorted(line_ids - used_lines)
    if unused:
        warnings.append(f"unused budget lines: {', '.join(unused)}")
    if errors:
        return fail(*errors)
    return ok(*warnings)


def gate_measure(store: CampaignStore, campaign_id: str) -> GateResult:
    strict = store.load_meta(campaign_id).quality_profile == "evidence_v2"
    try:
        measurement = Measurement.model_validate(_load_json(store, campaign_id, "measurement.json"))
        plan = Plan.model_validate(_load_json(store, campaign_id, "plan.json"))
        brief = Brief.model_validate(_load_json(store, campaign_id, "brief.json")) if strict else None
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        return fail(str(exc))
    except ValidationError as exc:
        return fail(*_validation_errors(exc))

    errors: list[str] = []
    if measurement.campaign_id != campaign_id:
        errors.append("measurement.campaign_id mismatch")
    if not measurement.kpis:
        errors.append("no KPIs defined")
    kpi_ids = {kpi.id for kpi in measurement.kpis}
    if len(kpi_ids) != len(measurement.kpis):
        errors.append("KPI ids are not unique")

    polarities = {kpi.polarity for kpi in measurement.kpis}
    if measurement.kpis and polarities != {"leading", "lagging"} and not (
        "leading" in polarities and "lagging" in polarities
    ):
        errors.append("KPIs must include both leading and lagging measures")
    if strict:
        tiers = {kpi.communication_tier for kpi in measurement.kpis}
        if tiers != {"output", "outtake", "outcome"}:
            errors.append("evidence-v2 measurement must include output, outtake, and outcome KPI tiers")
        objective_ids = {objective.id for objective in brief.objectives} if brief else set()
        covered_objectives: set[str] = set()
        for kpi in measurement.kpis:
            if not kpi.objective_ids:
                errors.append(f"KPI {kpi.id}: evidence-v2 measurement must link to at least one objective")
            unknown_objectives = sorted(set(kpi.objective_ids) - objective_ids)
            if unknown_objectives:
                errors.append(f"KPI {kpi.id}: unknown objective ids {', '.join(unknown_objectives)}")
            covered_objectives.update(kpi.objective_ids)
        missing_objectives = sorted(objective_ids - covered_objectives)
        if missing_objectives:
            errors.append(f"campaign objectives have no linked KPI: {', '.join(missing_objectives)}")

    for kpi in measurement.kpis:
        if not kpi.measurable:
            errors.append(f"KPI {kpi.id} is marked not measurable")
        if not kpi.definition.strip():
            errors.append(f"KPI {kpi.id} has empty definition")
        if not kpi.data_source.strip():
            errors.append(f"KPI {kpi.id} has empty data_source")
        if not kpi.unit.strip():
            errors.append(f"KPI {kpi.id} has empty unit")
        if not kpi.target.strip():
            errors.append(f"KPI {kpi.id} has empty target")
        if strict:
            if not kpi.communication_tier:
                errors.append(f"KPI {kpi.id}: evidence-v2 target must be classified as output, outtake, or outcome")
            if kpi.target_status == "established":
                if _requirements_v3(store, campaign_id) and not (kpi.baseline or "").strip():
                    errors.append(f"KPI {kpi.id}: established target needs an explicit baseline or comparison value")
                if not kpi.target_evidence_ids:
                    errors.append(f"KPI {kpi.id}: established target needs source evidence ids")
                else:
                    try:
                        evidence = EvidenceLog.model_validate(_load_json(store, campaign_id, "evidence.json"))
                        source_by_id = {item.id: item for item in evidence.items}
                        for evidence_id in kpi.target_evidence_ids:
                            source = source_by_id.get(evidence_id)
                            if source is None or source.is_assumption:
                                errors.append(f"KPI {kpi.id}: target evidence {evidence_id} is missing or an assumption")
                    except (json.JSONDecodeError, FileNotFoundError, ValidationError):
                        errors.append(f"KPI {kpi.id}: target evidence could not be checked")
            elif not (kpi.calibration_method or "").strip():
                errors.append(f"KPI {kpi.id}: provisional target needs a calibration_method")

    needed = {t.kpi_id for t in plan.tactics}
    missing = sorted(needed - kpi_ids)
    if missing:
        errors.append(f"measurement missing KPIs referenced by plan tactics: {', '.join(missing)}")
    if errors:
        return fail(*errors)
    return ok()


def _marker(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return match.group("value")


def _section_bodies(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for index, heading in enumerate(REQUIRED_SECTIONS):
        start = text.find(heading)
        if start < 0:
            continue
        start += len(heading)
        end = len(text)
        for nxt in REQUIRED_SECTIONS[index + 1 :]:
            pos = text.find(nxt, start)
            if pos >= 0:
                end = pos
                break
        found[heading] = text[start:end].strip()
    return found


def _client_copy(text: str) -> str:
    stripped = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return re.sub(r"```.*?```", "", stripped, flags=re.DOTALL)


def _word_count(text: str) -> int:
    """Count Latin words plus CJK characters so both scripts clear a meaningful floor."""
    latin = len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’._-]*", text))
    cjk = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text))
    return latin + cjk


def _proposal_depth_errors(
    text: str, *, min_section_chars: int, min_words: int
) -> list[str]:
    errors: list[str] = []
    sections = _section_bodies(text)
    for heading, body in sections.items():
        if heading == "## References":
            continue
        plain = _client_copy(body).strip()
        if len(plain) < min_section_chars:
            errors.append(
                f"{heading} is too thin ({len(plain)} chars; minimum {min_section_chars} for a client-ready proposal)"
            )
    body_text = "\n".join(
        _client_copy(body) for heading, body in sections.items() if heading != "## References"
    )
    words = _word_count(body_text)
    if min_words and words < min_words:
        errors.append(
            f"proposal body is {words} words; minimum {min_words} for a client-ready proposal"
        )
    return errors


def _lean_tactic_errors(text: str, plan: Plan) -> list[str]:
    """Each tactic must read as a standalone plan line, not summary prose."""
    sections = _section_bodies(text)
    body = next((part for heading, part in sections.items() if "tactic" in heading.casefold()), "")
    if not body:
        return ["proposal needs a Channel and Tactics section"]
    folded = _client_copy(body).casefold()
    label_by_id = {line.id: line.label for line in plan.budget_lines}
    errors: list[str] = []
    for tactic in plan.tactics:
        missing: list[str] = []
        if tactic.name.casefold() not in folded:
            missing.append("name")
        if tactic.owner.casefold() not in folded:
            missing.append("owner")
        channel_forms = {tactic.channel.casefold(), tactic.channel.replace("_", " ").casefold()}
        if not any(form in folded for form in channel_forms):
            missing.append("channel")
        if tactic.start.casefold() not in folded:
            missing.append("start")
        if tactic.end.casefold() not in folded:
            missing.append("end")
        label = label_by_id.get(tactic.budget_line_id)
        if label and label.casefold() not in folded:
            missing.append(f"cost link ({label})")
        if missing:
            errors.append(
                f"tactic {tactic.name!r} is missing {', '.join(missing)} in the tactics section"
            )
    return errors


def gate_write(store: CampaignStore, campaign_id: str) -> GateResult:
    if not store.has_artifact(campaign_id, "proposal.md"):
        return fail("proposal.md is missing")
    text = store.read_artifact(campaign_id, "proposal.md")
    errors = [f"missing section {heading}" for heading in REQUIRED_SECTIONS if heading not in text]
    try:
        plan = Plan.model_validate(_load_json(store, campaign_id, "plan.json"))
        measurement = Measurement.model_validate(_load_json(store, campaign_id, "measurement.json"))
    except (json.JSONDecodeError, FileNotFoundError, ValidationError) as exc:
        return fail(f"write gate needs valid plan and measurement: {exc}")

    strict = store.load_meta(campaign_id).quality_profile == "evidence_v2"
    if strict:
        try:
            assets = CampaignAssets.model_validate(_load_json(store, campaign_id, "campaign_assets.json"))
        except (json.JSONDecodeError, FileNotFoundError) as exc:
            return fail(f"campaign_assets.json is unreadable: {exc}")
        except ValidationError as exc:
            return fail(*_validation_errors(exc))
        if assets.campaign_id != campaign_id:
            errors.append("campaign_assets.campaign_id mismatch")
        line_by_id = {line.id: line for line in plan.budget_lines}
        ledger = {line.budget_line_id: line for line in assets.budget_ledger}
        if len(ledger) != len(assets.budget_ledger):
            errors.append("campaign budget ledger ids must be unique")
        if set(ledger) != set(line_by_id):
            errors.append("campaign budget ledger must include every plan budget line exactly once")
        for line_id, entry in ledger.items():
            line = line_by_id.get(line_id)
            if line is None:
                continue
            if entry.estimate_low != line.low_amount or entry.estimate_base != line.amount or entry.estimate_high != line.high_amount:
                errors.append(f"campaign budget ledger {line_id} does not match plan estimates")
            if entry.actual is not None and entry.status not in {"actual", "committed"}:
                errors.append(f"campaign budget ledger {line_id}: actual spend needs actual/committed status")
            if entry.actual is None and entry.status == "actual":
                errors.append(f"campaign budget ledger {line_id}: actual status needs an actual amount")
            if entry.currency != plan.budget_currency:
                errors.append(f"campaign budget ledger {line_id} currency differs from plan")
        if not assets.press_release.approval_note.strip():
            errors.append("press release must state its source/approval limitations")
        if _requirements_v3(store, campaign_id):
            required_copy = {
                "media_pitch.subject": assets.media_pitch.subject,
                "media_pitch.recipient_personalization": assets.media_pitch.recipient_personalization,
                "media_pitch.hook": assets.media_pitch.hook,
                "media_pitch.body": assets.media_pitch.body,
                "media_pitch.call_to_action": assets.media_pitch.call_to_action,
                "press_release.headline": assets.press_release.headline,
                "press_release.dateline": assets.press_release.dateline,
                "press_release.body": assets.press_release.body,
                "press_release.quote": assets.press_release.quote,
                "press_release.quote_attribution": assets.press_release.quote_attribution,
                "press_release.boilerplate": assets.press_release.boilerplate,
            }
            for field, value in required_copy.items():
                if not value.strip():
                    errors.append(f"campaign_assets.{field} must not be empty; record the client-owned input needed if unknown")
            for index, faq in enumerate(assets.issue_faq, start=1):
                if not faq.question.strip() or not faq.answer.strip():
                    errors.append(f"issue FAQ item {index} needs both a question and an answer or an explicit pending-input note")
            for index, post in enumerate(assets.social_calendar, start=1):
                for field in ("date_or_phase", "platform", "post_copy", "visual_cue"):
                    if not getattr(post, field).strip():
                        errors.append(f"social calendar item {index} is missing {field}")
            for index, faq in enumerate(assets.issue_faq, start=1):
                if faq.approval_status == "draft":
                    errors.append(f"issue FAQ answer {index} must be labeled needs_client_review until approved")
                if faq.approval_status == "approved" and not (faq.approved_by or "").strip():
                    errors.append(f"issue FAQ answer {index} marked approved needs an approver name")
        try:
            operation = OperationsPlan.model_validate(_load_json(store, campaign_id, "operations.json"))
            measurement = Measurement.model_validate(_load_json(store, campaign_id, "measurement.json"))
            brief = Brief.model_validate(_load_json(store, campaign_id, "brief.json"))
            kpi_ids = {kpi.id for kpi in measurement.kpis}
            objective_ids = {objective.id for objective in brief.objectives}
            if not assets.post_campaign_evaluation:
                errors.append("post_campaign_evaluation must not be empty")
            if _requirements_v3(store, campaign_id):
                evaluated_kpis = {item.kpi_id for item in assets.post_campaign_evaluation}
                evaluated_objectives = {item.objective_id for item in assets.post_campaign_evaluation}
                if evaluated_kpis != kpi_ids:
                    errors.append("post_campaign_evaluation must cover every campaign KPI")
                if evaluated_objectives != objective_ids:
                    errors.append("post_campaign_evaluation must cover every campaign objective")
            for item in assets.post_campaign_evaluation:
                if item.kpi_id not in kpi_ids:
                    errors.append(f"evaluation outline references unknown KPI {item.kpi_id}")
                if item.objective_id not in objective_ids:
                    errors.append(f"evaluation outline references unknown objective {item.objective_id}")
            if not operation.risks:
                errors.append("campaign operations need at least one risk review")
            brief_copy = " ".join([
                text,
                assets.media_pitch.subject,
                assets.media_pitch.hook,
                assets.media_pitch.body,
                assets.press_release.headline,
                assets.press_release.body,
                " ".join(faq.question + " " + faq.answer for faq in assets.issue_faq),
                " ".join(post.post_copy + " " + post.visual_cue for post in assets.social_calendar),
            ]).casefold()
            forbidden_phrases = [*brief.forbidden_associations, *brief.forbidden_phrases]
            for forbidden in forbidden_phrases:
                if forbidden.strip() and forbidden.casefold() in brief_copy:
                    errors.append(f"forbidden brand association appears in client copy: {forbidden}")
        except (json.JSONDecodeError, FileNotFoundError, ValidationError) as exc:
            errors.append(f"campaign asset cross-check failed: {exc}")
    totals = plan_range(plan) if strict else None
    total = totals.base if totals else sum(line.amount or 0 for line in plan.budget_lines)
    raw_total = _marker(PROPOSAL_MARKERS["budget_total"], text)
    raw_range = _marker(PROPOSAL_MARKERS["budget_range"], text)
    raw_complete = _marker(PROPOSAL_MARKERS["budget_complete"], text)
    raw_ccy = _marker(PROPOSAL_MARKERS["budget_currency"], text)
    raw_kpis = _marker(PROPOSAL_MARKERS["kpi_ids"], text)
    raw_tactics = _marker(PROPOSAL_MARKERS["tactic_ids"], text)
    if raw_total is None:
        errors.append("proposal missing <!-- coo:budget_total=... -->")
    else:
        try:
            if total is None or abs(float(raw_total) - total) > 0.01:
                errors.append(f"proposal budget_total {raw_total} != plan total {total}")
        except ValueError:
            errors.append("coo:budget_total is not a number")
    if raw_ccy is None:
        errors.append("proposal missing <!-- coo:budget_currency=... -->")
    elif raw_ccy != plan.budget_currency:
        errors.append(f"proposal currency {raw_ccy} != plan {plan.budget_currency}")
    if strict:
        if raw_range is None:
            errors.append("proposal missing <!-- coo:budget_range=LOW,BASE,HIGH -->")
        else:
            try:
                values = [float(part) for part in raw_range.split(",")]
                expected = [totals.low, totals.base, totals.high]
                if len(values) != 3 or any(value is None for value in expected) or any(abs(value - target) > 0.01 for value, target in zip(values, expected)):
                    errors.append("proposal budget_range does not match calculated plan range")
            except ValueError:
                errors.append("coo:budget_range must contain low,base,high numbers")
        if raw_complete is None or (raw_complete == "true") != totals.complete:
            errors.append("proposal budget_complete marker does not match the plan")

    expected_kpis = {kpi.id for kpi in measurement.kpis}
    if raw_kpis is None:
        errors.append("proposal missing <!-- coo:kpi_ids=... -->")
    else:
        listed = {item for item in raw_kpis.split(",") if item}
        if listed != expected_kpis:
            errors.append(f"proposal kpi_ids {sorted(listed)} != measurement {sorted(expected_kpis)}")

    expected_tactics = {t.id for t in plan.tactics}
    if raw_tactics is None:
        errors.append("proposal missing <!-- coo:tactic_ids=... -->")
    else:
        listed_t = {item for item in raw_tactics.split(",") if item}
        if listed_t != expected_tactics:
            errors.append(f"proposal tactic_ids {sorted(listed_t)} != plan {sorted(expected_tactics)}")

    copy = _client_copy(text)
    if "evidence.json" in copy:
        errors.append("proposal must not send the reader to evidence.json")
    leaked = sorted(set(ID_LEAK_RE.findall(copy)))
    if leaked:
        errors.append(f"proposal leaks artifact ids into client copy: {', '.join(leaked)}")
    deep = _v3_quality_checks(store, campaign_id)
    for heading, body in _section_bodies(text).items():
        if deep and heading != "## References":
            continue
        plain = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL).strip()
        if len(plain) < MIN_SECTION_CHARS:
            errors.append(
                f"{heading} is too thin ({len(plain)} chars; minimum {MIN_SECTION_CHARS} for a client-ready proposal)"
            )
    if deep:
        lean = _is_lean(store, campaign_id)
        errors.extend(
            _proposal_depth_errors(
                text,
                min_section_chars=_env_int(
                    "COO_MIN_SECTION_CHARS",
                    MIN_LEAN_SECTION_CHARS if lean else MIN_V3_SECTION_CHARS,
                ),
                min_words=_env_int(
                    "COO_MIN_PROPOSAL_WORDS",
                    MIN_LEAN_PROPOSAL_WORDS if lean else MIN_V3_PROPOSAL_WORDS,
                ),
            )
        )
        if lean:
            errors.extend(_lean_tactic_errors(text, plan))

    try:
        evidence = EvidenceLog.model_validate(_load_json(store, campaign_id, "evidence.json"))
    except (json.JSONDecodeError, FileNotFoundError, ValidationError) as exc:
        errors.append(f"write gate needs valid evidence.json: {exc}")
        return fail(*errors)

    sourced = sourced_items(evidence)
    source_urls = [
        (item.source_url or "").strip()
        for item in sourced
        if item.source_kind == "public" and (item.source_url or "").strip()
    ]
    ref_urls = extract_reference_urls(text)
    missing_urls = [url for url in source_urls if url not in ref_urls]
    if missing_urls:
        errors.append(f"References missing evidence URLs: {', '.join(missing_urls)}")
    extra_urls = [url for url in ref_urls if url not in source_urls]
    if extra_urls:
        errors.append(f"References URLs not in evidence.json: {', '.join(extra_urls)}")
    pairs = extract_in_text_pairs(text)
    cited_ids: set[str] = set()
    for author, year in pairs:
        match = next(
            (
                item
                for item in sourced
                if authors_match(author, item.author or "") and (item.year or "").strip() == year
            ),
            None,
        )
        if match is None:
            errors.append(f"in-text cite ({author}, {year}) has no matching evidence item")
        else:
            cited_ids.add(match.id)
    uncited = [item.id for item in sourced if item.id not in cited_ids]
    if uncited:
        errors.append(f"sourced evidence is not cited in the proposal: {', '.join(uncited)}")
    if len(cited_ids) < MIN_HTTP_SOURCES:
        errors.append(f"need at least {MIN_HTTP_SOURCES} checkable in-text citations")

    if errors:
        return fail(*errors)
    return ok()


def _deck_layout_errors(store: CampaignStore, campaign_id: str) -> list[str]:
    """Verify the deck is native, editable PowerPoint rather than a picture book.

    Every slide must carry editable text, must not consist of a single
    full-slide picture, and must not contain speaker notes or internal notes.
    """
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs = Presentation(io.BytesIO(store.read_bytes(campaign_id, "proposal.pptx")))
    diagnostics: list[str] = []
    if not prs.slides:
        return ["deck has no slides"]
    width, height = prs.slide_width, prs.slide_height
    if not width or not height or abs(width / height - 16 / 9) > 0.02:
        diagnostics.append("deck is not a 16:9 widescreen presentation")
    if store.has_artifact(campaign_id, "slides.json"):
        try:
            expected = len(Deck.model_validate_json(store.read_artifact(campaign_id, "slides.json")).slides)
        except Exception:  # noqa: BLE001 - the deck schema gate reports this separately
            expected = 0
        if expected and len(prs.slides) != expected:
            diagnostics.append(f"deck has {len(prs.slides)} slides but slides.json has {expected}")
    for index, slide in enumerate(prs.slides, start=1):
        shapes = list(slide.shapes)
        text_shapes = [
            shape
            for shape in shapes
            if shape.has_text_frame and shape.text_frame.text.strip()
        ]
        editable_chars = sum(len(shape.text_frame.text.strip()) for shape in text_shapes)
        if not text_shapes:
            diagnostics.append(f"slide {index}: has no editable text")
        elif editable_chars < 12:
            diagnostics.append(f"slide {index}: editable text is too sparse to be a real slide")
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            diagnostics.append(f"slide {index}: contains speaker notes")
        pictures = [shape for shape in shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE]
        full_bleed = [
            picture
            for picture in pictures
            if (picture.left or 0) <= 0
            and (picture.top or 0) <= 0
            and width
            and height
            and picture.width
            and picture.height
            and picture.width >= width * 0.98
            and picture.height >= height * 0.98
        ]
        if full_bleed and len(text_shapes) <= 2:
            diagnostics.append(f"slide {index}: is a full-slide image, not an editable layout")
    return diagnostics


def _lean_slide_errors(deck: Deck, plan: Plan) -> list[str]:
    """Lean decks must cover every tactic and rotate composition variants."""
    from coo.slides.variants import resolve_variant

    errors: list[str] = []
    titles = [slide.title.casefold() for slide in deck.slides]
    for tactic in plan.tactics:
        if not any(tactic.name.casefold() in title for title in titles):
            errors.append(f"deck needs a slide for tactic {tactic.id} ({tactic.name})")
    run_variant: str | None = None
    run_length = 0
    for index, slide in enumerate(deck.slides):
        if slide.layout in {"title", "section"}:
            run_variant, run_length = None, 0
            continue
        variant = resolve_variant(slide, index, deck.design)
        if variant == run_variant:
            run_length += 1
        else:
            run_variant, run_length = variant, 1
        if run_length > 2:
            errors.append(
                "deck repeats the same composition variant on more than two consecutive slides"
            )
            break
    return errors


def gate_slides(store: CampaignStore, campaign_id: str) -> GateResult:
    if not store.has_artifact(campaign_id, "slides.json"):
        return fail("slides.json is missing")
    try:
        deck = Deck.model_validate(_load_json(store, campaign_id, "slides.json"))
        plan = Plan.model_validate(_load_json(store, campaign_id, "plan.json"))
        measurement = Measurement.model_validate(_load_json(store, campaign_id, "measurement.json"))
        evidence = EvidenceLog.model_validate(_load_json(store, campaign_id, "evidence.json"))
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        return fail(str(exc))
    except ValidationError as exc:
        return fail(*_validation_errors(exc))

    meta = store.load_meta(campaign_id)
    lean = meta.pipeline_version == "lean"
    errors: list[str] = []
    if deck.campaign_id != campaign_id:
        errors.append("slides.campaign_id mismatch")
    minimum_slides = MIN_LEAN_SLIDES if lean else MIN_SLIDES
    if len(deck.slides) < minimum_slides:
        errors.append(f"need at least {minimum_slides} slides, found {len(deck.slides)}")
    layouts = {slide.layout for slide in deck.slides}
    if "title" not in layouts:
        errors.append("deck is missing a title layout")
    if "references" not in layouts:
        errors.append("deck is missing a references layout")
    if "kpis" not in layouts and "budget" not in layouts:
        errors.append("deck needs a kpis or budget layout")
    evidence_ids = {item.id for item in evidence.items}
    strict = meta.quality_profile == "evidence_v2"
    if lean:
        errors.extend(_lean_slide_errors(deck, plan))
    if strict and not any(slide.layout in {"diagram", "timeline"} for slide in deck.slides):
        errors.append("new campaign deck needs a native campaign diagram or timeline")
    if deck.design.visual_ratio > 0:
        visual_layouts = {
            "photo", "chart", "diagram", "timeline", "table", "stats", "gallery", "comparison", "map", "kpis", "budget",
            "board", "evidence",
        }
        visual_count = sum(
            1
            for slide in deck.slides
            if slide.layout in visual_layouts
            or slide.image
            or slide.images
            or slide.chart
            or slide.diagram
            or slide.table
            or slide.stats
        )
        required_visuals = ceil(deck.design.visual_ratio * len(deck.slides))
        if visual_count < required_visuals:
            errors.append(
                f"deck design asks for at least {required_visuals} visual/data slides, found {visual_count}"
            )
        data_count = sum(
            1
            for slide in deck.slides
            if slide.layout in {"chart", "table", "stats", "kpis"} or slide.chart or slide.table or slide.stats
        )
        if data_count < 2:
            errors.append("deck design needs at least two data slides (chart, table, stats, or KPIs)")
        run = 0
        for slide in deck.slides:
            if slide.layout in {"bullets", "two_column", "next_steps"}:
                run += 1
                if run >= 3:
                    errors.append("deck design allows at most two consecutive text-heavy slides")
                    break
            else:
                run = 0
        for slide in deck.slides:
            if slide.layout == "table":
                note = slide.source_note.strip() or (slide.table.source_note.strip() if slide.table else "")
                if not note:
                    errors.append(f"table slide '{slide.title}' needs a source note")
            if slide.layout == "chart" and not slide.source_note.strip():
                errors.append(f"chart slide '{slide.title}' needs a source note")
    for slide in deck.slides:
        unknown = [cid for cid in slide.cite_ids if cid not in evidence_ids]
        if unknown:
            errors.append(f"unknown cite_ids on '{slide.title}': {', '.join(unknown)}")
        if slide.diagram:
            node_ids = {node.id for node in slide.diagram.nodes}
            for edge in slide.diagram.edges:
                if edge.source not in node_ids or edge.target not in node_ids:
                    errors.append(f"diagram on '{slide.title}' has an edge to an unknown node")
            if slide.layout == "timeline" and slide.diagram.kind != "timeline":
                errors.append(f"timeline slide '{slide.title}' needs a timeline diagram")
        if slide.layout == "chart" and not slide.chart:
            errors.append(f"chart slide '{slide.title}' is missing chart data")
        if slide.image:
            try:
                image_path = store.asset_path(campaign_id, slide.image.path)
                if not image_path.is_file():
                    errors.append(f"image asset missing for '{slide.title}': {slide.image.path}")
            except ValueError as exc:
                errors.append(f"unsafe image path for '{slide.title}': {exc}")
    totals = plan_range(plan) if strict else None
    total = totals.base if totals else sum(line.amount or 0 for line in plan.budget_lines)
    if deck.budget_total is None:
        errors.append("slides.json missing budget_total")
    elif abs(deck.budget_total - total) > 0.01:
        errors.append(f"slides budget_total {deck.budget_total} != plan total {total}")
    if strict:
        if deck.budget_low is None or abs(deck.budget_low - totals.low) > 0.01:
            errors.append("slides budget_low does not match calculated plan range")
        if deck.budget_high is None or abs(deck.budget_high - totals.high) > 0.01:
            errors.append("slides budget_high does not match calculated plan range")
        if deck.budget_complete != totals.complete:
            errors.append("slides budget_complete does not match plan completeness")
    if deck.budget_currency and deck.budget_currency != plan.budget_currency:
        errors.append(f"slides currency {deck.budget_currency} != plan {plan.budget_currency}")
    expected_kpis = {kpi.id for kpi in measurement.kpis}
    if set(deck.kpi_ids) != expected_kpis:
        errors.append(f"slides kpi_ids {sorted(deck.kpi_ids)} != measurement {sorted(expected_kpis)}")
    expected_tactics = {t.id for t in plan.tactics}
    if set(deck.tactic_ids) != expected_tactics:
        errors.append(f"slides tactic_ids {sorted(deck.tactic_ids)} != plan {sorted(expected_tactics)}")
    if not store.has_artifact(campaign_id, "proposal.pptx"):
        errors.append("proposal.pptx is missing")
    else:
        blob = store.read_bytes(campaign_id, "proposal.pptx")
        if not blob.startswith(ZIP_MAGIC):
            errors.append("proposal.pptx is not a PPTX/ZIP file")
        elif _v3_quality_checks(store, campaign_id):
            try:
                diagnostics = _deck_layout_errors(store, campaign_id)
            except Exception as exc:  # noqa: BLE001 - surface any PPTX inspection failure as a gate error
                errors.append(f"proposal.pptx layout could not be verified: {exc}")
            else:
                for item in diagnostics[:12]:
                    errors.append(f"deck layout: {item}")
                if len(diagnostics) > 12:
                    errors.append(f"deck layout: {len(diagnostics) - 12} more diagnostics; shorten the deck copy")
    if errors:
        return fail(*errors)
    return ok()


def gate_critique(store: CampaignStore, campaign_id: str, *, threshold: float) -> GateResult:
    write_result = gate_write(store, campaign_id)
    slides_result = (
        gate_slides(store, campaign_id) if store.has_artifact(campaign_id, "slides.json") else fail("slides.json is missing")
    )
    try:
        review = Review.model_validate(_load_json(store, campaign_id, "review.json"))
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        return fail(f"review.json is unreadable: {exc}").merge(write_result).merge(slides_result)
    except ValidationError as exc:
        return fail(*_validation_errors(exc)).merge(write_result).merge(slides_result)

    errors: list[str] = []
    meta = store.load_meta(campaign_id)
    if review.campaign_id != campaign_id:
        errors.append("review.campaign_id mismatch")
    if meta.quality_profile == "evidence_v2":
        required = set(V2_CRITERIA)
        received = {item.criterion for item in review.scores}
        missing = sorted(required - received)
        if missing:
            errors.append(f"new campaign critique is missing criteria: {', '.join(missing)}")
    if not review.scores:
        errors.append("review has no rubric scores")
    expected = sum(item.score for item in review.scores) / len(review.scores) if review.scores else 0.0
    if review.scores and abs(review.overall - expected) > 0.05:
        errors.append(f"review.overall {review.overall} != mean of scores {expected:.2f}")
    if _v3_quality_checks(store, campaign_id) and not review.human_override:
        substantive = [
            note for note in review.revision_notes if len(note.strip()) >= MIN_REVISION_NOTE_CHARS
        ]
        if not substantive:
            errors.append(
                "requirements-v3 critique needs at least one substantive revision note "
                f"({MIN_REVISION_NOTE_CHARS}+ chars) naming a defect and its fix"
            )
    if review.human_override:
        return write_result.merge(slides_result).merge(ok("human override on review"))
    if review.overall < threshold and not review.passed:
        errors.append(f"rubric overall {review.overall} below threshold {threshold}")
    if review.passed and review.overall < threshold:
        errors.append("review.passed is true but overall is below threshold")
    if not review.passed and review.overall >= threshold:
        errors.append("review.passed is false but overall meets threshold")
    scores = [item.score for item in review.scores]
    if scores and len(set(scores)) == 1:
        errors.append("critique scores are uniform; differentiate criteria and justify each score")
    if any(item.score < 4 for item in review.scores) and not review.revision_notes:
        errors.append("criterion below 4 requires revision_notes and a rewrite")
    if review.revision_notes:
        if not store.has_artifact(campaign_id, "proposal.md"):
            errors.append("revision_notes require proposal.md")
        else:
            current = store.artifact_hash(campaign_id, "proposal.md")
            if not meta.proposal_hash_at_write:
                errors.append("missing write-stage proposal hash")
            elif current == meta.proposal_hash_at_write:
                errors.append("revision_notes is non-empty but proposal.md is unchanged from write")
        if store.has_artifact(campaign_id, "slides.json"):
            slides_hash = store.artifact_hash(campaign_id, "slides.json")
            if not meta.slides_hash_at_slides:
                errors.append("missing slides-stage hash")
            elif slides_hash == meta.slides_hash_at_slides:
                errors.append("revision_notes is non-empty but slides.json is unchanged")
    result = fail(*errors) if errors else ok()
    return result.merge(write_result).merge(slides_result)


def gate_plan_lean(store: CampaignStore, campaign_id: str) -> GateResult:
    """Merged plan stage: plan.json and measurement.json ship together."""
    plan_result = gate_plan(store, campaign_id)
    measure_result = gate_measure(store, campaign_id)
    if plan_result.passed and measure_result.passed:
        return ok()
    return fail(*plan_result.errors, *measure_result.errors)


def gate_deliver(store: CampaignStore, campaign_id: str) -> GateResult:
    """Merged deliver stage: proposal.md and slides.json must both pass."""
    write_result = gate_write(store, campaign_id)
    slides_result = (
        gate_slides(store, campaign_id)
        if store.has_artifact(campaign_id, "slides.json")
        else fail("slides.json is missing")
    )
    if write_result.passed and slides_result.passed:
        return ok()
    return fail(*write_result.errors, *slides_result.errors)


GATES = {
    "intake": gate_intake,
    "research": gate_research,
    "strategy": gate_strategy,
    "plan": gate_plan,
    "plan_lean": gate_plan_lean,
    "measure": gate_measure,
    "write": gate_write,
    "slides": gate_slides,
    "deliver": gate_deliver,
    "critique": gate_critique,
}

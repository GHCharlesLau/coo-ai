"""LLM client plus delimited-file parser. Stub client is for tests and dry runs."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Protocol

import httpx

from coo.config import Settings
from coo.gates.rubric import DEFAULT_CRITERIA, V2_CRITERIA

FILE_BLOCK = re.compile(
    r"<<<FILE:(?P<name>[^\n]+)>>>\n(?P<body>.*?)<<<END:(?P=name)>>>",
    re.DOTALL,
)
CAMPAIGN_ID_RE = re.compile(r"campaign_id:\s*(cmp-[0-9]{8}-[a-f0-9]{8})")
ARTIFACT_RE = re.compile(
    r"## Artifact: (?P<name>\S+)\n(?P<body>.*?)(?=\n## Artifact: |\Z)",
    re.DOTALL,
)


class LLMClient(Protocol):
    model: str

    def complete(self, *, system: str, user: str) -> str: ...


class AgentFillClient:
    """Marker client: the coding agent writes artifacts; the CLI only gates them."""

    model = "coding-agent"

    def complete(self, *, system: str, user: str) -> str:
        del system, user
        raise RuntimeError("Agent-fill mode does not call an external LLM.")


class OpenAICompatibleClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.api_key:
            raise RuntimeError(
                "No API key. Set COO_LLM_API_KEY or OPENAI_API_KEY, or use agent-fill (the default)."
            )
        self.settings = settings
        self.model = settings.model

    def complete(self, *, system: str, user: str) -> str:
        response = httpx.post(
            f"{self.settings.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.api_key}"},
            json={
                "model": self.settings.model,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=self.settings.timeout_s,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"]


def parse_files(text: str, expected: tuple[str, ...]) -> dict[str, str]:
    text = text.strip()
    found = {match.group("name").strip(): match.group("body").strip() for match in FILE_BLOCK.finditer(text)}
    if found:
        missing = [name for name in expected if name not in found]
        extra_ok = True  # ignore extra files
        del extra_ok
        if missing:
            raise ValueError(f"LLM output missing files: {', '.join(missing)}")
        return {name: _strip_fences(found[name]) for name in expected}
    if len(expected) == 1:
        return {expected[0]: _strip_fences(text)}
    raise ValueError(
        "Expected delimited files of the form <<<FILE:name>>> ... <<<END:name>>>"
    )


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    return stripped.strip()


def _context_artifacts(prompt: str) -> dict[str, str]:
    return {m.group("name"): m.group("body").strip() for m in ARTIFACT_RE.finditer(prompt)}


def _emitted_files(text: str) -> dict[str, str]:
    """Parse files a nested stub stage produced in the delimited FILE protocol."""
    return {m.group("name").strip(): m.group("body").strip() for m in FILE_BLOCK.finditer(text)}


def _json_artifact(prompt: str, name: str) -> dict:
    artifacts = _context_artifacts(prompt)
    if name not in artifacts:
        raise KeyError(name)
    return json.loads(artifacts[name])


def _campaign_id(prompt: str) -> str:
    match = CAMPAIGN_ID_RE.search(prompt)
    if not match:
        raise ValueError("Stub LLM could not find campaign_id in prompt")
    return match.group(1)


def _dump(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def _wrap(files: dict[str, str]) -> str:
    chunks = [f"<<<FILE:{name}>>>\n{body.strip()}\n<<<END:{name}>>>" for name, body in files.items()]
    return "\n\n".join(chunks)


def _demand_title(prompt: str) -> str:
    start = prompt.find("## User demand")
    if start < 0:
        return "Untitled campaign"
    body = prompt[start:].split("## Artifact:", 1)[0]
    lines = [ln.strip() for ln in body.splitlines()[1:] if ln.strip() and not ln.startswith("##")]
    if not lines:
        return "Untitled campaign"
    first = lines[0]
    return first[:80]


def _month_offset(months: int) -> str:
    today = date.today()
    index = today.year * 12 + (today.month - 1) + months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


class StubClient:
    """Produces valid artifacts so the spine can be tested without a network."""

    model = "stub"

    def complete(self, *, system: str, user: str) -> str:
        del system
        if "## Previous gate errors" in user and "below threshold" in user:
            return self._critique(user, score=5)
        if "coo-intake" in user or "Intake" in user and "brief.json" in user:
            # Stage skills mention their output names; detect by expected discussion.
            pass
        stage = _detect_stage(user)
        return {
            "intake": self._intake,
            "research": self._research,
            "strategy": self._strategy,
            "plan": self._plan,
            "deliver": self._deliver,
            "measure": self._measure,
            "write": self._write,
            "slides": self._slides,
            "critique": lambda prompt: self._critique(prompt, score=4),
        }[stage](user)

    def _deliver(self, prompt: str) -> str:
        files = _emitted_files(self._write(prompt))
        files.update(_emitted_files(self._slides(prompt)))
        return _wrap(files)

    def _intake(self, prompt: str) -> str:
        campaign_id = _campaign_id(prompt)
        demand_block = prompt.split("## User demand", 1)[-1]
        demand = demand_block.split("## ", 1)[0].strip()
        open_questions = []
        if "LEAVE_QUESTION" in demand:
            open_questions.append(
                {
                    "id": "q_budget",
                    "question": "What is the working budget cap?",
                    "status": "unanswered",
                    "answer": None,
                    "defer_reason": None,
                }
            )
        title = _demand_title(prompt)
        brief = {
            "campaign_id": campaign_id,
            "title": title,
            "brand": "Acme",
            "user_demand": demand,
            "objectives": [
                {
                    "id": "obj_awareness",
                    "statement": "Raise prompted brand awareness among the primary audience.",
                    "metric": "prompted awareness",
                    "target": "+8 pts",
                    "timeframe": "12 weeks",
                },
                {
                    "id": "obj_action",
                    "statement": "Drive qualified actions against the offer.",
                    "metric": "qualified signups",
                    "target": "5,000",
                    "timeframe": "12 weeks",
                },
            ],
            "audience": {
                "primary": "Urban professionals 25-40 considering the category",
                "secondary": "Existing customers due for renewal",
                "insights": ["Time-poor", "Skeptical of generic lifestyle claims"],
            },
            "offer": "The product or service named in the user demand",
            "success_definition": "Awareness lift plus 5,000 qualified actions in 12 weeks without exceeding the budget cap.",
            "constraints": [
                {"kind": "timeline", "detail": "12-week flight"},
                {"kind": "budget", "detail": "Cap 100000 USD unless the brief says otherwise"},
            ],
            "intake_topics": {
                "event_date": "Not set; confirm the event date before final scheduling.",
                "budget": "100000 USD cap.",
                "brand_guardrails": "No additional guardrails supplied; client to confirm.",
                "key_competitors": "Research should identify current competitors.",
                "key_challenges": "Prove the product claim and earn attention in a crowded market.",
                "blacklisted_terms": "No client blacklist supplied; request confirmation before copy approval.",
            },
            "forbidden_associations": [],
            "forbidden_phrases": [],
            "open_questions": open_questions,
            "notes": "",
        }
        return _wrap({"brief.json": _dump(brief)})

    def _research(self, prompt: str) -> str:
        campaign_id = _campaign_id(prompt)
        situation = """# Situation

## Category
The category is crowded and claims of convenience and price are table stakes rather than a distinctive point of view.

## Audience
Primary buyers compare options in public channels and distrust unsupported superlatives from brands they do not already know.

## Competitors
Rivals lead with ubiquity and discount language rather than a finished-job demonstration that a skeptical buyer can verify.

## Opportunity
A specific, proof-backed job-to-be-done can still own a narrow but valuable space in English-language trade and consumer press.

## Geography
Urban professional markets named in the brief, with English-language trade and consumer media as the first discovery layer.
"""
        evidence = {"campaign_id": campaign_id, "items": _stub_evidence_items()}
        return _wrap({"situation.md": situation, "evidence.json": _dump(evidence)})

    def _strategy(self, prompt: str) -> str:
        campaign_id = _campaign_id(prompt)
        brief = _json_artifact(prompt, "brief.json")
        strategy = {
            "campaign_id": campaign_id,
            "insight": "The audience does not need another convenience claim; they need proof that one option actually finishes a specific job.",
            "positioning": f"{brief.get('brand', 'Brand')} is the reliable way to complete the job named in the offer.",
            "message_house": {
                "headline": "Finish the job.",
                "pillars": ["Specific job", "Visible proof", "No wasted steps"],
                "proof_points": ["Product does the named job", "Credible demonstration", "Clear next action"],
            },
            "big_idea": "Make the unfinished job impossible to ignore, then show it completed.",
            "objective_links": [obj["id"] for obj in brief.get("objectives", [])],
        }
        return _wrap({"strategy.json": _dump(strategy)})

    def _plan(self, prompt: str) -> str:
        campaign_id = _campaign_id(prompt)
        strict = "operations.json" in prompt
        month_start = _month_offset(1)
        month_end = _month_offset(3)
        current = date.today().isoformat()
        plan = {
            "campaign_id": campaign_id,
            "channels": ["owned_social", "partnerships", "search"],
            "tactics": [
                {
                    "id": "tac_proof",
                    "name": "Proof serial",
                    "channel": "owned_social",
                    "description": "Weekly proof films of the job being finished.",
                    "kpi_id": "kpi_awareness",
                    "budget_line_id": "bl_content",
                    "owner": "Brand",
                    "start": month_start if strict else "week-1",
                    "end": month_end if strict else "week-12",
                },
                {
                    "id": "tac_search",
                    "name": "Intent capture",
                    "channel": "search",
                    "description": "Search around the job-to-be-done language.",
                    "kpi_id": "kpi_action",
                    "budget_line_id": "bl_media",
                    "owner": "Performance",
                    "start": month_start if strict else "week-2",
                    "end": month_end if strict else "week-12",
                },
                {
                    "id": "tac_partner",
                    "name": "Partner demonstration",
                    "channel": "partnerships",
                    "description": "Co-hosted live demonstration with a trusted partner.",
                    "kpi_id": "kpi_action",
                    "budget_line_id": "bl_partner",
                    "owner": "Partnerships",
                    "start": month_start if strict else "week-4",
                    "end": month_end if strict else "week-8",
                },
            ],
            "timeline_start": month_start if strict else "week-1",
            "timeline_end": month_end if strict else "week-12",
            "budget_currency": "USD",
            "budget_cap": 100000,
            "budget_lines": [
                {"id": "bl_content", "label": "Content production", "amount": 40000},
                {"id": "bl_media", "label": "Paid search", "amount": 40000},
                {"id": "bl_partner", "label": "Partnership activation", "amount": 10000},
            ],
            "notes": "",
        }
        if strict:
            for line, low, base, high in zip(plan["budget_lines"], (36000, 36000, 9000), (40000, 40000, 10000), (44000, 44000, 11000)):
                line.update({"low_amount": low, "high_amount": high, "estimate_status": "assumption", "components": [{
                    "label": line["label"], "quantity": 1, "unit": "campaign package", "basis": "assumption",
                    "rate_currency": "USD", "rate_low": low, "rate_base": base, "rate_high": high,
                    "range_rationale": "Planning range for a small campaign package; validate with supplier quotes.",
                    "geography": "Hong Kong", "priced_on": current,
                    "assumption_rationale": "Illustrative package allowance pending client and supplier validation.",
                    "confidence": "low",
                }]})
            plan["estimate_as_of"] = current
            operations = {
                "campaign_id": campaign_id,
                "ropes": {
                    "research": "Use current Hong Kong audience and category evidence.",
                    "stakeholder_analysis": ["Map the client, audiences, partners, media, and review owners before activation."],
                    "objectives": ["Align outputs and outcomes with approved objectives."],
                    "impact_objectives": ["Improve the long-term communication outcome after baseline calibration."],
                    "output_objectives": ["Deliver approved proof content and qualified media outreach."],
                    "outcome_objectives": ["Calibrate a measurable audience response against a pre-launch baseline."],
                    "programming": ["Demonstrate the product claim through owned, search, and partner activity."],
                    "programming_theme": "Proof made useful.",
                    "message_strategy": ["Lead with one verifiable audience benefit; substantiate before publication."],
                    "pretesting": ["Pretest the core message with the primary audience before launch."],
                    "monitoring": ["Monitor media pickup, audience response, and risk signals weekly."],
                    "evaluation": ["Use leading, lagging, and communication-tier KPIs."],
                    "stewardship": ["Report results and protect attendee and audience data."],
                },
                "media_klos": [],
                "media_coverage_note": "No outlet or KOL is shortlisted until current local fit and risk are researched.",
                "media_coverage_status": "pending_research",
                "countdown": [{"phase": phase, "tasks": [f"Confirm {phase} readiness and owners."], "owner": "Campaign lead"}
                              for phase in ("month_6", "month_3", "week_1", "day_1", "post_event")],
                "run_of_show": [],
                "run_of_show_note": "This stub is not an event schedule; confirm event timing, talent, A/V cues, and owners.",
                "risks": [{"risk": "A public claim cannot be substantiated.", "likelihood": "medium", "impact": "high",
                           "mitigation": "Maintain approved substantiation before publication.",
                           "immediate_pr_response": "Pause the claim, verify facts, and use an approved holding statement.",
                           "owner": "Communications lead"}],
                "compliance": [{"area": area, "status": "pending_review", "jurisdiction": "Hong Kong",
                                "notes": "Client/legal reviewer to confirm applicability; this is not legal advice."}
                               for area in ("local_law", "data_privacy", "media_consent", "influencer_disclosure", "claims_and_brand_safety", "event_safety")],
            }
            files = {"plan.json": _dump(plan), "operations.json": _dump(operations)}
        else:
            files = {"plan.json": _dump(plan)}
        if "pipeline_version: lean" in prompt:
            measure_prompt = prompt + f"\n## Artifact: plan.json\n{_dump(plan)}\n"
            files.update(_emitted_files(self._measure(measure_prompt)))
        return _wrap(files)

    def _measure(self, prompt: str) -> str:
        campaign_id = _campaign_id(prompt)
        plan = _json_artifact(prompt, "plan.json")
        needed = sorted({t["kpi_id"] for t in plan["tactics"]})
        catalog = {
            "kpi_awareness": {
                "id": "kpi_awareness",
                "name": "Prompted awareness",
                "definition": "Percent of primary audience who recognize the brand when prompted.",
                "unit": "percentage points",
                "target": "+8 vs baseline",
                "polarity": "lagging",
                "data_source": "Brand tracker survey",
                "cadence": "monthly",
                "formula": "prompted_aware / sample",
                "measurable": True,
            },
            "kpi_action": {
                "id": "kpi_action",
                "name": "Qualified actions",
                "definition": "Completed signups that pass the qualification rule in the brief.",
                "unit": "count",
                "target": "5000",
                "polarity": "lagging",
                "data_source": "CRM / landing analytics",
                "cadence": "weekly",
                "formula": "count(qualified_signups)",
                "measurable": True,
            },
        }
        kpis = [catalog.get(kid) or _generic_kpi(kid, i) for i, kid in enumerate(needed)]
        if not any(k["polarity"] == "leading" for k in kpis):
            kpis.append(
                {
                    "id": "kpi_engagement",
                    "name": "Proof-content engagement",
                    "definition": "3-second views plus meaningful comments on proof films.",
                    "unit": "count",
                    "target": "250000 views",
                    "polarity": "leading",
                    "data_source": "Social analytics",
                    "cadence": "weekly",
                    "formula": None,
                    "measurable": True,
                }
            )
        if "quality_profile: evidence_v2" in prompt:
            brief = _json_artifact(prompt, "brief.json")
            objective_ids = [obj["id"] for obj in brief.get("objectives", [])]
            tiers = ("output", "outtake", "outcome")
            for index, kpi in enumerate(kpis):
                kpi["communication_tier"] = tiers[index % len(tiers)]
                target_objective = next((obj for obj in brief.get("objectives", []) if obj["id"].endswith("action")), None) if kpi["id"] == "kpi_action" else next((obj for obj in brief.get("objectives", []) if obj["id"].endswith("awareness")), None)
                kpi["objective_ids"] = [target_objective["id"]] if target_objective else objective_ids[:1]
                kpi["target_status"] = "provisional"
                kpi["calibration_method"] = "Set the target after a pre-launch baseline and one pilot reporting cycle."
            if len({kpi["communication_tier"] for kpi in kpis}) < 3:
                for tier in tiers:
                    if tier not in {kpi["communication_tier"] for kpi in kpis}:
                        kpis.append({
                            "id": f"kpi_{tier}", "name": f"{tier.title()} measure",
                            "definition": f"A measurable {tier} result tied to the campaign objective.",
                            "unit": "count", "target": "Set after baseline", "polarity": "leading" if tier != "outcome" else "lagging",
                            "data_source": "Campaign measurement system", "cadence": "weekly", "measurable": True,
                            "target_status": "provisional", "calibration_method": "Set after a pre-launch baseline and one pilot reporting cycle.",
                            "communication_tier": tier, "objective_ids": objective_ids[:1],
                        })
        measurement = {
            "campaign_id": campaign_id,
            "kpis": kpis,
            "reporting_cadence": "weekly working session; monthly tracker",
            "decision_rules": [
                "If leading engagement is <50% of target by week 4, recut proof films.",
                "If qualified actions lag >20% at week 8, shift budget from partnerships to search.",
            ],
        }
        return _wrap({"measurement.json": _dump(measurement)})

    def _write(self, prompt: str) -> str:
        brief = _json_artifact(prompt, "brief.json")
        strategy = _json_artifact(prompt, "strategy.json")
        plan = _json_artifact(prompt, "plan.json")
        measurement = _json_artifact(prompt, "measurement.json")
        total = sum(line["amount"] for line in plan["budget_lines"])
        kpi_ids = ",".join(k["id"] for k in measurement["kpis"])
        tactic_ids = ",".join(t["id"] for t in plan["tactics"])
        tactics = "\n".join(
            f"- {t['name']} on {t['channel']}: {t['description']} Owner {t['owner']}, {t['start']} to {t['end']}."
            for t in plan["tactics"]
        )
        lines = "\n".join(
            f"- {line['label']}: {plan['budget_currency']} {line['amount']}"
            for line in plan["budget_lines"]
        )
        kpis = "\n".join(
            f"- {k['name']} ({k['polarity']}): {k['definition']} Target {k['target']} via {k['data_source']}."
            for k in measurement["kpis"]
        )
        sample = strategy["message_house"]["headline"]
        pillars = strategy["message_house"].get("pillars") or ["Specific job", "Visible proof"]
        strict = "campaign_assets.json" in prompt
        if strict:
            low = sum(line.get("low_amount") or 0 for line in plan["budget_lines"])
            high = sum(line.get("high_amount") or 0 for line in plan["budget_lines"])
        proposal = f"""# Campaign Proposal: {brief['title']}

<!-- coo:budget_total={total} -->
<!-- coo:budget_currency={plan['budget_currency']} -->
{"<!-- coo:budget_range=" + str(low) + "," + str(total) + "," + str(high) + " -->" if strict else ""}
{"<!-- coo:budget_complete=true -->" if strict else ""}
<!-- coo:kpi_ids={kpi_ids} -->
<!-- coo:tactic_ids={tactic_ids} -->

## 1. Executive Summary
{strategy['big_idea']} The campaign answers {brief['brand']}'s demand to {brief['success_definition']} in urban English-language markets.

## 2. Brief and Objectives
Offer: {brief['offer']}. Primary audience: {brief['audience']['primary']}.
Objectives: {"; ".join(o['statement'] for o in brief['objectives'])}

## 3. Situation
Category messaging still clusters around convenience and price <!-- cite:ev1 -->.
Award-winning public campaigns lead with a specific problem and proof rather than lifestyle claims <!-- cite:ev2 -->.
Digital-first buyers discover options through search and owned proof before paid reach <!-- cite:ev3 -->.
Geography: urban professional markets with English-language trade and consumer press as the first layer. Assumption: a proof-led job-to-be-done will out-perform a slogan with this audience.

## 4. Strategy
Insight: {strategy['insight']}
Positioning: {strategy['positioning']}
Big idea: {strategy['big_idea']}
Sample lines: "{sample}" / "See it finished." / "{pillars[0]} you can verify."

## 5. Channel and Tactics Plan
{tactics}

## 6. Budget
{lines}
Total budget: {plan['budget_currency']} {total}{f" (low {low}; high {high}; illustrative assumptions pending supplier quotes)" if strict else ""}

## 7. Measurement
{kpis}

## 8. Risks and Constraints
{"; ".join(c['detail'] for c in brief.get('constraints', [])) or "No additional constraints were stated in the brief beyond timeline and budget discipline."}

## 9. Next Steps
Approve this proposal, lock owners for week-one proof production, and confirm the first reporting session.

## References
"""
        if not strict:
            return _wrap({"proposal.md": proposal})
        brief_ids = [obj["id"] for obj in brief.get("objectives", [])]
        kpis_by_objective = {objective_id: next((kpi["id"] for kpi in measurement["kpis"] if objective_id in kpi.get("objective_ids", [])), measurement["kpis"][0]["id"]) for objective_id in brief_ids}
        assets = {
            "campaign_id": brief["campaign_id"],
            "media_pitch": {
                "subject": "A proof-led campaign idea for Acme",
                "recipient_personalization": "Personalize after selecting a current, relevant outlet.",
                "hook": "Show a verifiable demonstration tied to the audience's job.",
                "body": "Draft only; substantiate every product claim and tailor it to the recipient.",
                "call_to_action": "Would you be open to a short briefing?",
            },
            "press_release": {
                "headline": "Acme proposes a proof-led campaign",
                "subheadline": "Draft announcement pending client review.",
                "dateline": "Hong Kong — date to be confirmed",
                "body": "The campaign will demonstrate an approved product benefit after claims are substantiated.",
                "quote": "Placeholder; no spokesperson quote supplied.",
                "quote_attribution": "Spokesperson to be approved",
                "boilerplate": "Client-approved company description to be supplied.",
                "approval_note": "Draft only; claims, quote, date, and boilerplate require client approval.",
            },
            "issue_faq": [{"question": "What does the campaign promise?", "answer": "Use only the substantiated product claim approved by the client.", "approval_status": "needs_client_review"}],
            "social_calendar": [{"date_or_phase": "Pre-launch", "platform": "Owned social", "copy": "See the proof before making a choice.", "visual_cue": "A genuine demonstration using a cleared supplied asset.", "hashtags": []}],
            "budget_ledger": [{"budget_line_id": line["id"], "category": line["label"], "estimate_low": line.get("low_amount"),
                               "estimate_base": line.get("amount"), "estimate_high": line.get("high_amount"), "actual": None,
                               "currency": plan["budget_currency"], "status": "estimated" if line["estimate_status"] != "unpriced" else "unpriced"}
                              for line in plan["budget_lines"]],
            "post_campaign_evaluation": [{"objective_id": objective_id, "kpi_id": kpi["id"],
                                          "evaluation_method": "Compare the campaign result to a pre-launch baseline.",
                                          "data_source": "Campaign measurement system", "timing": "After campaign close"}
                                         for objective_id in brief_ids for kpi in measurement["kpis"]
                                         if objective_id in kpi.get("objective_ids", [])],
        }
        return _wrap({"proposal.md": proposal, "campaign_assets.json": _dump(assets)})

    def _slides(self, prompt: str) -> str:
        campaign_id = _campaign_id(prompt)
        brief = _json_artifact(prompt, "brief.json")
        strategy = _json_artifact(prompt, "strategy.json")
        plan = _json_artifact(prompt, "plan.json")
        measurement = _json_artifact(prompt, "measurement.json")
        evidence = _json_artifact(prompt, "evidence.json")
        deck = _stub_deck(campaign_id, brief, strategy, plan, measurement, evidence)
        return _wrap({"slides.json": _dump(deck)})

    def _critique(self, prompt: str, score: int) -> str:
        campaign_id = _campaign_id(prompt)
        artifacts = _context_artifacts(prompt)
        proposal = artifacts.get("proposal.md", "")
        slides = artifacts.get("slides.json", "")
        strict = "quality_profile: evidence_v2" in prompt
        criteria = V2_CRITERIA if strict else DEFAULT_CRITERIA
        if score == 4:
            pattern = [5 if index % 3 == 0 else 4 for index in range(len(criteria))]
        else:
            pattern = [score] * len(criteria)
            if all(item == 4 for item in pattern):
                pattern[0] = 5
        overall = sum(pattern) / len(pattern)
        review = {
            "campaign_id": campaign_id,
            "scores": [
                {"criterion": name, "score": pattern[index], "comment": "Stub evaluation."}
                for index, name in enumerate(criteria)
            ],
            "overall": overall,
            "pass_threshold": 3.5,
            "passed": overall >= 3.5,
            "revision_notes": [],
            "human_override": False,
        }
        files = {"review.json": _dump(review), "proposal.md": proposal}
        if slides:
            files["slides.json"] = slides
        else:
            brief = json.loads(artifacts["brief.json"]) if "brief.json" in artifacts else {"title": "Campaign", "brand": "Brand"}
            strategy = json.loads(artifacts["strategy.json"]) if "strategy.json" in artifacts else {"big_idea": "", "message_house": {"headline": "", "pillars": []}}
            plan = json.loads(artifacts["plan.json"])
            measurement = json.loads(artifacts["measurement.json"])
            evidence = json.loads(artifacts["evidence.json"]) if "evidence.json" in artifacts else {"items": []}
            files["slides.json"] = _dump(_stub_deck(campaign_id, brief, strategy, plan, measurement, evidence))
        return _wrap(files)


def _stub_evidence_items() -> list[dict]:
    checked_at = date.today().isoformat()
    return [
        {
            "id": "ev1",
            "claim": "Category messaging clusters around convenience and price.",
            "source": "American Marketing Association",
            "source_url": "https://www.ama.org/marketing-news/",
            "author": "American Marketing Association",
            "year": "2024",
            "title": "Marketing News",
            "container": "American Marketing Association",
            "is_assumption": False,
            "confidence": "high",
            "source_kind": "public",
            "checked_at": checked_at,
            "geography": "Hong Kong",
            "applicable_period": "Current campaign planning",
        },
        {
            "id": "ev2",
            "claim": "Award-winning campaigns lead with a specific public problem and proof.",
            "source": "PRSA Silver Anvil case studies",
            "source_url": "https://www.prsa.org/conferences-and-awards/awards/example-silver-anvil-case-studies",
            "author": "Public Relations Society of America",
            "year": "2023",
            "title": "Silver Anvil example case studies",
            "container": "PRSA",
            "is_assumption": False,
            "confidence": "high",
            "source_kind": "public",
            "checked_at": checked_at,
            "geography": "Hong Kong",
            "applicable_period": "Historical campaign comparison",
        },
        {
            "id": "ev3",
            "claim": "Digital-first audiences discover brands through search and owned proof content.",
            "source": "Digital Marketing Institute",
            "source_url": "https://digitalmarketinginstitute.com/blog",
            "author": "Digital Marketing Institute",
            "year": "2024",
            "title": "Digital marketing blog",
            "container": "Digital Marketing Institute",
            "is_assumption": False,
            "confidence": "medium",
            "source_kind": "public",
            "checked_at": checked_at,
            "geography": "Hong Kong",
            "applicable_period": "Current campaign planning",
        },
        {
            "id": "ev4",
            "claim": "A proof-led job-to-be-done will outperform a lifestyle slogan with this audience.",
            "source": None,
            "source_url": None,
            "author": None,
            "year": None,
            "title": None,
            "container": None,
            "is_assumption": True,
            "confidence": "low",
        },
    ]


def _stub_deck(campaign_id: str, brief: dict, strategy: dict, plan: dict, measurement: dict, evidence: dict) -> dict:
    total = sum(line["amount"] for line in plan["budget_lines"])
    sourced = [item for item in evidence.get("items", []) if not item.get("is_assumption")]
    cite_ids = [item["id"] for item in sourced]
    refs = [
        f"{item.get('author')}. ({item.get('year')}). {item.get('title')}. {item.get('source_url')}"
        for item in sourced
    ]
    kpi_rows = [[k["name"], k["target"], k["data_source"]] for k in measurement["kpis"][:4]]
    budget_rows = [["Line", "Amount"], *[[line["label"], f"{plan['budget_currency']} {line['amount']}"] for line in plan["budget_lines"]]]
    budget_rows.append(["Total", f"{plan['budget_currency']} {total}"])
    house = strategy.get("message_house") or {}
    return {
        "campaign_id": campaign_id,
        "theme": "editorial",
        "budget_total": total,
        "budget_low": sum(line.get("low_amount") or 0 for line in plan["budget_lines"]),
        "budget_high": sum(line.get("high_amount") or 0 for line in plan["budget_lines"]),
        "budget_complete": all(line.get("estimate_status") != "unpriced" for line in plan["budget_lines"]),
        "budget_currency": plan["budget_currency"],
        "kpi_ids": [k["id"] for k in measurement["kpis"]],
        "tactic_ids": [t["id"] for t in plan["tactics"]],
        "design": {"style": "editorial", "accent_mode": "contrast", "visual_ratio": 0.25},
        "slides": [
            {
                "layout": "title",
                "title": brief.get("title", "Campaign"),
                "subtitle": f"{brief.get('brand', '')} · {plan.get('timeline_start', '')}–{plan.get('timeline_end', '')}",
                "notes": "Open with the demand and the window.",
            },
            {
                "layout": "section",
                "title": "Agenda",
                "body": "Situation, strategy, plan, budget, measurement, next steps.",
                "bullets": [
                    "Situation and audience",
                    "Strategy and message house",
                    "Workstreams and owners",
                    "Budget and range",
                    "Measurement and risks",
                    "Next steps",
                ],
                "notes": "Walk the room through the spine before numbers.",
            },
            {
                "layout": "bullets",
                "title": "Situation",
                "bullets": [item["claim"] for item in sourced] or ["Category is crowded."],
                "cite_ids": cite_ids,
                "notes": "Cite live sources, not the brief.",
            },
            {
                "layout": "two_column",
                "title": "Strategy",
                "subtitle": "Insight",
                "left": [strategy.get("insight", "Proof beats slogans.")],
                "right": house.get("pillars") or ["Specific job", "Visible proof"],
                "notes": strategy.get("positioning", ""),
            },
            {
                "layout": "quote",
                "title": "Big idea",
                "quote": strategy.get("big_idea", "Finish the job."),
                "attribution": house.get("headline", ""),
                "notes": "Hold the line; do not dilute into lifestyle.",
            },
            {
                "layout": "stats",
                "title": strategy.get("message_house", {}).get("headline", "The plan in numbers"),
                "stats": [
                    {
                        "value": plan.get("timeline_end", "12 weeks"),
                        "label": "Campaign window",
                        "detail": f"From {plan.get('timeline_start', 'week 1')} to {plan.get('timeline_end', 'week 12')}.",
                    },
                    {
                        "value": str(len(plan["tactics"])),
                        "label": "Workstreams",
                        "detail": "Each has its own owner, budget line, and KPI.",
                    },
                ],
                "notes": "A data beat inside the strategy section.",
            },
            {
                "layout": "timeline",
                "title": "Campaign sequence",
                "subtitle": "From proof to action",
                "diagram": {
                    "kind": "timeline",
                    "nodes": [
                        {"id": "prepare", "label": "Prepare", "detail": "Confirm owners and assets", "date": plan.get("timeline_start", "")},
                        {"id": "activate", "label": "Activate", "detail": "Launch the campaign", "date": "Mid-flight"},
                        {"id": "evaluate", "label": "Evaluate", "detail": "Review outcomes and learn", "date": plan.get("timeline_end", "")},
                    ],
                    "edges": [
                        {"source": "prepare", "target": "activate"},
                        {"source": "activate", "target": "evaluate"},
                    ],
                },
                "notes": "Sequence is illustrative until dates and owners are confirmed.",
            },
            *[
                {
                    "layout": "table",
                    "title": tactic["name"],
                    "subtitle": f"{tactic['channel']} · {tactic['start']} to {tactic['end']}",
                    "table": {
                        "columns": ["Planning item", "Detail"],
                        "rows": [
                            ["Workstream", tactic["description"]],
                            ["Owner", tactic["owner"]],
                            ["Channel", tactic["channel"].replace("_", " ")],
                            ["Timing", f"{tactic['start']} to {tactic['end']}"],
                            [
                                "Cost link",
                                next(
                                    line["label"]
                                    for line in plan["budget_lines"]
                                    if line["id"] == tactic["budget_line_id"]
                                ),
                            ],
                            [
                                "Measure",
                                next(
                                    kpi["name"]
                                    for kpi in measurement["kpis"]
                                    if kpi["id"] == tactic["kpi_id"]
                                ),
                            ],
                        ],
                        "highlight_rows": [],
                        "source_note": "Derived from plan.json and measurement.json.",
                        "align": ["left", "left"],
                    },
                    "notes": "One slide per tactic, with owner, timing, channel, cost link, and measurement.",
                }
                for tactic in plan["tactics"]
            ],
            {
                "layout": "budget",
                "title": "Budget",
                "rows": budget_rows,
                "notes": f"Total {plan['budget_currency']} {total}",
            },
            {
                "layout": "kpis",
                "title": "Measurement",
                "rows": kpi_rows,
                "notes": "Leading and lagging both present.",
            },
            {
                "layout": "bullets",
                "title": "Risks",
                "bullets": [c.get("detail", "Constraint") for c in brief.get("constraints", [])] or ["Lock owners before week one."],
                "notes": "Surface constraints without inventing legal advice.",
            },
            {
                "layout": "next_steps",
                "title": "Next steps",
                "bullets": [
                    "Approve the proposal.",
                    "Lock owners for week-one proof.",
                    "Schedule the first reporting session.",
                ],
                "notes": "Checkpoint for the human sponsor.",
            },
            {
                "layout": "references",
                "title": "References",
                "bullets": refs or ["Sources in the evidence log."],
                "cite_ids": cite_ids,
                "notes": "Every URL matches evidence.json.",
            },
        ],
    }


def _generic_kpi(kpi_id: str, index: int) -> dict:
    polarity = "leading" if index % 2 == 0 else "lagging"
    return {
        "id": kpi_id,
        "name": kpi_id,
        "definition": f"Operational definition for {kpi_id}.",
        "unit": "count",
        "target": "TBD",
        "polarity": polarity,
        "data_source": "Campaign dashboard",
        "cadence": "weekly",
        "formula": None,
        "measurable": True,
    }


def _detect_stage(prompt: str) -> str:
    markers = (
        ("brief.json", "intake"),
        ("situation.md", "research"),
        ("strategy.json", "strategy"),
        ("plan.json", "plan"),
        ("measurement.json", "measure"),
        ("review.json", "critique"),
        ("proposal.md", "write"),
    )
    # The exact stage-skill line is unique; prose mentions of another skill are not.
    for skill, stage in (
        ("coo-intake", "intake"),
        ("coo-research", "research"),
        ("coo-strategy", "strategy"),
        ("coo-plan", "plan"),
        ("coo-measure", "measure"),
        ("coo-critique", "critique"),
        ("coo-deliver", "deliver"),
        ("coo-slides", "slides"),
        ("coo-write", "write"),
    ):
        if f"Stage skill: {skill}" in prompt:
            return stage
    for token, stage in markers:
        if f"<<<FILE:{token}>>>" in prompt or f"Output files: {token}" in prompt:
            return stage
    raise ValueError("Stub LLM could not detect stage")


def build_client(settings: Settings) -> LLMClient:
    if settings.stub:
        return StubClient()
    if settings.agent_fill or not settings.api_key:
        return AgentFillClient()
    return OpenAICompatibleClient(settings)

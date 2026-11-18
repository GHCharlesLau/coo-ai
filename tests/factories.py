from __future__ import annotations

import json

from coo.store import CampaignStore


def write_json(store: CampaignStore, campaign_id: str, name: str, payload: dict) -> None:
    store.write_artifact(campaign_id, name, json.dumps(payload, indent=2))


def valid_brief(campaign_id: str, **overrides) -> dict:
    data = {
        "campaign_id": campaign_id,
        "title": "Finish the job",
        "brand": "Acme",
        "user_demand": "Launch a 12-week campaign.",
        "objectives": [
            {
                "id": "obj_awareness",
                "statement": "Raise awareness.",
                "metric": "prompted awareness",
                "target": "+8",
                "timeframe": "12 weeks",
            }
        ],
        "audience": {"primary": "Urban professionals 25-40", "secondary": None, "insights": []},
        "offer": "Acme Widget",
        "success_definition": "Awareness lift in 12 weeks.",
        "constraints": [{"kind": "budget", "detail": "Cap 100000 USD"}],
        "open_questions": [],
        "intake_topics": {
            "event_date": "Not set; use a proposed campaign window.",
            "budget": "100000 USD cap.",
            "brand_guardrails": "No additional restrictions provided.",
            "key_competitors": "Research should identify current competitors.",
            "key_challenges": "Limited awareness and unproven claims.",
            "blacklisted_terms": "No blacklist provided; client to confirm.",
        },
        "notes": "",
    }
    data.update(overrides)
    return data


def valid_situation() -> str:
    return """# Situation

## Category
The category is crowded and convenience claims are table stakes rather than a reason to switch.

## Audience
Primary buyers compare options publicly and distrust unsupported superlatives from unfamiliar brands.

## Competitors
Rivals lead with price and ubiquity rather than a finished-job demonstration a buyer can verify.

## Opportunity
A specific, proof-backed job-to-be-done can still own a narrow but valuable space.

## Geography
Urban professional markets in English-language trade and consumer press.
"""


def valid_evidence(campaign_id: str) -> dict:
    return {
        "campaign_id": campaign_id,
        "items": [
            {
                "id": "ev1",
                "claim": "Buyers distrust unsourced superlatives.",
                "source": "American Marketing Association",
                "source_url": "https://www.ama.org/marketing-news/",
                "author": "American Marketing Association",
                "year": "2024",
                "title": "Marketing News",
                "container": "American Marketing Association",
                "is_assumption": False,
                "confidence": "high",
            },
            {
                "id": "ev2",
                "claim": "Award-winning campaigns lead with a public problem and proof.",
                "source": "PRSA Silver Anvil case studies",
                "source_url": "https://www.prsa.org/conferences-and-awards/awards/example-silver-anvil-case-studies",
                "author": "Public Relations Society of America",
                "year": "2023",
                "title": "Silver Anvil example case studies",
                "container": "PRSA",
                "is_assumption": False,
                "confidence": "high",
            },
            {
                "id": "ev3",
                "claim": "Digital-first audiences discover brands through search and owned proof.",
                "source": "Digital Marketing Institute",
                "source_url": "https://digitalmarketinginstitute.com/blog",
                "author": "Digital Marketing Institute",
                "year": "2024",
                "title": "Digital marketing blog",
                "container": "Digital Marketing Institute",
                "is_assumption": False,
                "confidence": "medium",
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
        ],
    }


def valid_strategy(campaign_id: str) -> dict:
    return {
        "campaign_id": campaign_id,
        "insight": "The audience needs proof the job gets finished.",
        "positioning": "Acme finishes the job others advertise.",
        "message_house": {
            "headline": "Finish the job.",
            "pillars": ["Specific job", "Visible proof"],
            "proof_points": ["Demo", "Guarantee"],
        },
        "big_idea": "Make the unfinished job impossible to ignore.",
        "objective_links": ["obj_awareness"],
    }


def valid_plan(campaign_id: str, *, cap: float | None = 100000, extra_line: float | None = None) -> dict:
    lines = [
        {"id": "bl_content", "label": "Content", "amount": 40000},
        {"id": "bl_media", "label": "Media", "amount": 60000},
    ]
    if extra_line is not None:
        lines.append({"id": "bl_extra", "label": "Extra", "amount": extra_line})
    return {
        "campaign_id": campaign_id,
        "channels": ["owned_social", "search"],
        "tactics": [
            {
                "id": "tac_proof",
                "name": "Proof serial",
                "channel": "owned_social",
                "description": "Weekly proof films",
                "kpi_id": "kpi_awareness",
                "budget_line_id": "bl_content",
                "owner": "Brand",
                "start": "week-1",
                "end": "week-12",
            },
            {
                "id": "tac_search",
                "name": "Search",
                "channel": "search",
                "description": "Intent capture",
                "kpi_id": "kpi_action",
                "budget_line_id": "bl_media",
                "owner": "Performance",
                "start": "week-2",
                "end": "week-12",
            },
        ],
        "timeline_start": "week-1",
        "timeline_end": "week-12",
        "budget_currency": "USD",
        "budget_cap": cap,
        "budget_lines": lines,
        "notes": "",
    }


def valid_measurement(campaign_id: str) -> dict:
    return {
        "campaign_id": campaign_id,
        "kpis": [
            {
                "id": "kpi_awareness",
                "name": "Prompted awareness",
                "definition": "Percent who recognize the brand when prompted.",
                "unit": "pp",
                "target": "+8",
                "polarity": "lagging",
                "data_source": "Brand tracker",
                "cadence": "monthly",
                "formula": None,
                "measurable": True,
            },
            {
                "id": "kpi_action",
                "name": "Qualified actions",
                "definition": "Qualified signups counted in CRM.",
                "unit": "count",
                "target": "5000",
                "polarity": "lagging",
                "data_source": "CRM",
                "cadence": "weekly",
                "formula": None,
                "measurable": True,
            },
            {
                "id": "kpi_engagement",
                "name": "Proof engagement",
                "definition": "3-second views of proof films.",
                "unit": "count",
                "target": "250000",
                "polarity": "leading",
                "data_source": "Social analytics",
                "cadence": "weekly",
                "formula": None,
                "measurable": True,
            },
        ],
        "reporting_cadence": "weekly",
        "decision_rules": ["If leading KPI is under 50% by week 4, recut films."],
    }


def valid_proposal(plan: dict, measurement: dict, title: str = "Finish the job", evidence: dict | None = None) -> str:
    total = sum(line["amount"] for line in plan["budget_lines"])
    kpi_ids = ",".join(k["id"] for k in measurement["kpis"])
    tactic_ids = ",".join(t["id"] for t in plan["tactics"])
    evidence = evidence or valid_evidence("cmp-20260101-abcd1234")
    sourced = [item for item in evidence["items"] if not item.get("is_assumption")]
    cites = " ".join(f"({item['author']}, {item['year']})" for item in sourced)
    refs = "\n".join(
        f"{item['author']}. ({item['year']}). {item['title']}. {item['container']}. {item['source_url']}"
        for item in sourced
    )
    tactics = "\n".join(
        f"- {t['name']} on {t['channel']}: {t['description']} Owner {t['owner']}."
        for t in plan["tactics"]
    )
    lines = "\n".join(f"- {line['label']}: {plan['budget_currency']} {line['amount']}" for line in plan["budget_lines"])
    kpis = "\n".join(
        f"- {k['name']} ({k['polarity']}): {k['definition']} Target {k['target']} via {k['data_source']}."
        for k in measurement["kpis"]
    )
    return f"""# Campaign Proposal: {title}

<!-- coo:budget_total={total} -->
<!-- coo:budget_currency={plan['budget_currency']} -->
<!-- coo:kpi_ids={kpi_ids} -->
<!-- coo:tactic_ids={tactic_ids} -->

## 1. Executive Summary
Make the unfinished job impossible to ignore, then show it completed for urban English-language buyers.

## 2. Brief and Objectives
Raise prompted awareness and drive qualified actions against the named offer within a twelve-week flight.

## 3. Situation
Urban professional markets still hear convenience claims {cites}. Geography: English-language trade and consumer press. Assumption: proof will beat a slogan.

## 4. Strategy
Position the brand as the reliable way to finish the named job. Sample lines: "Finish the job." / "See it done." / "Proof, not promises."

## 5. Channel and Tactics Plan
{tactics}

## 6. Budget
{lines}
Total budget: {plan['budget_currency']} {total}

## 7. Measurement
{kpis}

## 8. Risks and Constraints
Stay inside the named budget cap and twelve-week window; lock legal clearance before paid launch.

## 9. Next Steps
Approve this proposal, lock owners, and begin week-one proof production.

## References
{refs}
"""


def valid_deck(campaign_id: str, plan: dict, measurement: dict, evidence: dict | None = None, title: str = "Finish the job") -> dict:
    evidence = evidence or valid_evidence(campaign_id)
    total = sum(line["amount"] for line in plan["budget_lines"])
    sourced = [item for item in evidence["items"] if not item.get("is_assumption")]
    cite_ids = [item["id"] for item in sourced]
    refs = [f"{item['author']}. ({item['year']}). {item['title']}. {item['source_url']}" for item in sourced]
    return {
        "campaign_id": campaign_id,
        "theme": "navy_gold",
        "budget_total": total,
        "budget_currency": plan["budget_currency"],
        "kpi_ids": [k["id"] for k in measurement["kpis"]],
        "tactic_ids": [t["id"] for t in plan["tactics"]],
        "design": {"style": "editorial", "accent_mode": "contrast", "visual_ratio": 0.25},
        "slides": [
            {"layout": "title", "title": title, "subtitle": "Campaign proposal", "notes": "Open."},
            {"layout": "section", "title": "Agenda", "body": "Situation through next steps.", "notes": "Spine."},
            {"layout": "bullets", "title": "Situation", "bullets": [item["claim"] for item in sourced], "cite_ids": cite_ids, "notes": "Cited."},
            {"layout": "two_column", "title": "Strategy", "left": ["Finish the job."], "right": ["Visible proof"], "notes": "House."},
            {"layout": "quote", "title": "Big idea", "quote": "Make the unfinished job impossible to ignore.", "notes": "Hold."},
            {
                "layout": "stats",
                "title": "Proof beats slogans",
                "stats": [
                    {"value": "+8pp", "label": "Awareness target", "detail": "Prompted awareness lift."},
                    {"value": "5,000", "label": "Qualified actions", "detail": "Tracked in CRM."},
                ],
                "notes": "One data beat per major section.",
            },
            {
                "layout": "timeline",
                "title": "Campaign sequence",
                "diagram": {
                    "kind": "timeline",
                    "nodes": [
                        {"id": "prepare", "label": "Prepare"},
                        {"id": "activate", "label": "Activate"},
                        {"id": "evaluate", "label": "Evaluate"},
                    ],
                    "edges": [
                        {"source": "prepare", "target": "activate"},
                        {"source": "activate", "target": "evaluate"},
                    ],
                },
                "notes": "Sequence.",
            },
            *[
                {
                    "layout": "bullets",
                    "title": tactic["name"],
                    "subtitle": f"{tactic['channel']} · {tactic['start']} to {tactic['end']}",
                    "bullets": [
                        tactic["description"],
                        f"Owner: {tactic['owner']}.",
                        f"Cost link: {next(line['label'] for line in plan['budget_lines'] if line['id'] == tactic['budget_line_id'])}.",
                    ],
                    "notes": "One slide per tactic.",
                }
                for tactic in plan["tactics"]
            ],
            {
                "layout": "budget",
                "title": "Budget",
                "rows": [["Line", "Amount"], *[[line["label"], str(line["amount"])] for line in plan["budget_lines"]]],
                "notes": "Totals.",
            },
            {
                "layout": "kpis",
                "title": "Measurement",
                "rows": [[k["name"], k["target"]] for k in measurement["kpis"]],
                "notes": "KPIs.",
            },
            {"layout": "bullets", "title": "Risks", "bullets": ["Stay inside the cap.", "Lock legal clearance."], "notes": "Risks."},
            {"layout": "next_steps", "title": "Next steps", "bullets": ["Approve", "Lock owners", "Produce week-one proof"], "notes": "Go."},
            {"layout": "references", "title": "References", "bullets": refs, "cite_ids": cite_ids, "notes": "URLs."},
        ],
    }


def valid_campaign_assets(campaign_id: str, plan: dict) -> dict:
    return {
        "campaign_id": campaign_id,
        "media_pitch": {
            "subject": "A proof-led campaign idea for Acme",
            "recipient_personalization": "For a relevant trade editor; personalize after outlet research.",
            "hook": "A verifiable demonstration tied to the audience's job.",
            "body": "Draft pitch copy pending substantiation and editor personalization.",
            "call_to_action": "Would you be open to a short briefing?",
        },
        "press_release": {
            "headline": "Acme proposes proof-led campaign",
            "subheadline": "Draft announcement pending client approval.",
            "dateline": "Hong Kong — date to be confirmed",
            "body": "The campaign will demonstrate the named product benefit after claims are cleared.",
            "quote": "Placeholder; no spokesperson quote supplied.",
            "quote_attribution": "Spokesperson to be approved",
            "boilerplate": "Acme company description to be supplied by the client.",
            "approval_note": "Draft only; claims, quote, dateline, and boilerplate require client review.",
        },
        "issue_faq": [{
            "question": "What is the campaign promising?",
            "answer": "Use only the substantiated product claim approved by the client.",
            "approval_status": "needs_client_review",
        }],
        "social_calendar": [{
            "date_or_phase": "Pre-launch",
            "platform": "Owned social",
            "copy": "See the proof before making a choice.",
            "visual_cue": "A genuine product demonstration; use cleared supplied assets only.",
            "hashtags": [],
        }],
        "budget_ledger": [{
            "budget_line_id": line["id"],
            "category": line["label"],
            "estimate_low": line.get("low_amount"),
            "estimate_base": line.get("amount"),
            "estimate_high": line.get("high_amount"),
            "actual": None,
            "currency": plan["budget_currency"],
            "status": "estimated",
        } for line in plan["budget_lines"]],
        "post_campaign_evaluation": [{
            "objective_id": "obj_awareness",
            "kpi_id": kpi_id,
            "evaluation_method": "Compare post-campaign performance with the pre-campaign baseline.",
            "data_source": "Brand tracker survey",
            "timing": "After campaign close",
        } for kpi_id in ("kpi_awareness", "kpi_action", "kpi_engagement")],
    }


def valid_operations(campaign_id: str) -> dict:
    return {
        "campaign_id": campaign_id,
        "ropes": {
            "research": "Use dated local evidence and audience research.",
            "stakeholder_analysis": ["Map audiences, partners, media, and review owners."],
            "objectives": ["Tie each objective to a measurable outcome."],
            "impact_objectives": ["Calibrate the intended long-term communication impact."],
            "output_objectives": ["Deliver the approved communication outputs."],
            "outcome_objectives": ["Measure audience response against a pre-campaign baseline."],
            "programming": ["Run proof-led owned and partner activities."],
            "programming_theme": "Proof made useful.",
            "message_strategy": ["Lead with the substantiated audience benefit."],
            "pretesting": ["Pretest draft messages with the target audience."],
            "monitoring": ["Monitor delivery and response weekly."],
            "evaluation": ["Review leading and lagging measures."],
            "stewardship": ["Report results and protect audience data."],
        },
        "media_klos": [],
        "media_coverage_note": "No individual media or KOL is recommended until a current local shortlist is checked.",
        "media_coverage_status": "pending_research",
        "countdown": [
            {"phase": phase, "tasks": [f"Confirm {phase} tasks and readiness."], "owner": "Campaign lead"}
            for phase in ("month_6", "month_3", "week_1", "day_1", "post_event")
        ],
        "run_of_show": [],
        "run_of_show_note": "Event timing and talent are pending client confirmation.",
        "risks": [{
            "risk": "Unverified campaign claims are challenged publicly.",
            "likelihood": "medium", "impact": "high",
            "mitigation": "Pre-clear claims and maintain a substantiation file.",
            "immediate_pr_response": "Pause the disputed claim, verify facts, and issue an approved holding statement.",
            "owner": "Communications lead",
        }],
        "compliance": [
            {"area": area, "status": "pending_review", "jurisdiction": "Hong Kong", "notes": "Confirm applicability with local counsel or the client reviewer."}
            for area in ("local_law", "data_privacy", "media_consent", "influencer_disclosure", "claims_and_brand_safety", "event_safety")
        ],
    }

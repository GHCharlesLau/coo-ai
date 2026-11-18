from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RopesPlan(BaseModel):
    research: str
    stakeholder_analysis: list[str] = Field(default_factory=list)
    objectives: list[str] = Field(min_length=1)
    impact_objectives: list[str] = Field(default_factory=list)
    output_objectives: list[str] = Field(default_factory=list)
    outcome_objectives: list[str] = Field(default_factory=list)
    programming: list[str] = Field(min_length=1)
    programming_theme: str = ""
    message_strategy: list[str] = Field(default_factory=list)
    pretesting: list[str] = Field(default_factory=list)
    monitoring: list[str] = Field(default_factory=list)
    evaluation: list[str] = Field(min_length=1)
    stewardship: list[str] = Field(min_length=1)


class MediaDimension(BaseModel):
    score: int | None = Field(default=None, ge=1, le=5)
    basis_kind: Literal["evidence", "assumption", "not_assessed"] = "not_assessed"
    basis: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] | None = None

    @model_validator(mode="after")
    def score_has_basis(self):
        if self.score is not None and self.basis_kind == "evidence" and not self.evidence_ids:
            raise ValueError("evidence-scored media dimension needs evidence_ids")
        if self.score is not None and self.basis_kind == "assumption" and (not self.basis.strip() or not self.confidence):
            raise ValueError("assumed media score needs a rationale and confidence")
        if self.score is not None and self.basis_kind == "not_assessed":
            raise ValueError("a numeric media score must be sourced or explicitly labeled an assumption")
        return self


class MediaProfile(BaseModel):
    name: str
    kind: Literal["media_outlet", "journalist", "kol"]
    tier: str
    tier_category: Literal["tier_1_mainstream", "tier_2_vertical", "tier_3_niche", "unclassified"] = "unclassified"
    tier_rationale: str = ""
    audience: str
    relevance: MediaDimension
    reach: MediaDimension
    resonance: MediaDimension
    risk_ethics: MediaDimension
    disclosure_required: bool | None = None
    disclosure_notes: str = ""
    selection_rationale: str


class CountdownMilestone(BaseModel):
    phase: Literal["month_6", "month_3", "week_1", "day_1", "post_event"]
    tasks: list[str] = Field(min_length=1)
    owner: str


class RunOfShowItem(BaseModel):
    time: str
    duration: str
    activity: str
    on_stage_talent: str
    av_cues: str
    responsible_party: str


class CampaignRisk(BaseModel):
    risk: str
    likelihood: Literal["low", "medium", "high", "unknown"]
    impact: Literal["low", "medium", "high", "unknown"]
    mitigation: str
    immediate_pr_response: str
    owner: str


class ComplianceCheck(BaseModel):
    area: Literal[
        "local_law",
        "data_privacy",
        "media_consent",
        "influencer_disclosure",
        "claims_and_brand_safety",
        "event_safety",
    ]
    status: Literal["pending_review", "confirmed_by_client", "not_applicable"]
    jurisdiction: str
    notes: str
    reviewer: str = ""


class OperationsPlan(BaseModel):
    campaign_id: str
    ropes: RopesPlan
    media_klos: list[MediaProfile] = Field(default_factory=list)
    media_coverage_note: str
    media_coverage_status: Literal["assessed", "pending_client_list", "pending_research", "not_applicable"] = "pending_research"
    countdown: list[CountdownMilestone] = Field(default_factory=list)
    run_of_show: list[RunOfShowItem] = Field(default_factory=list)
    run_of_show_note: str = ""
    risks: list[CampaignRisk] = Field(min_length=1)
    compliance: list[ComplianceCheck] = Field(default_factory=list)


class PitchEmail(BaseModel):
    subject: str
    recipient_personalization: str
    hook: str
    body: str
    call_to_action: str


class PressRelease(BaseModel):
    headline: str
    subheadline: str = ""
    dateline: str
    body: str
    quote: str
    quote_attribution: str
    boilerplate: str
    approval_note: str = ""


class FAQItem(BaseModel):
    question: str
    answer: str
    approval_status: Literal["draft", "needs_client_review", "approved"] = "draft"
    approved_by: str | None = None


class SocialPost(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date_or_phase: str
    platform: str
    post_copy: str = Field(alias="copy")
    visual_cue: str
    hashtags: list[str] = Field(default_factory=list)


class BudgetLedgerEntry(BaseModel):
    budget_line_id: str
    category: str
    estimate_low: float | None = Field(default=None, ge=0)
    estimate_base: float | None = Field(default=None, ge=0)
    estimate_high: float | None = Field(default=None, ge=0)
    actual: float | None = Field(default=None, ge=0)
    currency: str
    status: Literal["estimated", "quoted", "committed", "actual", "unpriced"]


class EvaluationOutline(BaseModel):
    objective_id: str
    kpi_id: str
    evaluation_method: str
    data_source: str
    timing: str


class CampaignAssets(BaseModel):
    campaign_id: str
    media_pitch: PitchEmail
    press_release: PressRelease
    issue_faq: list[FAQItem] = Field(min_length=1)
    social_calendar: list[SocialPost] = Field(min_length=1)
    budget_ledger: list[BudgetLedgerEntry] = Field(min_length=1)
    post_campaign_evaluation: list[EvaluationOutline] = Field(min_length=1)

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CostComponent(BaseModel):
    label: str
    quantity: float = Field(ge=0)
    unit: str
    basis: Literal["published_rate", "benchmark", "client_quote", "assumption", "unpriced"]
    rate_currency: str = "USD"
    rate_low: float | None = Field(default=None, ge=0)
    rate_base: float | None = Field(default=None, ge=0)
    rate_high: float | None = Field(default=None, ge=0)
    range_rationale: str | None = None
    geography: str
    priced_on: str | None = None
    evidence_id: str | None = None
    fx_to_budget: float | None = Field(default=None, gt=0)
    fx_evidence_id: str | None = None
    fx_date: str | None = None
    assumption_rationale: str | None = None
    confidence: Literal["low", "medium", "high"] | None = None
    quote_needed: str | None = None

    @field_validator("rate_currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        value = value.upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("rate_currency must be a three-letter currency code")
        return value

    @model_validator(mode="after")
    def validate_basis(self):
        rates = (self.rate_low, self.rate_base, self.rate_high)
        if self.basis == "unpriced":
            if any(rate is not None for rate in rates):
                raise ValueError("unpriced component cannot contain rates")
            if not (self.quote_needed or "").strip():
                raise ValueError("unpriced component needs quote_needed")
            return self
        if any(rate is None for rate in rates):
            raise ValueError("priced component needs low, base, and high rates")
        if not self.rate_low <= self.rate_base <= self.rate_high:
            raise ValueError("component rates must satisfy low <= base <= high")
        if self.rate_low != self.rate_high and not (self.range_rationale or "").strip():
            raise ValueError("rate ranges need a range_rationale")
        if not (self.unit or "").strip() or not (self.geography or "").strip():
            raise ValueError("priced component needs unit and geography")
        if self.basis in {"published_rate", "benchmark", "client_quote"} and not self.evidence_id:
            raise ValueError(f"{self.basis} component needs evidence_id")
        if self.basis == "assumption" and not (self.assumption_rationale or "").strip():
            raise ValueError("assumption component needs assumption_rationale")
        if self.basis == "assumption" and not self.confidence:
            raise ValueError("assumption component needs confidence")
        return self


class BudgetLine(BaseModel):
    id: str
    label: str
    amount: float | None = None
    low_amount: float | None = Field(default=None, ge=0)
    high_amount: float | None = Field(default=None, ge=0)
    estimate_status: Literal["complete", "assumption", "partial", "unpriced"] = "complete"
    components: list[CostComponent] = Field(default_factory=list)
    quote_needed: str | None = None


class Tactic(BaseModel):
    id: str
    name: str
    channel: str
    description: str
    kpi_id: str
    budget_line_id: str
    owner: str
    start: str
    end: str
    status: Literal["planned", "in_progress", "completed"] = "planned"


class Plan(BaseModel):
    campaign_id: str
    channels: list[str]
    tactics: list[Tactic]
    timeline_start: str
    timeline_end: str
    budget_currency: str = "USD"
    budget_cap: float | None = None
    budget_lines: list[BudgetLine] = Field(default_factory=list)
    estimate_as_of: str | None = None
    notes: str = ""

    @field_validator("budget_currency")
    @classmethod
    def budget_currency_code(cls, value: str) -> str:
        value = value.upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("budget_currency must be a three-letter currency code")
        return value

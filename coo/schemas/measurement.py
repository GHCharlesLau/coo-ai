from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class KPI(BaseModel):
    id: str
    name: str
    definition: str
    unit: str
    target: str
    polarity: Literal["leading", "lagging"]
    data_source: str
    cadence: str
    formula: str | None = None
    measurable: bool = True
    target_status: Literal["established", "provisional"] = "established"
    communication_tier: Literal["output", "outtake", "outcome"] | None = None
    objective_ids: list[str] = Field(default_factory=list)
    target_evidence_ids: list[str] = Field(default_factory=list)
    baseline: str | None = None
    calibration_method: str | None = None


class Measurement(BaseModel):
    campaign_id: str
    kpis: list[KPI]
    reporting_cadence: str
    decision_rules: list[str] = Field(default_factory=list)

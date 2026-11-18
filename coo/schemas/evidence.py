from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    id: str
    claim: str
    source: str | None = None
    source_url: str | None = None
    is_assumption: bool = False
    confidence: Literal["low", "medium", "high"] = "medium"
    author: str | None = None
    year: str | None = None
    title: str | None = None
    container: str | None = None
    source_kind: Literal["public", "client_quote", "internal"] = "public"
    source_reference: str | None = None
    checked_at: str | None = None
    geography: str | None = None
    applicable_period: str | None = None
    numeric_value: float | None = None
    numeric_unit: str | None = None
    numeric_currency: str | None = None
    cost_scope: str | None = None


class EvidenceLog(BaseModel):
    campaign_id: str
    items: list[EvidenceItem] = Field(default_factory=list)

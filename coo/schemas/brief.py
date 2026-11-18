from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Objective(BaseModel):
    id: str
    statement: str
    metric: str | None = None
    target: str | None = None
    timeframe: str | None = None


class Audience(BaseModel):
    primary: str
    secondary: str | None = None
    insights: list[str] = Field(default_factory=list)


class Constraint(BaseModel):
    kind: Literal["budget", "timeline", "channel", "legal", "brand", "other"]
    detail: str


class OpenQuestion(BaseModel):
    id: str
    question: str
    status: Literal["unanswered", "answered", "deferred"]
    answer: str | None = None
    defer_reason: str | None = None


class Brief(BaseModel):
    campaign_id: str
    title: str
    brand: str
    user_demand: str
    objectives: list[Objective]
    audience: Audience
    offer: str
    success_definition: str
    constraints: list[Constraint] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    # Evidence-v2 intake coverage. Values may explicitly say "not set" or
    # "unknown"; the gate distinguishes an acknowledged gap from omission.
    intake_topics: dict[str, str] = Field(default_factory=dict)
    forbidden_associations: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    notes: str = ""

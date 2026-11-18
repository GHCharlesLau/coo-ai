from __future__ import annotations

from pydantic import BaseModel, Field


class RubricScore(BaseModel):
    criterion: str
    score: int = Field(ge=1, le=5)
    comment: str


class Review(BaseModel):
    campaign_id: str
    scores: list[RubricScore]
    overall: float
    pass_threshold: float = 3.5
    passed: bool
    revision_notes: list[str] = Field(default_factory=list)
    human_override: bool = False

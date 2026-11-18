from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MessageHouse(BaseModel):
    headline: str
    pillars: list[str]
    proof_points: list[str]


class Strategy(BaseModel):
    """Strategy must not carry a media mix, tactics, or budget."""

    model_config = ConfigDict(extra="forbid")

    campaign_id: str
    insight: str
    positioning: str
    message_house: MessageHouse
    big_idea: str
    objective_links: list[str] = Field(description="Brief objective ids this strategy answers.")

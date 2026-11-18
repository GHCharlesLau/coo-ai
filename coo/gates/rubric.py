"""Rubric helpers used by the critique gate and the critique skill."""

from __future__ import annotations

DEFAULT_CRITERIA: tuple[str, ...] = (
    "brief_fidelity",
    "insight_quality",
    "message_distinctiveness",
    "plan_kpi_coherence",
    "budget_clarity",
    "measurability",
    "proposal_completeness",
)

V2_CRITERIA: tuple[str, ...] = DEFAULT_CRITERIA + (
    "budget_evidence_quality",
    "visual_communication",
)


def apply_threshold(overall: float, threshold: float) -> bool:
    return overall >= threshold

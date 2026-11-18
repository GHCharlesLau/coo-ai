"""Proposal document contract: required headings and machine-readable markers."""

from __future__ import annotations

REQUIRED_SECTIONS: tuple[str, ...] = (
    "## 1. Executive Summary",
    "## 2. Brief and Objectives",
    "## 3. Situation",
    "## 4. Strategy",
    "## 5. Channel and Tactics Plan",
    "## 6. Budget",
    "## 7. Measurement",
    "## 8. Risks and Constraints",
    "## 9. Next Steps",
    "## References",
)

# Writer must emit these HTML comments so hard gates can reconcile numbers.
PROPOSAL_MARKERS = {
    "budget_total": r"<!--\s*coo:budget_total=(?P<value>[-0-9.]+)\s*-->",
    "budget_range": r"<!--\s*coo:budget_range=(?P<value>[-0-9.,]+)\s*-->",
    "budget_complete": r"<!--\s*coo:budget_complete=(?P<value>true|false)\s*-->",
    "budget_currency": r"<!--\s*coo:budget_currency=(?P<value>[A-Za-z]{3,8})\s*-->",
    "kpi_ids": r"<!--\s*coo:kpi_ids=(?P<value>[^\s]+)\s*-->",
    "tactic_ids": r"<!--\s*coo:tactic_ids=(?P<value>[^\s]+)\s*-->",
}

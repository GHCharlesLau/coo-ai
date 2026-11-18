"""Budget calculations shared by validation and proposal rendering."""

from __future__ import annotations

from dataclasses import dataclass

from coo.schemas.plan import BudgetLine, Plan


@dataclass(frozen=True)
class Range:
    low: float | None
    base: float | None
    high: float | None
    complete: bool


def component_range(component, budget_currency: str) -> Range:
    if component.basis == "unpriced":
        return Range(None, None, None, False)
    if component.rate_currency == budget_currency:
        fx = 1.0 if component.fx_to_budget is None else component.fx_to_budget
    else:
        fx = component.fx_to_budget
        if fx is None:
            return Range(None, None, None, False)
    return Range(
        component.quantity * component.rate_low * fx,
        component.quantity * component.rate_base * fx,
        component.quantity * component.rate_high * fx,
        True,
    )


def line_range(line: BudgetLine, budget_currency: str) -> Range:
    if not line.components:
        return Range(line.low_amount, line.amount, line.high_amount, line.estimate_status != "unpriced")
    priced = [component_range(c, budget_currency) for c in line.components if c.basis != "unpriced"]
    complete = all(c.basis != "unpriced" for c in line.components) and all(r.complete for r in priced)
    if not priced:
        return Range(None, None, None, False)
    return Range(
        sum(r.low or 0 for r in priced),
        sum(r.base or 0 for r in priced),
        sum(r.high or 0 for r in priced),
        complete,
    )


def plan_range(plan: Plan) -> Range:
    ranges = [line_range(line, plan.budget_currency) for line in plan.budget_lines]
    valued = [r for r in ranges if r.base is not None]
    if not valued:
        return Range(0.0, 0.0, 0.0, False)
    complete = len(valued) == len(ranges) and all(r.complete for r in ranges)
    return Range(
        sum(r.low or 0 for r in valued),
        sum(r.base or 0 for r in valued),
        sum(r.high or 0 for r in valued),
        complete,
    )

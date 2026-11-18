from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GateResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    needs_human: bool = False
    needs_agent: bool = False

    def merge(self, other: GateResult) -> GateResult:
        return GateResult(
            passed=self.passed and other.passed,
            errors=[*self.errors, *other.errors],
            warnings=[*self.warnings, *other.warnings],
            needs_human=self.needs_human or other.needs_human,
            needs_agent=self.needs_agent or other.needs_agent,
        )


def fail(*errors: str, needs_human: bool = False, needs_agent: bool = False) -> GateResult:
    return GateResult(
        passed=False,
        errors=list(errors),
        needs_human=needs_human,
        needs_agent=needs_agent,
    )


def ok(*warnings: str) -> GateResult:
    return GateResult(passed=True, warnings=list(warnings))

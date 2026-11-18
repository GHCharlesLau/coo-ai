"""Shared composition selection for HTML rendering and deck-quality gates."""

from __future__ import annotations

from coo.schemas.slides import Deck, DesignSpec, SlideSpec

_VARIANTS: dict[str, tuple[str, ...]] = {
    "title": ("cover", "split"),
    "section": ("agenda", "editorial"),
    "bullets": ("ledger", "split", "rail"),
    "two_column": ("split", "offset"),
    "kpis": ("grid", "rail"),
    "budget": ("editorial", "rail"),
    "quote": ("editorial", "split"),
    "references": ("editorial", "ledger"),
    "next_steps": ("steps", "rail"),
    "diagram": ("flow", "framework"),
    "timeline": ("timeline", "rail"),
    "chart": ("data", "split"),
    "table": ("editorial", "dense"),
    "stats": ("grid", "rail"),
    "gallery": ("gallery", "mosaic"),
    "comparison": ("split", "offset"),
    "map": ("grid", "editorial"),
    "matrix": ("matrix", "split"),
    "photo": ("split", "bleed"),
    "board": ("wall",),
    "evidence": ("annotated",),
}


def resolve_variant(spec: SlideSpec, index: int, design: DesignSpec) -> str:
    """Resolve an explicit hint or rotate through layout-safe compositions."""
    explicit = spec.variant.strip()
    if explicit and explicit != "auto":
        return explicit
    # The briefing-board style is a wall of evidence: wide grids keep the
    # canvas full, while the narrow rail variants leave half a wall blank.
    if design.style == "briefing" and not spec.image and spec.layout in {"kpis", "stats", "timeline"}:
        return _VARIANTS[spec.layout][0]
    choices = _VARIANTS.get(spec.layout, ("editorial", "split", "rail"))
    hint = design.variant.strip()
    start = choices.index(hint) if hint in choices else index
    return choices[start % len(choices)]


def slide_tone(spec: SlideSpec, index: int, design: DesignSpec) -> str:
    if design.style == "briefing":
        return "light"
    if design.accent_mode == "mono":
        return "light"
    if design.accent_mode == "warm":
        return "dark" if spec.layout == "quote" else "light"
    return "dark" if spec.layout in {"section", "quote"} and index % 2 == 1 else "light"


def deck_variant(deck: Deck, spec: SlideSpec, index: int) -> str:
    return resolve_variant(spec, index, deck.design)

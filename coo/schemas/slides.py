from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SlideLayout = Literal[
    "title",
    "section",
    "bullets",
    "two_column",
    "kpis",
    "budget",
    "quote",
    "references",
    "next_steps",
    "diagram",
    "timeline",
    "chart",
    "photo",
    "table",
    "stats",
    "gallery",
    "comparison",
    "map",
    "matrix",
    "board",
    "evidence",
]


class DiagramNode(BaseModel):
    id: str
    label: str
    detail: str = ""
    date: str | None = None


class DiagramEdge(BaseModel):
    source: str
    target: str
    label: str = ""


class DiagramSpec(BaseModel):
    kind: Literal["flow", "framework", "timeline", "hub", "route"]
    nodes: list[DiagramNode] = Field(min_length=2)
    edges: list[DiagramEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_node_ids(self):
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("diagram node ids must be unique")
        known = set(ids)
        if any(edge.source not in known or edge.target not in known for edge in self.edges):
            raise ValueError("diagram edges must reference existing node ids")
        if any(edge.source == edge.target for edge in self.edges):
            raise ValueError("diagram edges cannot loop a node to itself")
        if self.kind == "timeline" and len(self.nodes) > 6:
            raise ValueError("timeline diagrams support at most six readable milestones per slide")
        return self


class ChartSeries(BaseModel):
    label: str
    values: list[float]

    @field_validator("values")
    @classmethod
    def nonnegative_values(cls, values: list[float]) -> list[float]:
        if any(value < 0 for value in values):
            raise ValueError("chart values must be non-negative")
        return values


class ChartSpec(BaseModel):
    kind: Literal["bar", "line", "donut", "horizontal_bar", "stacked_bar"]
    categories: list[str] = Field(min_length=1)
    series: list[ChartSeries] = Field(min_length=1)
    unit: str = ""
    axis_label: str = ""

    @model_validator(mode="after")
    def matching_values(self):
        if any(len(series.values) != len(self.categories) for series in self.series):
            raise ValueError("each chart series must have one value per category")
        if self.kind == "donut" and len(self.series) != 1:
            raise ValueError("donut charts need exactly one series")
        return self


class TableSpec(BaseModel):
    columns: list[str] = Field(min_length=1)
    rows: list[list[str]] = Field(min_length=1)
    align: list[Literal["left", "center", "right"]] = Field(default_factory=list)
    highlight_rows: list[int] = Field(default_factory=list)
    column_widths: list[float] = Field(default_factory=list)
    source_note: str = ""

    @model_validator(mode="after")
    def matching_columns(self):
        width = len(self.columns)
        if any(len(row) != width for row in self.rows):
            raise ValueError("every table row must match the column count")
        if self.align and len(self.align) != width:
            raise ValueError("table align must match the column count")
        if self.column_widths and len(self.column_widths) != width:
            raise ValueError("table column_widths must match the column count")
        if any(index < 0 or index >= len(self.rows) for index in self.highlight_rows):
            raise ValueError("table highlight_rows must reference existing rows")
        return self


class StatSpec(BaseModel):
    value: str
    label: str
    detail: str = ""
    source_note: str = ""


class MatrixCellSpec(BaseModel):
    title: str
    detail: str = ""
    tone: Literal["low", "medium", "high"] = "medium"


class MatrixSpec(BaseModel):
    x_label: str = "Likelihood"
    y_label: str = "Impact"
    cells: list[MatrixCellSpec] = Field(min_length=4, max_length=4)


class DesignSpec(BaseModel):
    density: Literal["airy", "balanced", "dense"] = "balanced"
    visual_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    reference_style: str = ""
    style: Literal["editorial", "brief", "report", "briefing"] = "editorial"
    accent_mode: Literal["contrast", "warm", "mono"] = "contrast"
    variant: str = "auto"


class ImageSpec(BaseModel):
    path: str
    alt_text: str
    caption: str = ""
    rights_status: Literal["supplied", "licensed"]
    usage: str
    source_url: str | None = None
    creator: str | None = None
    license: str | None = None
    placement: Literal["right", "left", "full_bleed", "inset"] = "right"

    @model_validator(mode="after")
    def verified_rights(self):
        if self.rights_status == "licensed" and not all((self.source_url, self.creator, self.license)):
            raise ValueError("licensed image needs source_url, creator, and license")
        if not self.alt_text.strip():
            raise ValueError("image needs alt_text")
        if not self.usage.strip():
            raise ValueError("image needs a usage-rights statement")
        return self


class SlideSpec(BaseModel):
    layout: SlideLayout
    title: str
    subtitle: str | None = None
    body: str | None = None
    bullets: list[str] = Field(default_factory=list)
    left: list[str] = Field(default_factory=list)
    right: list[str] = Field(default_factory=list)
    left_title: str | None = None
    right_title: str | None = None
    notes: str = ""
    cite_ids: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    quote: str | None = None
    attribution: str | None = None
    diagram: DiagramSpec | None = None
    chart: ChartSpec | None = None
    image: ImageSpec | None = None
    table: TableSpec | None = None
    stats: list[StatSpec] = Field(default_factory=list, max_length=4)
    images: list[ImageSpec] = Field(default_factory=list, max_length=4)
    matrix: MatrixSpec | None = None
    stamp: str | None = None
    source_note: str = ""
    variant: str = "auto"

    @model_validator(mode="after")
    def layout_payload(self):
        if self.layout == "table" and self.table is None:
            raise ValueError("table slide needs a table")
        if self.layout == "stats" and len(self.stats) < 2:
            raise ValueError("stats slide needs at least two stats")
        if self.layout == "gallery" and not 2 <= len(self.images) <= 4:
            raise ValueError("gallery slide needs two to four images")
        if self.layout == "comparison" and not (self.left and self.right):
            raise ValueError("comparison slide needs left and right items")
        if self.layout == "map" and not self.rows:
            raise ValueError("map slide needs rows of region names and notes")
        if self.layout == "matrix" and self.matrix is None:
            raise ValueError("matrix slide needs matrix cells")
        if self.layout == "board":
            if not 2 <= len(self.images) <= 4:
                raise ValueError("board slide needs two to four pinned images")
            if len(self.bullets) < 2:
                raise ValueError("board slide needs at least two tagged points")
        if self.layout == "evidence":
            if self.image is None:
                raise ValueError("evidence slide needs a photograph")
            if not 2 <= len(self.bullets) <= 5:
                raise ValueError("evidence slide needs two to five annotations")
        return self


class Deck(BaseModel):
    campaign_id: str
    theme: Literal["editorial", "navy_gold"] = "editorial"
    budget_total: float | None = None
    budget_low: float | None = None
    budget_high: float | None = None
    budget_complete: bool = True
    budget_currency: str | None = None
    kpi_ids: list[str] = Field(default_factory=list)
    tactic_ids: list[str] = Field(default_factory=list)
    slides: list[SlideSpec]
    # Tolerated for old decks; the HTML-first engine intentionally ignores it.
    template_path: str | None = None
    palette: dict[str, str] = Field(default_factory=dict)
    font_heading: str | None = None
    font_body: str | None = None
    design: DesignSpec = Field(default_factory=DesignSpec)

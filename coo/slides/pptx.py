"""Render a Deck to a native, editable PowerPoint presentation.

Every slide is built from OOXML primitives: text boxes, autoshapes, native
tables, native charts, and picture frames. Nothing is rasterized, no speaker
notes are written, and no internal generation metadata is embedded in the file.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from coo.schemas.brief import Brief
from coo.schemas.evidence import EvidenceLog
from coo.schemas.slides import Deck, ImageSpec, SlideSpec
from coo.slides.web import build_html, palette_for
from coo.store import CampaignStore

# 1920 x 1080 design units map exactly onto a 13.333 x 7.5 inch slide.
_DESIGN_W = 1920
_DESIGN_H = 1080
_EMU_PER_UNIT = 6350


def _u(value: float) -> Emu:
    return Emu(int(round(value * _EMU_PER_UNIT)))


def _rgb(value: str) -> RGBColor:
    return RGBColor.from_string(value.lstrip("#").upper())


def _hex(value: str) -> str:
    return value.lstrip("#").upper()


FONT_BODY = "Segoe UI"
FONT_DISPLAY = "Segoe UI Semibold"
FONT_SERIF = "Palatino Linotype"
FONT_MONO = "Consolas"
FONT_MARKER = "Segoe Print"

_LABEL = {
    "title": "Campaign proposal",
    "section": "Section",
    "bullets": "Plan",
    "two_column": "Context",
    "kpis": "Measurement",
    "budget": "Budget",
    "quote": "Strategy",
    "references": "Sources",
    "next_steps": "Next steps",
    "diagram": "Plan",
    "timeline": "Plan",
    "chart": "Measurement",
    "photo": "Visual",
    "table": "Data",
    "stats": "At a glance",
    "gallery": "Visual",
    "comparison": "Comparison",
    "map": "Reach",
    "matrix": "Risk",
    "board": "Briefing wall",
    "evidence": "Evidence",
}


# ---------------------------------------------------------------------------
# primitives


def _type_scale(size: float) -> float:
    """Enlarge small presentation type while leaving display sizes stable."""
    if size <= 10:
        return round(size * 1.35, 1)
    if size <= 14:
        return round(size * 1.25, 1)
    if size <= 20:
        return round(size * 1.16, 1)
    if size <= 30:
        return round(size * 1.06, 1)
    return size


def _style_run(run, size: float, color: str, *, bold: bool = False, italic: bool = False, font: str = FONT_BODY) -> None:
    run.font.size = Pt(_type_scale(size))
    run.font.bold = bold
    run.font.italic = italic
    run.font.name = font
    run.font.color.rgb = _rgb(color)


def _text(
    slide,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    *,
    size: float = 18,
    color: str = "24241E",
    bold: bool = False,
    italic: bool = False,
    font: str = FONT_BODY,
    align=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
    spacing: float = 1.0,
    after: float = 0,
    caps: bool = False,
):
    box = slide.shapes.add_textbox(_u(x), _u(y), _u(w), _u(h))
    frame = box.text_frame
    frame.word_wrap = True
    frame.auto_size = MSO_AUTO_SIZE.NONE
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    frame.vertical_anchor = anchor
    lines = str(text or "").split("\n")
    for index, line in enumerate(lines):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = align
        paragraph.line_spacing = spacing
        paragraph.space_after = Pt(after)
        run = paragraph.add_run()
        run.text = line.upper() if caps else line
        _style_run(run, size, color, bold=bold, italic=italic, font=font)
    return box


def _hanging(paragraph, indent: float = 0.36) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_pr.set("marL", str(int(Inches(indent))))
    p_pr.set("indent", str(-int(Inches(indent))))


def _list(
    slide,
    x: float,
    y: float,
    w: float,
    h: float,
    items: list[str],
    *,
    size: float = 18,
    color: str = "24241E",
    marker_color: str = "B03A2E",
    numbered: bool = True,
    bullet: bool = False,
    gap: float = 10,
    spacing: float = 1.06,
    indent: float = 0.42,
    start: int = 1,
):
    box = slide.shapes.add_textbox(_u(x), _u(y), _u(w), _u(h))
    frame = box.text_frame
    frame.word_wrap = True
    frame.auto_size = MSO_AUTO_SIZE.NONE
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    for index, item in enumerate(items):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.line_spacing = spacing
        paragraph.space_after = Pt(gap)
        _hanging(paragraph, indent)
        prefix = ""
        if numbered:
            prefix = f"{start + index:02d}  "
        elif bullet:
            prefix = "•  "
        if prefix:
            run = paragraph.add_run()
            run.text = prefix
            _style_run(run, size, marker_color, bold=numbered, font=FONT_MONO if numbered else FONT_BODY)
        run = paragraph.add_run()
        run.text = item
        _style_run(run, size, color)
    return box


def _rect(slide, x: float, y: float, w: float, h: float, fill: str, *, line: str | None = None, radius: float | None = None):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius is not None else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, _u(x), _u(y), _u(w), _u(h))
    if radius is not None:
        shape.adjustments[0] = radius
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(fill)
    if line:
        shape.line.color.rgb = _rgb(line)
        shape.line.width = Pt(0.9)
    else:
        shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def _rule(slide, x: float, y: float, w: float, color: str, *, thickness: float = 1.5) -> None:
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, _u(x), _u(y), _u(w), _u(thickness))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(color)
    shape.line.fill.background()
    shape.shadow.inherit = False


def _card(slide, x: float, y: float, w: float, h: float, palette: dict[str, str], *, fill: str | None = None, accent: str | None = None):
    shape = _rect(slide, x, y, w, h, fill or palette["tag"], line=palette["rule"], radius=0.035)
    if accent:
        _rect(slide, x, y + 10, 8, h - 20, accent)
    return shape


def _pill(slide, x: float, y: float, w: float, text: str, palette: dict[str, str], *, fill: str | None = None, color: str | None = None, size: float = 12):
    shape = _rect(slide, x, y, w, 40, fill or palette["tag"], line=palette["rule"], radius=0.5)
    frame = shape.text_frame
    frame.word_wrap = False
    frame.margin_left = frame.margin_right = Inches(0.08)
    frame.margin_top = frame.margin_bottom = 0
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    paragraph = frame.paragraphs[0]
    paragraph.alignment = PP_ALIGN.CENTER
    run = paragraph.add_run()
    run.text = text
    _style_run(run, size, color or palette["ink"], bold=True)
    return shape


def _set_alpha(shape, pct: float) -> None:
    sp_pr = shape._element.spPr
    solid = sp_pr.find(qn("a:solidFill"))
    if solid is None:
        return
    color = solid.find(qn("a:srgbClr"))
    if color is None:
        return
    alpha = color.makeelement(qn("a:alpha"), {"val": str(int(pct * 100000))})
    color.append(alpha)


def _image_path(assets_root: Path | None, image: ImageSpec) -> Path:
    if assets_root is None:
        raise ValueError(f"image '{image.path}' needs an assets root")
    root = assets_root.resolve()
    path = (root / image.path).resolve()
    if path != root and root not in path.parents:
        raise ValueError("image path must stay inside campaign artifacts")
    if not path.is_file():
        raise FileNotFoundError(f"image asset not found: {image.path}")
    return path


def _picture(slide, assets_root: Path | None, image: ImageSpec, x: float, y: float, w: float, h: float):
    path = _image_path(assets_root, image)
    picture = slide.shapes.add_picture(str(path), _u(x), _u(y), _u(w), _u(h))
    try:
        with Image.open(path) as source:
            image_w, image_h = source.size
        target = w / max(1.0, h)
        actual = image_w / max(1, image_h)
        if actual > target:
            crop = (1 - target / actual) / 2
            picture.crop_left = crop
            picture.crop_right = crop
        elif actual < target:
            crop = (1 - actual / target) / 2
            picture.crop_top = crop
            picture.crop_bottom = crop
    except Exception:  # noqa: BLE001 - a cropped frame is cosmetic
        pass
    picture._element.nvPicPr.cNvPr.set("descr", image.alt_text)
    return picture


# ---------------------------------------------------------------------------
# deck chrome


def _background(slide, palette: dict[str, str]) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = _rgb(palette["paper"])


def _header(slide, spec: SlideSpec, index: int, total: int, palette: dict[str, str]) -> float:
    label = _LABEL.get(spec.layout, "Campaign proposal")
    _text(slide, 96, 58, 520, 26, label, size=10.5, color=palette["accent"], font=FONT_MONO, caps=True)
    _text(slide, 1600, 58, 224, 26, f"{index + 1:02d} / {total:02d}", size=10.5, color=palette["muted"], font=FONT_MONO, align=PP_ALIGN.RIGHT)
    _rule(slide, 96, 90, 1728, palette["rule"], thickness=1)

    title_size = 34 if len(spec.title) <= 46 else 30 if len(spec.title) <= 64 else 26
    _text(slide, 96, 108, 1728, 120, spec.title, size=title_size, color=palette["ink"], bold=True, font=FONT_DISPLAY, spacing=0.98)
    top = 300.0
    if spec.subtitle:
        _text(slide, 96, 238, 1600, 46, spec.subtitle, size=18, color=palette["blue"], font=FONT_MARKER, spacing=1.0)
        top = 330.0
    return top


def _footer(slide, spec: SlideSpec, brand: str, citations: dict[str, str], palette: dict[str, str]) -> None:
    _rule(slide, 96, 1000, 1728, palette["rule"], thickness=1)
    if brand:
        _text(slide, 96, 1012, 280, 22, brand.upper(), size=8.5, color=palette["ink"], bold=True, font=FONT_MONO, caps=True)
    if spec.cite_ids:
        labels = [citations.get(cite_id, cite_id) for cite_id in spec.cite_ids]
        source = "Sources: " + "; ".join(labels)
        if len(source) > 165:
            source = source[:162].rstrip() + "..."
        _text(slide, 400, 1012, 1110, 22, source, size=8, color=palette["muted"], font=FONT_MONO)
    _text(slide, 1470, 1012, 354, 22, "Draft for client review", size=8, color=palette["muted"], font=FONT_MONO, align=PP_ALIGN.RIGHT)


def _source_note(slide, text: str, palette: dict[str, str], *, y: float = 936, width: float = 1500) -> None:
    if text:
        _text(slide, 96, y, width, 34, text, size=10, color=palette["muted"], font=FONT_MONO, spacing=1.05)


# ---------------------------------------------------------------------------
# shared layout blocks


def _stat_cards(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> None:
    stats = spec.stats[:4]
    columns = len(stats)
    gap = 24.0
    width = (1728 - gap * (columns - 1)) / columns
    height = min(520.0, 960 - top)
    for index, stat in enumerate(stats):
        x = 96 + index * (width + gap)
        _card(slide, x, top, width, height, palette, accent=palette["blue"] if index else palette["accent"])
        _text(slide, x + 28, top + 24, width - 56, 24, f"{index + 1:02d}", size=10, color=palette["accent"], font=FONT_MONO)
        value_size = 40 if len(stat.value) <= 8 else 28
        _text(slide, x + 28, top + 62, width - 56, 96, stat.value, size=value_size, color=palette["ink"], bold=True, font=FONT_SERIF, spacing=0.95)
        _text(slide, x + 28, top + 166, width - 56, 78, stat.label, size=16, color=palette["ink"], bold=True, spacing=1.05)
        _text(slide, x + 28, top + 256, width - 56, height - 316, stat.detail, size=13, color=palette["muted"], spacing=1.12)
        if stat.source_note:
            _text(slide, x + 28, top + height - 54, width - 56, 38, stat.source_note, size=9, color=palette["muted"], font=FONT_MONO, spacing=1.0)


def _kpi_rows(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> None:
    rows = spec.rows
    height = min(112.0, (950 - top) / max(1, len(rows)) - 8)
    for index, row in enumerate(rows):
        name = row[0] if row else ""
        value = row[1] if len(row) > 1 else ""
        detail = row[2] if len(row) > 2 else ""
        y = top + index * (height + 10)
        _card(slide, 96, y, 1728, height, palette, fill=palette["tag"], accent=palette["accent"] if index % 2 else palette["blue"])
        _text(slide, 118, y + 16, 42, 36, f"{index + 1:02d}", size=10, color=palette["accent"], font=FONT_MONO)
        _text(slide, 176, y + 12, 430, height - 24, name, size=15, color=palette["ink"], bold=True, anchor=MSO_ANCHOR.MIDDLE, spacing=1.02)
        _text(slide, 630, y + 12, 250, height - 24, value, size=18 if len(value) > 8 else 24, color=palette["accent"] if len(value) > 8 else palette["ink"], bold=True, font=FONT_SERIF, anchor=MSO_ANCHOR.MIDDLE, spacing=0.98)
        _text(slide, 900, y + 12, 900, height - 24, detail, size=12, color=palette["muted"], anchor=MSO_ANCHOR.MIDDLE, spacing=1.1)


def _budget_table(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> float:
    """Render the budget's rows as a native table and return its bottom edge."""
    rows = spec.rows
    if not rows:
        return top
    columns = max(len(row) for row in rows)
    row_height = 60.0
    table_height = row_height * len(rows)
    frame = slide.shapes.add_table(len(rows), columns, _u(96), _u(top), _u(1728), _u(table_height))
    table = frame.table
    table.first_row = False
    table.horz_banding = False
    for row in table.rows:
        row.height = _u(row_height)
    proportions = [2.3, 1.0, 1.5, 1.0, 1.0]
    total = sum(proportions[:columns])
    for index, column in enumerate(table.columns):
        column.width = _u(1728 * proportions[index] / total)
    for row_index, row in enumerate(rows):
        is_header = row_index == 0
        is_total = row_index == len(rows) - 1
        for column_index in range(columns):
            cell = table.cell(row_index, column_index)
            cell.margin_left = cell.margin_right = Inches(0.1)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.text = ""
            paragraph = cell.text_frame.paragraphs[0]
            paragraph.line_spacing = 1.0
            if column_index:
                paragraph.alignment = PP_ALIGN.RIGHT
            run = paragraph.add_run()
            run.text = str(row[column_index]) if column_index < len(row) else ""
            if is_header:
                _style_run(run, 12.5, palette["white"], bold=True, font=FONT_MONO)
                cell.fill.solid()
                cell.fill.fore_color.rgb = _rgb(palette["navy"])
            elif is_total:
                _style_run(run, 15, palette["accent"], bold=True, font=FONT_SERIF)
                cell.fill.solid()
                cell.fill.fore_color.rgb = _rgb(palette["note"])
            else:
                _style_run(run, 14, palette["ink"])
                cell.fill.solid()
                cell.fill.fore_color.rgb = _rgb(palette["tag"] if row_index % 2 else palette["white"])
    return top + table_height


def _table_row_heights(rows: list[list[str]], widths: list[float], font_size: float, base: float) -> list[float]:
    """Estimate wrapped row heights so the table and its note never collide."""
    scaled = _type_scale(font_size)
    total_width = sum(widths) or len(widths)
    heights: list[float] = []
    for row in rows:
        lines = 1
        for index, value in enumerate(row):
            column_width = 1728 * widths[index] / total_width - 36
            per_line = max(8, int(column_width / (scaled * 1.05)))
            needed = 1
            for chunk in str(value).split("\n"):
                needed = max(needed, math.ceil(len(chunk) / per_line))
            lines = max(lines, needed)
        heights.append(max(base, lines * scaled * 2.15 + 12))
    return heights


def _table(slide, spec: SlideSpec, top: float, palette: dict[str, str], *, height: float | None = None) -> None:
    table_spec = spec.table
    if table_spec is None:
        return
    rows = [table_spec.columns, *table_spec.rows]
    columns = len(table_spec.columns)
    longest = max((len(str(cell)) for row in rows for cell in row), default=10)
    font_size = 14.0 if longest <= 28 and len(rows) <= 6 else 12.5 if longest <= 48 else 11.5
    row_height = 54.0 if len(rows) <= 6 else 48.0
    widths = table_spec.column_widths or [1.0] * columns
    row_heights = _table_row_heights(rows, widths, font_size, row_height)
    table_height = height or sum(row_heights)
    frame = slide.shapes.add_table(len(rows), columns, _u(96), _u(top), _u(1728), _u(table_height))
    table = frame.table
    table.first_row = False
    table.horz_banding = False
    for row, row_height_value in zip(table.rows, row_heights):
        row.height = _u(row_height_value)
    total = sum(widths) or columns
    for index, column in enumerate(table.columns):
        column.width = _u(1728 * widths[index] / total)
    for row_index, row in enumerate(rows):
        for column_index in range(columns):
            cell = table.cell(row_index, column_index)
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.text = ""
            paragraph = cell.text_frame.paragraphs[0]
            paragraph.line_spacing = 1.0
            run = paragraph.add_run()
            run.text = str(row[column_index])
            if row_index == 0:
                _style_run(run, font_size, palette["white"], bold=True)
                cell.fill.solid()
                cell.fill.fore_color.rgb = _rgb(palette["navy"])
            else:
                highlight = (row_index - 1) in table_spec.highlight_rows
                _style_run(run, font_size, palette["ink"] if not highlight else palette["accent"], bold=highlight)
                cell.fill.solid()
                if highlight:
                    cell.fill.fore_color.rgb = _rgb(palette["note"])
                else:
                    cell.fill.fore_color.rgb = _rgb(palette["tag"] if row_index % 2 else palette["white"])
    _source_note(slide, spec.source_note or table_spec.source_note, palette, y=top + table_height + 12)


def _flow(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> None:
    diagram = spec.diagram
    if diagram is None:
        return
    nodes = diagram.nodes[:4]
    gap = 34.0
    width = (1728 - gap * (len(nodes) - 1)) / len(nodes)
    height = min(330.0, 940 - top)
    for index, node in enumerate(nodes):
        x = 96 + index * (width + gap)
        _card(slide, x, top, width, height, palette, accent=palette["blue"])
        _text(slide, x + 24, top + 22, 60, 24, f"{index + 1:02d}", size=10, color=palette["accent"], font=FONT_MONO)
        _text(slide, x + 24, top + 58, width - 48, 82, node.label, size=19, color=palette["ink"], bold=True, spacing=1.02)
        _text(slide, x + 24, top + 150, width - 48, height - 176, node.detail, size=12.5, color=palette["muted"], spacing=1.12)
        if index < len(nodes) - 1:
            arrow = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, _u(x + width + 6), _u(top + height / 2 - 17), _u(gap - 12), _u(34))
            arrow.fill.solid()
            arrow.fill.fore_color.rgb = _rgb(palette["blue"])
            arrow.line.fill.background()
            arrow.shadow.inherit = False


def _framework(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> None:
    diagram = spec.diagram
    if diagram is None:
        return
    head = diagram.nodes[0]
    _text(slide, 96, top, 1728, 22, "HEADLINE", size=10, color=palette["blue"], font=FONT_MONO)
    _text(slide, 96, top + 28, 1728, 60, head.label, size=25, color=palette["ink"], bold=True, font=FONT_SERIF, spacing=1.0)
    _text(slide, 96, top + 94, 1500, 52, head.detail, size=13, color=palette["muted"], spacing=1.1)
    pillars = diagram.nodes[1:5]
    if not pillars:
        return
    gap = 30.0
    width = (1728 - gap * (len(pillars) - 1)) / len(pillars)
    y = top + 170
    height = min(360.0, 950 - y)
    for index, node in enumerate(pillars):
        x = 96 + index * (width + gap)
        _card(slide, x, y, width, height, palette, accent=palette["accent"])
        _text(slide, x + 24, y + 22, width - 48, 22, f"PILLAR {index + 1:02d}", size=9.5, color=palette["accent"], font=FONT_MONO)
        _text(slide, x + 24, y + 56, width - 48, 84, node.label, size=21, color=palette["ink"], bold=True, spacing=1.02)
        _text(slide, x + 24, y + 148, width - 48, height - 172, node.detail, size=13, color=palette["muted"], spacing=1.12)


def _hub(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> None:
    diagram = spec.diagram
    if diagram is None:
        return
    hub = diagram.nodes[0]
    spokes = diagram.nodes[1:5]
    center_x, center_y = 960.0, top + 300.0
    hub_w, hub_h = 470.0, 220.0
    hub_shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, _u(center_x - hub_w / 2), _u(center_y - hub_h / 2), _u(hub_w), _u(hub_h))
    hub_shape.fill.solid()
    hub_shape.fill.fore_color.rgb = _rgb(palette["navy"])
    hub_shape.line.color.rgb = _rgb(palette["blue"])
    hub_shape.line.width = Pt(2)
    hub_shape.shadow.inherit = False
    hub_shape.text_frame.word_wrap = True
    hub_shape.text_frame.margin_left = hub_shape.text_frame.margin_right = Inches(0.12)
    hub_paragraph = hub_shape.text_frame.paragraphs[0]
    hub_paragraph.alignment = PP_ALIGN.CENTER
    run = hub_paragraph.add_run()
    run.text = hub.label
    _style_run(run, 18, palette["white"], bold=True)
    if hub.detail:
        detail_paragraph = hub_shape.text_frame.add_paragraph()
        detail_paragraph.alignment = PP_ALIGN.CENTER
        detail_run = detail_paragraph.add_run()
        detail_run.text = hub.detail
        _style_run(detail_run, 10, palette["white"], italic=True)
    positions = [
        (110, top + 20, 440, 180),
        (1370, top + 20, 440, 180),
        (110, top + 410, 440, 180),
        (1370, top + 410, 440, 180),
    ]
    for index, node in enumerate(spokes):
        x, y, w, h = positions[index]
        _card(slide, x, y, w, h, palette, accent=palette["accent"] if index % 2 else palette["blue"])
        _text(slide, x + 20, y + 18, w - 40, 58, node.label, size=17, color=palette["ink"], bold=True, spacing=1.0)
        _text(slide, x + 20, y + 78, w - 40, h - 96, node.detail, size=11.5, color=palette["muted"], spacing=1.08)
        target_x = x + w if x < center_x else x
        target_y = y + h / 2
        connector = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, _u(center_x), _u(center_y), _u(target_x), _u(target_y))
        connector.line.color.rgb = _rgb(palette["blue"])
        connector.line.width = Pt(1.5)


def _timeline(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> None:
    diagram = spec.diagram
    if diagram is None:
        return
    nodes = diagram.nodes[:6]
    line_y = top + 190
    left, right = 150.0, 1770.0
    _rule(slide, left, line_y, right - left, palette["blue"], thickness=2.5)
    step = (right - left) / max(1, len(nodes) - 1) if len(nodes) > 1 else 0
    for index, node in enumerate(nodes):
        x = left + index * step if len(nodes) > 1 else (left + right) / 2
        circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, _u(x - 15), _u(line_y - 15), _u(30), _u(30))
        circle.fill.solid()
        circle.fill.fore_color.rgb = _rgb(palette["paper"])
        circle.line.color.rgb = _rgb(palette["blue"])
        circle.line.width = Pt(3)
        circle.shadow.inherit = False
        if node.date:
            _text(slide, x - 170, line_y - 74, 340, 40, node.date, size=13, color=palette["blue"], font=FONT_MARKER, align=PP_ALIGN.CENTER)
        card_w = 285.0
        _text(slide, x - card_w / 2, line_y + 38, card_w, 60, node.label, size=16, color=palette["ink"], bold=True, align=PP_ALIGN.CENTER, spacing=1.0)
        _text(slide, x - card_w / 2, line_y + 100, card_w, 170, node.detail, size=11.5, color=palette["muted"], align=PP_ALIGN.CENTER, spacing=1.1)


def _route(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> None:
    diagram = spec.diagram
    if diagram is None:
        return
    nodes = diagram.nodes[:6]
    line_y = top + 250
    left, right = 170.0, 1750.0
    _rule(slide, left, line_y, right - left, palette["blue"], thickness=3.0)
    step = (right - left) / max(1, len(nodes) - 1) if len(nodes) > 1 else 0
    for index, node in enumerate(nodes):
        x = left + index * step if len(nodes) > 1 else (left + right) / 2
        circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, _u(x - 18), _u(line_y - 18), _u(36), _u(36))
        circle.fill.solid()
        circle.fill.fore_color.rgb = _rgb(palette["paper"])
        circle.line.color.rgb = _rgb(palette["blue"])
        circle.line.width = Pt(3.5)
        circle.shadow.inherit = False
        above = index % 2 == 0
        card_w = 280.0
        if above:
            date_y, label_y, detail_y = line_y - 210, line_y - 168, line_y - 106
        else:
            date_y, label_y, detail_y = line_y + 44, line_y + 86, line_y + 148
        if node.date:
            _text(slide, x - card_w / 2, date_y, card_w, 34, node.date, size=13, color=palette["blue"], font=FONT_MARKER, align=PP_ALIGN.CENTER)
        _text(slide, x - card_w / 2, label_y, card_w, 54, node.label, size=17, color=palette["ink"], bold=True, align=PP_ALIGN.CENTER, spacing=1.0)
        _text(slide, x - card_w / 2, detail_y, card_w, 90, node.detail, size=11, color=palette["muted"], align=PP_ALIGN.CENTER, spacing=1.08)


def _chart(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> None:
    chart_spec = spec.chart
    if chart_spec is None:
        return
    data = CategoryChartData()
    data.categories = chart_spec.categories
    for series in chart_spec.series:
        data.add_series(series.label, series.values)
    kind = {
        "bar": XL_CHART_TYPE.COLUMN_CLUSTERED,
        "line": XL_CHART_TYPE.LINE_MARKERS,
        "donut": XL_CHART_TYPE.DOUGHNUT,
        "horizontal_bar": XL_CHART_TYPE.BAR_CLUSTERED,
        "stacked_bar": XL_CHART_TYPE.COLUMN_STACKED,
    }[chart_spec.kind]
    frame = slide.shapes.add_chart(kind, _u(96), _u(top), _u(1728), _u(600), data)
    chart = frame.chart
    chart.has_title = False
    chart.font.name = FONT_BODY
    chart.font.size = Pt(_type_scale(11))
    chart.font.color.rgb = _rgb(palette["ink"])
    chart.has_legend = len(chart_spec.series) > 1 or chart_spec.kind == "donut"
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.RIGHT
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(_type_scale(11))
    plot = chart.plots[0]
    if chart_spec.kind != "donut":
        plot.gap_width = 55
        plot.has_data_labels = True
        labels = plot.data_labels
        labels.font.size = Pt(_type_scale(10))
        labels.number_format = "#,##0"
        labels.number_format_is_linked = False
        if chart_spec.kind in {"bar", "horizontal_bar", "stacked_bar"}:
            labels.position = XL_LABEL_POSITION.OUTSIDE_END
    colors = [palette["accent"], palette["blue"], palette["gold"], palette["olive"], palette["muted"], palette["navy"]]
    for series_index, series in enumerate(chart.series):
        if chart_spec.kind == "line":
            series.format.line.color.rgb = _rgb(colors[series_index % len(colors)])
            series.format.line.width = Pt(2.5)
            series.smooth = False
        elif chart_spec.kind == "donut":
            for point_index, point in enumerate(series.points):
                point.format.fill.solid()
                point.format.fill.fore_color.rgb = _rgb(colors[point_index % len(colors)])
        else:
            series.format.fill.solid()
            series.format.fill.fore_color.rgb = _rgb(colors[series_index % len(colors)])
    if chart_spec.kind != "donut":
        chart.value_axis.has_major_gridlines = False
        chart.value_axis.tick_labels.font.size = Pt(_type_scale(10))
        chart.category_axis.tick_labels.font.size = Pt(_type_scale(10))
        if chart_spec.axis_label:
            chart.value_axis.has_title = True
            chart.value_axis.axis_title.text_frame.text = chart_spec.axis_label
            for paragraph in chart.value_axis.axis_title.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(9.5)
                    run.font.name = FONT_BODY
    _source_note(slide, spec.source_note, palette, y=top + 616)
    if chart_spec.kind == "donut" and len(chart_spec.series) == 1:
        total = sum(chart_spec.series[0].values)
        unit = (chart_spec.unit or "").split()[0]
        if "000" in (chart_spec.unit or ""):
            total *= 1000
        label = f"{unit} {total:,.0f}".strip()
        _text(slide, 620, top + 258, 460, 64, label, size=20.5, color=palette["ink"], bold=True, font=FONT_SERIF, align=PP_ALIGN.CENTER)
        _text(slide, 620, top + 322, 460, 30, "base case", size=11, color=palette["muted"], font=FONT_MONO, align=PP_ALIGN.CENTER)


def _gallery(slide, spec: SlideSpec, top: float, palette: dict[str, str], assets_root: Path | None) -> None:
    images = spec.images
    gap = 22.0
    width = (1728 - gap * (len(images) - 1)) / len(images)
    height = 430.0 if len(images) <= 3 else 340.0
    if len(images) > 3:
        card_extra, caption_h, credit_y = 200.0, 120.0, 128.0
    else:
        card_extra, caption_h, credit_y = 160.0, 96.0, 104.0
    for index, image in enumerate(images):
        x = 96 + index * (width + gap)
        _rect(slide, x, top, width, height + card_extra, palette["white"], line=palette["rule"])
        picture = _picture(slide, assets_root, image, x + 10, top + 10, width - 20, height - 20)
        picture.line.color.rgb = _rgb(palette["rule"])
        caption = image.caption or image.alt_text
        _text(slide, x + 12, top + height + 4, width - 24, caption_h, caption, size=12.5, color=palette["ink"], bold=True, spacing=1.05)
        credit = " / ".join(part for part in (image.creator, image.license) if part)
        if credit and not any(part in caption for part in (image.creator or "", image.license or "")):
            _text(slide, x + 12, top + height + credit_y, width - 24, 40, credit, size=10, color=palette["muted"], font=FONT_MONO)


def _comparison(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> None:
    body = spec.body or ""
    body_height = (0 if not body else 88 if len(body) > 92 else 52)
    if body:
        _text(slide, 96, top, 1728, body_height, body, size=13, color=palette["muted"], spacing=1.1)
    panel_top = top + body_height + 10
    panel_w = 760.0
    panel_h = min(470.0, 950 - panel_top)
    _card(slide, 96, panel_top, panel_w, panel_h, palette, fill=palette["card"], accent=palette["muted"])
    _card(slide, 1064, panel_top, panel_w, panel_h, palette, fill=palette["tag"], accent=palette["accent"])
    _text(slide, 126, panel_top + 22, panel_w - 60, 30, (spec.left_title or "Before").upper(), size=11, color=palette["muted"], font=FONT_MONO)
    _text(slide, 1094, panel_top + 22, panel_w - 60, 30, (spec.right_title or "After").upper(), size=11, color=palette["accent"], font=FONT_MONO)
    _list(slide, 126, panel_top + 66, panel_w - 60, panel_h - 90, spec.left, size=15, color=palette["ink"], numbered=False, bullet=True, marker_color=palette["muted"], gap=9)
    _list(slide, 1094, panel_top + 66, panel_w - 60, panel_h - 90, spec.right, size=15, color=palette["ink"], numbered=False, bullet=True, marker_color=palette["accent"], gap=9)
    circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, _u(930), _u(panel_top + panel_h / 2 - 30), _u(60), _u(60))
    circle.fill.solid()
    circle.fill.fore_color.rgb = _rgb(palette["paper"])
    circle.line.color.rgb = _rgb(palette["rule"])
    circle.line.width = Pt(1)
    circle.shadow.inherit = False
    circle.text_frame.word_wrap = False
    paragraph = circle.text_frame.paragraphs[0]
    paragraph.alignment = PP_ALIGN.CENTER
    run = paragraph.add_run()
    run.text = "VS"
    _style_run(run, 10.5, palette["accent"], bold=True, font=FONT_MONO)


def _map(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> None:
    rows = spec.rows
    columns = 4 if len(rows) > 24 else 3
    row_count = (len(rows) + columns - 1) // columns
    gap_x, gap_y = 18.0, 8.0
    width = (1728 - gap_x * (columns - 1)) / columns
    available = 930 - top - 46
    height = max(54.0, (available - gap_y * (row_count - 1)) / row_count)
    for index, row in enumerate(rows):
        column = index % columns
        line = index // columns
        x = 96 + column * (width + gap_x)
        y = top + line * (height + gap_y)
        host = "host" in (row[1] if len(row) > 1 else "").casefold()
        _rect(slide, x, y, width, height, palette["note"] if host else palette["tag"], line=palette["rule"])
        _text(slide, x + 12, y + 8, 30, 20, f"{index + 1:02d}", size=8, color=palette["accent"], font=FONT_MONO)
        _text(slide, x + 46, y + 6, width - 58, 28, row[0] if row else "", size=13, color=palette["ink"], bold=True)
        _text(slide, x + 46, y + 38, width - 58, height - 42, row[1] if len(row) > 1 else "", size=9.5, color=palette["muted"], font=FONT_MONO)
    _source_note(slide, spec.source_note, palette, y=940)


def _matrix(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> None:
    matrix = spec.matrix
    if matrix is None:
        return
    _text(slide, 96, top - 4, 500, 24, f"{matrix.y_label.upper()} ↑", size=10, color=palette["muted"], font=FONT_MONO)
    grid_x, grid_y = 170.0, top + 26
    grid_w, grid_h = 1540.0, min(530.0, 940 - grid_y)
    gap = 18.0
    cell_w = (grid_w - gap) / 2
    cell_h = (grid_h - gap) / 2
    tones = {
        "high": (palette["note"], palette["accent"]),
        "medium": (palette["tag"], palette["gold"]),
        "low": (palette["white"], palette["blue"]),
    }
    for index, cell in enumerate(matrix.cells):
        column = index % 2
        row = index // 2
        x = grid_x + column * (cell_w + gap)
        y = grid_y + row * (cell_h + gap)
        fill, accent = tones[cell.tone]
        _card(slide, x, y, cell_w, cell_h, palette, fill=fill, accent=accent)
        _text(slide, x + 22, y + 18, 90, 22, f"{index + 1:02d}", size=9, color=accent, font=FONT_MONO)
        _text(slide, x + 22, y + 48, cell_w - 44, 50, cell.title, size=20, color=palette["ink"], bold=True, font=FONT_SERIF, spacing=1.0)
        _text(slide, x + 22, y + 104, cell_w - 44, cell_h - 120, cell.detail, size=13, color=palette["muted"], spacing=1.12)
    _text(slide, grid_x + grid_w / 2 - 150, grid_y + grid_h + 10, 300, 24, f"{matrix.x_label.upper()} →", size=10, color=palette["muted"], font=FONT_MONO, align=PP_ALIGN.CENTER)
    _source_note(slide, spec.source_note, palette, y=942)


def _board(slide, spec: SlideSpec, top: float, palette: dict[str, str], assets_root: Path | None) -> None:
    images = spec.images[:4]
    rail_x = 1260.0
    rail_w = 564.0
    if len(images) == 2:
        cell_w, cell_h = 545.0, 560.0
        positions = [(96, top), (96 + cell_w + 30, top)]
    elif len(images) == 3:
        positions = [(96, top), (96 + 682 + 22, top), (96 + 682 + 22, top + 292)]
    else:
        cell_w, cell_h = 545.0, 258.0
        positions = [
            (96, top),
            (96 + cell_w + 30, top),
            (96, top + cell_h + 24),
            (96 + cell_w + 30, top + cell_h + 24),
        ]
    for index, image in enumerate(images):
        x, y = positions[index]
        w = 545.0 if len(images) in (2, 4) else (682.0 if index == 0 else 416.0)
        h = cell_h if len(images) in (2, 4) else (560.0 if index == 0 else 268.0)
        _rect(slide, x, y, w, h, palette["white"], line=palette["rule"])
        _picture(slide, assets_root, image, x + 10, y + 10, w - 20, h - 58)
        caption = image.caption or image.alt_text
        if len(caption) > 78:
            caption = caption[:75].rstrip() + "..."
        _text(slide, x + 10, y + h - 46, w - 20, 42, caption, size=9.5, color=palette["ink"], spacing=1.0)
    _text(slide, rail_x, top, rail_w, 34, "THE WALL", size=10, color=palette["blue"], font=FONT_MONO)
    _text(slide, rail_x, top + 34, rail_w, 210, spec.body or "", size=13.5, color=palette["ink"], spacing=1.14)
    for index, tag in enumerate(spec.bullets[:5]):
        _pill(slide, rail_x, top + 260 + index * 50, rail_w, tag, palette, fill=palette["tag"], color=palette["ink"], size=11.5)
    if spec.stamp:
        stamp = _rect(slide, rail_x + 40, top + 510, 300, 56, palette["paper"], line=palette["accent"], radius=0.08)
        stamp.fill.background()
        stamp.line.color.rgb = _rgb(palette["accent"])
        stamp.line.width = Pt(2.5)
        stamp.rotation = -7
        paragraph = stamp.text_frame.paragraphs[0]
        paragraph.alignment = PP_ALIGN.CENTER
        run = paragraph.add_run()
        run.text = spec.stamp.upper()
        _style_run(run, 15, palette["accent"], bold=True, font=FONT_MONO)
    _source_note(slide, spec.source_note, palette, y=898, width=1120)


def _evidence(slide, spec: SlideSpec, top: float, palette: dict[str, str], assets_root: Path | None) -> None:
    image = spec.image
    if image is None:
        return
    image_w, image_h = 1040.0, 500.0
    _rect(slide, 96, top, image_w + 20, image_h + 90, palette["white"], line=palette["rule"])
    picture = _picture(slide, assets_root, image, 106, top + 10, image_w, image_h - 20)
    picture.line.color.rgb = _rgb(palette["rule"])
    _text(slide, 106, top + image_h + 12, image_w, 58, image.caption or image.alt_text, size=9.5, color=palette["muted"], spacing=1.0)
    badge_positions = [(0.18, 0.30), (0.42, 0.48), (0.66, 0.60), (0.82, 0.34), (0.30, 0.72)]
    for index, _ in enumerate(spec.bullets[:5]):
        fx, fy = badge_positions[index]
        cx, cy = 106 + image_w * fx, top + 10 + (image_h - 20) * fy
        circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, _u(cx - 17), _u(cy - 17), _u(34), _u(34))
        circle.fill.solid()
        circle.fill.fore_color.rgb = _rgb(palette["accent"])
        circle.line.color.rgb = _rgb(palette["white"])
        circle.line.width = Pt(2)
        circle.shadow.inherit = False
        paragraph = circle.text_frame.paragraphs[0]
        paragraph.alignment = PP_ALIGN.CENTER
        run = paragraph.add_run()
        run.text = str(index + 1)
        _style_run(run, 11, palette["white"], bold=True)
    rail_x = 1190.0
    rail_w = 634.0
    _text(slide, rail_x, top, rail_w, 34, "ANNOTATIONS", size=10, color=palette["blue"], font=FONT_MONO)
    _list(slide, rail_x, top + 42, rail_w, 460, spec.bullets[:5], size=13.5, color=palette["ink"], numbered=True, marker_color=palette["accent"], gap=12, indent=0.38)
    if spec.stamp:
        stamp = _rect(slide, rail_x, top + 560, 320, 56, palette["paper"], line=palette["accent"], radius=0.08)
        stamp.fill.background()
        stamp.line.color.rgb = _rgb(palette["accent"])
        stamp.line.width = Pt(2.5)
        stamp.rotation = -7
        paragraph = stamp.text_frame.paragraphs[0]
        paragraph.alignment = PP_ALIGN.CENTER
        run = paragraph.add_run()
        run.text = spec.stamp.upper()
        _style_run(run, 15, palette["accent"], bold=True, font=FONT_MONO)
    _source_note(slide, spec.source_note, palette, y=948)


def _next_steps(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> None:
    items = spec.bullets[:6]
    columns = 2 if len(items) > 3 else 1
    rows = (len(items) + columns - 1) // columns
    gap_x, gap_y = 24.0, 16.0
    width = (1728 - gap_x * (columns - 1)) / columns
    height = min(230.0, (950 - top - gap_y * (rows - 1)) / rows)
    for index, item in enumerate(items):
        column = index % columns
        row = index // columns
        x = 96 + column * (width + gap_x)
        y = top + row * (height + gap_y)
        _card(slide, x, y, width, height, palette, accent=palette["accent"] if index % 2 == 0 else palette["blue"])
        _text(slide, x + 24, y + 18, 70, 50, f"{index + 1:02d}", size=22, color=palette["accent"], bold=True, font=FONT_SERIF)
        _text(slide, x + 100, y + 20, width - 124, height - 40, item, size=15, color=palette["ink"], anchor=MSO_ANCHOR.MIDDLE, spacing=1.12)


def _references(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> None:
    items = spec.bullets
    columns = 2 if len(items) > 4 else 1
    per_column = (len(items) + columns - 1) // columns
    width = (1728 - 70) / columns
    for column in range(columns):
        chunk = items[column * per_column : (column + 1) * per_column]
        if not chunk:
            continue
        x = 96 + column * (width + 70)
        _list(slide, x, top, width, 700, chunk, size=11.5, color=palette["ink"], numbered=True, marker_color=palette["accent"], gap=9, spacing=1.0, indent=0.38, start=column * per_column + 1)


# ---------------------------------------------------------------------------
# slide dispatch


def _title(slide, spec: SlideSpec, index: int, total: int, palette: dict[str, str], assets_root: Path | None, brand: str) -> None:
    _background(slide, palette)
    photo = spec.image
    if photo is not None:
        _picture(slide, assets_root, photo, 0, 0, 1920, 1080)
        scrim = _rect(slide, 0, 0, 1920, 1080, "000000")
        _set_alpha(scrim, 0.42)
        text_color, muted, rule = palette["white"], "E8E2D6", "FFFFFF"
        _text(slide, 96, 84, 900, 28, "CAMPAIGN PROPOSAL", size=10.5, color=muted, font=FONT_MONO, caps=True)
        _text(slide, 1500, 84, 324, 28, brand.upper(), size=10.5, color=muted, font=FONT_MONO, align=PP_ALIGN.RIGHT, caps=True)
        _rule(slide, 96, 122, 1728, rule, thickness=1)
        _rule(slide, 96, 360, 132, palette["accent"], thickness=9)
        _text(slide, 96, 404, 1500, 210, spec.title, size=48, color=text_color, bold=True, font=FONT_DISPLAY, spacing=0.94)
        if spec.subtitle:
            _text(slide, 96, 610, 1560, 100, spec.subtitle, size=24, color="C6DAEC", font=FONT_MARKER, spacing=1.05)
        if spec.body:
            _text(slide, 96, 750, 980, 170, spec.body, size=15, color="EDE7DA", spacing=1.18)
        _rule(slide, 96, 944, 1728, "FFFFFF", thickness=1)
        _text(slide, 96, 962, 700, 30, brand, size=10, color=text_color, font=FONT_MONO, caps=True)
        _text(slide, 1500, 962, 324, 30, "CAMPAIGN PROPOSAL", size=10, color=muted, font=FONT_MONO, align=PP_ALIGN.RIGHT)
        return

    _text(slide, 96, 84, 900, 28, "CAMPAIGN PROPOSAL", size=10.5, color=palette["accent"], font=FONT_MONO, caps=True)
    _text(slide, 1500, 84, 324, 28, brand.upper(), size=10.5, color=palette["muted"], font=FONT_MONO, align=PP_ALIGN.RIGHT, caps=True)
    _rule(slide, 96, 122, 1728, palette["rule"], thickness=1)
    _rule(slide, 96, 292, 132, palette["accent"], thickness=9)
    _text(slide, 96, 334, 1600, 250, spec.title, size=52 if len(spec.title) <= 34 else 42, color=palette["ink"], bold=True, font=FONT_DISPLAY, spacing=0.94)
    if spec.subtitle:
        _text(slide, 96, 590, 1200, 100, spec.subtitle, size=24, color=palette["blue"], font=FONT_MARKER, spacing=1.05)
    if spec.body:
        _text(slide, 96, 730, 1050, 170, spec.body, size=16, color=palette["muted"], spacing=1.2)
    _rule(slide, 96, 944, 1728, palette["rule"], thickness=1)
    _text(slide, 96, 962, 700, 30, brand, size=10, color=palette["ink"], font=FONT_MONO, caps=True)
    _text(slide, 1500, 962, 324, 30, "CAMPAIGN PROPOSAL", size=10, color=palette["muted"], font=FONT_MONO, align=PP_ALIGN.RIGHT)


def _section(slide, spec: SlideSpec, index: int, total: int, palette: dict[str, str], assets_root: Path | None, brand: str) -> None:
    _background(slide, palette)
    _text(slide, 96, 58, 520, 26, "SECTION", size=10.5, color=palette["accent"], font=FONT_MONO, caps=True)
    _text(slide, 1600, 58, 224, 26, f"{index + 1:02d} / {total:02d}", size=10.5, color=palette["muted"], font=FONT_MONO, align=PP_ALIGN.RIGHT)
    _rule(slide, 96, 90, 1728, palette["rule"], thickness=1)
    copy_w = 1050.0 if spec.image else 1500.0
    _text(slide, 96, 176, 260, 140, f"{index + 1:02d}", size=86, color=palette["card"], bold=True, font=FONT_SERIF)
    _text(slide, 96, 330, copy_w, 120, spec.title, size=40 if len(spec.title) <= 36 else 34, color=palette["ink"], bold=True, font=FONT_DISPLAY, spacing=0.98)
    if spec.subtitle:
        _text(slide, 96, 456, copy_w, 52, spec.subtitle, size=19, color=palette["blue"], font=FONT_MARKER)
    if spec.body:
        _text(slide, 96, 512, copy_w, 70, spec.body, size=15, color=palette["muted"], spacing=1.15)
    if spec.bullets:
        _list(slide, 96, 596, copy_w, 340, spec.bullets, size=14.5, color=palette["ink"], numbered=True, marker_color=palette["accent"], gap=8, indent=0.4)
    if spec.image:
        _rect(slide, 1250, 220, 574, 660, palette["white"], line=palette["rule"])
        _picture(slide, assets_root, spec.image, 1260, 230, 554, 560)
        _text(slide, 1260, 798, 554, 62, spec.image.caption or spec.image.alt_text, size=9, color=palette["muted"], spacing=1.0)
    _footer(slide, spec, brand, {}, palette)


def _bullets(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> None:
    if spec.body:
        _text(slide, 96, top, 1500, 58, spec.body, size=14, color=palette["muted"], spacing=1.12)
        top += 64
    items = spec.bullets or ([spec.body] if spec.body else [])
    if not items:
        return
    size = 18.0 if len(items) <= 4 else 16.5 if len(items) <= 6 else 15.0
    if sum(len(item) for item in items) > 900:
        size -= 1.0
    _list(slide, 96, top, 1700, 940 - top, items, size=size, color=palette["ink"], numbered=True, marker_color=palette["accent"], gap=14, spacing=1.1, indent=0.5)


def _two_column(slide, spec: SlideSpec, top: float, palette: dict[str, str]) -> None:
    gap = 40.0
    width = (1728 - gap) / 2
    height = min(560.0, 950 - top)
    for index, (title, items, accent) in enumerate(
        (
            (spec.left_title or "Context", spec.left, palette["blue"]),
            (spec.right_title or "Response", spec.right, palette["accent"]),
        )
    ):
        x = 96 + index * (width + gap)
        _card(slide, x, top, width, height, palette, accent=accent)
        _text(slide, x + 26, top + 20, width - 52, 30, title.upper(), size=11, color=accent, font=FONT_MONO)
        _list(slide, x + 26, top + 62, width - 52, height - 84, items, size=16, color=palette["ink"], numbered=False, bullet=True, marker_color=accent, gap=11)


def _quote(slide, spec: SlideSpec, top: float, palette: dict[str, str], assets_root: Path | None) -> None:
    quote = spec.quote or spec.title
    width = 1000.0 if spec.image else 1600.0
    _text(slide, 96, top - 30, 100, 120, "“", size=96, color=palette["accent"], bold=True, font=FONT_SERIF)
    _text(slide, 150, top + 20, width, 300, quote, size=38 if len(quote) <= 60 else 32, color=palette["ink"], bold=True, font=FONT_SERIF, spacing=1.02)
    if spec.attribution:
        _text(slide, 150, top + 340, width, 120, spec.attribution, size=18, color=palette["muted"], spacing=1.15)
    if spec.image:
        _rect(slide, 1300, top - 10, 524, 604, palette["white"], line=palette["rule"])
        _picture(slide, assets_root, spec.image, 1310, top, 504, 520)
        _text(slide, 1310, top + 532, 504, 58, spec.image.caption or "", size=8.5, color=palette["muted"], spacing=1.0)


def _photo(slide, spec: SlideSpec, index: int, total: int, top: float, palette: dict[str, str], assets_root: Path | None, brand: str) -> None:
    image = spec.image
    if image is None:
        _bullets(slide, spec, top, palette)
        return
    if image.placement == "full_bleed":
        _picture(slide, assets_root, image, 0, 0, 1920, 1080)
        scrim = _rect(slide, 0, 0, 1920, 1080, "000000")
        _set_alpha(scrim, 0.46)
        _text(slide, 96, 58, 520, 26, "VISUAL", size=10.5, color="E8E2D6", font=FONT_MONO, caps=True)
        _text(slide, 1600, 58, 224, 26, f"{index + 1:02d} / {total:02d}", size=10.5, color="E8E2D6", font=FONT_MONO, align=PP_ALIGN.RIGHT)
        _text(slide, 96, 560, 1500, 130, spec.title, size=40, color=palette["white"], bold=True, font=FONT_DISPLAY, spacing=0.98)
        if spec.subtitle:
            _text(slide, 96, 700, 1200, 60, spec.subtitle, size=20, color="C6DAEC", font=FONT_MARKER)
        if spec.body:
            _text(slide, 96, 770, 1100, 100, spec.body, size=14, color="E8E2D6", spacing=1.15)
        _text(slide, 96, 940, 1400, 34, image.caption or "", size=9, color="D8D2C6", spacing=1.0)
        return

    image_x = 1130.0 if image.placement != "left" else 96.0
    text_x = 96.0 if image.placement != "left" else 1210.0
    _rect(slide, image_x, top, 694, 640, palette["white"], line=palette["rule"])
    _picture(slide, assets_root, image, image_x + 10, top + 10, 674, 540)
    _text(slide, image_x + 10, top + 564, 674, 58, image.caption or image.alt_text, size=9, color=palette["muted"], spacing=1.0)
    _text(slide, text_x, top + 20, 940, 300, spec.body or spec.subtitle or "", size=18, color=palette["ink"], spacing=1.2)


def _content(slide, spec: SlideSpec, top: float, palette: dict[str, str], assets_root: Path | None) -> None:
    layout = spec.layout
    if layout == "stats":
        _stat_cards(slide, spec, top, palette)
        _source_note(slide, spec.source_note, palette, y=940)
    elif layout == "kpis":
        _kpi_rows(slide, spec, top, palette)
    elif layout == "budget":
        table_bottom = _budget_table(slide, spec, top, palette)
        if spec.body:
            _text(slide, 96, table_bottom + 30, 1728, 60, spec.body, size=13, color=palette["muted"], spacing=1.12)
        if spec.rows:
            total = spec.rows[-1][1] if len(spec.rows[-1]) > 1 else ""
            if total:
                _text(slide, 96, table_bottom + 104, 1728, 44, f"Base case: USD {total}", size=20, color=palette["accent"], bold=True, font=FONT_SERIF)
    elif layout == "table":
        if spec.body:
            _text(slide, 96, top, 1728, 52, spec.body, size=13, color=palette["muted"], spacing=1.1)
            top += 62
        _table(slide, spec, top, palette)
    elif layout == "diagram":
        kind = spec.diagram.kind if spec.diagram else "flow"
        if spec.body:
            _text(slide, 96, top, 1600, 52, spec.body, size=13, color=palette["muted"], spacing=1.1)
            top += 58
        if kind == "framework":
            _framework(slide, spec, top, palette)
        elif kind == "hub":
            _hub(slide, spec, top, palette)
        elif kind == "route":
            _route(slide, spec, top, palette)
        elif kind == "timeline":
            _timeline(slide, spec, top, palette)
        else:
            _flow(slide, spec, top, palette)
        _source_note(slide, spec.source_note, palette, y=944)
    elif layout == "timeline":
        _timeline(slide, spec, top + 20, palette)
        _source_note(slide, spec.source_note, palette, y=944)
    elif layout == "chart":
        _chart(slide, spec, top, palette)
    elif layout == "gallery":
        if spec.body:
            _text(slide, 96, top, 1728, 46, spec.body, size=13, color=palette["muted"], spacing=1.1)
            top += 50
        _gallery(slide, spec, top, palette, assets_root)
        _source_note(slide, spec.source_note, palette, y=944)
    elif layout == "comparison":
        _comparison(slide, spec, top, palette)
        _source_note(slide, spec.source_note, palette, y=942)
    elif layout == "photo":
        _photo(slide, spec, 0, 0, top, palette, assets_root, "")
    elif layout == "map":
        _map(slide, spec, top, palette)
    elif layout == "matrix":
        _matrix(slide, spec, top, palette)
    elif layout == "board":
        _board(slide, spec, top, palette, assets_root)
    elif layout == "evidence":
        _evidence(slide, spec, top, palette, assets_root)
    elif layout == "next_steps":
        _next_steps(slide, spec, top, palette)
    elif layout == "references":
        _references(slide, spec, top - 40, palette)
    elif layout == "two_column":
        _two_column(slide, spec, top, palette)
    elif layout == "quote":
        _quote(slide, spec, top, palette, assets_root)
    else:
        _bullets(slide, spec, top, palette)


def _render_deck(deck: Deck, *, assets_root: Path | None, brand: str, citations: dict[str, str]) -> bytes:
    if not deck.slides:
        raise ValueError("slides.json has no slides")
    palette = palette_for(deck)
    palette["paper"] = palette["background"]
    palette["ink"] = palette["text"]
    presentation = Presentation()
    presentation.slide_width = Emu(int(_DESIGN_W * _EMU_PER_UNIT))
    presentation.slide_height = Emu(int(_DESIGN_H * _EMU_PER_UNIT))
    blank = presentation.slide_layouts[6]
    total = len(deck.slides)
    for index, spec in enumerate(deck.slides):
        slide = presentation.slides.add_slide(blank)
        _background(slide, palette)
        if spec.layout == "title":
            _title(slide, spec, index, total, palette, assets_root, brand)
            continue
        if spec.layout == "section":
            _section(slide, spec, index, total, palette, assets_root, brand)
            continue
        if spec.layout == "photo" and spec.image and spec.image.placement == "full_bleed":
            _photo(slide, spec, index, total, 300, palette, assets_root, brand)
            continue
        top = _header(slide, spec, index, total, palette)
        _content(slide, spec, top, palette, assets_root)
        _footer(slide, spec, brand, citations, palette)

    properties = presentation.core_properties
    properties.title = deck.slides[0].title
    properties.author = brand or "Campaign team"
    properties.last_modified_by = brand or "Campaign team"
    properties.subject = "Campaign proposal"
    properties.comments = ""
    properties.keywords = ""
    properties.category = ""
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def render_pptx_bytes(
    deck: Deck,
    *,
    assets_root: Path | None = None,
    citations: dict[str, str] | None = None,
    brand: str = "",
    html_path: Path | None = None,
    timeout: int = 90,
) -> bytes:
    """Render a deck to native, editable PPTX bytes.

    ``html_path`` and ``timeout`` are accepted for callers that previously used
    the rasterized renderer; they are no longer needed.
    """
    del html_path, timeout
    return _render_deck(deck, assets_root=assets_root, brand=brand, citations=citations or {})


def _brand(store: CampaignStore, campaign_id: str) -> str:
    if not store.has_artifact(campaign_id, "brief.json"):
        return ""
    try:
        return Brief.model_validate_json(store.read_artifact(campaign_id, "brief.json")).brand
    except Exception:  # noqa: BLE001 - brand is cosmetic for rendering
        return ""


def _citations(store: CampaignStore, campaign_id: str) -> dict[str, str]:
    if not store.has_artifact(campaign_id, "evidence.json"):
        return {}
    try:
        evidence = EvidenceLog.model_validate_json(store.read_artifact(campaign_id, "evidence.json"))
    except Exception:  # noqa: BLE001 - citations are cosmetic for rendering
        return {}
    labels: dict[str, str] = {}
    for item in evidence.items:
        author = item.author or item.source or "Source"
        labels[item.id] = f"{author}, {item.year}" if item.year and item.year != "n.d." else author
    return labels


def render_campaign_deck(store: CampaignStore, campaign_id: str) -> Path:
    """Write proposal.html and proposal.pptx from the current slides.json."""
    deck = Deck.model_validate_json(store.read_artifact(campaign_id, "slides.json"))
    html_path = store.artifact_path(campaign_id, "proposal.html")
    payload = build_html(
        deck,
        citations=_citations(store, campaign_id),
        assets_root=store.artifacts_dir(campaign_id),
        brand=_brand(store, campaign_id),
    )
    store.write_bytes(campaign_id, "proposal.html", payload)
    data = render_pptx_bytes(
        deck,
        assets_root=store.artifacts_dir(campaign_id),
        citations=_citations(store, campaign_id),
        brand=_brand(store, campaign_id),
        html_path=html_path,
    )
    return store.write_bytes(campaign_id, "proposal.pptx", data)

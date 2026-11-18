"""Deterministic, self-contained HTML slide-deck renderer for COO AI decks.

The deck is generated from ``slides.json``. Output is a single HTML file with
inline CSS, inline JavaScript, and embedded image assets, so it can be shared
without a server, build step, or external asset folder.
"""

from __future__ import annotations

import base64
import html
import mimetypes
import re
from pathlib import Path

from coo.schemas.slides import Deck, DiagramSpec, SlideSpec
from coo.slides.variants import deck_variant, slide_tone

DEFAULT_PALETTE = {
    "navy": "171A17",
    "accent": "C7432F",
    "background": "F1EDE2",
    "text": "171A17",
    "muted": "5E6158",
    "card": "E5DFCF",
    "white": "FFFFFF",
    "rule": "C9C1AE",
    "olive": "5B6248",
    "gold": "A67C3D",
    "blue": "2C5578",
    "tag": "F7F1E3",
    "note": "F2E6A8",
}

# Lemo-Opuscar style: Engineering Briefing Board — enamel ground, graphite
# facts, blue measurement, red verdict, pinned prints and marker lettering.
BRIEFING_PALETTE = {
    "navy": "2A2B26",
    "accent": "B03A2E",
    "background": "EDE7DA",
    "text": "24241E",
    "muted": "6B675C",
    "card": "F6F0E2",
    "white": "FFFFFF",
    "rule": "C9C0AE",
    "olive": "5B6248",
    "gold": "A67C3D",
    "blue": "2C5578",
    "tag": "F7F1E3",
    "note": "F2E6A8",
}

_HEX = re.compile(r"^[0-9A-Fa-f]{6}$")

_LAYOUT_LABEL = {
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


def _e(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _color(value: str | None, fallback: str) -> str:
    candidate = (value or "").strip().lstrip("#")
    return candidate.upper() if _HEX.fullmatch(candidate) else fallback


def palette_for(deck: Deck) -> dict[str, str]:
    base = dict(BRIEFING_PALETTE if deck.design.style == "briefing" else DEFAULT_PALETTE)
    raw = {**base, **deck.palette}
    return {key: _color(raw.get(key), fallback) for key, fallback in base.items()}


def _is_long(text: str, limit: int) -> str:
    return " is-long" if len(text) > limit else ""


def _render_sources(spec: SlideSpec, citations: dict[str, str]) -> str:
    if not spec.cite_ids or spec.layout == "references":
        return ""
    labels = [citations.get(cite_id, cite_id) for cite_id in spec.cite_ids]
    return f'<span class="footer-sources">Sources: {_e("; ".join(labels))}</span>'


def _slide_shell(
    spec: SlideSpec,
    index: int,
    total: int,
    *,
    brand: str,
    citations: dict[str, str],
    content: str,
    extra_class: str = "",
    density: str = "balanced",
    variant: str = "editorial",
    tone: str = "light",
) -> str:
    title = spec.title.strip() or f"Slide {index + 1}"
    kicker = _LAYOUT_LABEL.get(spec.layout, "Campaign proposal")
    subtitle = f'<p class="slide-subtitle">{_e(spec.subtitle)}</p>' if spec.subtitle else ""
    return f"""
<section class="slide layout-{_e(spec.layout)} density-{_e(density)} variant-{_e(variant)} tone-{_e(tone)}{extra_class}" id="slide-{index + 1}" data-index="{index}" data-variant="{_e(variant)}" aria-label="Slide {index + 1}: {_e(title)}" aria-hidden="true">
  <div class="slide-inner">
    <header class="slide-head">
      <span class="kicker">{_e(kicker)}</span>
      <span class="head-line"></span>
      <span class="head-page">{index + 1:02d} / {total:02d}</span>
    </header>
    <h2 class="slide-title{_is_long(title, 42)}">{_e(title)}</h2>
    {subtitle}
    <div class="slide-content">{content}</div>
  </div>
  <footer class="slide-footer">
    <span class="footer-brand">{_e(brand)}</span>
    {_render_sources(spec, citations)}
    <span class="footer-note">Draft for client review</span>
  </footer>
</section>"""


def _title_slide(
    spec: SlideSpec,
    index: int,
    total: int,
    *,
    brand: str,
    citations: dict[str, str],
    assets_root: Path | None = None,
    variant: str = "cover",
    tone: str = "light",
) -> str:
    subtitle = f'<p class="title-subtitle">{_e(spec.subtitle)}</p>' if spec.subtitle else ""
    body = f'<p class="title-body">{_e(spec.body)}</p>' if spec.body else ""
    photo = ""
    photo_class = ""
    if spec.image:
        source = _asset_uri(spec.image, assets_root, slide_title=spec.title)
        if spec.image.placement == "full_bleed":
            photo = f'<img class="title-bleed" src="{source}" alt="{_e(spec.image.alt_text)}"/>'
            photo_class = " title-photo"
        else:
            photo = f'<img class="title-side" src="{source}" alt="{_e(spec.image.alt_text)}"/>'
            photo_class = " title-side-photo"
    return f"""
<section class="slide layout-title variant-{_e(variant)} tone-{_e(tone)}{photo_class}" id="slide-{index + 1}" data-index="{index}" data-variant="{_e(variant)}" aria-label="Slide {index + 1}: {_e(spec.title)}" aria-hidden="true">
  {photo}
  <div class="slide-inner title-inner">
    <header class="title-top">
      <span class="kicker">Campaign proposal</span>
      <span class="kicker">{_e(brand)}</span>
    </header>
    <div class="title-main">
      <div class="title-rule"></div>
      <h1 class="display{_is_long(spec.title, 34)}">{_e(spec.title)}</h1>
      {subtitle}
      {body}
    </div>
    <div class="title-meta">
      <span>{_e(brand)}</span>
      <span>Campaign proposal</span>
    </div>
    <div class="title-index" aria-hidden="true">{index + 1:02d}</div>
  </div>
</section>"""


def _section_slide(
    spec: SlideSpec,
    index: int,
    total: int,
    *,
    brand: str,
    citations: dict[str, str],
    assets_root: Path | None = None,
    variant: str = "agenda",
    tone: str = "light",
) -> str:
    subtitle = f'<p class="section-subtitle">{_e(spec.subtitle)}</p>' if spec.subtitle else ""
    body = f'<p class="section-body">{_e(spec.body)}</p>' if spec.body else ""
    items = spec.bullets
    listing = (
        '<ul class="section-list">'
        + "".join(f"<li><span>{i + 1:02d}</span>{_e(item)}</li>" for i, item in enumerate(items))
        + "</ul>"
        if items
        else ""
    )
    photo = ""
    grid_class = ""
    if spec.image and assets_root is not None:
        source = _asset_uri(spec.image, assets_root, slide_title=spec.title)
        caption = spec.image.caption or spec.image.alt_text
        photo = (
            '<figure class="print section-print">'
            '<span class="print-magnet" aria-hidden="true"></span>'
            f'<img src="{source}" alt="{_e(spec.image.alt_text)}"/>'
            f"<figcaption>{_e(caption)}</figcaption></figure>"
        )
        grid_class = " has-photo"
    return f"""
<section class="slide layout-section variant-{_e(variant)} tone-{_e(tone)}" id="slide-{index + 1}" data-index="{index}" data-variant="{_e(variant)}" aria-label="Slide {index + 1}: {_e(spec.title)}" aria-hidden="true">
  <div class="slide-inner section-inner">
    <header class="slide-head">
      <span class="kicker">Section</span>
      <span class="head-line"></span>
      <span class="head-page">{index + 1:02d} / {total:02d}</span>
    </header>
    <div class="section-grid{grid_class}">
      <div class="section-number" aria-hidden="true">{index + 1:02d}</div>
      <div class="section-copy">
        <h2 class="section-title{_is_long(spec.title, 34)}">{_e(spec.title)}</h2>
        {subtitle}
        {body}
        {listing}
      </div>
      {photo}
    </div>
  </div>
  <footer class="slide-footer">
    <span class="footer-brand">{_e(brand)}</span>
    {_render_sources(spec, citations)}
    <span class="footer-note">Draft for client review</span>
  </footer>
</section>"""


def _bullets(spec: SlideSpec) -> str:
    items = spec.bullets or ([spec.body] if spec.body else [])
    if not items:
        return ""
    rows = "".join(
        f'<li><span class="ledger-index">{index + 1:02d}</span><span class="ledger-copy">{_e(item)}</span></li>'
        for index, item in enumerate(items)
    )
    return f'<ul class="ledger-list">{rows}</ul>'


def _two_column(spec: SlideSpec) -> str:
    split = max(1, len(spec.bullets) // 2) if spec.bullets else 0
    left = spec.left or spec.bullets[:split]
    right = spec.right or spec.bullets[split:]
    left_title = spec.left_title or "Situation"
    right_title = spec.right_title or "Implication"

    def column(title: str, items: list[str]) -> str:
        rows = "".join(f"<li>{_e(item)}</li>" for item in items)
        return f'<section class="column"><h3>{_e(title)}</h3><ul class="rule-list">{rows}</ul></section>'

    return (
        f'<div class="two-col">{column(left_title, left)}'
        f'<div class="column-rule" aria-hidden="true"></div>'
        f'{column(right_title, right)}</div>'
    )


def _kpis(spec: SlideSpec) -> str:
    rows = spec.rows or [[item, "", ""] for item in spec.bullets]
    if not rows:
        return ""
    cols = 2 if len(rows) in {2, 4} else 3
    cards = []
    for index, cells in enumerate(rows):
        label = cells[0] if cells else f"Measure {index + 1}"
        value = cells[1] if len(cells) > 1 else ""
        detail = cells[2] if len(cells) > 2 else ""
        value_class = " is-word" if len(value) > 10 else ""
        cards.append(
            '<article class="kpi-card">'
            f'<span class="kpi-index">KPI {index + 1:02d}</span>'
            f'<h3>{_e(label)}</h3>'
            f'<p class="kpi-value{value_class}">{_e(value)}</p>'
            f'<p class="kpi-detail">{_e(detail)}</p>'
            "</article>"
        )
    return f'<div class="kpi-grid cols-{cols}">{"".join(cards)}</div>'


def _budget_summary(deck: Deck) -> str:
    currency = deck.budget_currency or "USD"
    if deck.budget_low is None or deck.budget_total is None or deck.budget_high is None:
        return "Budget range not supplied."
    if not deck.budget_complete and (deck.budget_total or 0) == 0:
        return (
            f"No priced component yet · {currency} 0 priced subtotal · "
            "full campaign cost undetermined."
        )
    completeness = "Complete estimate" if deck.budget_complete else "Priced subtotal · quotes outstanding"
    return (
        f"{completeness}: {currency} {deck.budget_low:,.0f} low · "
        f"{deck.budget_total:,.0f} base · {deck.budget_high:,.0f} high."
    )


def _budget(spec: SlideSpec, deck: Deck) -> str:
    rows = spec.rows or [["Line", "Amount"], *[[item, ""] for item in spec.bullets]]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    header = rows[0]
    head_cells = "".join(f"<th scope=\"col\">{_e(header[c] if c < len(header) else '')}</th>" for c in range(width))
    body_rows = []
    for row_index, row in enumerate(rows[1:], start=1):
        cells = []
        for column in range(width):
            value = row[column] if column < len(row) else ""
            cells.append(f"<td>{_e(value)}</td>")
        row_class = "total-row" if row_index == len(rows) - 1 and len(rows) > 2 else ""
        body_rows.append(f'<tr class="{row_class}">{"".join(cells)}</tr>')
    table = (
        '<div class="budget-wrap"><table class="budget-table">'
        f"<thead><tr>{head_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table></div>"
    )
    note = f'<p class="body-note">{_e(spec.body)}</p>' if spec.body else ""
    return f'{table}<p class="budget-summary">{_e(_budget_summary(deck))}</p>{note}'


def _quote(spec: SlideSpec, assets_root: Path | None = None) -> str:
    quote = spec.quote or spec.body or (spec.bullets[0] if spec.bullets else spec.title)
    attribution = f'<p class="quote-attribution">{_e(spec.attribution)}</p>' if spec.attribution else ""
    body = f'<p class="body-note">{_e(spec.body)}</p>' if spec.quote and spec.body else ""
    quote_block = (
        f'<figure class="pull-quote"><blockquote>{_e(quote)}</blockquote>{attribution}</figure>{body}'
    )
    if not spec.image:
        return quote_block
    source = _asset_uri(spec.image, assets_root, slide_title=spec.title)
    caption = f"<figcaption>{_e(spec.image.caption)}</figcaption>" if spec.image.caption else ""
    image_block = (
        '<figure class="quote-image print print-2">'
        '<span class="print-magnet" aria-hidden="true"></span>'
        f'<img src="{source}" alt="{_e(spec.image.alt_text)}"/>{caption}</figure>'
    )
    return f'<div class="quote-layout"><div class="quote-copy">{quote_block}</div>{image_block}</div>'


def _references(spec: SlideSpec) -> str:
    items = spec.bullets or ([spec.body] if spec.body else [])
    if not items:
        return ""
    rows = "".join(f"<li>{_e(item)}</li>" for item in items)
    dense = " dense" if len(items) > 6 else ""
    return f'<ol class="reference-list{dense}">{rows}</ol>'


def _next_steps(spec: SlideSpec) -> str:
    if not spec.bullets:
        return ""
    rows = "".join(
        f'<li><span class="step-number">{index + 1:02d}</span>'
        f'<span class="step-copy">{_e(item)}</span></li>'
        for index, item in enumerate(spec.bullets)
    )
    return f'<ol class="step-list">{rows}</ol>'


def _flow(diagram: DiagramSpec) -> str:
    nodes = diagram.nodes
    if len(nodes) > 4:
        cards = "".join(
            '<article class="flow-node compact">'
            f'<span class="flow-number">{index + 1:02d}</span>'
            f"<h3>{_e(node.label)}</h3>"
            f"<p>{_e(node.detail)}</p>"
            "</article>"
            for index, node in enumerate(nodes)
        )
        return f'<div class="flow-grid">{cards}</div>'
    parts: list[str] = []
    for index, node in enumerate(nodes):
        parts.append(
            '<article class="flow-node">'
            f'<span class="flow-number">{index + 1:02d}</span>'
            f"<h3>{_e(node.label)}</h3>"
            f"<p>{_e(node.detail)}</p>"
            "</article>"
        )
        if index < len(nodes) - 1:
            next_id = nodes[index + 1].id
            edge = next(
                (item for item in diagram.edges if item.source == node.id and item.target == next_id),
                None,
            )
            label = edge.label if edge else ""
            parts.append(
                f'<div class="flow-link"><span>{_e(label)}</span><span class="flow-arrow">→</span></div>'
            )
    return f'<div class="flow">{"".join(parts)}</div>'


def _framework(diagram: DiagramSpec) -> str:
    nodes = diagram.nodes
    if len(nodes) < 2:
        return _flow(diagram)
    headline = nodes[0]
    pillars = nodes[1:4]
    cards = "".join(
        '<article class="framework-pillar">'
        f'<span class="framework-index">{index + 1:02d}</span>'
        f"<h3>{_e(node.label)}</h3>"
        f"<p>{_e(node.detail)}</p>"
        "</article>"
        for index, node in enumerate(pillars)
    )
    return (
        '<div class="framework">'
        '<div class="framework-head">'
        '<span class="framework-kicker">Headline</span>'
        f"<h3>{_e(headline.label)}</h3>"
        f"<p>{_e(headline.detail)}</p>"
        "</div>"
        f'<div class="framework-pillars">{cards}</div>'
        "</div>"
    )


def _timeline(diagram: DiagramSpec) -> str:
    nodes = diagram.nodes
    items = "".join(
        '<div class="timeline-item">'
        f'<span class="timeline-date">{_e(node.date or "")}</span>'
        '<span class="timeline-dot" aria-hidden="true"></span>'
        f"<h3>{_e(node.label)}</h3>"
        f"<p>{_e(node.detail)}</p>"
        "</div>"
        for node in nodes
    )
    return f'<div class="timeline count-{len(nodes)}">{items}</div>'


def _hub(diagram: DiagramSpec) -> str:
    """A hub-and-spoke ink diagram: one centre card, spokes to up to six cards."""
    import math

    nodes = diagram.nodes
    if len(nodes) < 2:
        return _flow(diagram)
    hub = nodes[0]
    spokes = nodes[1:7]
    count = len(spokes)
    cx, cy, rx, ry = 50.0, 50.0, 38.0, 33.0
    lines: list[str] = []
    cards: list[str] = []
    for index, node in enumerate(spokes):
        angle = math.radians(-90 + 360 * index / count)
        x = round(cx + rx * math.cos(angle), 2)
        y = round(cy + ry * math.sin(angle), 2)
        lines.append(
            f'<line class="hub-spoke" x1="{cx}" y1="{cy}" x2="{x}" y2="{y}"/>'
            f'<circle class="hub-end" cx="{x}" cy="{y}" r="1.2"/>'
        )
        detail = f"<p>{_e(node.detail)}</p>" if node.detail else ""
        cards.append(
            f'<article class="hub-node" style="left:{x}%;top:{y}%">'
            f'<span class="hub-index">{index + 1:02d}</span>'
            f"<h3>{_e(node.label)}</h3>{detail}</article>"
        )
    hub_detail = f"<p>{_e(hub.detail)}</p>" if hub.detail else ""
    hub_card = (
        '<article class="hub-node is-hub" style="left:50%;top:50%">'
        '<span class="hub-index">Centre</span>'
        f"<h3>{_e(hub.label)}</h3>{hub_detail}</article>"
    )
    return (
        '<div class="hub">'
        '<svg class="hub-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">'
        f"{''.join(lines)}</svg>{hub_card}{''.join(cards)}</div>"
    )


def _route(diagram: DiagramSpec) -> str:
    """A transit-route diagram: one line, numbered stops, dates and cards."""
    nodes = diagram.nodes
    if len(nodes) < 2:
        return _flow(diagram)
    count = len(nodes)
    cards: list[str] = []
    for index, node in enumerate(nodes):
        x = round((index + 1) / (count + 1) * 100, 2)
        side = "is-above" if index % 2 == 0 else "is-below"
        date = f'<span class="route-date">{_e(node.date or "")}</span>' if node.date else ""
        detail = f"<p>{_e(node.detail)}</p>" if node.detail else ""
        cards.append(
            f'<article class="route-card {side}" style="left:{x}%">'
            f"{date}<h3>{_e(node.label)}</h3>{detail}</article>"
            f'<span class="route-stop" style="left:{x}%"></span>'
        )
    return (
        f'<div class="route count-{count}">'
        '<div class="route-line" aria-hidden="true"></div>'
        f"{''.join(cards)}</div>"
    )


def _diagram(spec: SlideSpec) -> str:
    if spec.diagram is None:
        return _bullets(spec)
    if spec.diagram.kind == "timeline":
        return _timeline(spec.diagram)
    if spec.diagram.kind == "framework":
        return _framework(spec.diagram)
    if spec.diagram.kind == "hub":
        return _hub(spec.diagram)
    if spec.diagram.kind == "route":
        return _route(spec.diagram)
    return _flow(spec.diagram)


def _donut_chart(spec: SlideSpec, chart, palette: dict[str, str], colors: list[str]) -> str:
    width, height = 1600, 650
    cx, cy, radius, inner = 500, 325, 270, 150
    values = chart.series[0].values
    total = sum(values) or 1.0
    start = -90.0
    marks: list[str] = []
    legend: list[str] = []
    import math

    for index, (category, value) in enumerate(zip(chart.categories, values)):
        angle = 360.0 * value / total
        end = start + angle
        large = 1 if angle > 180 else 0
        x1 = cx + radius * math.cos(math.radians(start))
        y1 = cy + radius * math.sin(math.radians(start))
        x2 = cx + radius * math.cos(math.radians(end))
        y2 = cy + radius * math.sin(math.radians(end))
        ix1 = cx + inner * math.cos(math.radians(end))
        iy1 = cy + inner * math.sin(math.radians(end))
        ix2 = cx + inner * math.cos(math.radians(start))
        iy2 = cy + inner * math.sin(math.radians(start))
        color = colors[index % len(colors)]
        marks.append(
            f'<path d="M {x1:.1f} {y1:.1f} A {radius} {radius} 0 {large} 1 {x2:.1f} {y2:.1f} '
            f'L {ix1:.1f} {iy1:.1f} A {inner} {inner} 0 {large} 0 {ix2:.1f} {iy2:.1f} Z" fill="{color}"/>'
        )
        legend.append(
            f'<div class="donut-legend-item"><i style="background:{color}"></i>'
            f'<span>{_e(category)}</span><strong>{value:g}</strong></div>'
        )
        start = end

    center_label = f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" class="donut-total">{total:,.0f}</text>'
    center_unit = f'<text x="{cx}" y="{cy + 34}" text-anchor="middle" class="donut-unit">{_e(chart.unit or "total")}</text>'
    return (
        f'<div class="chart-head"><div class="chart-legend"><span class="legend-item"><i style="background:{palette["accent"]}"></i>{_e(chart.series[0].label)}</span></div>'
        f'<span class="chart-unit">{_e(chart.axis_label or chart.unit)}</span></div>'
        f'<div class="donut-wrap"><svg class="chart donut" viewBox="0 0 {width} {height}" role="img" aria-label="{_e(spec.title)}">'
        f"<title>{_e(spec.title)}</title>{''.join(marks)}{center_label}{center_unit}</svg>"
        f'<div class="donut-legend">{"".join(legend)}</div></div>'
    )


def _horizontal_bar_chart(spec: SlideSpec, chart, palette: dict[str, str], colors: list[str]) -> str:
    width, height = 1600, 650
    left, right, top, bottom = 460, 1540, 46, 566
    plot_w, plot_h = right - left, bottom - top
    max_value = max((max(series.values) for series in chart.series), default=1) or 1
    n = max(1, len(chart.categories))
    row_h = plot_h / n
    group_h = min(72.0, row_h * 0.68)
    bar_h = group_h / max(1, len(chart.series))
    grid: list[str] = []
    for tick in range(5):
        x = left + plot_w * tick / 4
        value = max_value * tick / 4
        grid.append(
            f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}" stroke="{palette["rule"]}" stroke-width="1.5" opacity="0.7"/>'
            f'<text x="{x:.1f}" y="{bottom + 28}" text-anchor="middle" class="chart-axis">{value:g}</text>'
        )
    marks: list[str] = []
    for category_index, category in enumerate(chart.categories):
        cy = top + row_h * category_index + row_h / 2
        marks.append(
            f'<text x="{left - 22}" y="{cy + 6:.1f}" text-anchor="end" class="chart-category">{_e(category)}</text>'
        )
        for series_index, series in enumerate(chart.series):
            value = series.values[category_index]
            bar_w = plot_w * value / max_value
            y = cy - group_h / 2 + series_index * bar_h
            marks.append(
                f'<rect x="{left}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h - 4:.1f}" fill="{colors[series_index % len(colors)]}"/>'
                f'<text x="{left + bar_w + 10:.1f}" y="{y + bar_h / 2 + 5:.1f}" class="chart-value">{value:g}</text>'
            )
    legend = "".join(
        f'<span class="legend-item"><i style="background:{colors[index % len(colors)]}"></i>{_e(series.label)}</span>'
        for index, series in enumerate(chart.series)
    )
    return (
        f'<div class="chart-head"><div class="chart-legend">{legend}</div>'
        f'<span class="chart-unit">{_e(chart.axis_label or chart.unit)}</span></div>'
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{_e(spec.title)}">'
        f"<title>{_e(spec.title)}</title>{''.join(grid)}{''.join(marks)}</svg>"
    )


def _stacked_bar_chart(spec: SlideSpec, chart, palette: dict[str, str], colors: list[str]) -> str:
    width, height = 1600, 650
    left, right, top, bottom = 96, 1560, 46, 558
    plot_w, plot_h = right - left, bottom - top
    totals = [sum(series.values[index] for series in chart.series) for index in range(len(chart.categories))]
    max_value = max(totals, default=1) or 1
    n = max(1, len(chart.categories))
    cluster_w = plot_w / n
    bar_w = min(140.0, cluster_w * 0.58)
    grid: list[str] = []
    for tick in range(5):
        y = bottom - plot_h * tick / 4
        grid.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="{palette["rule"]}" stroke-width="1.5" opacity="0.7"/>'
            f'<text x="{left - 18}" y="{y + 6:.1f}" text-anchor="end" class="chart-axis">{max_value * tick / 4:g}</text>'
        )
    marks: list[str] = []
    for category_index, category in enumerate(chart.categories):
        center = left + cluster_w * category_index + cluster_w / 2
        cursor = bottom
        for series_index, series in enumerate(chart.series):
            value = series.values[category_index]
            bar_h = plot_h * value / max_value
            y = cursor - bar_h
            marks.append(
                f'<rect x="{center - bar_w / 2:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
                f'fill="{colors[series_index % len(colors)]}"/>'
            )
            if value:
                marks.append(
                    f'<text x="{center:.1f}" y="{y + bar_h / 2 + 5:.1f}" text-anchor="middle" class="chart-value-inverse">{value:g}</text>'
                )
            cursor = y
        marks.append(
            f'<text x="{center:.1f}" y="{bottom + 52}" text-anchor="middle" class="chart-category">{_e(category)}</text>'
        )
        marks.append(
            f'<text x="{center:.1f}" y="{bottom - plot_h * totals[category_index] / max_value - 14:.1f}" text-anchor="middle" class="chart-value">{totals[category_index]:g}</text>'
        )
    legend = "".join(
        f'<span class="legend-item"><i style="background:{colors[index % len(colors)]}"></i>{_e(series.label)}</span>'
        for index, series in enumerate(chart.series)
    )
    return (
        f'<div class="chart-head"><div class="chart-legend">{legend}</div>'
        f'<span class="chart-unit">{_e(chart.axis_label or chart.unit)}</span></div>'
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{_e(spec.title)}">'
        f"<title>{_e(spec.title)}</title>{''.join(grid)}{''.join(marks)}</svg>"
    )


def _chart_svg(spec: SlideSpec, palette: dict[str, str], style: str = "editorial") -> str:
    chart = spec.chart
    if chart is None:
        return _bullets(spec)
    if style == "briefing":
        colors = [
            f"#{palette['blue']}",
            f"#{palette['navy']}",
            f"#{palette['accent']}",
            f"#{palette['olive']}",
            f"#{palette.get('gold', 'A67C3D')}",
        ]
    else:
        colors = [
            f"#{palette['accent']}",
            f"#{palette['navy']}",
            f"#{palette['olive']}",
            f"#{palette['muted']}",
            f"#{palette.get('gold', 'A67C3D')}",
        ]
    if chart.kind == "donut":
        return _donut_chart(spec, chart, palette, colors)
    if chart.kind == "horizontal_bar":
        return _horizontal_bar_chart(spec, chart, palette, colors)
    if chart.kind == "stacked_bar":
        return _stacked_bar_chart(spec, chart, palette, colors)
    width, height = 1600, 650
    left, right, top, bottom = 96, 1560, 48, 558
    plot_w, plot_h = right - left, bottom - top
    max_value = max((max(series.values) for series in chart.series), default=1) or 1
    tick_count = 4
    grid = []
    for tick in range(tick_count + 1):
        y = bottom - plot_h * tick / tick_count
        value = max_value * tick / tick_count
        grid.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="{palette["rule"]}" stroke-width="1.5" opacity="0.7"/>'
            f'<text x="{left - 18}" y="{y + 6:.1f}" text-anchor="end" class="chart-axis">{value:g}</text>'
        )
    categories = chart.categories
    n = max(1, len(categories))
    cluster_w = plot_w / n
    marks: list[str] = []
    if chart.kind == "line":
        x_step = plot_w / max(1, n - 1)
        for series_index, series in enumerate(chart.series):
            color = colors[series_index % len(colors)]
            points = []
            for index, value in enumerate(series.values):
                x = left + index * x_step
                y = bottom - plot_h * value / max_value
                points.append((x, y))
                marks.append(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="{color}"/>'
                    f'<text x="{x:.1f}" y="{y - 16:.1f}" text-anchor="middle" class="chart-value">{value:g}</text>'
                )
            polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
            marks.append(
                f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="6" stroke-linejoin="round" stroke-linecap="round"/>'
            )
        for index, category in enumerate(categories):
            x = left + index * x_step
            marks.append(
                f'<text x="{x:.1f}" y="{bottom + 52}" text-anchor="middle" class="chart-category">{_e(category)}</text>'
            )
    else:
        group_w = min(180.0, cluster_w * 0.62)
        bar_w = group_w / max(1, len(chart.series))
        for category_index, category in enumerate(categories):
            center = left + cluster_w * category_index + cluster_w / 2
            for series_index, series in enumerate(chart.series):
                value = series.values[category_index]
                bar_h = plot_h * value / max_value
                x = center - group_w / 2 + series_index * bar_w
                y = bottom - bar_h
                marks.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w - 6:.1f}" height="{bar_h:.1f}" fill="{colors[series_index % len(colors)]}"/>'
                    f'<text x="{x + (bar_w - 6) / 2:.1f}" y="{y - 14:.1f}" text-anchor="middle" class="chart-value">{value:g}</text>'
                )
            marks.append(
                f'<text x="{center:.1f}" y="{bottom + 52}" text-anchor="middle" class="chart-category">{_e(category)}</text>'
            )
    legend = "".join(
        f'<span class="legend-item"><i style="background:{colors[index % len(colors)]}"></i>{_e(series.label)}</span>'
        for index, series in enumerate(chart.series)
    )
    axis_label = chart.axis_label or chart.unit
    axis = f'<span class="chart-unit">{_e(axis_label)}</span>' if axis_label else ""
    title = f'<title>{_e(spec.title)}</title>'
    return (
        f'<div class="chart-head"><div class="chart-legend">{legend}</div>{axis}</div>'
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{_e(spec.title)}">'
        f"{title}{''.join(grid)}{''.join(marks)}</svg>"
    )


def _image_data_uri(image_path: Path) -> str:
    mime = mimetypes.guess_type(image_path.name)[0] or "image/png"
    payload = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def _asset_uri(image, assets_root: Path | None, *, slide_title: str) -> str:
    if assets_root is None:
        raise ValueError(f"slide '{slide_title}' references an image without an asset root")
    root = assets_root.resolve()
    path = (root / image.path).resolve()
    if path != root and root not in path.parents:
        raise ValueError("image path must stay inside campaign artifacts")
    if not path.is_file():
        raise FileNotFoundError(f"image asset not found: {image.path}")
    return _image_data_uri(path)


def _source_note(text: str) -> str:
    return f'<p class="source-note">{_e(text)}</p>' if text.strip() else ""


def _credit_in_caption(image) -> bool:
    """True when the caption already carries the creator and licence."""
    caption = (image.caption or "").lower()
    parts = [part for part in (image.creator, image.license) if part]
    return bool(parts) and all(part.lower() in caption for part in parts)


def _print_frame(image, source: str, index: int, *, extra: str = "") -> str:
    """A pinned photograph: white print border, magnet, credit line."""
    caption = image.caption or image.alt_text
    return (
        f'<figure class="print print-{index % 4} {extra.strip()}">'
        '<span class="print-magnet" aria-hidden="true"></span>'
        f'<img src="{source}" alt="{_e(image.alt_text)}"/>'
        f"<figcaption>{_e(caption)}</figcaption>"
        "</figure>"
    )


def _stamp(text: str, tone: str = "red") -> str:
    return f'<span class="board-stamp stamp-{_e(tone)}">{_e(text)}</span>'


def _tag(text: str, index: int) -> str:
    return (
        f'<span class="board-tag board-tag-{index % 3} tag-{_e("blue" if index % 2 else "red")}">'
        f'<i aria-hidden="true"></i>{_e(text)}</span>'
    )


def _ink_dim(label: str) -> str:
    return f'<div class="ink-dim" aria-hidden="true"><span>{_e(label)}</span></div>'


def _table(spec: SlideSpec) -> str:
    table = spec.table
    if table is None:
        return _bullets(spec)
    align = table.align or ["left"] * len(table.columns)
    widths = table.column_widths or [1.0] * len(table.columns)
    total_width = sum(widths) or 1.0
    colgroup = "".join(
        f'<col style="width:{max(0.01, width / total_width) * 100:.2f}%"/>' for width in widths
    )
    head = "".join(
        f'<th scope="col" class="align-{_e(align[index])}">{_e(column)}</th>'
        for index, column in enumerate(table.columns)
    )
    body_rows = []
    highlights = set(table.highlight_rows)
    for row_index, row in enumerate(table.rows):
        cells = "".join(
            f'<td class="align-{_e(align[index])}">{_e(cell)}</td>'
            for index, cell in enumerate(row)
        )
        highlight = " is-highlight" if row_index in highlights else ""
        body_rows.append(f'<tr class="data-row{highlight}">{cells}</tr>')
    note = _source_note(table.source_note or spec.source_note)
    return (
        '<div class="table-wrap">'
        f'<table class="data-table"><colgroup>{colgroup}</colgroup>'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
        f"{note}</div>"
    )


def _stats(spec: SlideSpec) -> str:
    cards = []
    for index, stat in enumerate(spec.stats):
        detail = f'<p class="stat-detail">{_e(stat.detail)}</p>' if stat.detail else ""
        source = f'<p class="stat-source">{_e(stat.source_note)}</p>' if stat.source_note else ""
        long_class = " is-long" if len(stat.value) > 8 else ""
        cards.append(
            '<article class="stat-card">'
            f'<span class="stat-index">0{index + 1}</span>'
            f'<p class="stat-value{long_class}">{_e(stat.value)}</p>'
            f"<h3>{_e(stat.label)}</h3>"
            f"{detail}{source}</article>"
        )
    note = _source_note(spec.source_note)
    return f'<div class="stat-grid count-{len(cards)}">{"".join(cards)}</div>{note}'


def _gallery(spec: SlideSpec, assets_root: Path | None) -> str:
    items = []
    for index, image in enumerate(spec.images):
        source = _asset_uri(image, assets_root, slide_title=spec.title)
        caption = image.caption or image.alt_text
        credit_parts = [part for part in (image.creator, image.license) if part]
        credit = " / ".join(credit_parts) or ("Supplied asset" if image.rights_status == "supplied" else "")
        if _credit_in_caption(image):
            credit = ""
        credit_node = f'<span class="gallery-credit">{_e(credit)}</span>' if credit else ""
        items.append(
            f'<figure class="gallery-item print print-{index % 4}">'
            '<span class="print-magnet" aria-hidden="true"></span>'
            f'<img src="{source}" alt="{_e(image.alt_text)}"/>'
            f"<figcaption><strong>{_e(caption)}</strong>{credit_node}</figcaption>"
            "</figure>"
        )
    note = _source_note(spec.source_note)
    return f'<div class="gallery count-{len(items)}">{"".join(items)}</div>{note}'


def _comparison(spec: SlideSpec) -> str:
    note = _source_note(spec.source_note)
    body = f'<p class="body-note">{_e(spec.body)}</p>' if spec.body else ""
    return (
        f"{body}"
        '<div class="comparison">'
        '<section class="comparison-panel">'
        f'<h3>{_e(spec.left_title or "Before")}</h3>'
        f'<ul class="rule-list">{"".join(f"<li>{_e(item)}</li>" for item in spec.left)}</ul>'
        "</section>"
        '<div class="versus" aria-hidden="true">VS</div>'
        '<section class="comparison-panel">'
        f'<h3>{_e(spec.right_title or "After")}</h3>'
        f'<ul class="rule-list">{"".join(f"<li>{_e(item)}</li>" for item in spec.right)}</ul>'
        "</section></div>"
        f"{note}"
    )


def _map(spec: SlideSpec) -> str:
    tiles = []
    for index, row in enumerate(spec.rows):
        name = row[0] if row else ""
        detail = " ".join(row[1:]).strip()
        tiles.append(
            '<div class="map-tile">'
            f'<span class="map-index">{index + 1:02d}</span>'
            f"<strong>{_e(name)}</strong>"
            f'<span class="map-detail">{_e(detail)}</span>'
            "</div>"
        )
    legend = ""
    if spec.bullets:
        legend = '<div class="map-legend">' + "".join(
            f'<span><i aria-hidden="true"></i>{_e(item)}</span>' for item in spec.bullets
        ) + "</div>"
    note = _source_note(spec.source_note)
    return f'<div class="map-grid count-{len(tiles)}">{"".join(tiles)}</div>{legend}{note}'


def _matrix(spec: SlideSpec) -> str:
    matrix = spec.matrix
    if matrix is None:
        return _bullets(spec)
    cells = "".join(
        f'<article class="matrix-cell tone-{_e(cell.tone)}">'
        f"<h3>{_e(cell.title)}</h3>"
        f"<p>{_e(cell.detail)}</p>"
        "</article>"
        for cell in matrix.cells
    )
    note = _source_note(spec.source_note)
    return (
        '<div class="matrix-wrap">'
        f'<span class="matrix-axis matrix-axis-y">{_e(matrix.y_label)}</span>'
        f'<div class="matrix-grid">{cells}</div>'
        f'<span class="matrix-axis matrix-axis-x">{_e(matrix.x_label)}</span>'
        f"</div>{note}"
    )


def _photo(spec: SlideSpec, assets_root: Path | None) -> str:
    image = spec.image
    if image is None:
        return _bullets(spec)
    source = _asset_uri(image, assets_root, slide_title=spec.title)
    caption = f"<figcaption>{_e(image.caption)}</figcaption>" if image.caption else ""
    body = f'<p class="photo-body">{_e(spec.body)}</p>' if spec.body else ""
    return (
        '<div class="photo-grid">'
        f'<figure class="photo-frame"><img src="{source}" alt="{_e(image.alt_text)}"/>{caption}</figure>'
        f'<div class="photo-copy">{body}</div>'
        "</div>"
    )


def _board(spec: SlideSpec, assets_root: Path | None) -> str:
    """Lemo-Opuscar briefing wall: pinned prints, a sticky note, tags and a verdict."""
    figures = []
    for index, image in enumerate(spec.images):
        source = _asset_uri(image, assets_root, slide_title=spec.title)
        figures.append(_print_frame(image, source, index, extra=f"board-print board-print-{index}"))
    tags = "".join(_tag(text, index) for index, text in enumerate(spec.bullets))
    note = (
        f'<div class="board-note"><span class="board-note-kicker">Note</span>'
        f"<p>{_e(spec.body)}</p></div>"
        if spec.body
        else ""
    )
    sources = (
        f'<p class="board-sources">{_e(spec.source_note)}</p>' if spec.source_note else ""
    )
    stamp = _stamp(spec.stamp or "BRIEFING")
    return (
        '<div class="board-wall">'
        f'<div class="board-prints count-{len(figures)}">{"".join(figures)}</div>'
        f'<aside class="board-rail">{stamp}{note}'
        f'<div class="board-tags">{tags}</div>{sources}</aside>'
        "</div>"
    )


def _evidence(spec: SlideSpec, assets_root: Path | None) -> str:
    """One pinned photograph with numbered leader lines to marker annotations."""
    image = spec.image
    if image is None:
        return _bullets(spec)
    source = _asset_uri(image, assets_root, slide_title=spec.title)
    count = len(spec.bullets)
    anchors = [max(12.0, min(88.0, (index + 0.5) / count * 100)) for index in range(count)]
    leaders: list[str] = []
    for index, y in enumerate(anchors):
        x = 52.0 if index % 2 == 0 else 44.0
        leaders.append(f'<path class="leader" d="M {x} {y} L 98 {y}"/>')
        leaders.append(f'<circle class="leader-ring" cx="{x}" cy="{y}" r="2.6"/>')
    callouts = "".join(
        f'<div class="callout"><span class="callout-index">{index + 1:02d}</span>'
        f"<p>{_e(text)}</p></div>"
        for index, text in enumerate(spec.bullets)
    )
    caption = image.caption or image.alt_text
    credit_parts = [part for part in (image.creator, image.license) if part]
    credit = "" if _credit_in_caption(image) else " / ".join(credit_parts)
    credit_node = f" · {_e(credit)}" if credit else ""
    stamp = _stamp(spec.stamp) if spec.stamp else ""
    return (
        '<div class="evidence">'
        '<div class="evidence-photo">'
        '<figure class="print evidence-print">'
        '<span class="print-magnet" aria-hidden="true"></span>'
        f'<img src="{source}" alt="{_e(image.alt_text)}"/>'
        '<svg class="leader-layer" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">'
        f"{''.join(leaders)}</svg>"
        f"<figcaption>{_e(caption)}{credit_node}</figcaption></figure>"
        "</div>"
        f'<div class="evidence-notes">{callouts}{stamp}</div>'
        "</div>"
    )


def _content(spec: SlideSpec, deck: Deck, assets_root: Path | None, palette: dict[str, str]) -> str:
    if spec.layout == "bullets":
        content = _bullets(spec)
        note = f'<p class="body-note">{_e(spec.body)}</p>' if spec.bullets and spec.body else ""
        return content + note
    if spec.layout == "two_column":
        note = f'<p class="body-note">{_e(spec.body)}</p>' if spec.body else ""
        return _two_column(spec) + note
    if spec.layout == "kpis":
        note = f'<p class="body-note">{_e(spec.body)}</p>' if spec.body else ""
        return _kpis(spec) + note
    if spec.layout == "budget":
        return _budget(spec, deck)
    if spec.layout == "quote":
        return _quote(spec, assets_root)
    if spec.layout == "references":
        return _references(spec)
    if spec.layout == "next_steps":
        note = f'<p class="body-note">{_e(spec.body)}</p>' if spec.body else ""
        return _next_steps(spec) + note
    if spec.layout in {"diagram", "timeline"}:
        note = f'<p class="body-note">{_e(spec.body)}</p>' if spec.body else ""
        return _diagram(spec) + note
    if spec.layout == "chart":
        note = f'<p class="body-note">{_e(spec.body)}</p>' if spec.body else ""
        return _chart_svg(spec, palette, deck.design.style) + note + _source_note(spec.source_note)
    if spec.layout == "table":
        return _table(spec)
    if spec.layout == "stats":
        note = f'<p class="body-note">{_e(spec.body)}</p>' if spec.body else ""
        return _stats(spec) + note
    if spec.layout == "gallery":
        return _gallery(spec, assets_root)
    if spec.layout == "comparison":
        return _comparison(spec)
    if spec.layout == "map":
        note = f'<p class="body-note">{_e(spec.body)}</p>' if spec.body else ""
        return _map(spec) + note
    if spec.layout == "matrix":
        return _matrix(spec)
    if spec.layout == "photo":
        return _photo(spec, assets_root)
    if spec.layout == "board":
        return _board(spec, assets_root)
    if spec.layout == "evidence":
        return _evidence(spec, assets_root) + _source_note(spec.source_note)
    return _bullets(spec)


def _photo_full_slide(
    spec: SlideSpec,
    index: int,
    total: int,
    *,
    brand: str,
    citations: dict[str, str],
    assets_root: Path | None,
    variant: str = "bleed",
    tone: str = "dark",
) -> str:
    image = spec.image
    if image is None or assets_root is None:
        raise ValueError(f"full-bleed photo slide '{spec.title}' needs an image and asset root")
    root = assets_root.resolve()
    path = (root / image.path).resolve()
    if path != root and root not in path.parents:
        raise ValueError("image path must stay inside campaign artifacts")
    if not path.is_file():
        raise FileNotFoundError(f"image asset not found: {image.path}")
    source = _image_data_uri(path)
    subtitle = f'<p class="slide-subtitle">{_e(spec.subtitle)}</p>' if spec.subtitle else ""
    body = f'<p class="body-note">{_e(spec.body)}</p>' if spec.body else ""
    caption = f'<figcaption>{_e(image.caption)}</figcaption>' if image.caption else ""
    return f"""
<section class="slide layout-photo photo-full-bleed variant-{_e(variant)} tone-{_e(tone)}" id="slide-{index + 1}" data-index="{index}" data-variant="{_e(variant)}" aria-label="Slide {index + 1}: {_e(spec.title)}" aria-hidden="true">
  <img class="full-bleed-image" src="{source}" alt="{_e(image.alt_text)}"/>
  <div class="photo-scrim" aria-hidden="true"></div>
  <div class="slide-inner photo-inner">
    <header class="slide-head">
      <span class="kicker">Visual</span>
      <span class="head-line"></span>
      <span class="head-page">{index + 1:02d} / {total:02d}</span>
    </header>
    <h2 class="slide-title">{_e(spec.title)}</h2>
    {subtitle}
    {body}
    {caption}
  </div>
  <footer class="slide-footer">
    <span class="footer-brand">{_e(brand)}</span>
    {_render_sources(spec, citations)}
    <span class="footer-note">Draft for client review</span>
  </footer>
</section>"""


def _render_slide(
    spec: SlideSpec,
    index: int,
    total: int,
    *,
    deck: Deck,
    brand: str,
    citations: dict[str, str],
    assets_root: Path | None,
    palette: dict[str, str],
) -> str:
    variant = deck_variant(deck, spec, index)
    tone = slide_tone(spec, index, deck.design)
    if spec.layout == "title":
        return _title_slide(spec, index, total, brand=brand, citations=citations, assets_root=assets_root, variant=variant, tone=tone)
    if spec.layout == "section":
        return _section_slide(
            spec, index, total, brand=brand, citations=citations,
            assets_root=assets_root, variant=variant, tone=tone,
        )
    if spec.layout == "photo" and spec.image and spec.image.placement == "full_bleed":
        return _photo_full_slide(
            spec, index, total, brand=brand, citations=citations, assets_root=assets_root,
            variant=variant, tone=tone,
        )
    content = _content(spec, deck, assets_root, palette)
    return _slide_shell(
        spec,
        index,
        total,
        brand=brand,
        citations=citations,
        content=content,
        density=deck.design.density,
        variant=variant,
        tone=tone,
    )


def build_html(
    deck: Deck,
    *,
    citations: dict[str, str] | None = None,
    assets_root: Path | None = None,
    brand: str = "",
) -> bytes:
    """Render a Deck to a self-contained HTML document."""
    if not deck.slides:
        raise ValueError("slides.json has no slides")
    palette = palette_for(deck)
    citation_labels = citations or {}
    total = len(deck.slides)
    brand_label = brand.strip() or "Campaign proposal"
    title_slide = next((slide for slide in deck.slides if slide.layout == "title"), None)
    document_title = (
        f"{title_slide.title} · {brand_label}" if title_slide else f"{brand_label} · Campaign proposal"
    )
    slides = "\n".join(
        _render_slide(
            spec,
            index,
            total,
            deck=deck,
            brand=brand_label,
            citations=citation_labels,
            assets_root=assets_root,
            palette=palette,
        )
        for index, spec in enumerate(deck.slides)
    )
    css = _CSS
    for key, value in palette.items():
        css = css.replace(f"__{key.upper()}__", value)
    heading = deck.font_heading or "Iowan Old Style"
    body = deck.font_body or "Avenir Next"
    if not re.fullmatch(r"[A-Za-z0-9 ,.'-]+", heading):
        heading = "Georgia"
    if not re.fullmatch(r"[A-Za-z0-9 ,.'-]+", body):
        body = "Segoe UI"
    css = css.replace("__FONT_HEADING__", heading).replace("__FONT_BODY__", body)
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="description" content="{_e(document_title)}. Self-contained HTML campaign deck."/>
<title>{_e(document_title)}</title>
<style>{css}</style>
</head>
<body class="style-{_e(deck.design.style)} accent-{_e(deck.design.accent_mode)}">
<main class="stage-wrap" aria-label="Campaign proposal slide deck">
  <article class="stage" id="stage">
{slides}
  </article>
</main>
<div class="chrome">
  <div class="progress" aria-hidden="true"><div class="progress-bar" id="progress-bar"></div></div>
  <nav class="controls" aria-label="Deck controls">
    <button type="button" id="prev" aria-label="Previous slide">←</button>
    <span class="counter" id="counter" aria-live="polite">01 / {total:02d}</span>
    <button type="button" id="next" aria-label="Next slide">→</button>
    <span class="control-spacer"></span>
    <button type="button" id="fullscreen" title="Toggle full screen (F)">Full screen <kbd>F</kbd></button>
    <button type="button" id="print" title="Print or save as PDF">Print</button>
  </nav>
</div>
<script>{_JS}</script>
</body>
</html>
"""
    return document.encode("utf-8")


_CSS = r"""
:root{
  --paper:#__BACKGROUND__;--ink:#__TEXT__;--muted:#__MUTED__;--accent:#__ACCENT__;
  --card:#__CARD__;--rule:#__RULE__;--navy:#__NAVY__;--white:#__WHITE__;--olive:#__OLIVE__;
  --blue:#__BLUE__;--tag:#__TAG__;--note:#__NOTE__;
  --serif:"Iowan Old Style","Palatino Linotype","Book Antiqua",Palatino,"Times New Roman",Georgia,serif;
  --sans:"Avenir Next",Avenir,"Segoe UI","Helvetica Neue",Arial,sans-serif;
  --mono:"SFMono-Regular",Consolas,"Liberation Mono",Menlo,monospace;
  --marker:"Segoe Print","Bradley Hand","Comic Sans MS",cursive;
}
body.style-brief{--serif:var(--sans)}
body.style-brief .display{font-size:132px;line-height:.98}
body.style-brief .slide-title{font-size:68px}
body.style-report .slide-inner{padding:84px 108px 100px}
body.style-report .slide-head{margin-bottom:28px}
body.style-briefing .stage::before{background:
  radial-gradient(ellipse at 16% 8%,rgba(255,255,255,.78),transparent 44%),
  linear-gradient(116deg,rgba(255,255,255,.24) 0,rgba(255,255,255,.02) 30%,rgba(255,255,255,.18) 50%,rgba(255,255,255,.02) 72%),
  radial-gradient(ellipse at 86% 92%,rgba(72,62,46,.13),transparent 56%)}
body.style-briefing .kicker{color:var(--blue)}
body.style-briefing .head-page{color:var(--muted)}
body.style-briefing .slide-title{font-family:var(--sans);font-weight:700;letter-spacing:-.02em}
body.style-briefing .display{font-family:var(--sans);font-weight:700;letter-spacing:-.035em}
body.style-briefing .slide-subtitle{font-family:var(--marker);font-size:26px;color:var(--blue)}
body.style-briefing .title-subtitle,body.style-briefing .section-subtitle{font-family:var(--marker);font-style:normal;color:var(--blue)}
body.style-briefing .title-photo .title-subtitle{color:#C6DAEC;text-shadow:0 2px 12px rgba(6,12,20,.62)}
body.style-briefing .title-photo .title-body{color:rgba(255,255,255,.86)}
body.style-briefing .title-photo .kicker{color:rgba(226,236,245,.82)}
body.style-briefing .slide-footer{border-top:2px dashed var(--rule)}
body.style-briefing .flow-node{background:var(--tag);border-top:3px dashed var(--blue);box-shadow:0 8px 14px rgba(52,44,28,.10)}
body.style-briefing .flow-arrow{color:var(--blue);font-size:42px}
body.style-briefing .flow-link span:first-child{font-family:var(--marker);font-size:13px;letter-spacing:0;text-transform:none;color:var(--blue)}
body.style-briefing .timeline-item::before{height:3px;background:var(--blue);opacity:.85}
body.style-briefing .timeline-dot{background:var(--paper);border:3px solid var(--blue);box-shadow:0 0 0 7px var(--paper)}
body.style-briefing .timeline-date{font-family:var(--marker);font-size:17px;letter-spacing:.02em;text-transform:none;color:var(--blue)}
body.style-briefing .timeline-item h3{font-size:27px}
body.style-briefing .timeline-item p{font-size:17px}
body.style-briefing .matrix-cell{background:#fff;border-top:0;border-left:5px solid var(--blue);box-shadow:0 12px 20px rgba(52,44,28,.15);padding-top:26px}
body.style-briefing .matrix-cell.tone-high{border-left-color:var(--accent)}
body.style-briefing .matrix-cell.tone-medium{border-left-color:var(--gold)}
body.style-briefing .matrix-cell.tone-low{border-left-color:var(--blue)}
body.style-briefing .stat-card,body.style-briefing .kpi-card{background:var(--tag);border-top:0;border-left:5px solid var(--blue);box-shadow:0 10px 18px rgba(52,44,28,.12);min-height:0}
body.style-briefing .kpi-card{border-left-color:var(--accent)}
body.style-briefing .gallery-item{padding:10px 10px 30px;background:#fff;box-shadow:0 14px 24px rgba(52,44,28,.20)}
body.style-briefing .gallery-item figcaption{padding:0 2px}
body.style-briefing .quote-image{padding:10px 10px 30px;background:#fff;box-shadow:0 16px 28px rgba(52,44,28,.24)}
body.style-briefing .map-tile{border-top:2px dashed var(--rule)}
body.style-briefing .map-index{color:var(--blue)}
body.style-briefing .layout-section .section-grid.has-photo{grid-template-columns:210px minmax(0,1fr) 440px;gap:44px;align-items:center;margin-top:auto;margin-bottom:54px}
body.style-briefing .layout-section .section-grid.has-photo .section-number{order:0;margin-top:0;font-size:150px;color:#DFD6C2;opacity:1}
body.style-briefing .layout-section .section-grid.has-photo .section-title{font-size:92px;max-width:820px}
body.style-briefing .layout-section .section-grid.has-photo .section-subtitle{font-size:26px;margin-bottom:24px}
body.style-briefing .layout-section .section-grid.has-photo .section-body{font-size:20px;margin-bottom:24px}
body.style-briefing .layout-section .section-grid.has-photo .section-list{columns:1;max-width:760px}
body.style-briefing .layout-section .section-grid.has-photo .section-list li{font-size:20px;padding:12px 0}
body.style-briefing .section-print img{height:430px}
body.style-briefing .section-print{padding-bottom:44px}
body.style-briefing .section-print figcaption{white-space:normal;font-size:12px;line-height:1.3;bottom:6px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
body.style-briefing .layout-stats .slide-content,body.style-briefing .layout-map .slide-content{align-content:center;padding-top:0}
body.style-briefing .stat-card{padding:28px 30px 24px;display:flex;flex-direction:column}
body.style-briefing .stat-source{margin-top:auto;padding-top:16px}
body.style-briefing .stat-value{font-size:74px;margin:22px 0 12px}
body.style-briefing .stat-detail{font-size:17px}
body.style-briefing .map-grid{gap:12px 22px}
body.style-briefing .map-tile{padding:15px 0 13px}
body.style-briefing .map-tile strong{font-size:22px}
body.style-briefing .map-detail{font-size:16px}
body.style-briefing .matrix-wrap{height:660px;max-width:1560px}
body.style-briefing .matrix-cell{min-height:0;display:flex;flex-direction:column;justify-content:flex-start}
body.style-briefing .layout-matrix .slide-content{align-content:stretch;padding-top:0}
body.style-briefing .framework{gap:34px}
body.style-briefing .framework-pillar{min-height:300px;padding:26px 24px 22px}
body.style-briefing .framework-pillar h3{font-size:32px;margin:20px 0 12px}
body.style-briefing .framework-pillar p{font-size:18px}
body.style-briefing .kpi-grid{gap:16px}
body.style-briefing .kpi-card{padding:22px 24px 18px;min-height:210px;display:flex;flex-direction:column}
body.style-briefing .kpi-card h3{font-size:19px;margin:10px 0 6px}
body.style-briefing .kpi-value{font-size:42px;margin:4px 0 10px}
body.style-briefing .kpi-value.is-word{font-size:28px}
body.style-briefing .kpi-detail{font-size:16px;line-height:1.4;margin:auto 0 0}
body.style-briefing .donut-total{font-family:var(--sans);font-weight:700}
body.accent-mono{--accent:var(--ink)}
body.accent-warm{--accent:var(--olive)}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:#11130f;color:var(--ink);font-family:var(--sans);overflow:hidden}
::selection{background:var(--accent);color:var(--white)}
button{font:inherit;color:inherit}
.stage-wrap{position:fixed;inset:0 0 64px 0;overflow:hidden}
.stage{position:absolute;left:0;top:0;width:1920px;height:1080px;background:var(--paper);overflow:hidden;transform-origin:top left}
.stage::before{content:"";position:absolute;inset:0;pointer-events:none;z-index:0;background:
  radial-gradient(circle at 12% 8%,rgba(255,255,255,.55),transparent 42%),
  radial-gradient(circle at 88% 94%,rgba(23,26,23,.055),transparent 48%);}
.stage::after{content:"";position:absolute;inset:0;pointer-events:none;z-index:0;opacity:.20;background-image:repeating-linear-gradient(0deg,rgba(23,26,23,.08) 0,rgba(23,26,23,.08) 1px,transparent 1px,transparent 4px)}
.slide{position:absolute;inset:0;z-index:1;opacity:0;visibility:hidden;transform:translateY(14px);transition:opacity .36s ease,transform .36s ease;background:var(--paper);color:var(--ink)}
.slide.is-active{opacity:1;visibility:visible;transform:none}
.slide.tone-dark{--paper:var(--navy);--ink:var(--white);--muted:rgba(255,255,255,.70);--card:rgba(255,255,255,.08);--rule:rgba(255,255,255,.26);background:var(--navy)}
.slide.tone-dark .title-index{color:rgba(255,255,255,.05)}
.slide.tone-dark .stat-card,.slide.tone-dark .data-table td,.slide.tone-dark .data-table th{background:rgba(255,255,255,.06)}
.slide-inner{position:absolute;inset:0;padding:78px 96px 94px;display:flex;flex-direction:column;z-index:2}
.slide-head{display:flex;align-items:center;gap:22px;min-height:30px;margin-bottom:34px}
.kicker{font-family:var(--mono);font-size:16px;line-height:1;letter-spacing:.16em;text-transform:uppercase;color:var(--accent)}
.head-line{flex:1;height:1px;background:var(--rule)}
.head-page{font-family:var(--mono);font-size:16px;letter-spacing:.08em;color:var(--muted)}
.slide-title{font-family:var(--serif);font-weight:600;font-size:76px;line-height:1.02;letter-spacing:-.025em;margin:0 0 20px;max-width:1560px;color:var(--ink)}
.slide-title.is-long{font-size:64px}
.slide-subtitle{font-family:var(--sans);font-size:28px;line-height:1.35;color:var(--muted);margin:0 0 34px;max-width:1280px}
.slide-content{flex:1;min-height:0;position:relative}
.layout-diagram .slide-content,.layout-timeline .slide-content,.layout-quote .slide-content{display:grid;align-content:center}
.layout-stats .slide-content,.layout-table .slide-content,.layout-map .slide-content,.layout-comparison .slide-content,.layout-matrix .slide-content,.layout-references .slide-content{display:grid;align-content:start;padding-top:14px}
.slide-footer{position:absolute;left:96px;right:96px;bottom:36px;z-index:3;display:flex;align-items:baseline;gap:24px;padding-top:12px;border-top:1px solid var(--rule);font-family:var(--mono);font-size:13px;letter-spacing:.05em;color:var(--muted)}
.footer-brand{text-transform:uppercase;color:var(--ink);white-space:nowrap}
.footer-sources{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.footer-note{margin-left:auto;white-space:nowrap;opacity:.7}
.layout-title .slide-footer{display:none}

/* Cover */
.title-inner{justify-content:space-between;padding:78px 96px 74px}
.title-top{display:flex;justify-content:space-between;align-items:baseline;gap:24px;border-bottom:1px solid var(--rule);padding-bottom:16px}
.title-main{margin-top:70px;max-width:1540px;position:relative;z-index:2}
.title-rule{width:132px;height:9px;background:var(--accent);margin-bottom:36px}
.display{font-family:var(--serif);font-weight:600;font-size:148px;line-height:.92;letter-spacing:-.045em;margin:0 0 34px;max-width:1480px}
.display.is-long{font-size:112px;line-height:.96}
.title-subtitle{font-family:var(--serif);font-style:italic;font-size:36px;line-height:1.28;color:var(--muted);margin:0 0 22px;max-width:1180px}
.title-body{font-size:24px;line-height:1.55;color:var(--muted);max-width:900px;margin:0}
.title-meta{display:flex;justify-content:space-between;align-items:baseline;gap:24px;border-top:1px solid var(--rule);padding-top:18px;font-family:var(--mono);font-size:14px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.title-index{position:absolute;right:54px;bottom:-64px;z-index:1;font-family:var(--serif);font-size:520px;line-height:.8;color:var(--card);opacity:.35;pointer-events:none}
.title-bleed{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:0}
.title-photo::after{content:"";position:absolute;inset:0;z-index:1;pointer-events:none;background:linear-gradient(180deg,rgba(0,0,0,.22) 0%,rgba(0,0,0,0) 32%,rgba(0,0,0,.42) 62%,rgba(0,0,0,.72) 100%)}
.title-photo .title-inner{position:relative;z-index:2}
.title-photo .display,.title-photo .title-subtitle,.title-photo .title-body{color:#fff}
.title-photo .kicker,.title-photo .title-meta{color:rgba(255,255,255,.92)}
.title-photo .title-meta{text-shadow:0 2px 8px rgba(0,0,0,.85);background:rgba(10,12,10,.38);padding:10px 12px;border-top-color:rgba(255,255,255,.24)}
.title-photo .title-top,.title-photo .title-meta{border-color:rgba(255,255,255,.3)}
.title-photo .title-index{color:rgba(255,255,255,.10);opacity:.6}
.title-photo .title-rule{background:var(--accent)}
.title-side{position:absolute;right:0;top:0;width:42%;height:100%;object-fit:cover;z-index:0}
.title-side-photo .title-main{max-width:880px}

/* Section */
.section-inner{padding-top:78px}
.section-grid{flex:1;display:grid;grid-template-columns:330px 1fr;gap:64px;align-items:start;margin-top:34px}
.section-number{font-family:var(--serif);font-size:250px;line-height:.8;color:var(--card);letter-spacing:-.06em}
.section-title{font-family:var(--serif);font-weight:600;font-size:104px;line-height:.95;letter-spacing:-.035em;margin:0 0 24px;max-width:1180px}
.section-title.is-long{font-size:84px}
.section-subtitle{font-family:var(--serif);font-style:italic;font-size:30px;line-height:1.3;color:var(--muted);margin:0 0 34px;max-width:1050px}
.section-body{font-size:24px;line-height:1.55;color:var(--muted);max-width:1050px;margin:0 0 34px}
.section-list{list-style:none;margin:0;padding:0;max-width:1120px}
.section-list li{display:grid;grid-template-columns:56px 1fr;gap:18px;padding:18px 0;border-top:1px solid var(--rule);font-size:25px;line-height:1.4}
.section-list li span{font-family:var(--mono);font-size:13px;letter-spacing:.08em;color:var(--accent);padding-top:6px}

/* Ledger list */
.ledger-list{list-style:none;margin:0;padding:0;max-width:1560px}
.ledger-list li{display:grid;grid-template-columns:74px 1fr;gap:24px;align-items:start;padding:20px 0;border-top:1px solid var(--rule)}
.ledger-list li:last-child{border-bottom:1px solid var(--rule)}
.ledger-index{font-family:var(--mono);font-size:14px;letter-spacing:.08em;color:var(--accent);padding-top:8px}
.ledger-copy{font-size:31px;line-height:1.32;max-width:1420px}

/* Two column */
.two-col{display:grid;grid-template-columns:1fr 1px 1fr;gap:52px;align-items:start;max-width:1640px}
.column-rule{width:1px;height:100%;min-height:420px;background:var(--rule)}
.column h3{font-family:var(--mono);font-size:15px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin:0 0 24px}
.rule-list{list-style:none;margin:0;padding:0}
.rule-list li{position:relative;padding:16px 0 16px 28px;border-top:1px solid var(--rule);font-size:27px;line-height:1.42}
.rule-list li::before{content:"";position:absolute;left:0;top:28px;width:9px;height:9px;background:var(--accent)}

/* KPIs */
.kpi-grid{display:grid;gap:26px;max-width:1640px}
.kpi-grid.cols-2{grid-template-columns:repeat(2,1fr)}
.kpi-grid.cols-3{grid-template-columns:repeat(3,1fr)}
.kpi-card{border-top:3px solid var(--accent);padding:24px 28px 20px;background:rgba(255,255,255,.22);min-height:250px}
.kpi-index{font-family:var(--mono);font-size:12px;letter-spacing:.12em;color:var(--accent)}
.kpi-card h3{font-family:var(--sans);font-weight:600;font-size:21px;line-height:1.28;margin:14px 0 8px;color:var(--ink)}
.kpi-value{font-family:var(--serif);font-size:54px;line-height:1;letter-spacing:-.03em;margin:8px 0 14px;color:var(--ink)}
.kpi-value.is-word{font-size:36px;font-style:italic;color:var(--accent)}
.kpi-detail{font-size:18px;line-height:1.42;color:var(--muted);margin:0}

/* Budget */
.budget-wrap{max-width:1640px}
.budget-table{width:100%;border-collapse:collapse;font-size:22px}
.budget-table th{font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase;text-align:left;color:var(--accent);padding:0 14px 14px 0;border-bottom:1px solid var(--ink)}
.budget-table td{padding:14px 14px 14px 0;border-bottom:1px solid var(--rule);vertical-align:top;line-height:1.32}
.budget-table th:not(:first-child),.budget-table td:not(:first-child){text-align:right}
.budget-table tbody tr.total-row td{border-top:2px solid var(--ink);border-bottom:none;font-weight:700;padding-top:18px}
.budget-summary{font-family:var(--mono);font-size:16px;line-height:1.45;letter-spacing:.02em;color:var(--ink);margin:26px 0 0;border-left:4px solid var(--accent);padding-left:16px;max-width:1500px}

/* Quote */
.pull-quote{margin:26px 0 0;max-width:1580px;position:relative;padding-left:76px}
.pull-quote::before{content:"“";position:absolute;left:0;top:-104px;font-family:var(--serif);font-size:180px;line-height:1;color:var(--accent);opacity:.55}
.pull-quote blockquote{font-family:var(--serif);font-size:86px;line-height:1.03;letter-spacing:-.035em;margin:0;max-width:1500px}
.quote-attribution{font-family:var(--sans);font-size:26px;line-height:1.45;color:var(--muted);margin:32px 0 0;max-width:1100px}
.quote-layout{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(0,.88fr);gap:46px;align-items:center;max-width:1640px}
.quote-layout .pull-quote{margin-top:0;max-width:900px}
.quote-layout .pull-quote blockquote{font-size:70px;max-width:900px}
.quote-image{margin:0}
.quote-image img{display:block;width:100%;height:510px;object-fit:cover}
.quote-image figcaption{font-family:var(--mono);font-size:11px;line-height:1.4;color:var(--muted);margin-top:10px}

/* References */
.reference-list{columns:2;column-gap:64px;margin:0;padding-left:28px;max-width:1640px}
.reference-list li{break-inside:avoid;font-size:19px;line-height:1.42;color:var(--muted);padding:0 0 18px 4px}
.reference-list li::marker{font-family:var(--mono);font-size:13px;color:var(--accent)}
.reference-list.dense li{font-size:15px;line-height:1.38;padding-bottom:10px}

/* Next steps */
.step-list{list-style:none;margin:0;padding:0;max-width:1550px;counter-reset:step}
.step-list li{display:grid;grid-template-columns:104px 1fr;gap:26px;align-items:start;padding:20px 0;border-top:1px solid var(--rule)}
.step-list li:last-child{border-bottom:1px solid var(--rule)}
.step-number{font-family:var(--serif);font-size:58px;line-height:.9;color:var(--accent)}
.step-copy{font-size:28px;line-height:1.35;padding-top:4px}

/* Flow diagram */
.flow{display:flex;align-items:stretch;gap:0;width:100%;max-width:1640px;margin-top:18px}
.flow-node{flex:1;min-width:0;border-top:3px solid var(--accent);padding:26px 22px 22px;background:rgba(255,255,255,.22);min-height:230px}
.flow-number{font-family:var(--mono);font-size:13px;letter-spacing:.12em;color:var(--accent)}
.flow-node h3{font-family:var(--serif);font-size:34px;line-height:1.05;margin:16px 0 10px;letter-spacing:-.02em}
.flow-node p{font-size:19px;line-height:1.42;color:var(--muted);margin:0;max-width:300px}
.flow-link{flex:0 0 70px;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:6px;padding-top:12px}
.flow-link span:first-child{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.flow-arrow{font-size:34px;line-height:1;color:var(--accent)}
.flow-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:26px;max-width:1640px}
.flow-node.compact{border-top:2px solid var(--rule);padding:18px 16px 16px 0}
.flow-node.compact h3{font-size:28px}

/* Timeline */
.timeline{position:relative;display:grid;grid-template-columns:repeat(var(--count,5),1fr);gap:22px;margin-top:36px;max-width:1640px}
.timeline.count-2{--count:2}
.timeline.count-3{--count:3}
.timeline.count-4{--count:4}
.timeline.count-5{--count:5}
.timeline.count-6{--count:6}
.timeline-item{position:relative;display:flex;flex-direction:column;padding-top:0}
.timeline-item::before{content:"";position:absolute;left:30px;right:-22px;top:73px;height:2px;background:var(--rule)}
.timeline-item:last-child::before{display:none}
.timeline-date{display:block;min-height:24px;font-family:var(--mono);font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);margin:0 0 34px}
.timeline-dot{position:absolute;left:0;top:64px;width:20px;height:20px;background:var(--accent);border-radius:50%;box-shadow:0 0 0 8px var(--paper)}
.timeline-item h3{font-family:var(--serif);font-size:25px;line-height:1.12;margin:36px 0 8px;letter-spacing:-.01em}
.timeline-item p{font-size:18px;line-height:1.4;color:var(--muted);margin:0;max-width:280px}

/* Chart */
.chart-head{display:flex;align-items:baseline;justify-content:space-between;gap:24px;max-width:1560px;margin:0 0 8px}
.chart-legend{display:flex;gap:24px;flex-wrap:wrap}
.legend-item{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:12px;letter-spacing:.06em;color:var(--muted)}
.legend-item i{display:inline-block;width:16px;height:16px}
.chart-unit{font-family:var(--mono);font-size:12px;letter-spacing:.06em;color:var(--muted)}
.chart{width:100%;max-width:1560px;height:auto;margin-top:4px}
.chart-axis{font-family:var(--mono);font-size:15px;fill:var(--muted)}
.chart-category{font-family:var(--mono);font-size:16px;fill:var(--ink)}
.chart-value{font-family:var(--mono);font-size:15px;fill:var(--ink)}
.chart-value-inverse{font-family:var(--mono);font-size:14px;fill:var(--white)}
.donut-wrap{display:grid;grid-template-columns:minmax(0,1.2fr) 420px;gap:30px;align-items:center;max-width:1640px}
.donut{max-width:100%}
.donut-total{font-family:var(--serif);font-size:64px;fill:var(--ink);font-weight:600}
.donut-unit{font-family:var(--mono);font-size:14px;fill:var(--muted);letter-spacing:.08em;text-transform:uppercase}
.donut-legend{display:flex;flex-direction:column;gap:14px}
.donut-legend-item{display:grid;grid-template-columns:18px 1fr auto;gap:12px;align-items:center;border-top:1px solid var(--rule);padding-top:12px;font-size:20px}
.donut-legend-item i{width:16px;height:16px}
.donut-legend-item strong{font-family:var(--mono);font-size:16px}

/* Tables */
.table-wrap{max-width:1640px}
.data-table{width:100%;border-collapse:collapse;font-size:24px;line-height:1.3}
.data-table th{font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase;text-align:left;color:var(--accent);padding:0 22px 14px 0;border-bottom:1px solid var(--ink)}
.data-table td{padding:18px 22px 18px 0;border-bottom:1px solid var(--rule);vertical-align:top}
.data-table th:not(:first-child),.data-table td:not(:first-child){padding-left:24px}
.data-table .align-right{text-align:right}
.data-table .align-center{text-align:center}
.data-table .align-left{text-align:left}
.data-table tr.is-highlight td{border-top:2px solid var(--ink);border-bottom:none;font-weight:700;padding-top:18px}
.source-note{font-family:var(--mono);font-size:14px;line-height:1.45;letter-spacing:.02em;color:var(--muted);margin:18px 0 0;max-width:1500px}

/* Stats */
.stat-grid{display:grid;gap:24px;max-width:1640px}
.stat-grid.count-2{grid-template-columns:repeat(2,1fr)}
.stat-grid.count-3{grid-template-columns:repeat(3,1fr)}
.stat-grid.count-4{grid-template-columns:repeat(4,1fr)}
.stat-card{border-top:3px solid var(--accent);padding:22px 24px 20px;background:rgba(255,255,255,.22);min-height:260px}
.stat-index{font-family:var(--mono);font-size:12px;letter-spacing:.12em;color:var(--accent)}
.stat-value{font-family:var(--serif);font-size:66px;line-height:.95;letter-spacing:-.035em;margin:20px 0 10px;color:var(--ink)}
.stat-value.is-long{font-size:42px}
.stat-card h3{font-family:var(--sans);font-weight:600;font-size:19px;line-height:1.28;margin:0 0 10px}
.stat-detail{font-size:17px;line-height:1.45;color:var(--muted);margin:0}
.stat-source{font-family:var(--mono);font-size:12px;line-height:1.4;color:var(--muted);margin:16px 0 0;opacity:.8}

/* Gallery */
.gallery{display:grid;gap:24px;max-width:1640px}
.gallery.count-2{grid-template-columns:repeat(2,1fr)}
.gallery.count-3{grid-template-columns:repeat(3,1fr)}
.gallery.count-4{grid-template-columns:repeat(2,1fr)}
.gallery-item{margin:0;min-width:0}
.gallery-item img{display:block;width:100%;height:430px;object-fit:cover}
.gallery.count-4 .gallery-item img{height:300px}
.gallery-item figcaption{display:flex;flex-direction:column;gap:4px;font-size:18px;line-height:1.4;color:var(--ink);margin-top:10px}
.gallery-item figcaption strong{font-weight:600}
.gallery-credit{font-family:var(--mono);font-size:13px;letter-spacing:.04em;color:var(--muted)}

/* Comparison */
.comparison{display:grid;grid-template-columns:minmax(0,1fr) 80px minmax(0,1fr);gap:20px;align-items:center;max-width:1640px}
.comparison-panel h3{font-family:var(--mono);font-size:15px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin:0 0 22px}
.comparison-panel .rule-list li{font-size:27px;padding-top:18px;padding-bottom:18px}
.versus{width:64px;height:64px;border:1px solid var(--rule);border-radius:50%;display:grid;place-items:center;font-family:var(--mono);font-size:13px;letter-spacing:.08em;color:var(--accent);margin:0 auto}

/* Map / region grid */
.map-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px 20px;max-width:1640px}
.map-tile{display:grid;grid-template-columns:36px 1fr;grid-template-rows:auto auto;column-gap:10px;border-top:1px solid var(--rule);padding:11px 0 9px}
.map-index{grid-row:1 / span 2;font-family:var(--mono);font-size:11px;letter-spacing:.08em;color:var(--accent);padding-top:3px}
.map-tile strong{font-size:20px;line-height:1.2}
.map-detail{font-size:16px;line-height:1.3;color:var(--muted);margin-top:2px}
.map-legend{display:flex;flex-wrap:wrap;gap:22px;margin-top:20px;font-family:var(--mono);font-size:12px;letter-spacing:.04em;color:var(--muted)}
.map-legend span{display:flex;align-items:center;gap:8px}
.map-legend i{width:10px;height:10px;background:var(--accent)}

/* Framework */
.framework{max-width:1640px;display:grid;gap:26px}
.framework-head{border-left:6px solid var(--accent);padding:10px 0 10px 24px;max-width:1500px}
.framework-kicker{font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
.framework-head h3{font-family:var(--serif);font-size:46px;line-height:1.05;letter-spacing:-.025em;margin:12px 0 10px;max-width:1400px}
.framework-head p{font-size:19px;line-height:1.45;color:var(--muted);margin:0;max-width:1400px}
.framework-pillars{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}
.framework-pillar{border-top:3px solid var(--accent);padding:20px 20px 18px;background:rgba(255,255,255,.22);min-height:220px}
.framework-index{font-family:var(--mono);font-size:12px;letter-spacing:.12em;color:var(--accent)}
.framework-pillar h3{font-family:var(--serif);font-size:28px;line-height:1.1;margin:16px 0 10px}
.framework-pillar p{font-size:17px;line-height:1.45;color:var(--muted);margin:0}

/* Matrix */
.matrix-wrap{display:grid;grid-template-columns:44px minmax(0,1fr);grid-template-rows:minmax(0,1fr) 34px;gap:12px;max-width:1500px}
.matrix-axis{font-family:var(--mono);font-size:14px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.matrix-axis-y{writing-mode:vertical-rl;transform:rotate(180deg);grid-row:1;grid-column:1;justify-self:center}
.matrix-axis-x{grid-row:2;grid-column:2;text-align:center}
.matrix-grid{grid-row:1;grid-column:2;display:grid;grid-template-columns:repeat(2,1fr);grid-template-rows:repeat(2,1fr);gap:10px}
.matrix-cell{padding:22px 24px;min-height:180px;border-top:3px solid var(--accent);background:var(--card)}
.matrix-cell.tone-low{background:rgba(229,223,207,.55)}
.matrix-cell.tone-medium{background:rgba(201,193,174,.72)}
.matrix-cell.tone-high{background:rgba(199,67,47,.16);border-top-color:var(--accent)}
.matrix-cell h3{font-family:var(--serif);font-size:28px;line-height:1.1;margin:0 0 10px;letter-spacing:-.02em}
.matrix-cell p{font-size:21px;line-height:1.45;color:var(--muted);margin:0}

/* Composition variants */
.layout-title.variant-split .title-main{margin-top:auto;margin-bottom:120px;max-width:1040px}
.layout-title.variant-split .display{font-size:126px}
.layout-title.variant-split .title-index{right:auto;left:56%;bottom:-110px;font-size:600px}
.layout-title.variant-split .title-subtitle{max-width:900px}

.layout-section.variant-editorial .section-grid{grid-template-columns:1fr;gap:0;margin-top:auto;margin-bottom:54px}
.layout-section.variant-editorial .section-number{order:2;font-size:110px;margin-top:34px;color:var(--accent);opacity:.55}
.layout-section.variant-editorial .section-title{font-size:132px;max-width:1520px}
.layout-section.variant-editorial .section-body{max-width:1320px;font-size:25px}
.layout-section.variant-editorial .section-list{columns:2;column-gap:56px;max-width:1480px}
.layout-section.variant-editorial .section-list li{break-inside:avoid}

.variant-split .ledger-list{display:grid;grid-template-columns:1fr 1fr;gap:0 56px;max-width:1640px}
.variant-split .ledger-list li:nth-child(odd){padding-right:24px}
.variant-split .ledger-copy{font-size:27px}
.variant-rail .ledger-list{max-width:1320px;border-left:6px solid var(--accent);padding-left:38px}
.variant-rail .ledger-copy{font-size:28px}

.variant-offset .two-col{grid-template-columns:1fr;gap:26px;max-width:1380px}
.variant-offset .column-rule{display:none}
.variant-offset .column:last-child{margin-left:120px;border-top:1px solid var(--rule);padding-top:24px}

.variant-rail .kpi-grid{grid-template-columns:1fr;gap:0;max-width:900px;border-left:6px solid var(--accent);padding-left:28px}
.variant-rail .kpi-card{min-height:0;border-top:1px solid var(--rule);border-left:0;background:transparent;padding:18px 20px}
.variant-rail .kpi-card:last-child{border-bottom:1px solid var(--rule)}
.variant-rail .kpi-value{font-size:42px;margin:8px 0 10px}

.variant-rail .stat-grid{grid-template-columns:1fr;gap:0;max-width:720px;border-left:6px solid var(--accent);padding-left:28px}
.variant-rail .stat-card{min-height:0;border-top:1px solid var(--rule);border-left:0;background:transparent;padding:16px 20px}
.variant-rail .stat-card:last-child{border-bottom:1px solid var(--rule)}
.variant-rail .stat-value{font-size:46px;margin:8px 0}

.variant-rail .budget-wrap{max-width:1180px;border-left:6px solid var(--accent);padding-left:30px}
.variant-dense .data-table{font-size:20px}
.variant-dense .data-table th{padding-bottom:10px}
.variant-dense .data-table td{padding-top:12px;padding-bottom:12px}

.variant-split .pull-quote{padding-left:0;max-width:1200px}
.variant-split .pull-quote::before{left:auto;right:0;top:-84px;opacity:.22}
.variant-split .pull-quote blockquote{font-size:78px}

.variant-ledger .reference-list{columns:1;max-width:1560px;padding-left:0;list-style:none;counter-reset:ref}
.variant-ledger .reference-list li{counter-increment:ref;border-top:1px solid var(--rule);padding:15px 0 15px 58px;position:relative;font-size:17px}
.variant-ledger .reference-list li::before{content:counter(ref,decimal-leading-zero);position:absolute;left:0;top:16px;font-family:var(--mono);font-size:12px;color:var(--accent)}

.variant-rail .step-list{max-width:1160px;border-left:6px solid var(--accent);padding-left:32px}
.variant-rail .step-list li{grid-template-columns:72px 1fr;padding:16px 0}
.variant-rail .step-number{font-size:40px}
.variant-rail .step-copy{font-size:25px}

.variant-rail .timeline{display:block;max-width:1220px;border-left:3px solid var(--accent);padding-left:34px;margin-top:18px}
.variant-rail .timeline-item{display:grid;grid-template-columns:150px 1fr;gap:8px 22px;padding:16px 0;border-top:1px solid var(--rule)}
.variant-rail .timeline-item::before,.variant-rail .timeline-dot{display:none}
.variant-rail .timeline-date{grid-column:1;margin:0;padding-top:4px}
.variant-rail .timeline-item h3{grid-column:2;margin:0 0 6px;font-size:27px}
.variant-rail .timeline-item p{grid-column:2;max-width:820px}

.variant-split .chart{max-width:1120px}
.variant-mosaic .gallery{grid-template-columns:1.45fr 1fr;grid-auto-rows:250px;gap:18px}
.variant-mosaic .gallery-item:first-child{grid-row:span 2}
.variant-mosaic .gallery-item img{height:100%}
.variant-mosaic .gallery.count-2{grid-template-columns:repeat(2,1fr);grid-auto-rows:auto}
.variant-mosaic .gallery.count-2 .gallery-item:first-child{grid-row:auto}
.variant-mosaic .gallery.count-2 .gallery-item img{height:430px}

.variant-offset .comparison{grid-template-columns:minmax(0,1fr);max-width:1320px;gap:0}
.variant-offset .comparison-panel:last-child{margin-left:120px;border-top:1px solid var(--rule);padding-top:24px}
.variant-offset .versus{display:none}

.variant-editorial .map-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:0 44px}
.variant-editorial .map-tile{padding:18px 0 16px}
.variant-editorial .map-tile strong{font-size:22px}

/* Density */
.density-dense .slide-inner{padding:64px 76px 82px}
.density-dense .slide-title{font-size:68px;margin-bottom:14px}
.density-dense .slide-subtitle{margin-bottom:24px}
.density-dense .ledger-copy{font-size:27px}
.density-dense .rule-list li{font-size:23px;padding-top:13px;padding-bottom:13px}
.density-dense .slide-head{margin-bottom:26px}

/* Photo */
.photo-grid{display:grid;grid-template-columns:1.1fr .9fr;gap:48px;align-items:start;max-width:1640px}
.photo-frame{margin:0}
.photo-frame img{display:block;width:100%;height:auto}
.photo-frame figcaption{font-family:var(--mono);font-size:12px;line-height:1.4;color:var(--muted);margin-top:10px}
.photo-body{font-size:26px;line-height:1.45;margin:0;color:var(--ink)}
.photo-full-bleed .full-bleed-image{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:0}
.photo-scrim{position:absolute;inset:0;z-index:1;background:linear-gradient(90deg,rgba(17,19,15,.88) 0%,rgba(17,19,15,.58) 48%,rgba(17,19,15,.16) 100%)}
.photo-inner{z-index:2;color:var(--white)}
.photo-inner .slide-title,.photo-inner .slide-subtitle,.photo-inner .body-note,.photo-inner figcaption{color:var(--white)}
.photo-inner .body-note{max-width:900px;margin-top:18px}
.photo-inner .slide-head .kicker{color:#f2b3a9}
.photo-inner .head-line{background:rgba(255,255,255,.35)}
.photo-inner .head-page{color:rgba(255,255,255,.72)}
.photo-full-bleed .slide-footer{border-top-color:rgba(255,255,255,.28);color:rgba(255,255,255,.72)}
.photo-full-bleed .footer-brand{color:var(--white)}

.body-note{font-size:17px;line-height:1.5;color:var(--muted);margin:24px 0 0;max-width:1450px}

/* Pinned prints, tags, stamps, dimension lines (briefing board) */
.print{position:relative;margin:0;background:#fff;padding:10px 10px 30px;box-shadow:0 14px 26px rgba(36,30,20,.20);min-width:0}
.print img{display:block;width:100%;height:100%;object-fit:cover}
.print-magnet{position:absolute;top:-11px;left:50%;transform:translateX(-50%);width:20px;height:20px;border-radius:50%;background:var(--accent);box-shadow:0 3px 5px rgba(0,0,0,.25);z-index:3}
.print figcaption{position:absolute;left:10px;right:10px;bottom:7px;font-family:var(--mono);font-size:12px;line-height:1.35;color:#6b675c;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.print-0{transform:rotate(-1.6deg)}
.print-1{transform:rotate(1.1deg)}
.print-2{transform:rotate(-.8deg)}
.print-3{transform:rotate(1.8deg)}
.board-print-0,.board-print-2{transform:rotate(-.7deg)}
.board-print-1,.board-print-3{transform:rotate(.6deg)}
.print.gallery-item{padding-bottom:10px}
.print.gallery-item figcaption{position:static;margin-top:8px;white-space:normal;overflow:visible}
.quote-image.print figcaption{position:static;margin-top:8px;white-space:normal;overflow:visible}
body.style-briefing .gallery.count-4 .gallery-item img{height:262px}
.board-stamp{display:inline-block;align-self:flex-start;font-family:var(--marker);font-size:27px;line-height:1;letter-spacing:.06em;text-transform:uppercase;color:var(--accent);border:4px double var(--accent);padding:10px 15px;transform:rotate(-4deg);background:rgba(255,255,255,.35)}
.board-stamp.stamp-blue{color:var(--blue);border-color:var(--blue)}
.board-note{background:var(--note);padding:18px 20px;box-shadow:0 10px 18px rgba(52,44,28,.18);transform:rotate(1.4deg);font-family:var(--marker);font-size:21px;line-height:1.35;color:#3a3326}
.board-note-kicker{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:#6b5a34}
.board-note p{margin:8px 0 0}
.board-tags{display:flex;flex-wrap:wrap;gap:10px 12px}
.board-tag{display:inline-flex;align-items:center;gap:8px;background:var(--tag);border:1px solid var(--rule);padding:9px 12px;font-family:var(--mono);font-size:13px;line-height:1.2;letter-spacing:.02em;box-shadow:0 4px 8px rgba(52,44,28,.12)}
.board-tag i{width:9px;height:9px;border-radius:50%;background:var(--accent);flex:0 0 auto}
.board-tag.tag-blue i{background:var(--blue)}
.board-tag-1{transform:rotate(-1.2deg)}
.board-tag-2{transform:rotate(.8deg)}
.ink-dim{display:flex;align-items:center;gap:12px;font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--blue);margin-top:6px}
.ink-dim span{white-space:nowrap}
.ink-dim::before,.ink-dim::after{content:"";flex:1;height:2px;background:var(--blue)}

/* Board: the whole briefing wall */
.layout-board .slide-content,.layout-evidence .slide-content{display:block;min-height:0}
.board-wall{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,.8fr);gap:32px;height:100%;max-width:1700px}
.board-prints{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:repeat(2,minmax(0,1fr));gap:20px 24px;padding-bottom:14px;min-height:0}
.board-prints.count-2{grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:1fr}
.board-prints .print{height:100%;min-height:0;display:flex;flex-direction:column}
.board-prints .print img{flex:1;min-height:0;height:auto}
.board-rail{display:flex;flex-direction:column;gap:18px;min-height:0}
.board-sources{font-family:var(--mono);font-size:11px;line-height:1.45;color:var(--muted);margin:auto 0 0}

/* Evidence: one print with leader-line annotations */
.evidence{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,.7fr);gap:52px;height:100%;align-items:stretch}
.evidence-photo{position:relative;min-height:0}
.evidence-photo .print{height:100%;display:flex;flex-direction:column}
.evidence-photo .print img{flex:1;min-height:0}
.leader-layer{position:absolute;left:10px;right:10px;top:10px;bottom:30px;width:calc(100% - 20px);height:calc(100% - 40px);pointer-events:none;z-index:2;overflow:visible}
.leader-layer .leader{stroke:var(--blue);stroke-width:1.1;fill:none;vector-effect:non-scaling-stroke}
.leader-layer .leader-ring{fill:none;stroke:var(--blue);stroke-width:1.4;vector-effect:non-scaling-stroke}
.evidence-notes{display:flex;flex-direction:column;justify-content:space-around;gap:12px;padding:6px 0}
.callout{display:grid;grid-template-columns:42px 1fr;gap:13px;align-items:start}
.callout-index{font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--blue);border:1px solid var(--blue);padding:4px 0;text-align:center}
.callout p{margin:0;font-size:19px;line-height:1.4}

/* Hub-and-spoke and route diagrams */
.hub{position:relative;width:100%;max-width:1640px;height:100%;min-height:660px;margin:0 auto}
.hub-svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.hub-spoke{stroke:var(--blue);stroke-width:2.4;fill:none;vector-effect:non-scaling-stroke}
.hub-end{fill:var(--paper);stroke:var(--blue);stroke-width:2;vector-effect:non-scaling-stroke}
.hub-node{position:absolute;transform:translate(-50%,-50%);width:250px;background:var(--tag);border:1px solid var(--rule);box-shadow:0 12px 20px rgba(52,44,28,.16);padding:15px 17px}
.hub-node.is-hub{width:330px;background:#fff;border-top:5px solid var(--accent);padding:20px 22px}
.hub-index{font-family:var(--mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--blue)}
.hub-node h3{font-family:var(--sans);font-weight:700;font-size:21px;line-height:1.2;margin:6px 0}
.hub-node.is-hub h3{font-family:var(--serif);font-size:29px;line-height:1.1}
.hub-node p{font-size:13px;line-height:1.4;color:var(--muted);margin:0}
.route{position:relative;width:100%;height:560px;max-width:1680px;margin:6px auto 0}
.route-line{position:absolute;left:6%;right:4%;top:50%;height:4px;background:var(--blue);transform:translateY(-50%)}
.route-line::after{content:"";position:absolute;right:-2px;top:50%;transform:translateY(-50%);border-left:15px solid var(--blue);border-top:9px solid transparent;border-bottom:9px solid transparent}
.route-stop{position:absolute;top:50%;transform:translate(-50%,-50%);width:22px;height:22px;border-radius:50%;background:var(--paper);border:4px solid var(--blue);z-index:2}
.route-card{position:absolute;transform:translateX(-50%);width:224px;background:#fff;padding:15px 17px;box-shadow:0 12px 20px rgba(52,44,28,.16);border-top:3px solid var(--blue)}
.route.count-5 .route-card,.route.count-6 .route-card{width:196px}
.route-card.is-above{bottom:calc(50% + 32px)}
.route-card.is-below{top:calc(50% + 32px)}
.route-date{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--blue)}
.route-card h3{font-family:var(--sans);font-size:19px;line-height:1.2;margin:5px 0 6px}
.route-card p{font-size:12px;line-height:1.4;color:var(--muted);margin:0}

/* Chrome */
.chrome{position:fixed;left:0;right:0;bottom:0;height:64px;z-index:20;background:#0d0f0c;color:#e9e4d8;border-top:1px solid rgba(255,255,255,.12)}
.controls{height:100%;display:flex;align-items:center;gap:8px;padding:0 18px}
.controls button{background:transparent;border:1px solid rgba(255,255,255,.2);color:#e9e4d8;padding:8px 12px;cursor:pointer;border-radius:0;font-size:13px}
.controls button:hover,.controls button:focus-visible{background:rgba(255,255,255,.1);outline:none}
.controls button kbd{font-family:var(--mono);font-size:10px;opacity:.6;margin-left:5px}
.counter{font-family:var(--mono);font-size:12px;letter-spacing:.08em;min-width:64px;text-align:center;color:#cfc9ba}
.control-spacer{flex:1}
.progress{position:absolute;left:0;right:0;top:-1px;height:3px;background:rgba(255,255,255,.08)}
.progress-bar{height:100%;width:0;background:var(--accent);transition:width .3s ease}

@media (max-width:900px){
  .chrome{height:56px}
  .stage-wrap{inset:0 0 56px 0}
  .controls button kbd{display:none}
}
@media (prefers-reduced-motion:reduce){
  .slide,.progress-bar{transition:none}
}
body.shot-mode{background:var(--paper);overflow:hidden}
body.shot-mode .stage-wrap{position:fixed;inset:0;overflow:hidden}
body.shot-mode .chrome{display:none!important}
body.shot-mode .stage{transform:none!important}
body.shot-mode .slide{transition:none!important}
@media print{
  @page{size:13.333in 7.5in;margin:0}
  html,body{background:#fff;overflow:visible}
  .chrome{display:none!important}
  .stage-wrap{position:static;display:block;inset:auto}
  .stage{position:relative;width:1920px;height:auto;transform:none!important;overflow:visible}
  .slide{position:relative;display:block!important;width:1920px;height:1080px;opacity:1!important;visibility:visible!important;transform:none!important;page-break-after:always;break-after:page;zoom:.6666667}
  .slide:last-child{page-break-after:auto;break-after:auto}
}

/* Readability type scale: larger body copy, tables, labels, captions and credits */
.kicker,.head-page{font-size:19px!important}
.slide-title{font-size:80px!important}
.slide-title.is-long{font-size:64px!important}
.slide-subtitle{font-size:33px!important}
.title-subtitle{font-size:40px!important}
.title-body{font-size:29px!important}
.title-meta{font-size:17px!important}
.section-body{font-size:29px!important}
.layout-section .section-grid.has-photo .section-title{font-size:80px!important;max-width:1330px!important}
.section-print{padding-bottom:64px!important}
.section-list li{font-size:30px!important}
.section-list li span{font-size:16px!important}
.ledger-index{font-size:17px!important}
.ledger-copy{font-size:35px!important}
.column h3{font-size:18px!important}
.rule-list li{font-size:31px!important}
.kpi-index,.stat-index,.framework-index,.map-index{font-size:15px!important}
.kpi-card h3{font-size:25px!important}
.kpi-value{font-size:60px!important}
.kpi-value.is-word{font-size:42px!important}
.kpi-detail{font-size:23px!important}
.budget-table{font-size:28px!important}
.budget-table th{font-size:15px!important}
.budget-summary{font-size:19px!important}
.pull-quote blockquote{font-size:94px!important}
.quote-layout .pull-quote blockquote{font-size:78px!important}
.quote-attribution{font-size:31px!important}
.quote-image figcaption,.photo-frame figcaption{font-size:16px!important}
.reference-list li{font-size:24px!important}
.reference-list.dense li{font-size:19px!important}
.reference-list li::marker{font-size:15px!important}
.step-copy{font-size:33px!important}
.flow-node h3{font-size:39px!important}
.flow-node p{font-size:24px!important}
.flow-node.compact h3{font-size:32px!important}
.flow-link span:first-child{font-size:14px!important}
.flow-arrow{font-size:39px!important}
.timeline-date{font-size:16px!important}
.timeline-item h3{font-size:29px!important}
.timeline-item p{font-size:22px!important}
.legend-item,.chart-unit{font-size:15px!important}
.chart-axis{font-size:18px!important}
.chart-category{font-size:19px!important}
.chart-value{font-size:18px!important}
.chart-value-inverse{font-size:17px!important}
.donut-total{font-size:70px!important}
.donut-unit{font-size:17px!important}
.donut-legend-item{font-size:24px!important}
.donut-legend-item strong{font-size:19px!important}
.data-table{font-size:29px!important}
.data-table th{font-size:15px!important}
.variant-dense .data-table{font-size:24px!important}
.source-note{font-size:19px!important}
.stat-value{font-size:72px!important}
.stat-value.is-long{font-size:50px!important}
.stat-card h3{font-size:24px!important}
.stat-detail{font-size:22px!important}
.stat-source{font-size:16px!important}
.gallery-item figcaption{font-size:23px!important}
.gallery-credit{font-size:17px!important}
.comparison-panel h3{font-size:18px!important}
.comparison-panel .rule-list li{font-size:31px!important}
.layout-comparison .body-note{margin:0 0 22px!important}
.variant-offset .comparison-panel .rule-list li{font-size:26px!important;padding-top:10px!important;padding-bottom:10px!important}
.variant-offset .comparison-panel h3{margin-bottom:12px}
.versus{font-size:16px!important}
.map-tile strong{font-size:25px!important}
.map-detail{font-size:20px!important}
.map-legend{font-size:15px!important}
.framework-kicker{font-size:15px!important}
.framework-head h3{font-size:50px!important}
.framework-head p{font-size:24px!important}
.framework-pillar h3{font-size:33px!important}
.framework-pillar p{font-size:22px!important}
.matrix-axis{font-size:17px!important}
.matrix-cell h3{font-size:33px!important}
.matrix-cell p{font-size:26px!important}
.slide-footer{font-size:16px!important}
.callout p{font-size:23px!important}
.callout-index{font-size:14px!important}
.hub-node h3{font-size:24px!important}
.hub-node.is-hub h3{font-size:33px!important}
.hub-node p{font-size:16px!important}
.hub-index{font-size:13px!important}
.route-card h3{font-size:22px!important}
.route-card p{font-size:15px!important}
.route-date{font-size:13px!important}
.print figcaption{font-size:16px!important}
.board-stamp{font-size:30px!important}
.board-note{font-size:24px!important}
.board-note-kicker{font-size:13px!important}
.board-tag{font-size:16px!important}
.board-sources{font-size:15px!important}
.body-note{font-size:22px!important}
.layout-chart .chart{max-width:1380px!important}
body.style-briefing .gallery.count-4 .gallery-item img{height:220px!important}
"""


_JS = r"""
(() => {
  const slides = Array.from(document.querySelectorAll('.slide'));
  const shot = new URLSearchParams(location.search).get('shot');
  const stage = document.getElementById('stage');
  const counter = document.getElementById('counter');
  const progress = document.getElementById('progress-bar');
  let index = 0;

  function pad(value) { return String(value).padStart(2, '0'); }

  function fit() {
    const wrap = document.querySelector('.stage-wrap');
    if (!wrap) return;
    const scale = Math.min(wrap.clientWidth / 1920, wrap.clientHeight / 1080);
    const x = (wrap.clientWidth - 1920 * scale) / 2;
    const y = (wrap.clientHeight - 1080 * scale) / 2;
    stage.style.transform = `translate(${x}px, ${y}px) scale(${Math.max(0.1, scale)})`;
  }

  function show(next, updateHash = true) {
    if (!slides.length) return;
    index = Math.max(0, Math.min(slides.length - 1, next));
    slides.forEach((slide, i) => {
      const active = i === index;
      slide.classList.toggle('is-active', active);
      slide.setAttribute('aria-hidden', String(!active));
    });
    counter.textContent = `${pad(index + 1)} / ${pad(slides.length)}`;
    progress.style.width = `${((index + 1) / slides.length) * 100}%`;
    if (updateHash) {
      try { history.replaceState(null, '', `#slide-${index + 1}`); } catch (error) {}
    }
  }

  function toggleFullscreen() {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
  }

  document.getElementById('prev').addEventListener('click', () => show(index - 1));
  document.getElementById('next').addEventListener('click', () => show(index + 1));
  document.getElementById('print').addEventListener('click', () => window.print());
  document.getElementById('fullscreen').addEventListener('click', toggleFullscreen);

  window.addEventListener('keydown', (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const key = event.key;
    if (key === 'ArrowRight' || key === 'ArrowDown' || key === 'PageDown' || key === ' ') {
      event.preventDefault();
      show(index + 1);
    } else if (key === 'ArrowLeft' || key === 'ArrowUp' || key === 'PageUp') {
      event.preventDefault();
      show(index - 1);
    } else if (key === 'Home') {
      event.preventDefault();
      show(0);
    } else if (key === 'End') {
      event.preventDefault();
      show(slides.length - 1);
    } else if (key === 'f' || key === 'F') {
      event.preventDefault();
      toggleFullscreen();
    }
  });

  let touchStartX = null;
  window.addEventListener('touchstart', (event) => {
    if (event.touches.length === 1) touchStartX = event.touches[0].clientX;
  }, { passive: true });
  window.addEventListener('touchend', (event) => {
    if (touchStartX === null) return;
    const delta = event.changedTouches[0].clientX - touchStartX;
    touchStartX = null;
    if (Math.abs(delta) > 48) show(index + (delta < 0 ? 1 : -1));
  }, { passive: true });

  if (shot) {
    document.body.classList.add('shot-mode');
    const target = Math.max(0, Math.min(slides.length - 1, Number(shot) - 1));
    show(Number.isFinite(target) ? target : 0, false);
    return;
  }

  const initial = Number((location.hash.match(/^#slide-(\d+)$/) || [])[1] || 1) - 1;
  show(Number.isFinite(initial) ? initial : 0, false);
  fit();
  window.addEventListener('resize', fit);
  window.addEventListener('orientationchange', fit);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit).catch(() => {});
})();
"""

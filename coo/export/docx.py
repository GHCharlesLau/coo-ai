"""Render a proposal to a styled Word document with cover, TOC, and page numbers."""

from __future__ import annotations

import io
import re
import threading

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from coo.export.markdown import INLINE_TOKEN_RE, Proposal, clean_title

NAVY = RGBColor(0x1F, 0x3A, 0x5F)
GOLD = RGBColor(0xB0, 0x8A, 0x3E)
GREY = RGBColor(0x6B, 0x70, 0x76)
BODY_FONT = "Calibri"
HEADING_FONT = "Georgia"
_BUILD_LOCK = threading.Lock()


def _rgb(value: str | None, fallback: RGBColor) -> RGBColor:
    candidate = (value or "").strip().lstrip("#").upper()
    return RGBColor.from_string(candidate) if re.fullmatch(r"[0-9A-F]{6}", candidate) else fallback


def _hex(color: RGBColor) -> str:
    return str(color)


def build_docx(
    proposal: Proposal,
    *,
    brand: str = "",
    prepared_on: str = "",
    palette: dict[str, str] | None = None,
) -> bytes:
    global NAVY, GOLD, GREY
    with _BUILD_LOCK:
        original = (NAVY, GOLD, GREY)
        NAVY = _rgb((palette or {}).get("navy"), NAVY)
        GOLD = _rgb((palette or {}).get("accent"), GOLD)
        GREY = _rgb((palette or {}).get("muted"), GREY)
        try:
            return _build_docx(proposal, brand=brand, prepared_on=prepared_on)
        finally:
            NAVY, GOLD, GREY = original


def _build_docx(proposal: Proposal, *, brand: str, prepared_on: str) -> bytes:
    document = Document()
    _configure_page(document)
    _configure_styles(document)
    _add_cover(document, proposal, brand=brand, prepared_on=prepared_on)
    _add_contents(document)
    _add_body(document, proposal)
    _add_footer(document, proposal.title)
    _enable_field_updates(document)

    document.core_properties.title = proposal.title
    document.core_properties.author = brand or "Campaign team"
    document.core_properties.subject = "Campaign proposal"
    document.core_properties.comments = ""

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _configure_page(document) -> None:
    section = document.sections[0]
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(0.95)
    section.left_margin = Inches(1.05)
    section.right_margin = Inches(1.05)
    section.different_first_page_header_footer = True


def _configure_styles(document) -> None:
    normal = document.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(13.5)
    normal.font.color.rgb = RGBColor(0x22, 0x24, 0x26)
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.15

    for name, size, before, after in (("Heading 1", 19, 18, 8), ("Heading 2", 14.5, 12, 5)):
        style = document.styles[name]
        style.font.name = HEADING_FONT
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = NAVY
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True


def _add_cover(document, proposal: Proposal, *, brand: str, prepared_on: str) -> None:
    for _ in range(5):
        document.add_paragraph()

    eyebrow = document.add_paragraph()
    eyebrow.paragraph_format.space_after = Pt(4)
    run = eyebrow.add_run("CAMPAIGN PROPOSAL")
    run.font.name = BODY_FONT
    run.font.size = Pt(12)
    run.font.bold = True
    run.font.color.rgb = GOLD

    title = document.add_paragraph()
    title.paragraph_format.space_after = Pt(12)
    run = title.add_run(clean_title(proposal.title))
    run.font.name = HEADING_FONT
    run.font.size = Pt(30)
    run.font.bold = True
    run.font.color.rgb = NAVY
    _bottom_border(title, color=_hex(GOLD), size="16")

    if brand:
        line = document.add_paragraph()
        line.paragraph_format.space_before = Pt(14)
        line.paragraph_format.space_after = Pt(2)
        run = line.add_run(brand)
        run.font.name = HEADING_FONT
        run.font.size = Pt(15.5)
        run.font.color.rgb = RGBColor(0x3A, 0x3F, 0x45)

    if prepared_on:
        line = document.add_paragraph()
        line.paragraph_format.space_after = Pt(2)
        run = line.add_run(prepared_on)
        run.font.size = Pt(12)
        run.font.color.rgb = GREY

    for _ in range(8):
        document.add_paragraph()
    line = document.add_paragraph()
    run = line.add_run("Prepared for client review")
    run.font.size = Pt(11.5)
    run.font.color.rgb = GREY

    document.add_page_break()


def _add_contents(document) -> None:
    heading = document.add_paragraph()
    heading.paragraph_format.space_before = Pt(0)
    heading.paragraph_format.space_after = Pt(10)
    run = heading.add_run("Contents")
    run.font.name = HEADING_FONT
    run.font.size = Pt(20)
    run.font.bold = True
    run.font.color.rgb = NAVY

    field_paragraph = document.add_paragraph()
    _add_field(field_paragraph, 'TOC \\o "1-2" \\h \\z \\u')
    document.add_page_break()


def _add_body(document, proposal: Proposal) -> None:
    in_references = False
    in_measurement = False
    expect_lead = False
    for block in proposal.blocks:
        if block.kind == "heading":
            in_references = block.text.strip().lower() == "references"
            in_measurement = "measurement" in block.text.casefold()
            expect_lead = block.level == 1 and not in_references
            paragraph = document.add_paragraph(style="Heading 1" if block.level == 1 else "Heading 2")
            _add_inline(paragraph, block.text)
        elif block.kind == "paragraph":
            if expect_lead:
                _add_lead(document, block.text)
                expect_lead = False
                continue
            paragraph = document.add_paragraph()
            if in_references:
                paragraph.paragraph_format.left_indent = Inches(0.3)
                paragraph.paragraph_format.first_line_indent = Inches(-0.3)
                paragraph.paragraph_format.space_after = Pt(4)
                paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            _add_inline(paragraph, block.text)
        elif block.kind == "bullets":
            for item in block.items:
                if in_measurement and _looks_like_stat(item):
                    _add_stat_callout(document, item)
                    continue
                paragraph = document.add_paragraph(style="List Bullet")
                _add_inline(paragraph, item)
        elif block.kind == "numbered":
            for number, item in enumerate(block.items, start=1):
                paragraph = document.add_paragraph()
                paragraph.paragraph_format.left_indent = Inches(0.3)
                paragraph.paragraph_format.first_line_indent = Inches(-0.22)
                paragraph.paragraph_format.space_after = Pt(4)
                paragraph.add_run(f"{number}. ")
                _add_inline(paragraph, item)
        elif block.kind == "quote":
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Inches(0.35)
            paragraph.paragraph_format.right_indent = Inches(0.35)
            run = paragraph.add_run("“")
            run.font.color.rgb = GOLD
            _add_inline(paragraph, block.text)
            run = paragraph.add_run("”")
            run.font.color.rgb = GOLD
        elif block.kind == "table":
            _add_table(document, block.rows)
        elif block.kind == "rule":
            paragraph = document.add_paragraph()
            _bottom_border(paragraph, color="D9DDE2", size="6")
            paragraph.paragraph_format.space_after = Pt(10)


def _add_table(document, rows: list[list[str]]) -> None:
    columns = max(len(row) for row in rows)
    table = document.add_table(rows=len(rows), cols=columns)
    table.style = "Table Grid"
    table.autofit = True
    for row_index, row in enumerate(rows):
        for column_index in range(columns):
            cell = table.cell(row_index, column_index)
            cell.text = ""
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(2)
            text = row[column_index] if column_index < len(row) else ""
            _add_inline(paragraph, text)
            for run in paragraph.runs:
                run.font.size = Pt(12.5 if row_index else 13)
                if row_index == 0:
                    run.font.bold = True
                    run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            if row_index == 0:
                _shade_cell(cell, _hex(NAVY))
            elif row_index % 2 == 0:
                _shade_cell(cell, "F2F4F7")
    document.add_paragraph().paragraph_format.space_after = Pt(2)


def _add_lead(document, text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(9)
    run = paragraph.add_run(text)
    run.font.name = HEADING_FONT
    run.font.size = Pt(14)
    run.italic = True
    run.font.color.rgb = GREY


def _looks_like_stat(text: str) -> bool:
    plain = text.strip()
    if len(plain) > 240 or not re.search(r"\d", plain):
        return False
    return bool(
        re.search(
            r"\b(target|kpi|lift|reach|awareness|signups?|actions?|usd|hkd|eur|%|pts?)\b",
            plain,
            re.IGNORECASE,
        )
    )


def _add_stat_callout(document, text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.left_indent = Inches(0.22)
    paragraph.paragraph_format.space_before = Pt(3)
    paragraph.paragraph_format.space_after = Pt(6)
    _shade_paragraph(paragraph, "F7F4EC")
    _left_border(paragraph, color=_hex(GOLD), size="18")
    _add_inline(paragraph, text)
    for run in paragraph.runs:
        run.font.size = Pt(12)


def _add_inline(paragraph, text: str) -> None:
    position = 0
    for match in INLINE_TOKEN_RE.finditer(text):
        if match.start() > position:
            paragraph.add_run(text[position : match.start()])
        token = match.group(0)
        if token.startswith("**") and token.endswith("**"):
            run = paragraph.add_run(token[2:-2])
            run.bold = True
        elif token.startswith("`") and token.endswith("`"):
            run = paragraph.add_run(token[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
        elif token.startswith("["):
            label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", token).groups()  # type: ignore[union-attr]
            _add_hyperlink(paragraph, url, label)
        elif token.startswith("http"):
            _add_hyperlink(paragraph, token, token)
        elif token.startswith("*") and token.endswith("*"):
            run = paragraph.add_run(token[1:-1])
            run.italic = True
        else:
            paragraph.add_run(token)
        position = match.end()
    if position < len(text):
        paragraph.add_run(text[position:])


def _add_hyperlink(paragraph, url: str, label: str) -> None:
    try:
        relationship_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    except Exception:
        paragraph.add_run(label)
        return
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    run_element = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), _hex(NAVY))
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.append(color)
    properties.append(underline)
    run_element.append(properties)
    text_element = OxmlElement("w:t")
    text_element.text = label
    run_element.append(text_element)
    hyperlink.append(run_element)
    paragraph._p.append(hyperlink)


def _add_field(paragraph, instruction: str, placeholder: str = "") -> None:
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    paragraph.add_run()._r.append(begin)

    instruction_element = OxmlElement("w:instrText")
    instruction_element.set(qn("xml:space"), "preserve")
    instruction_element.text = f" {instruction} "
    paragraph.add_run()._r.append(instruction_element)

    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    paragraph.add_run()._r.append(separate)

    if placeholder:
        paragraph.add_run(placeholder)

    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    paragraph.add_run()._r.append(end)


def _add_footer(document, title: str) -> None:
    section = document.sections[0]
    section.header.is_linked_to_previous = False
    header_paragraph = section.header.paragraphs[0]
    header_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = header_paragraph.add_run(title)
    run.font.size = Pt(9.5)
    run.font.color.rgb = GREY

    footer = section.footer
    footer.is_linked_to_previous = False
    paragraph = footer.paragraphs[0]
    paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(6.4), WD_TAB_ALIGNMENT.RIGHT)
    run = paragraph.add_run("Campaign Proposal")
    run.font.size = Pt(9.5)
    run.font.color.rgb = GREY
    paragraph.add_run("\t")
    run = paragraph.add_run("Page ")
    run.font.size = Pt(9.5)
    run.font.color.rgb = GREY
    _add_field(paragraph, "PAGE", "1")
    run = paragraph.add_run(" of ")
    run.font.size = Pt(9.5)
    run.font.color.rgb = GREY
    _add_field(paragraph, "NUMPAGES", "1")
    for run in paragraph.runs:
        run.font.size = Pt(9.5)
        run.font.color.rgb = GREY


def _enable_field_updates(document) -> None:
    settings = document.settings.element
    update = OxmlElement("w:updateFields")
    update.set(qn("w:val"), "true")
    settings.append(update)


def _bottom_border(paragraph, *, color: str, size: str) -> None:
    properties = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), size)
    bottom.set(qn("w:space"), "8")
    bottom.set(qn("w:color"), color)
    borders.append(bottom)
    properties.append(borders)


def _left_border(paragraph, *, color: str, size: str) -> None:
    properties = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), size)
    left.set(qn("w:space"), "6")
    left.set(qn("w:color"), color)
    borders.append(left)
    properties.append(borders)


def _shade_paragraph(paragraph, color: str) -> None:
    properties = paragraph._p.get_or_add_pPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), color)
    properties.append(shading)


def _shade_cell(cell, color: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), color)
    properties.append(shading)

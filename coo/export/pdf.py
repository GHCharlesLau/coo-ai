"""Render a proposal to a paginated PDF with cover, TOC, and page numbers."""

from __future__ import annotations

import io
import re
import threading
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from coo.export.markdown import INLINE_TOKEN_RE, Proposal, clean_title

NAVY = colors.HexColor("#1F3A5F")
GOLD = colors.HexColor("#B08A3E")
GREY = colors.HexColor("#6B7076")
BODY_TEXT = colors.HexColor("#222426")
LIGHT = colors.HexColor("#D9DDE2")
LIGHT_BG = colors.HexColor("#F2F4F7")
WHITE = colors.white
_BUILD_LOCK = threading.Lock()

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_CJK_FONT_CANDIDATES = (
    (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"),
    (r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\simhei.ttf"),
    ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/PingFang.ttc"),
    (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ),
    (
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    ),
)


def _hex_color(value: str | None, fallback) -> colors.Color:
    candidate = (value or "").strip().lstrip("#")
    if re.fullmatch(r"[0-9A-Fa-f]{6}", candidate):
        return colors.HexColor("#" + candidate.upper())
    return fallback


def build_pdf(
    proposal: Proposal,
    *,
    brand: str = "",
    prepared_on: str = "",
    palette: dict[str, str] | None = None,
) -> bytes:
    global NAVY, GOLD, GREY
    with _BUILD_LOCK:
        original = (NAVY, GOLD, GREY)
        NAVY = _hex_color((palette or {}).get("navy"), NAVY)
        GOLD = _hex_color((palette or {}).get("accent"), GOLD)
        GREY = _hex_color((palette or {}).get("muted"), GREY)
        try:
            return _build_pdf(proposal, brand=brand, prepared_on=prepared_on)
        finally:
            NAVY, GOLD, GREY = original


def _build_pdf(proposal: Proposal, *, brand: str, prepared_on: str) -> bytes:
    body_font, body_bold, body_italic, heading_font, heading_bold, table_font, table_bold = _fonts(proposal)
    styles = _styles(body_font, body_italic, heading_font, heading_bold, table_font, table_bold)

    buffer = io.BytesIO()
    document = _ProposalDoc(
        buffer,
        title=clean_title(proposal.title),
        brand=brand,
        pagesize=A4,
        leftMargin=2.1 * cm,
        rightMargin=2.1 * cm,
        topMargin=2.35 * cm,
        bottomMargin=2.2 * cm,
        author=brand or "Campaign team",
        subject="Campaign proposal",
    )
    frame = Frame(document.leftMargin, document.bottomMargin, document.width, document.height, id="body")
    document.addPageTemplates(
        [
            PageTemplate(id="cover", frames=[frame], onPage=document.draw_cover),
            PageTemplate(id="body", frames=[frame], onPage=document.draw_body),
        ]
    )

    story = _cover_story(proposal, brand=brand, prepared_on=prepared_on, styles=styles)
    story.append(NextPageTemplate("body"))
    story.append(PageBreak())
    story.append(Paragraph("Contents", styles["toc_title"]))
    story.append(Spacer(1, 4 * mm))
    contents = TableOfContents()
    contents.levelStyles = [styles["toc0"], styles["toc1"]]
    story.append(contents)
    story.append(PageBreak())
    story.extend(_body_story(proposal, styles))

    document.multiBuild(story)
    return buffer.getvalue()


class _ProposalDoc(BaseDocTemplate):
    def __init__(self, filename, *, title: str, brand: str, **kwargs):
        super().__init__(filename, title=title, **kwargs)
        self.proposal_title = title
        self.brand = brand

    def afterFlowable(self, flowable) -> None:
        if not isinstance(flowable, Paragraph):
            return
        name = flowable.style.name
        if name == "ProposalH1":
            self.notify("TOCEntry", (0, flowable.getPlainText(), self.page))
        elif name == "ProposalH2":
            self.notify("TOCEntry", (1, flowable.getPlainText(), self.page))

    def draw_cover(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1] - 26 * mm, A4[0], 26 * mm, fill=1, stroke=0)
        canvas.setFillColor(GOLD)
        canvas.rect(0, A4[1] - 27.4 * mm, A4[0], 1.4 * mm, fill=1, stroke=0)
        canvas.restoreState()

    def draw_body(self, canvas, doc) -> None:
        canvas.saveState()
        left = doc.leftMargin
        right = A4[0] - doc.rightMargin
        canvas.setStrokeColor(LIGHT)
        canvas.setLineWidth(0.5)
        canvas.line(left, 1.6 * cm, right, 1.6 * cm)
        canvas.setFillColor(GREY)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(left, 1.05 * cm, f"{self.brand}  |  Campaign Proposal" if self.brand else "Campaign Proposal")
        canvas.drawRightString(right, 1.05 * cm, f"Page {canvas.getPageNumber()}")
        title = self.proposal_title
        if len(title) > 88:
            title = title[:85].rstrip() + "…"
        canvas.drawString(left, A4[1] - 1.35 * cm, title)
        if self.brand:
            canvas.drawRightString(right, A4[1] - 1.35 * cm, self.brand)
        canvas.restoreState()


def _fonts(proposal: Proposal):
    text = " ".join([proposal.title, *(block.text for block in proposal.blocks)])
    if _CJK_RE.search(text):
        regular, bold = _register_cjk()
        if regular:
            return regular, bold, regular, bold, bold, regular, bold
    return "Times-Roman", "Times-Bold", "Times-Italic", "Helvetica-Bold", "Helvetica-Bold", "Helvetica", "Helvetica-Bold"


def _register_cjk() -> tuple[str, str]:
    for regular_path, bold_path in _CJK_FONT_CANDIDATES:
        if not Path(regular_path).is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont("ProposalCJK", regular_path, subfontIndex=0))
            bold_name = "ProposalCJK"
            if Path(bold_path).is_file():
                pdfmetrics.registerFont(TTFont("ProposalCJK-Bold", bold_path, subfontIndex=0))
                bold_name = "ProposalCJK-Bold"
            pdfmetrics.registerFontFamily(
                "ProposalCJK",
                normal="ProposalCJK",
                bold=bold_name,
                italic="ProposalCJK",
                boldItalic=bold_name,
            )
            return "ProposalCJK", bold_name
        except Exception:
            continue
    return "", ""


def _styles(body_font: str, body_italic: str, heading_font: str, heading_bold: str, table_font: str, table_bold: str):
    return {
        "body": ParagraphStyle(
            "ProposalBody",
            fontName=body_font,
            fontSize=10.3,
            leading=14.8,
            textColor=BODY_TEXT,
            alignment=TA_LEFT,
            spaceAfter=7,
        ),
        "bullet": ParagraphStyle(
            "ProposalBullet",
            fontName=body_font,
            fontSize=10.3,
            leading=14.5,
            textColor=BODY_TEXT,
            leftIndent=14,
            bulletIndent=4,
            spaceAfter=3,
        ),
        "lead": ParagraphStyle(
            "ProposalLead",
            fontName=body_italic,
            fontSize=11.4,
            leading=16,
            textColor=GREY,
            spaceAfter=9,
        ),
        "callout": ParagraphStyle(
            "ProposalCallout",
            fontName=body_font,
            fontSize=10.1,
            leading=14,
            textColor=BODY_TEXT,
        ),
        "quote": ParagraphStyle(
            "ProposalQuote",
            fontName=body_italic,
            fontSize=10.3,
            leading=15,
            textColor=colors.HexColor("#3A3F45"),
            leftIndent=16,
            rightIndent=16,
            borderPadding=6,
            backColor=colors.HexColor("#F7F4EC"),
            spaceBefore=4,
            spaceAfter=8,
        ),
        "ref": ParagraphStyle(
            "ProposalReference",
            fontName=body_font,
            fontSize=9.4,
            leading=13,
            textColor=BODY_TEXT,
            leftIndent=10,
            firstLineIndent=-10,
            spaceAfter=4,
        ),
        "h1": ParagraphStyle(
            "ProposalH1",
            fontName=heading_bold,
            fontSize=15.5,
            leading=20,
            textColor=NAVY,
            spaceBefore=14,
            spaceAfter=7,
            keepWithNext=1,
        ),
        "h2": ParagraphStyle(
            "ProposalH2",
            fontName=heading_font,
            fontSize=12,
            leading=16,
            textColor=NAVY,
            spaceBefore=10,
            spaceAfter=4,
            keepWithNext=1,
        ),
        "title": ParagraphStyle(
            "ProposalTitle",
            fontName=heading_bold,
            fontSize=26,
            leading=31,
            textColor=NAVY,
            spaceAfter=0,
        ),
        "eyebrow": ParagraphStyle(
            "ProposalEyebrow",
            fontName=table_bold,
            fontSize=10.5,
            leading=14,
            textColor=GOLD,
        ),
        "cover_meta": ParagraphStyle(
            "ProposalCoverMeta",
            fontName=table_font,
            fontSize=10.5,
            leading=15,
            textColor=GREY,
        ),
        "cover_brand": ParagraphStyle(
            "ProposalCoverBrand",
            fontName=heading_font,
            fontSize=14,
            leading=19,
            textColor=colors.HexColor("#3A3F45"),
        ),
        "toc_title": ParagraphStyle(
            "ProposalTOCTitle",
            fontName=heading_bold,
            fontSize=18,
            leading=22,
            textColor=NAVY,
            spaceAfter=8,
        ),
        "toc0": ParagraphStyle(
            "ProposalTOC0",
            fontName=table_bold,
            fontSize=10,
            leading=17,
            textColor=BODY_TEXT,
            spaceBefore=2,
        ),
        "toc1": ParagraphStyle(
            "ProposalTOC1",
            fontName=table_font,
            fontSize=9.2,
            leading=14,
            textColor=GREY,
        ),
        "cell": ParagraphStyle(
            "ProposalCell",
            fontName=table_font,
            fontSize=8.4,
            leading=10.4,
            textColor=BODY_TEXT,
        ),
        "cell_header": ParagraphStyle(
            "ProposalCellHeader",
            fontName=table_bold,
            fontSize=8.4,
            leading=10.4,
            textColor=WHITE,
        ),
    }


def _cover_story(proposal: Proposal, *, brand: str, prepared_on: str, styles) -> list:
    story: list = [Spacer(1, 56 * mm)]
    story.append(Paragraph("CAMPAIGN PROPOSAL", styles["eyebrow"]))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(_escape(clean_title(proposal.title)), styles["title"]))
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="38%", thickness=1.4, color=GOLD, spaceBefore=0, spaceAfter=0, hAlign="LEFT"))
    story.append(Spacer(1, 8 * mm))
    if brand:
        story.append(Paragraph(_escape(brand), styles["cover_brand"]))
        story.append(Spacer(1, 1.5 * mm))
    if prepared_on:
        story.append(Paragraph(_escape(prepared_on), styles["cover_meta"]))
    story.append(Spacer(1, 74 * mm))
    story.append(Paragraph("Prepared for client review", styles["cover_meta"]))
    return story


def _body_story(proposal: Proposal, styles) -> list:
    story: list = []
    in_references = False
    in_measurement = False
    expect_lead = False
    for block in proposal.blocks:
        if block.kind == "heading":
            in_references = block.text.strip().lower() == "references"
            in_measurement = "measurement" in block.text.casefold()
            expect_lead = block.level == 1 and not in_references
            story.append(
                Paragraph(_inline(block.text), styles["h1"] if block.level == 1 else styles["h2"])
            )
        elif block.kind == "paragraph":
            if expect_lead:
                story.append(Paragraph(_inline(block.text), styles["lead"]))
                expect_lead = False
                continue
            style = styles["ref"] if in_references else styles["body"]
            story.append(Paragraph(_inline(block.text), style))
        elif block.kind == "bullets":
            for item in block.items:
                if in_measurement and _looks_like_stat(item):
                    story.append(_stat_callout(item, styles))
                else:
                    story.append(Paragraph(_inline(item), styles["bullet"], bulletText="•"))
        elif block.kind == "numbered":
            for number, item in enumerate(block.items, start=1):
                story.append(Paragraph(_inline(item), styles["bullet"], bulletText=f"{number}."))
        elif block.kind == "quote":
            story.append(Paragraph(_inline(block.text), styles["quote"]))
        elif block.kind == "table":
            story.append(Spacer(1, 2 * mm))
            story.append(_table(block.rows, styles))
            story.append(Spacer(1, 3 * mm))
        elif block.kind == "rule":
            story.append(HRFlowable(width="100%", thickness=0.6, color=LIGHT, spaceBefore=4, spaceAfter=8))
    return story


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


def _stat_callout(text: str, styles) -> Table:
    available = A4[0] - 4.2 * cm
    table = Table([[Paragraph(_inline(text), styles["callout"])]], colWidths=[available])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7F4EC")),
                ("LINEBEFORE", (0, 0), (0, -1), 2.4, GOLD),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _table(rows: list[list[str]], styles) -> Table:
    columns = max(len(row) for row in rows)
    data = []
    for row_index, row in enumerate(rows):
        style = styles["cell_header"] if row_index == 0 else styles["cell"]
        data.append(
            [
                Paragraph(_inline(row[column_index] if column_index < len(row) else ""), style)
                for column_index in range(columns)
            ]
        )
    available = A4[0] - 4.2 * cm
    table = Table(data, colWidths=[available / columns] * columns, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("GRID", (0, 0), (-1, -1), 0.4, LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _inline(text: str) -> str:
    link_color = "#" + NAVY.hexval()[2:].upper()
    parts: list[str] = []
    position = 0
    for match in INLINE_TOKEN_RE.finditer(text):
        if match.start() > position:
            parts.append(_escape(text[position : match.start()]))
        token = match.group(0)
        if token.startswith("**") and token.endswith("**"):
            parts.append(f"<b>{_escape(token[2:-2])}</b>")
        elif token.startswith("`") and token.endswith("`"):
            parts.append(f'<font face="Courier">{_escape(token[1:-1])}</font>')
        elif token.startswith("["):
            label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", token).groups()  # type: ignore[union-attr]
            parts.append(f'<link href="{_escape_attr(url)}" color="{link_color}">{_escape(label)}</link>')
        elif token.startswith("http"):
            parts.append(f'<link href="{_escape_attr(token)}" color="{link_color}">{_escape(token)}</link>')
        elif token.startswith("*") and token.endswith("*"):
            parts.append(f"<i>{_escape(token[1:-1])}</i>")
        else:
            parts.append(_escape(token))
        position = match.end()
    if position < len(text):
        parts.append(_escape(text[position:]))
    return "".join(parts)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(text: str) -> str:
    return _escape(text).replace('"', "&quot;")

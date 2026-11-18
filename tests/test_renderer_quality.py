from __future__ import annotations

import io

import pytest
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pypdf import PdfReader

from coo.export.deck_pdf import deck_pdf_available, render_deck_pdf
from coo.schemas.slides import Deck
from coo.slides.pptx import render_pptx_bytes
from coo.slides.web import build_html


def _visual_deck() -> Deck:
    return Deck.model_validate(
        {
            "campaign_id": "cmp-20261108-a1b2c3d4",
            "design": {"style": "editorial", "accent_mode": "contrast", "visual_ratio": 0.4},
            "slides": [
                {"layout": "title", "title": "Visual deck", "subtitle": "Layout parity"},
                {
                    "layout": "table",
                    "title": "A source table",
                    "table": {
                        "columns": ["Item", "Status", "Date"],
                        "rows": [["Theme", "Published", "2025"], ["Vote", "Closed", "30 Oct"]],
                        "align": ["left", "center", "right"],
                        "highlight_rows": [1],
                        "source_note": "Planning assumptions.",
                    },
                },
                {
                    "layout": "stats",
                    "title": "Three numbers",
                    "stats": [
                        {"value": "21", "label": "Economies", "detail": "Working geography."},
                        {"value": "17-19", "label": "Leaders' Week", "detail": "November 2026."},
                        {"value": "5", "label": "Workstreams", "detail": "One sequence."},
                    ],
                },
                {
                    "layout": "comparison",
                    "title": "Open versus closed",
                    "left_title": "Closed",
                    "right_title": "Open",
                    "left": ["Vote ended.", "Submissions closed."],
                    "right": ["Verified routes.", "Current guidance."],
                },
                {
                    "layout": "chart",
                    "title": "Donut view",
                    "chart": {
                        "kind": "donut",
                        "categories": ["Editorial", "Media", "Monitoring"],
                        "series": [{"label": "Base budget", "values": [9, 14, 9]}],
                        "unit": "USD 000",
                    },
                    "source_note": "Planning assumptions.",
                },
                {"layout": "references", "title": "Sources", "bullets": ["APEC. (2025). A source."]},
            ],
        }
    )


def test_visual_layouts_render_native_editable_shapes():
    deck = _visual_deck()
    prs = Presentation(io.BytesIO(render_pptx_bytes(deck)))
    assert len(prs.slides) == len(deck.slides)
    for slide in prs.slides:
        assert not slide.has_notes_slide
        assert any(shape.has_text_frame and shape.text_frame.text.strip() for shape in slide.shapes)
    assert any(shape.has_table for shape in prs.slides[1].shapes)
    assert any(shape.has_chart for shape in prs.slides[4].shapes)
    assert not any(shape.shape_type == MSO_SHAPE_TYPE.PICTURE for slide in prs.slides for shape in slide.shapes)


def test_gallery_with_supplied_images_renders():
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        Image.new("RGB", (64, 36), (199, 67, 47)).save(root / "image.png")
        deck = Deck.model_validate(
            {
                "campaign_id": "cmp-20261108-a1b2c3d4",
                "slides": [
                    {
                        "layout": "gallery",
                        "title": "Two images",
                        "images": [
                            {
                                "path": "image.png",
                                "alt_text": "Coral image one",
                                "caption": "One.",
                                "rights_status": "supplied",
                                "usage": "Test.",
                            },
                            {
                                "path": "image.png",
                                "alt_text": "Coral image two",
                                "caption": "Two.",
                                "rights_status": "supplied",
                                "usage": "Test.",
                            },
                        ],
                    }
                ],
            }
        )
        prs = Presentation(io.BytesIO(render_pptx_bytes(deck, assets_root=root)))
        assert len(prs.slides) == 1
        slide = prs.slides[0]
        assert not slide.has_notes_slide
        pictures = [shape for shape in slide.shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE]
        assert len(pictures) == 2
        assert all(picture._element.nvPicPr.cNvPr.get("descr") for picture in pictures)


def test_variant_hint_changes_the_composition():
    deck = Deck.model_validate(
        {
            "campaign_id": "cmp-20261108-a1b2c3d4",
            "slides": [
                {"layout": "bullets", "title": "Rail slide", "variant": "rail", "bullets": ["One"]},
                {"layout": "bullets", "title": "Split slide", "variant": "split", "bullets": ["Two"]},
            ],
        }
    )
    document = build_html(deck).decode("utf-8")
    assert 'data-variant="rail"' in document
    assert 'data-variant="split"' in document
    assert "shot-mode" in document
    assert "URLSearchParams(location.search).get('shot')" in document


@pytest.mark.skipif(not deck_pdf_available(), reason="deck PDF needs Chrome, Chromium, or Edge")
def test_deck_pdf_page_count_comes_from_the_html(tmp_path):
    deck = Deck.model_validate(
        {
            "campaign_id": "cmp-20261108-a1b2c3d4",
            "slides": [
                {"layout": "title", "title": "HTML page one"},
                {"layout": "bullets", "title": "HTML page two", "bullets": ["Text"]},
                {"layout": "references", "title": "HTML page three", "bullets": ["Source"]},
            ],
        }
    )
    html_path = tmp_path / "deck.html"
    html_path.write_bytes(build_html(deck))
    pdf_path = tmp_path / "deck.pdf"
    render_deck_pdf(html_path, pdf_path, expected_pages=3)
    assert pdf_path.read_bytes().startswith(b"%PDF")
    reader = PdfReader(str(pdf_path))
    assert len(reader.pages) == 3
    assert "HTML page one" in (reader.pages[0].extract_text() or "")

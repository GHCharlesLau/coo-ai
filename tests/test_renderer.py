from __future__ import annotations

import io

import pytest
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from coo.schemas.slides import Deck
from coo.slides.pptx import render_pptx_bytes
from coo.slides.web import build_html


def _pictures(slide):
    return [shape for shape in slide.shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE]


def test_deck_becomes_native_editable_powerpoint_slides():
    deck = Deck.model_validate(
        {
            "campaign_id": "cmp-20261012-a1b2c3d4",
            "palette": {"background": "EDE7DA", "accent": "2F5D50"},
            "slides": [
                {
                    "layout": "title",
                    "title": "A distinctive campaign deck",
                    "subtitle": "Real text, real shapes",
                    "notes": "Open with the demand.",
                },
                {
                    "layout": "bullets",
                    "title": "What the evidence says",
                    "bullets": [
                        "Long headings wrap inside the content well.",
                        "Composition varies by index and design hint.",
                    ],
                    "notes": "Keep each bullet short.",
                },
            ],
        }
    )
    prs = Presentation(io.BytesIO(render_pptx_bytes(deck)))
    assert len(prs.slides) == len(deck.slides)
    assert abs(prs.slide_width - int(13.333 * 914400)) < 10000
    assert abs(prs.slide_height - int(7.5 * 914400)) < 10000
    for slide in prs.slides:
        texts = [shape for shape in slide.shapes if shape.has_text_frame and shape.text_frame.text.strip()]
        assert texts, "every slide needs editable text"
        assert not slide.has_notes_slide, "speaker notes must not be written"
        for picture in _pictures(slide):
            assert not (picture.width >= prs.slide_width * 0.98 and picture.height >= prs.slide_height * 0.98)
    assert "A distinctive campaign deck" in " ".join(
        shape.text_frame.text for shape in prs.slides[0].shapes if shape.has_text_frame
    )


def test_supplied_image_is_a_picture_frame_with_alt_text(tmp_path):
    Image.new("RGB", (600, 400), "#345678").save(tmp_path / "provided.png")
    deck = Deck.model_validate(
        {
            "campaign_id": "cmp-20261012-a1b2c3d4",
            "slides": [
                {
                    "layout": "photo",
                    "title": "A supplied campaign scene",
                    "body": "Supporting context",
                    "notes": "Speaker copy is internal only.",
                    "cite_ids": ["ev1"],
                    "image": {
                        "path": "provided.png",
                        "alt_text": "A blue test image for the campaign.",
                        "caption": "Supplied brand image",
                        "rights_status": "licensed",
                        "usage": "Client confirmed campaign usage through December 2026.",
                        "source_url": "https://example.com/image",
                        "creator": "Example Studio",
                        "license": "Client license",
                    },
                }
            ],
        }
    )
    prs = Presentation(
        io.BytesIO(
            render_pptx_bytes(
                deck,
                assets_root=tmp_path,
                citations={"ev1": "Example Research, 2026"},
            )
        )
    )
    slide = prs.slides[0]
    assert not slide.has_notes_slide
    pictures = _pictures(slide)
    assert pictures
    assert pictures[0]._element.nvPicPr.cNvPr.get("descr") == "A blue test image for the campaign."
    copy = " ".join(shape.text_frame.text for shape in slide.shapes if shape.has_text_frame)
    assert "Supplied brand image" in copy
    assert "Example Research, 2026" in copy
    assert "Speaker copy is internal only." not in copy


def test_missing_and_unsafe_image_assets_are_rejected(tmp_path):
    deck = Deck.model_validate(
        {
            "campaign_id": "cmp-20261012-a1b2c3d4",
            "slides": [
                {
                    "layout": "photo",
                    "title": "Missing",
                    "image": {
                        "path": "missing.png",
                        "alt_text": "Missing photo",
                        "rights_status": "supplied",
                        "usage": "Provided by the client and cleared for campaign use.",
                    },
                }
            ],
        }
    )
    with pytest.raises(FileNotFoundError):
        build_html(deck, assets_root=tmp_path)
    with pytest.raises(FileNotFoundError):
        render_pptx_bytes(deck, assets_root=tmp_path)
    unsafe = deck.model_copy(deep=True)
    unsafe.slides[0].image.path = "../outside.png"
    with pytest.raises(ValueError, match="inside campaign artifacts"):
        build_html(unsafe, assets_root=tmp_path)
    with pytest.raises(ValueError, match="inside campaign artifacts"):
        render_pptx_bytes(unsafe, assets_root=tmp_path)


def test_licensed_photo_requires_rights_metadata():
    with pytest.raises(ValueError, match="source_url, creator, and license"):
        Deck.model_validate(
            {
                "campaign_id": "cmp-20261012-a1b2c3d4",
                "slides": [
                    {
                        "layout": "photo",
                        "title": "Uncleared",
                        "image": {
                            "path": "x.png",
                            "alt_text": "Photo",
                            "rights_status": "licensed",
                            "usage": "Campaign use under license.",
                        },
                    }
                ],
            }
        )


def test_template_path_is_tolerated_and_ignored():
    deck = Deck.model_validate(
        {
            "campaign_id": "cmp-20261012-a1b2c3d4",
            "template_path": "does-not-exist.pptx",
            "slides": [{"layout": "title", "title": "No template required"}],
        }
    )
    document = build_html(deck).decode("utf-8")
    assert "No template required" in document
    assert "does-not-exist" not in document

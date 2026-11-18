from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from coo.export import export_campaign
from coo.export.deck_pdf import deck_pdf_available
from coo.schemas.slides import Deck
from coo.slides.web import build_html
from tests.factories import (
    valid_brief,
    valid_deck,
    valid_evidence,
    valid_measurement,
    valid_plan,
    valid_proposal,
    write_json,
)


def _write_image(tmp_path: Path) -> None:
    Image.new("RGB", (32, 18), (199, 67, 47)).save(tmp_path / "image.png")


def _all_layout_deck(tmp_path: Path) -> Deck:
    _write_image(tmp_path)
    return Deck.model_validate(
        {
            "campaign_id": "cmp-20261108-abcdef12",
            "theme": "editorial",
            "budget_total": 10000,
            "budget_low": 9000,
            "budget_high": 11000,
            "budget_complete": True,
            "budget_currency": "USD",
            "kpi_ids": ["kpi_one"],
            "tactic_ids": ["tac_one"],
            "slides": [
                {
                    "layout": "title",
                    "title": "A distinctive campaign deck",
                    "subtitle": "A fixed 16:9 stage with editorial typography",
                    "body": "Built from slides.json.",
                    "notes": "Cover note.",
                },
                {
                    "layout": "section",
                    "title": "The argument",
                    "subtitle": "Three moves",
                    "body": "A section opener.",
                    "bullets": ["Context", "Strategy", "Delivery"],
                    "notes": "Section note.",
                },
                {
                    "layout": "bullets",
                    "title": "What the evidence says",
                    "bullets": ["First finding", "Second finding", "Third finding"],
                    "body": "A source note.",
                    "cite_ids": ["E1"],
                    "notes": "Bullet note.",
                },
                {
                    "layout": "two_column",
                    "title": "Two sides of the same story",
                    "left_title": "Now",
                    "right_title": "Next",
                    "left": ["Current state", "Known constraint"],
                    "right": ["Future state", "Open decision"],
                    "notes": "Columns note.",
                },
                {
                    "layout": "kpis",
                    "title": "Measure what matters",
                    "rows": [
                        ["Qualified coverage", "Provisional", "Calibrate after baseline."],
                        ["Participation actions", "Provisional", "Separate clicks from completions."],
                        ["Framing share", "Provisional", "Use a fixed codebook."],
                        ["Prompted awareness", "Provisional", "Survey subject to funding."],
                    ],
                    "body": "No numeric target is established before baseline.",
                    "notes": "KPI note.",
                },
                {
                    "layout": "budget",
                    "title": "Budget status",
                    "rows": [
                        ["Workstream", "Estimate", "Status"],
                        ["Policy explainer", "USD 4,000", "Quoted"],
                        ["Participation guide", "USD 3,000", "Quoted"],
                        ["Media readiness", "USD 3,000", "Quoted"],
                        ["Priced subtotal", "USD 10,000", "Complete"],
                    ],
                    "body": "A complete illustration, not a real quote.",
                    "notes": "Budget note.",
                },
                {
                    "layout": "quote",
                    "title": "The organizing idea",
                    "quote": "Make the work visible, then make the invitation verifiable.",
                    "attribution": "Campaign strategy",
                    "notes": "Quote note.",
                },
                {
                    "layout": "diagram",
                    "title": "A clear sequence",
                    "diagram": {
                        "kind": "flow",
                        "nodes": [
                            {"id": "a", "label": "Theme", "detail": "Published priorities"},
                            {"id": "b", "label": "Proof", "detail": "Documented work"},
                            {"id": "c", "label": "Route", "detail": "Verified invitation"},
                            {"id": "d", "label": "Action", "detail": "Measured response"},
                        ],
                        "edges": [
                            {"source": "a", "target": "b", "label": "ground"},
                            {"source": "b", "target": "c", "label": "invite"},
                            {"source": "c", "target": "d", "label": "track"},
                        ],
                    },
                    "notes": "Flow note.",
                },
                {
                    "layout": "timeline",
                    "title": "The calendar sets the pace",
                    "diagram": {
                        "kind": "timeline",
                        "nodes": [
                            {"id": "a", "label": "Research", "date": "October", "detail": "Baseline."},
                            {"id": "b", "label": "Build", "date": "November", "detail": "Publish."},
                            {"id": "c", "label": "Event", "date": "18–19 Nov", "detail": "Leaders' Meeting."},
                            {"id": "d", "label": "Review", "date": "December", "detail": "Closeout."},
                        ],
                    },
                    "notes": "Timeline note.",
                },
                {
                    "layout": "chart",
                    "title": "A weekly calibration view",
                    "chart": {
                        "kind": "bar",
                        "categories": ["Week 1", "Week 2", "Week 3"],
                        "series": [{"label": "Coverage", "values": [4, 7, 9]}],
                        "unit": "items",
                        "axis_label": "Deduplicated items",
                    },
                    "notes": "Chart note.",
                },
                {
                    "layout": "photo",
                    "title": "A supplied visual",
                    "body": "Image rights are explicit.",
                    "image": {
                        "path": "image.png",
                        "alt_text": "A solid coral test image",
                        "caption": "Test image.",
                        "rights_status": "supplied",
                        "usage": "Test only.",
                        "placement": "right",
                    },
                    "notes": "Photo note.",
                },
                {
                    "layout": "table",
                    "title": "A source table",
                    "table": {
                        "columns": ["Item", "Status", "Date"],
                        "rows": [["Theme", "Published", "2025"], ["Vote", "Closed", "30 Oct"]],
                        "align": ["left", "center", "right"],
                        "highlight_rows": [1],
                        "source_note": "APEC, 2025-2026.",
                    },
                    "source_note": "APEC, 2025-2026.",
                    "notes": "Table note.",
                },
                {
                    "layout": "stats",
                    "title": "Three numbers",
                    "stats": [
                        {"value": "21", "label": "Member economies", "detail": "Working geography.", "source_note": "APEC."},
                        {"value": "17-19", "label": "Leaders' Week", "detail": "November 2026.", "source_note": "Xinhua."},
                        {"value": "5", "label": "Workstreams", "detail": "One sequence.", "source_note": "Plan."},
                    ],
                    "source_note": "Official sources.",
                    "notes": "Stats note.",
                },
                {
                    "layout": "gallery",
                    "title": "Two supplied images",
                    "images": [
                        {
                            "path": "image.png",
                            "alt_text": "A solid coral test image",
                            "caption": "First image.",
                            "rights_status": "supplied",
                            "usage": "Test only.",
                        },
                        {
                            "path": "image.png",
                            "alt_text": "A second solid coral test image",
                            "caption": "Second image.",
                            "rights_status": "supplied",
                            "usage": "Test only.",
                        },
                    ],
                    "source_note": "Test assets.",
                    "notes": "Gallery note.",
                },
                {
                    "layout": "comparison",
                    "title": "Open versus closed",
                    "left_title": "Closed",
                    "right_title": "Open",
                    "left": ["The photo vote ended 30 October.", "Submissions closed in September."],
                    "right": ["Verified participation routes.", "Current media guidance only."],
                    "source_note": "APEC contest rules.",
                    "notes": "Comparison note.",
                },
                {
                    "layout": "map",
                    "title": "The working geography",
                    "rows": [["China", "Host"], ["Japan", "Member"], ["Peru", "Member"], ["Australia", "Member"]],
                    "bullets": ["Host economy", "Member economy"],
                    "source_note": "APEC members.",
                    "notes": "Map note.",
                },
                {
                    "layout": "chart",
                    "title": "A donut view",
                    "chart": {
                        "kind": "donut",
                        "categories": ["Editorial", "Media", "Monitoring"],
                        "series": [{"label": "Base budget", "values": [9, 14, 9]}],
                        "unit": "USD 000",
                    },
                    "source_note": "Planning assumptions.",
                    "notes": "Donut note.",
                },
                {
                    "layout": "next_steps",
                    "title": "Decisions that unlock delivery",
                    "bullets": ["Confirm scope", "Approve budget", "Set the baseline"],
                    "notes": "Next steps note.",
                },
                {
                    "layout": "references",
                    "title": "Sources",
                    "bullets": ["APEC. (2025). A source.", "APEC. (2026). Another source."],
                    "cite_ids": ["E1"],
                    "notes": "Reference note.",
                },
            ],
        }
    )


def test_html_is_self_contained_and_escapes_untrusted_copy():
    deck = Deck.model_validate(
        {
            "campaign_id": "cmp-20261108-abcdef12",
            "slides": [
                {
                    "layout": "title",
                    "title": 'A <script>alert("x")</script> deck',
                    "subtitle": "<b>not markup</b>",
                    "notes": "Note <script>bad()</script>",
                }
            ],
        }
    )
    document = build_html(deck, brand="Acme").decode("utf-8")
    assert document.startswith("<!doctype html>")
    assert "COO AI" not in document
    assert "speaker-notes" not in document
    assert "Note &lt;script&gt;bad()" not in document
    assert '<span class="footer-note">Generated from slides.json</span>' not in document
    assert "1920px" in document and "1080px" in document
    assert "<script>alert" not in document
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in document
    assert "&lt;b&gt;not markup&lt;/b&gt;" in document
    assert "<script src=" not in document.lower()
    assert "<link " not in document.lower()
    assert "@import" not in document.lower()
    assert "http://" not in document.lower()
    assert "https://" not in document.lower()


def test_palette_and_dark_tone_reach_the_html():
    deck = Deck.model_validate(
        {
            "campaign_id": "cmp-20261108-abcdef12",
            "palette": {"navy": "123456", "accent": "ABCDEF"},
            "slides": [
                {"layout": "title", "title": "Cover"},
                {"layout": "section", "title": "A dark divider", "body": "Argument"},
                {"layout": "bullets", "title": "Light content", "bullets": ["One"]},
            ],
        }
    )
    document = build_html(deck).decode("utf-8")
    assert "--navy:#123456" in document
    assert "--accent:#ABCDEF" in document
    assert "tone-dark" in document
    assert "tone-light" in document


def test_design_style_and_accent_mode_are_applied():
    deck = Deck.model_validate(
        {
            "campaign_id": "cmp-20261108-abcdef12",
            "design": {"style": "brief", "accent_mode": "mono"},
            "slides": [{"layout": "title", "title": "Brief style"}],
        }
    )
    document = build_html(deck).decode("utf-8")
    assert 'class="style-brief accent-mono"' in document
    assert "body.style-brief" in document
    assert "body.accent-mono" in document


def test_composition_variants_have_real_layout_rules():
    deck = Deck.model_validate(
        {
            "campaign_id": "cmp-20261108-abcdef12",
            "slides": [{"layout": "bullets", "title": "Variant probe", "bullets": ["One"]}],
        }
    )
    document = build_html(deck).decode("utf-8")
    for selector in (
        ".variant-split .ledger-list",
        ".variant-rail .ledger-list",
        ".variant-offset .two-col",
        ".variant-rail .stat-grid",
        ".variant-rail .kpi-grid",
        ".variant-rail .timeline",
        ".variant-dense .data-table",
        ".variant-mosaic .gallery",
        ".variant-offset .comparison",
        ".variant-ledger .reference-list",
        ".layout-section.variant-editorial .section-grid",
        ".layout-title.variant-split .title-main",
    ):
        assert selector in document


def test_every_layout_renders_native_markup(tmp_path):
    deck = _all_layout_deck(tmp_path)
    document = build_html(
        deck,
        citations={"E1": "APEC, 2025"},
        assets_root=tmp_path,
        brand="Acme",
    ).decode("utf-8")
    assert "Draft for client review" in document
    assert '<span class="footer-note">Generated from slides.json</span>' not in document
    assert "speaker-notes" not in document
    assert "Cover note." not in document
    for layout in (
        "title",
        "section",
        "bullets",
        "two_column",
        "kpis",
        "budget",
        "quote",
        "diagram",
        "timeline",
        "chart",
        "photo",
        "table",
        "stats",
        "gallery",
        "comparison",
        "map",
        "next_steps",
        "references",
    ):
        assert f"layout-{layout}" in document
    assert 'class="flow"' in document
    assert 'class="timeline count-4"' in document
    assert '<svg class="chart"' in document
    assert 'class="data-table"' in document
    assert 'class="stat-grid count-3"' in document
    assert 'class="gallery count-2"' in document
    assert 'class="comparison"' in document
    assert 'class="map-grid count-4"' in document
    assert "data:image/png;base64," in document
    assert "Sources: APEC, 2025" in document
    assert "A solid coral test image" in document
    assert "Provisional" in document
    assert "No numeric target is established before baseline." in document
    assert document.count('<section class="slide') == len(deck.slides)
    assert "const x = (wrap.clientWidth - 1920 * scale) / 2" in document
    assert "transform-origin:top left" in document


def test_briefing_board_renders_pinned_evidence_and_wide_grids(tmp_path):
    _write_image(tmp_path)
    print_a = {
        "path": "image.png",
        "alt_text": "A solid coral test image",
        "caption": "Pinned print A. Photo: Tester / CC0.",
        "rights_status": "supplied",
        "usage": "Test only.",
        "creator": "Tester",
        "license": "CC0",
    }
    print_b = {
        "path": "image.png",
        "alt_text": "A solid coral test image",
        "caption": "Pinned print B.",
        "rights_status": "supplied",
        "usage": "Test only.",
        "creator": "Tester",
        "license": "CC0",
    }
    deck = Deck.model_validate(
        {
            "campaign_id": "cmp-20261108-abcdef12",
            "design": {"style": "briefing", "visual_ratio": 0.7},
            "slides": [
                {
                    "layout": "board",
                    "title": "The wall in one view",
                    "body": "One argument, four prints.",
                    "images": [print_a, print_b],
                    "bullets": ["21 economies", "One verified route"],
                    "stamp": "BRIEFED",
                },
                {
                    "layout": "kpis",
                    "title": "Five indicators",
                    "rows": [["Coverage", "Provisional", "Approved outlets."], ["Actions", "Provisional", "Tagged clicks."]],
                },
                {
                    "layout": "evidence",
                    "title": "The arrival gate",
                    "image": print_b,
                    "bullets": ["Main gateway.", "Photograph is context, not endorsement."],
                    "stamp": "ARRIVAL",
                },
                {
                    "layout": "diagram",
                    "title": "Four audiences",
                    "diagram": {
                        "kind": "hub",
                        "nodes": [
                            {"id": "welcome", "label": "One welcome"},
                            {"id": "media", "label": "Media"},
                            {"id": "business", "label": "Business"},
                        ],
                    },
                },
            ],
        }
    )
    document = build_html(deck, assets_root=tmp_path).decode("utf-8")
    assert 'body class="style-briefing accent-contrast"' in document
    assert "layout-board" in document and "variant-wall" in document
    assert 'class="board-wall"' in document
    assert 'class="board-stamp' in document and "BRIEFED" in document
    assert "Pinned print A. Photo: Tester / CC0. · Tester" not in document
    assert "Pinned print B. · Tester / CC0" in document
    assert "layout-evidence" in document and "variant-annotated" in document
    assert 'class="leader-layer"' in document
    assert document.count('class="callout"') == 2
    # Briefing decks keep the wide grid instead of the half-empty rail.
    assert "layout-kpis" in document and "variant-grid" in document
    assert 'class="hub-spoke"' in document
    assert 'class="hub-node is-hub"' in document


def test_html_export_reads_slides_json_without_a_proposal(store):
    meta = store.create("Launch a test campaign.", stub=True)
    meta.quality_profile = "legacy"
    store.save_meta(meta)
    plan = valid_plan(meta.id)
    measurement = valid_measurement(meta.id)
    evidence = valid_evidence(meta.id)
    write_json(store, meta.id, "brief.json", valid_brief(meta.id))
    write_json(store, meta.id, "plan.json", plan)
    write_json(store, meta.id, "measurement.json", measurement)
    write_json(store, meta.id, "evidence.json", evidence)
    write_json(store, meta.id, "slides.json", valid_deck(meta.id, plan, measurement, evidence))

    outputs = export_campaign(store, meta.id, formats=("html",))
    assert set(outputs) == {"html"}
    document = store.read_bytes(meta.id, "proposal.html").decode("utf-8")
    assert document.startswith("<!doctype html>")
    assert "Finish the job" in document
    assert "Acme" in document
    assert not store.has_artifact(meta.id, "proposal.md")


def test_html_export_requires_slides_json(store):
    meta = store.create("Launch a test campaign.", stub=True)
    meta.quality_profile = "legacy"
    store.save_meta(meta)
    with pytest.raises(FileNotFoundError, match="slides.json"):
        export_campaign(store, meta.id, formats=("html",))


def test_export_all_core_formats_includes_html_and_pptx(store):
    meta = store.create("Launch a test campaign.", stub=True)
    meta.quality_profile = "legacy"
    store.save_meta(meta)
    plan = valid_plan(meta.id)
    measurement = valid_measurement(meta.id)
    evidence = valid_evidence(meta.id)
    write_json(store, meta.id, "brief.json", valid_brief(meta.id))
    write_json(store, meta.id, "plan.json", plan)
    write_json(store, meta.id, "measurement.json", measurement)
    write_json(store, meta.id, "evidence.json", evidence)
    write_json(store, meta.id, "slides.json", valid_deck(meta.id, plan, measurement, evidence))
    store.write_artifact(meta.id, "proposal.md", valid_proposal(plan, measurement, evidence=evidence))

    outputs = export_campaign(store, meta.id, formats=("docx", "pdf", "html", "pptx"))
    assert set(outputs) == {"docx", "pdf", "html", "pptx"}
    assert store.read_bytes(meta.id, "proposal.html").startswith(b"<!doctype html>")
    assert store.read_bytes(meta.id, "proposal.pptx").startswith(b"PK")


@pytest.mark.skipif(not deck_pdf_available(), reason="deck PDF needs PowerPoint, Chrome, Chromium, or Edge")
def test_export_deck_pdf(store):
    meta = store.create("Launch a test campaign.", stub=True)
    meta.quality_profile = "legacy"
    store.save_meta(meta)
    plan = valid_plan(meta.id)
    measurement = valid_measurement(meta.id)
    evidence = valid_evidence(meta.id)
    write_json(store, meta.id, "brief.json", valid_brief(meta.id))
    write_json(store, meta.id, "plan.json", plan)
    write_json(store, meta.id, "measurement.json", measurement)
    write_json(store, meta.id, "evidence.json", evidence)
    write_json(store, meta.id, "slides.json", valid_deck(meta.id, plan, measurement, evidence))

    outputs = export_campaign(store, meta.id, formats=("deck-pdf",))
    assert set(outputs) == {"deck-pdf"}
    assert store.read_bytes(meta.id, "proposal-deck.pdf").startswith(b"%PDF")
    assert store.has_artifact(meta.id, "proposal.html")

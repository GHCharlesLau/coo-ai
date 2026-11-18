from __future__ import annotations

import io
import zipfile

from pypdf import PdfReader

from coo.export import export_campaign
from coo.export.markdown import parse_proposal
from tests.factories import (
    valid_brief,
    valid_deck,
    valid_evidence,
    valid_measurement,
    valid_plan,
    valid_proposal,
    write_json,
)


def _seed(store):
    meta = store.create("Launch Acme widgets to urban professionals.", stub=True)
    meta.quality_profile = "legacy"
    store.save_meta(meta)
    plan = valid_plan(meta.id)
    measurement = valid_measurement(meta.id)
    evidence = valid_evidence(meta.id)
    write_json(store, meta.id, "brief.json", valid_brief(meta.id))
    write_json(store, meta.id, "plan.json", plan)
    write_json(store, meta.id, "measurement.json", measurement)
    write_json(store, meta.id, "evidence.json", evidence)
    store.write_artifact(meta.id, "proposal.md", valid_proposal(plan, measurement, evidence=evidence))
    return meta


def _pdf_text(store, meta) -> list[str]:
    reader = PdfReader(str(store.artifact_path(meta.id, "proposal.pdf")))
    return [page.extract_text() or "" for page in reader.pages]


def test_markdown_parser_reads_headings_lists_tables_and_links():
    proposal = parse_proposal(
        """# Campaign Proposal: Test

## 1. Executive Summary

A **bold** claim with a [source](https://example.com/a).

- First point
- Second point

| Line | Amount |
| --- | --- |
| Media | 100 |
"""
    )
    assert proposal.title == "Test"
    kinds = [block.kind for block in proposal.blocks]
    assert kinds == ["heading", "paragraph", "bullets", "table"]
    assert proposal.blocks[2].items == ["First point", "Second point"]
    assert proposal.blocks[3].rows[0] == ["Line", "Amount"]


def test_markdown_parser_keeps_reference_entries_separate():
    proposal = parse_proposal(
        """# Campaign Proposal: Test

## References

APEC. (2025). First source. https://example.com/a
Xinhua. (2026). Second source. https://example.com/b
"""
    )
    references = [block.text for block in proposal.blocks if block.kind == "paragraph"]
    assert references == [
        "APEC. (2025). First source. https://example.com/a",
        "Xinhua. (2026). Second source. https://example.com/b",
    ]


def test_export_writes_docx_with_cover_toc_and_page_fields(store):
    meta = _seed(store)
    outputs = export_campaign(store, meta.id, formats=("docx",))
    assert set(outputs) == {"docx"}
    data = store.read_bytes(meta.id, "proposal.docx")
    assert data.startswith(b"PK")

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
        settings_xml = archive.read("word/settings.xml").decode("utf-8")
        footers = [
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.startswith("word/footer") and name.endswith(".xml")
        ]
    assert "Finish the job" in document_xml
    assert "Contents" in document_xml
    assert "1. Executive Summary" in document_xml
    assert "TOC" in document_xml
    assert "updateFields" in settings_xml
    assert footers
    assert any("PAGE" in footer for footer in footers)
    assert any("NUMPAGES" in footer for footer in footers)


def test_export_writes_paginated_pdf_with_cover_and_toc(store):
    meta = _seed(store)
    outputs = export_campaign(store, meta.id, formats=("pdf",))
    assert set(outputs) == {"pdf"}
    data = store.read_bytes(meta.id, "proposal.pdf")
    assert data.startswith(b"%PDF")

    pages = _pdf_text(store, meta)
    assert len(pages) >= 3
    assert "Finish the job" in pages[0]
    assert "Acme" in pages[0]
    assert "Contents" in pages[1]
    assert "1. Executive Summary" in pages[1]
    assert "1. Executive Summary" in pages[2]
    assert "Page 3" in pages[2]


def test_export_both_formats_by_default(store):
    meta = _seed(store)
    outputs = export_campaign(store, meta.id)
    assert set(outputs) == {"docx", "pdf"}
    assert store.has_artifact(meta.id, "proposal.docx")
    assert store.has_artifact(meta.id, "proposal.pdf")


def test_docx_uses_the_campaign_deck_palette(store):
    meta = _seed(store)
    plan = valid_plan(meta.id)
    measurement = valid_measurement(meta.id)
    evidence = valid_evidence(meta.id)
    deck = valid_deck(meta.id, plan, measurement, evidence)
    deck["palette"] = {"navy": "123456", "accent": "ABCDEF", "muted": "778899"}
    write_json(store, meta.id, "slides.json", deck)

    export_campaign(store, meta.id, formats=("docx",))
    with zipfile.ZipFile(io.BytesIO(store.read_bytes(meta.id, "proposal.docx"))) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "123456" in document_xml
    assert "ABCDEF" in document_xml

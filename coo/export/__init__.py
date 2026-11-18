"""Client-deliverable exports for a completed proposal."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from pydantic import ValidationError

from coo.export.docx import build_docx
from coo.export.markdown import parse_proposal
from coo.export.pdf import build_pdf
from coo.export.deck_pdf import render_deck_pdf
from coo.schemas.brief import Brief
from coo.schemas.evidence import EvidenceLog
from coo.schemas.slides import Deck
from coo.slides.pptx import render_pptx_bytes
from coo.slides.web import build_html
from coo.store import CampaignStore

EXPORT_FORMATS = ("docx", "pdf", "html", "pptx", "deck-pdf")
DEFAULT_EXPORT_FORMATS = ("docx", "pdf")
_FILENAMES = {
    "docx": "proposal.docx",
    "pdf": "proposal.pdf",
    "html": "proposal.html",
    "pptx": "proposal.pptx",
    "deck-pdf": "proposal-deck.pdf",
}


def export_campaign(
    store: CampaignStore,
    campaign_id: str,
    *,
    formats: tuple[str, ...] = DEFAULT_EXPORT_FORMATS,
) -> dict[str, Path]:
    """Render proposal.md and/or slides.json to the requested deliverables."""
    unknown = [fmt for fmt in formats if fmt not in _FILENAMES]
    if unknown:
        raise ValueError(f"Unsupported export format(s): {', '.join(unknown)}")
    needs_proposal = any(fmt in {"docx", "pdf"} for fmt in formats)
    needs_deck = any(fmt in {"html", "pptx", "deck-pdf"} for fmt in formats)
    if needs_proposal and not store.has_artifact(campaign_id, "proposal.md"):
        raise FileNotFoundError(
            f"Campaign {campaign_id} has no proposal.md; finish the deliver (or legacy write) stage before exporting"
        )
    if needs_deck and not store.has_artifact(campaign_id, "slides.json"):
        raise FileNotFoundError(
            f"Campaign {campaign_id} has no slides.json; finish the deliver (or legacy slides) stage before exporting deck formats"
        )

    brand = _brand(store, campaign_id)
    palette = _deck_palette(store, campaign_id)
    prepared_on = _prepared_on(store.load_meta(campaign_id).created_at)
    proposal = parse_proposal(store.read_artifact(campaign_id, "proposal.md")) if needs_proposal else None
    deck = Deck.model_validate_json(store.read_artifact(campaign_id, "slides.json")) if needs_deck else None
    citations = _citations(store, campaign_id) if needs_deck else {}

    outputs: dict[str, Path] = {}
    html_path: Path | None = None
    if needs_deck and deck is not None:
        html_path = store.write_bytes(
            campaign_id,
            _FILENAMES["html"],
            build_html(
                deck,
                citations=citations,
                assets_root=store.artifacts_dir(campaign_id),
                brand=brand,
            ),
        )
    for fmt in formats:
        if fmt == "docx":
            payload = build_docx(proposal, brand=brand, prepared_on=prepared_on, palette=palette)
            outputs[fmt] = store.write_bytes(campaign_id, _FILENAMES[fmt], payload)
        elif fmt == "pdf":
            payload = build_pdf(proposal, brand=brand, prepared_on=prepared_on, palette=palette)
            outputs[fmt] = store.write_bytes(campaign_id, _FILENAMES[fmt], payload)
        elif fmt == "html":
            assert html_path is not None
            outputs[fmt] = html_path
        elif fmt == "pptx":
            assert html_path is not None
            payload = render_pptx_bytes(
                deck,
                assets_root=store.artifacts_dir(campaign_id),
                citations=citations,
                brand=brand,
                html_path=html_path,
            )
            outputs[fmt] = store.write_bytes(campaign_id, _FILENAMES[fmt], payload)
        else:
            assert html_path is not None
            pdf_path = store.artifact_path(campaign_id, _FILENAMES[fmt])
            render_deck_pdf(html_path, pdf_path, expected_pages=len(deck.slides))
            outputs[fmt] = pdf_path
    return outputs


def _citations(store: CampaignStore, campaign_id: str) -> dict[str, str]:
    if not store.has_artifact(campaign_id, "evidence.json"):
        return {}
    try:
        evidence = EvidenceLog.model_validate_json(store.read_artifact(campaign_id, "evidence.json"))
    except ValidationError:
        return {}
    labels: dict[str, str] = {}
    for item in evidence.items:
        author = item.author or item.source or "Source"
        labels[item.id] = f"{author}, {item.year}" if item.year and item.year != "n.d." else author
    return labels


def _brand(store: CampaignStore, campaign_id: str) -> str:
    if not store.has_artifact(campaign_id, "brief.json"):
        return ""
    try:
        return Brief.model_validate_json(store.read_artifact(campaign_id, "brief.json")).brand
    except ValidationError:
        return ""


def _deck_palette(store: CampaignStore, campaign_id: str) -> dict[str, str]:
    if not store.has_artifact(campaign_id, "slides.json"):
        return {}
    try:
        return Deck.model_validate_json(store.read_artifact(campaign_id, "slides.json")).palette
    except ValidationError:
        return {}


def _prepared_on(created_at: str) -> str:
    try:
        day = datetime.fromisoformat(created_at).date()
    except ValueError:
        day = date.today()
    return day.strftime("%d %B %Y").lstrip("0")

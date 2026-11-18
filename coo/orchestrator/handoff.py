"""Merge public facts discovered in research into the brief without reopening intake."""

from __future__ import annotations

import json
import re

from coo.store import CampaignStore

MARKER = "<!-- coo:research_facts -->"


def _section(markdown: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\b\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(markdown)
    if not match:
        return ""
    start = match.end()
    nxt = re.search(r"^##\s+", markdown[start:], re.MULTILINE)
    end = start + nxt.start() if nxt else len(markdown)
    return re.sub(r"\s+", " ", markdown[start:end]).strip()


def merge_research_facts(store: CampaignStore, campaign_id: str) -> None:
    if not store.has_artifact(campaign_id, "brief.json") or not store.has_artifact(
        campaign_id, "situation.md"
    ):
        return
    brief = json.loads(store.read_artifact(campaign_id, "brief.json"))
    notes = brief.get("notes") or ""
    if MARKER in notes:
        return
    situation = store.read_artifact(campaign_id, "situation.md")
    extracted: list[str] = []
    for heading in ("Host", "Geography", "Market", "Calendar", "Timing"):
        block = _section(situation, heading)
        if block:
            extracted.append(f"{heading}: {block[:400]}")
    if not extracted:
        return
    addition = MARKER + "\n" + "\n".join(extracted)
    brief["notes"] = (notes.rstrip() + "\n\n" + addition).strip()
    store.write_artifact(campaign_id, "brief.json", json.dumps(brief, indent=2, ensure_ascii=False))

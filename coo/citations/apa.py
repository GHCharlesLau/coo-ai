"""Deterministic APA 7 in-text cites and reference list from evidence.json."""

from __future__ import annotations

import json
import re

from coo.schemas.evidence import EvidenceItem, EvidenceLog
from coo.store import CampaignStore

CITE_MARKER = re.compile(r"<!--\s*cite:(?P<id>[^\s]+)\s*-->")
PAREN = re.compile(r"\(([^)]+)\)")
PAIR = re.compile(r"([^;()]+?),\s*((?:n\.d\.|\d{4}))")
URL_RE = re.compile(r"https?://[^\s\]\)<>\"']+")
REFERENCES_SPLIT = re.compile(r"\n## References\s*\n", re.IGNORECASE)


def in_text_author(author: str) -> str:
    author = author.strip()
    if "," in author:
        return author.split(",", 1)[0].strip()
    return author


def in_text(item: EvidenceItem) -> str:
    author = in_text_author(item.author or "Unknown")
    year = (item.year or "n.d.").strip()
    return f"({author}, {year})"


def reference(item: EvidenceItem) -> str:
    author = (item.author or "Unknown").rstrip(".")
    year = (item.year or "n.d.").strip()
    title = (item.title or item.claim).rstrip(".")
    container = (item.container or "").rstrip(".")
    url = (item.source_url or "").strip()
    parts = [f"{author}. ({year}). {title}."]
    if container:
        parts.append(f"{container}.")
    source_reference = (item.source_reference or "").strip()
    if source_reference:
        parts.append(source_reference)
    if url:
        parts.append(url)
    return " ".join(parts)


def sourced_items(log: EvidenceLog) -> list[EvidenceItem]:
    return [item for item in log.items if not item.is_assumption]


def bibliography(log: EvidenceLog) -> str:
    lines = [reference(item) for item in sourced_items(log)]
    return "\n".join(lines)


def assemble_proposal(text: str, evidence: EvidenceLog) -> str:
    by_id = {item.id: item for item in evidence.items}

    def repl(match: re.Match[str]) -> str:
        item = by_id.get(match.group("id"))
        if item is None or item.is_assumption:
            return match.group(0)
        return in_text(item)

    expanded = CITE_MARKER.sub(repl, text)
    body = REFERENCES_SPLIT.split(expanded, maxsplit=1)[0].rstrip()
    refs = bibliography(evidence)
    if not refs:
        return body + "\n\n## References\n\n"
    return body + "\n\n## References\n\n" + refs + "\n"


def assemble_proposal_file(store: CampaignStore, campaign_id: str) -> None:
    text = store.read_artifact(campaign_id, "proposal.md")
    raw = json.loads(store.read_artifact(campaign_id, "evidence.json"))
    evidence = EvidenceLog.model_validate(raw)
    store.write_artifact(campaign_id, "proposal.md", assemble_proposal(text, evidence))


def extract_in_text_pairs(text: str) -> list[tuple[str, str]]:
    body = REFERENCES_SPLIT.split(text, maxsplit=1)[0]
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    pairs: list[tuple[str, str]] = []
    for paren in PAREN.findall(body):
        for match in PAIR.finditer(paren):
            pairs.append((match.group(1).strip(), match.group(2).strip()))
    return pairs


def extract_reference_urls(text: str) -> list[str]:
    parts = REFERENCES_SPLIT.split(text, maxsplit=1)
    if len(parts) < 2:
        return []
    return URL_RE.findall(parts[1])


def authors_match(left: str, right: str) -> bool:
    return in_text_author(left).casefold() == in_text_author(right).casefold()

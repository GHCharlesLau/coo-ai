"""Small, deterministic Markdown reader for client proposal exports.

The write stage produces a constrained Markdown dialect: one document title,
numbered section headings, paragraphs, bullet lists, simple tables, and links.
This parser intentionally ignores anything richer instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_TABLE_SPLIT_RE = re.compile(r"^\s*\|.*\|\s*$")
_RULE_RE = re.compile(r"^\s*(?:---+|\*\*\*+|___+)\s*$")
_TITLE_PREFIX_RE = re.compile(r"^\s*Campaign Proposal\s*[:\-–—]\s*", re.IGNORECASE)

# Order matters: bold, inline code, markdown link, bare URL, italic.
INLINE_TOKEN_RE = re.compile(
    r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|https?://[^\s]+|\*[^*]+\*)"
)


@dataclass
class Block:
    kind: str
    text: str = ""
    level: int = 0
    items: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


@dataclass
class Proposal:
    title: str
    blocks: list[Block]


def clean_title(title: str) -> str:
    return _TITLE_PREFIX_RE.sub("", title.strip()).strip()


def parse_proposal(text: str) -> Proposal:
    """Parse proposal.md into a title plus a flat list of renderable blocks."""
    text = _COMMENT_RE.sub("", text)
    lines = text.splitlines()
    blocks: list[Block] = []
    title = ""
    index = 0
    in_references = False
    while index < len(lines):
        raw = lines[index].rstrip()
        line = raw.strip()
        if not line:
            index += 1
            continue

        if line.startswith("# ") and not title:
            title = clean_title(line[2:])
            index += 1
            continue
        if line.startswith("### "):
            in_references = False
            blocks.append(Block("heading", line[4:].strip(), level=2))
            index += 1
            continue
        if line.startswith("## "):
            in_references = line[3:].strip().casefold() == "references"
            blocks.append(Block("heading", line[3:].strip(), level=1))
            index += 1
            continue
        if line.startswith("# "):
            in_references = False
            blocks.append(Block("heading", line[2:].strip(), level=1))
            index += 1
            continue
        if _RULE_RE.match(line):
            blocks.append(Block("rule"))
            index += 1
            continue
        if in_references:
            # One reference per source line: APA entries must not merge.
            blocks.append(Block("paragraph", line))
            index += 1
            continue

        if _TABLE_SPLIT_RE.match(raw):
            rows: list[list[str]] = []
            while index < len(lines) and _TABLE_SPLIT_RE.match(lines[index]):
                cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells if cell):
                    rows.append(cells)
                index += 1
            if rows:
                blocks.append(Block("table", rows=rows))
            continue

        bullet = _BULLET_RE.match(raw)
        if bullet:
            items: list[str] = []
            while index < len(lines):
                match = _BULLET_RE.match(lines[index])
                if not match:
                    break
                items.append(match.group(1).strip())
                index += 1
            blocks.append(Block("bullets", items=items))
            continue

        numbered = _NUMBERED_RE.match(raw)
        if numbered:
            items = []
            while index < len(lines):
                match = _NUMBERED_RE.match(lines[index])
                if not match:
                    break
                items.append(match.group(1).strip())
                index += 1
            blocks.append(Block("numbered", items=items))
            continue

        if line.startswith(">"):
            quote: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip().lstrip(">").strip())
                index += 1
            blocks.append(Block("quote", " ".join(part for part in quote if part)))
            continue

        paragraph = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not _starts_block(lines[index]):
            paragraph.append(lines[index].strip())
            index += 1
        blocks.append(Block("paragraph", " ".join(paragraph)))

    if not title:
        title = "Campaign Proposal"
    return Proposal(title=title, blocks=blocks)


def _starts_block(line: str) -> bool:
    stripped = line.strip()
    return bool(
        stripped.startswith("#")
        or _BULLET_RE.match(line)
        or _NUMBERED_RE.match(line)
        or _TABLE_SPLIT_RE.match(line)
        or stripped.startswith(">")
        or _RULE_RE.match(line)
    )

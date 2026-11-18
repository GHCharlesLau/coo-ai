"""Filesystem campaign store. Disk is memory; chat history is not."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from coo.paths import default_store_dir
from coo.schemas.campaign import STAGE_NAMES, CampaignMeta, StageState, initial_stage_states

ARTIFACT_DIR = "artifacts"
TRACES_DIR = "traces"
NOTES_DIR = "notes"
PROMPTS_DIR = "prompts"
META_FILE = "campaign.json"
DEMAND_FILE = "demand.txt"
TRACE_FILE = "events.ndjson"
USER_NOTES = "user.md"

_SAFE_ID = re.compile(r"^cmp-[0-9]{8}-[a-f0-9]{8}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_campaign_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"cmp-{day}-{uuid.uuid4().hex[:8]}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CampaignStore:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root else default_store_dir()
        self.root.mkdir(parents=True, exist_ok=True)

    def campaign_dir(self, campaign_id: str) -> Path:
        if not _SAFE_ID.match(campaign_id):
            raise ValueError(f"Invalid campaign id: {campaign_id}")
        return self.root / campaign_id

    def artifacts_dir(self, campaign_id: str) -> Path:
        return self.campaign_dir(campaign_id) / ARTIFACT_DIR

    def create(
        self,
        demand: str = "",
        *,
        stub: bool = False,
        model: str | None = None,
        revision_of: str | None = None,
        pipeline_version: str = "lean",
    ) -> CampaignMeta:
        if revision_of:
            parent = self.load_meta(revision_of)
            if not demand.strip():
                demand = self.demand(parent.id)
        demand = demand.strip()
        if not demand:
            raise ValueError("Demand text is empty.")
        campaign_id = new_campaign_id()
        now = utc_now()
        path = self.campaign_dir(campaign_id)
        path.mkdir(parents=False)
        (path / ARTIFACT_DIR).mkdir()
        (path / TRACES_DIR).mkdir()
        (path / NOTES_DIR).mkdir()
        (path / PROMPTS_DIR).mkdir()
        (path / DEMAND_FILE).write_text(demand + "\n", encoding="utf-8")
        (path / NOTES_DIR / USER_NOTES).write_text("", encoding="utf-8")
        (path / TRACES_DIR / TRACE_FILE).write_text("", encoding="utf-8")
        meta = CampaignMeta(
            id=campaign_id,
            revision_of=revision_of,
            quality_profile="evidence_v2",
            requirements_version=3,
            pipeline_version=pipeline_version,
            created_at=now,
            updated_at=now,
            status="ready",
            current_stage=STAGE_NAMES[0],
            stages=initial_stage_states(legacy=pipeline_version == "legacy"),
            model=model,
            stub=stub,
        )
        self.save_meta(meta)
        return meta

    def exists(self, campaign_id: str) -> bool:
        return self.campaign_dir(campaign_id).is_dir()

    def load_meta(self, campaign_id: str) -> CampaignMeta:
        path = self.campaign_dir(campaign_id) / META_FILE
        if not path.is_file():
            raise FileNotFoundError(f"Campaign not found: {campaign_id}")
        return CampaignMeta.model_validate_json(path.read_text(encoding="utf-8"))

    def save_meta(self, meta: CampaignMeta) -> None:
        meta.updated_at = utc_now()
        path = self.campaign_dir(meta.id) / META_FILE
        path.write_text(meta.model_dump_json(indent=2) + "\n", encoding="utf-8")

    def demand(self, campaign_id: str) -> str:
        return (self.campaign_dir(campaign_id) / DEMAND_FILE).read_text(encoding="utf-8").strip()

    def user_notes(self, campaign_id: str) -> str:
        path = self.campaign_dir(campaign_id) / NOTES_DIR / USER_NOTES
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def append_user_notes(self, campaign_id: str, text: str) -> None:
        path = self.campaign_dir(campaign_id) / NOTES_DIR / USER_NOTES
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        stamp = utc_now()
        path.write_text(existing + f"\n## {stamp}\n{text.strip()}\n", encoding="utf-8")

    def artifact_path(self, campaign_id: str, name: str) -> Path:
        if Path(name).name != name or ".." in name:
            raise ValueError(f"Illegal artifact name: {name}")
        return self.artifacts_dir(campaign_id) / name

    def asset_path(self, campaign_id: str, relative_path: str) -> Path:
        """Resolve a deck asset inside artifacts/ while rejecting traversal."""
        root = self.artifacts_dir(campaign_id).resolve()
        candidate = (root / relative_path).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("asset path must stay inside the campaign artifacts directory")
        return candidate

    def write_artifact(self, campaign_id: str, name: str, content: str) -> Path:
        path = self.artifact_path(campaign_id, name)
        path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
        return path

    def write_bytes(self, campaign_id: str, name: str, data: bytes) -> Path:
        path = self.artifact_path(campaign_id, name)
        path.write_bytes(data)
        return path

    def read_artifact(self, campaign_id: str, name: str) -> str:
        path = self.artifact_path(campaign_id, name)
        if not path.is_file():
            raise FileNotFoundError(f"Missing artifact {name} for {campaign_id}")
        return path.read_text(encoding="utf-8")

    def read_bytes(self, campaign_id: str, name: str) -> bytes:
        path = self.artifact_path(campaign_id, name)
        if not path.is_file():
            raise FileNotFoundError(f"Missing artifact {name} for {campaign_id}")
        return path.read_bytes()

    def has_artifact(self, campaign_id: str, name: str) -> bool:
        return self.artifact_path(campaign_id, name).is_file()

    def prompt_path(self, campaign_id: str, stage: str) -> Path:
        return self.campaign_dir(campaign_id) / PROMPTS_DIR / f"{stage}.md"

    def write_prompt(self, campaign_id: str, stage: str, content: str) -> Path:
        path = self.prompt_path(campaign_id, stage)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
        return path

    def read_prompt(self, campaign_id: str, stage: str) -> str:
        path = self.prompt_path(campaign_id, stage)
        if not path.is_file():
            raise FileNotFoundError(f"Missing prompt for stage {stage}")
        return path.read_text(encoding="utf-8")

    def artifact_hash(self, campaign_id: str, name: str) -> str:
        path = self.artifact_path(campaign_id, name)
        return sha256_bytes(path.read_bytes())

    def append_trace(self, campaign_id: str, event: dict) -> None:
        path = self.campaign_dir(campaign_id) / TRACES_DIR / TRACE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def list_campaigns(self) -> list[CampaignMeta]:
        metas: list[CampaignMeta] = []
        for child in sorted(self.root.iterdir()):
            if child.is_dir() and (child / META_FILE).is_file():
                metas.append(CampaignMeta.model_validate_json((child / META_FILE).read_text(encoding="utf-8")))
        return metas

    def stage(self, meta: CampaignMeta, name: str) -> StageState:
        if name not in meta.stages:
            raise KeyError(name)
        return meta.stages[name]

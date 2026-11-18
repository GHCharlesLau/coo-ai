"""Dump Pydantic models to JSON Schema files under schemas/."""

from __future__ import annotations

import json
from pathlib import Path

from coo.paths import project_root
from coo.schemas.brief import Brief
from coo.schemas.campaign import CampaignMeta
from coo.schemas.evidence import EvidenceLog
from coo.schemas.measurement import Measurement
from coo.schemas.operations import CampaignAssets, OperationsPlan
from coo.schemas.plan import Plan
from coo.schemas.review import Review
from coo.schemas.slides import Deck
from coo.schemas.strategy import Strategy

MODELS = {
    "brief": Brief,
    "strategy": Strategy,
    "plan": Plan,
    "measurement": Measurement,
    "operations": OperationsPlan,
    "campaign_assets": CampaignAssets,
    "evidence": EvidenceLog,
    "review": Review,
    "campaign": CampaignMeta,
    "slides": Deck,
}


def schemas_dir() -> Path:
    return project_root() / "schemas"


def dump_json_schemas(directory: Path | None = None) -> list[Path]:
    target = directory or schemas_dir()
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in MODELS.items():
        path = target / f"{name}.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    for path in dump_json_schemas():
        print(path)

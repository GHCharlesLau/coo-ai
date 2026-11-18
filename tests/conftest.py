from __future__ import annotations

import pytest

from coo.config import load_settings
from coo.llm import StubClient
from coo.store import CampaignStore


@pytest.fixture
def store(tmp_path) -> CampaignStore:
    return CampaignStore(tmp_path)


@pytest.fixture
def settings():
    return load_settings(stub=True)


@pytest.fixture
def stub_llm() -> StubClient:
    return StubClient()

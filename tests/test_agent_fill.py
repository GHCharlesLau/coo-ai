from __future__ import annotations

from coo.campaign_ops import format_status
from coo.config import load_settings
from coo.llm import AgentFillClient, build_client
from coo.orchestrator.runner import advance
from tests.factories import valid_brief, write_json


def test_agent_fill_pauses_then_gates_intake(store, monkeypatch):
    monkeypatch.delenv("COO_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("COO_LLM_STUB", raising=False)
    settings = load_settings(stub=False)
    assert settings.agent_fill
    llm = build_client(settings)
    assert isinstance(llm, AgentFillClient)

    meta = store.create("Propagate APEC 2026 to an international audience.", model="coding-agent")
    paused = advance(store, meta.id, llm, settings)
    assert paused.status == "awaiting_agent"
    assert store.load_meta(meta.id).pause_reason == "agent_fill:intake"
    prompt = store.prompt_path(meta.id, "intake")
    assert prompt.is_file()
    text = prompt.read_text(encoding="utf-8")
    assert "brief.json" in text
    assert "coo-intake" in text
    assert "Campaign workspace" in text
    assert str(store.artifacts_dir(meta.id)) in text
    assert not store.has_artifact(meta.id, "brief.json")

    write_json(
        store,
        meta.id,
        "brief.json",
        valid_brief(meta.id, title="APEC 2026 International Outreach", brand="APEC 2026"),
    )
    gated = advance(store, meta.id, llm, settings)
    assert gated.status == "awaiting_human"
    assert store.load_meta(meta.id).pause_reason == "checkpoint:intake"


def test_status_reports_the_exact_next_command(store, monkeypatch):
    monkeypatch.delenv("COO_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("COO_LLM_STUB", raising=False)
    settings = load_settings(stub=False)
    meta = store.create("Launch a campaign.", model="coding-agent")
    advance(store, meta.id, build_client(settings), settings)

    text = format_status(store.load_meta(meta.id), store)
    assert "Next:" in text
    assert "brief.json" in text
    assert f"resume {meta.id}" in text


def test_agent_fill_invalid_artifact_stays_paused(store, monkeypatch):
    monkeypatch.delenv("COO_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("COO_LLM_STUB", raising=False)
    settings = load_settings(stub=False)
    llm = build_client(settings)
    meta = store.create("Launch a campaign.", model="coding-agent")
    advance(store, meta.id, llm, settings)
    write_json(store, meta.id, "brief.json", {"campaign_id": meta.id, "title": "Nope"})
    again = advance(store, meta.id, llm, settings)
    assert again.status == "awaiting_agent"
    assert again.gate_errors
    prompt = store.read_prompt(meta.id, "intake")
    assert "Previous gate errors" in prompt

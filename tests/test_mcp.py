from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from coo.config import load_settings
from coo.llm import AgentFillClient, StubClient
from coo.mcp_server import LATEST_PROTOCOL, TOOLS, CooMCPServer
from coo.store import CampaignStore


@pytest.fixture
def server(tmp_path: Path) -> CooMCPServer:
    return CooMCPServer(CampaignStore(tmp_path), load_settings(stub=True), StubClient())


def call(server: CooMCPServer, name: str, arguments: dict) -> dict:
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response is not None
    return response["result"]


def test_initialize_and_list_tools(server: CooMCPServer):
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test"}},
        }
    )
    assert response is not None
    result = response["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["serverInfo"]["name"] == "coo-ai"
    assert result["capabilities"]["tools"]["listChanged"] is False
    assert "coo_artifact_write" in result["instructions"]

    listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listed is not None
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert names == {tool["name"] for tool in TOOLS}
    assert {"coo_new", "coo_status", "coo_resume", "coo_export"} <= names


def test_unknown_protocol_falls_back_to_latest(server: CooMCPServer):
    response = server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}}
    )
    assert response is not None
    assert response["result"]["protocolVersion"] == LATEST_PROTOCOL


def test_ping_and_notifications(server: CooMCPServer):
    assert server.handle({"jsonrpc": "2.0", "id": 3, "method": "ping"}) == {"jsonrpc": "2.0", "id": 3, "result": {}}
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/cancelled"}) is None


def test_unknown_method_is_an_rpc_error(server: CooMCPServer):
    response = server.handle({"jsonrpc": "2.0", "id": 4, "method": "resources/list"})
    assert response is not None
    assert response["error"]["code"] == -32601


def test_new_without_run_and_status(server: CooMCPServer):
    result = call(server, "coo_new", {"demand": "Launch a 12-week campaign for Acme.", "run": False})
    assert not result["isError"]
    campaign_id = result["structuredContent"]["campaign_id"]
    assert result["structuredContent"]["status"] == "ready"

    status = call(server, "coo_status", {"campaign_id": campaign_id})
    assert not status["isError"]
    assert campaign_id in status["content"][0]["text"]
    assert status["structuredContent"]["stage"] == "intake"


def test_new_run_stub_reaches_intake_checkpoint(server: CooMCPServer):
    result = call(server, "coo_new", {"demand": "Launch a 12-week campaign for Acme.", "run": True})
    assert not result["isError"], result["content"][0]["text"]
    payload = result["structuredContent"]
    assert payload["status"] == "awaiting_human"
    assert payload["pause_reason"] == "checkpoint:intake"
    campaign_id = payload["campaign_id"]

    artifacts = call(server, "coo_artifact_list", {"campaign_id": campaign_id})
    names = {row["name"] for row in artifacts["structuredContent"]["artifacts"]}
    assert "brief.json" in names

    status = call(server, "coo_status", {"campaign_id": campaign_id})
    assert not status["isError"]
    assert "checkpoint:intake" in status["content"][0]["text"]


def test_new_run_agent_fill_publishes_the_prompt(tmp_path: Path):
    settings = replace(load_settings(stub=False), api_key=None, agent_fill=True, stub=False)
    server = CooMCPServer(CampaignStore(tmp_path), settings, AgentFillClient())
    result = call(server, "coo_new", {"demand": "Launch a 12-week campaign for Acme.", "run": True})
    assert not result["isError"], result["content"][0]["text"]
    payload = result["structuredContent"]
    assert payload["status"] == "awaiting_agent"
    assert payload["prompt_path"].endswith("intake.md")

    prompt = call(server, "coo_prompt", {"campaign_id": payload["campaign_id"]})
    assert not prompt["isError"]
    assert "brief.json" in prompt["content"][0]["text"]


def test_artifact_round_trip(server: CooMCPServer):
    created = call(server, "coo_new", {"demand": "A campaign.", "run": False})
    campaign_id = created["structuredContent"]["campaign_id"]

    written = call(
        server,
        "coo_artifact_write",
        {"campaign_id": campaign_id, "name": "notes.md", "content": "# Notes\n\nProof first.\n"},
    )
    assert not written["isError"]
    read = call(server, "coo_artifact_read", {"campaign_id": campaign_id, "name": "notes.md"})
    assert not read["isError"]
    assert read["structuredContent"]["content"] == "# Notes\n\nProof first.\n"


def test_missing_artifact_is_a_tool_error(server: CooMCPServer):
    created = call(server, "coo_new", {"demand": "A campaign.", "run": False})
    campaign_id = created["structuredContent"]["campaign_id"]
    result = call(server, "coo_artifact_read", {"campaign_id": campaign_id, "name": "missing.md"})
    assert result["isError"] is True


def test_answer_unknown_question_is_a_tool_error(server: CooMCPServer):
    created = call(server, "coo_new", {"demand": "A campaign.", "run": True})
    campaign_id = created["structuredContent"]["campaign_id"]
    result = call(server, "coo_answer", {"campaign_id": campaign_id, "question_id": "q_missing", "text": "x"})
    assert result["isError"] is True
    assert "q_missing" in result["content"][0]["text"]


def test_export_before_write_is_a_tool_error(server: CooMCPServer):
    created = call(server, "coo_new", {"demand": "A campaign.", "run": False})
    campaign_id = created["structuredContent"]["campaign_id"]
    result = call(server, "coo_export", {"campaign_id": campaign_id})
    assert result["isError"] is True
    assert "proposal.md" in result["content"][0]["text"]


def test_stdio_is_utf8_when_the_console_codepage_is_not(tmp_path: Path):
    """A non-ASCII store path must not leak GBK bytes into the JSON-RPC stream."""
    store = tmp_path / "研究"
    requests = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        + "\n"
        + json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "coo_new",
                    "arguments": {"demand": "Launch a 12-week campaign for Acme.", "run": True},
                },
            }
        )
        + "\n"
    )
    env = {**os.environ, "PYTHONIOENCODING": "gbk", "COO_LLM_API_KEY": "", "OPENAI_API_KEY": "", "COO_LLM_STUB": ""}
    completed = subprocess.run(
        [sys.executable, "-m", "coo", "--store", str(store), "mcp"],
        input=requests.encode("ascii"),
        capture_output=True,
        timeout=60,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    responses = [json.loads(line) for line in completed.stdout.decode("utf-8").splitlines() if line.strip()]
    assert [response["id"] for response in responses] == [1, 2]
    payload = responses[1]["result"]["structuredContent"]
    assert "研究" in payload["prompt_path"]


def test_stdio_loop_keeps_stdout_protocol_only(tmp_path: Path):
    requests = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"}),
        ]
    )
    completed = subprocess.run(
        [sys.executable, "-m", "coo", "--store", str(tmp_path), "mcp"],
        input=requests + "\n",
        text=True,
        capture_output=True,
        timeout=60,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert completed.returncode == 0, completed.stderr
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert len(lines) == 3
    responses = [json.loads(line) for line in lines]
    assert [response["id"] for response in responses] == [1, 2, 3]

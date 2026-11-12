"""Drafts on the server, read-only SQL and the AI's MCP tools; each boundary has a test
(step 4 design 6)."""

from contextlib import asynccontextmanager

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from test_runs import DEFINITIONS, scenario

WORKER_TOOLS = {"task_get", "observe", "save_and_observe"}


@asynccontextmanager
async def mcp(app, headers=None):
    async with (
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), headers=headers or {}, timeout=30
        ) as http,
        Client(
            streamable_http_client("http://127.0.0.1:3110/mcp", http_client=http)
        ) as client,
    ):
        yield client


def test_drafts_are_written_not_saved(tmp_path, monkeypatch):
    # Definition 1: a version is made only when a run is decided; there is no saving (issue #3
    # U-08: the outside had draft_save, and its next actions led to it).
    async def body(app, client, dataset, ids):
        path = f"/v1/datasets/{dataset}/drafts/instruction"
        content = {"text": "下書き", "label_definitions": DEFINITIONS}
        first = (await client.put(path, json=content, headers={"X-Actor": "ai"})).json()
        assert first["written_by"] == "outside"
        await client.put(path, json={**content, "text": "人が直した"})
        stale = await client.put(
            path, json={**content, "if_updated_at": first["updated_at"]}
        )
        assert stale.status_code == 409
        assert (await client.post(path + "/save")).status_code in (404, 405)
        async with mcp(app) as ai:
            names = {t.name for t in (await ai.list_tools()).tools}
        assert "draft_save" not in names

    scenario(tmp_path, monkeypatch, body)


def test_ai_and_worker_tools_are_apart(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        async with mcp(app) as ai:
            names = {t.name for t in (await ai.list_tools()).tools}
            # The AI looks at anything (look); the worker observes only its own image and
            # result (observe, its own tool).
            assert "sql_query" not in names and not names & {
                "task_get",
                "save_and_observe",
            }
            listed = await ai.call_tool("read", {"type": "dataset"})
            assert listed.structured_content["ok"]
            assert listed.structured_content["data"]["items"][0]["id"] == dataset
        worker = {"X-Annotation-Run-Id": "run", "X-Annotation-Result-Id": "res"}
        async with mcp(app, worker) as inside:
            names = {t.name for t in (await inside.list_tools()).tools}
            assert names == WORKER_TOOLS
            blocked = await inside.call_tool("read", {"type": "dataset"})
            assert blocked.structured_content["error"]["code"] == "run_scope"

    scenario(tmp_path, monkeypatch, body)

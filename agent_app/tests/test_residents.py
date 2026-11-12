"""The workers' CLIs kept running per chat (definition 27), with the fake CLIs of fake_cli.py."""

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest
from agent_app.agent_answer import tool_recorder
from agent_app.system import WINDOWS

from agent_app import residents

FAKE = Path(__file__).with_name("fake_cli.py")
SETTINGS = {"effort": "low", "target_timeout_seconds": 30, "stall_seconds": 10}
SCHEMA = {"type": "object"}


def _wrapper(tmp_path, cli):
    """An executable that is the fake CLI (a kept CLI is started by its own path): a shell
    script, on Windows a .cmd (the CLIs there are .cmd too)."""
    if WINDOWS:
        path = tmp_path / f"{cli}.cmd"
        path.write_text(f'@"{sys.executable}" "{FAKE}" {cli} %*\n', encoding="utf-8")
        return str(path)
    path = tmp_path / cli
    path.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" {cli} "$@"\n', encoding="utf-8"
    )
    path.chmod(0o755)
    return str(path)


def _fakes(tmp_path, monkeypatch):
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_LOG", str(log))
    claude = _wrapper(tmp_path, "claude")
    monkeypatch.setattr(residents, "claude_argv", lambda directory, **_: [claude])
    monkeypatch.setattr(
        residents, "codex_executable", lambda: _wrapper(tmp_path, "codex")
    )
    return lambda: [
        json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
    ]


def _turn(kept, key, model, context, message, tools, session=None):
    return kept.turn(
        key,
        settings={**SETTINGS, "model": model},
        schema=SCHEMA,
        tools=["observe"],
        headers={"X-Annotation-Agent": key[1], "X-Annotation-Chat": str(key[2])},
        rules="RULES\n",
        context=context,
        message=message,
        session=session,
        record=tool_recorder(tools, time.monotonic()),
    )


def test_a_chat_keeps_its_cli_and_sends_only_what_changed(tmp_path, monkeypatch):
    # 2026-10-20: a CLI was started for every message, and every message sent the rules and
    # the whole context again.
    read = _fakes(tmp_path, monkeypatch)
    key = ("d", "instruction", 7)
    tools = []

    async def go():
        kept = residents.Residents(lambda: 6)
        model = "claude-sonnet-5-5"
        one = await _turn(
            kept,
            key,
            model,
            {"plan": 1, "earlier": ["a"], "language": "Japanese"},
            "一つ目",
            tools,
        )
        two = await _turn(
            kept,
            key,
            model,
            {
                "plan": 1,
                "earlier": ["a", "b"],
                "since": ["b"],
                "changes": ["x"],
                "language": "Japanese",
            },
            "二",
            tools,
        )
        await kept.stop_chat("instruction", 7)  # the chat was deleted
        three = await _turn(
            kept,
            key,
            model,
            {"plan": 2, "earlier": ["a"]},
            "三",
            tools,
            one[2]["session_id"],
        )
        await kept.close()
        return one, two, three

    one, two, three = asyncio.run(go())
    assert one[0]["message"] == two[0]["message"] != three[0]["message"]
    prompts = [e["prompt"] for e in read() if "prompt" in e]
    assert prompts[0].startswith("RULES\ncontext: ") and '"earlier"' in prompts[0]
    # Going on, the chat's lines since its last answer go each turn (2026-10-29: they were
    # never sent, so a server's question and the person's choice of it never reached it), and
    # the person's language (told once, an answer after English tools came in English).
    assert prompts[1] == (
        'context (only what changed since your last turn; the rest is as it was): {"changes":'
        ' ["x"], "since": ["b"], "language": "Japanese"}\nmessage: "二"\n'
    )
    # Started again going on from its conversation: the context all, its earlier lines not.
    assert prompts[2] == 'context: {"plan": 2}\nmessage: "三"\n'
    started = [e["started"] for e in read() if "started" in e]
    assert started[1][-2:] == ["--resume", one[2]["session_id"]]
    # Each tool call with when it started and how long it took (definition 47).
    assert [(t["tool"], t["ok"]) for t in tools] == [("observe", True)] * 3
    assert all(t["at"] >= 0 and t["ms"] >= 0 for t in tools)
    assert one[1]["input_tokens"] == 10


def test_a_codex_chat_is_one_app_server_thread(tmp_path, monkeypatch):
    read = _fakes(tmp_path, monkeypatch)
    key = ("d", "production", 3)
    tools = []

    async def go():
        kept = residents.Residents(lambda: 6)
        one = await _turn(kept, key, "gpt-6.1-sol", {"plan": 1}, "一つ目", tools)
        two = await _turn(kept, key, "gpt-6.1-sol", {"plan": 1}, "二", tools)
        # Anything but its answer and its MCP tools stops it, and it is not kept.
        with pytest.raises(ValueError, match="forbidden"):
            await _turn(kept, key, "gpt-6.1-sol", {"plan": 1}, "forbidden", tools)
        assert kept.kept == {}
        await kept.close()
        return one, two

    one, two = asyncio.run(go())
    said, usage, evidence = one
    assert said["message"] == two[0]["message"]
    assert evidence["session_id"] == f"th-{said['message']}"
    # The turn's usage is the sum of its model calls'.
    assert (usage["input_tokens"], usage["cached_input_tokens"]) == (30, 2)
    assert [(t["tool"], t["ok"]) for t in tools[:2]] == [("observe", True)] * 2
    assert all(t["at"] >= 0 and t["ms"] >= 0 for t in tools[:2])
    sent = [e for e in read() if "prompt" in e]
    assert sent[0]["schema"] == SCHEMA
    assert sent[1]["prompt"] == 'message: "二"\n'


def test_the_least_recently_used_idle_cli_goes_first(tmp_path, monkeypatch):
    read = _fakes(tmp_path, monkeypatch)
    model = "claude-sonnet-5-5"

    async def go():
        kept = residents.Residents(lambda: 2)
        for chat in (1, 2, 1, 3):  # the third chat: chat 2 was used longest ago
            await _turn(kept, ("d", "instruction", chat), model, {}, "x", [])
        left = sorted(k[2] for k in kept.kept)
        await kept.close()
        return left

    assert asyncio.run(go()) == [1, 3]
    assert len([e for e in read() if "started" in e]) == 3

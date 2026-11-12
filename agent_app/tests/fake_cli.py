"""A worker CLI kept running, faked (definition 27.8): "claude" reads stream-json user
messages, "codex" speaks app-server JSON-RPC. Each turn calls one tool and answers with its
own pid; what it was sent, and how it was started, go to the file FAKE_LOG.

usage: fake_cli.py claude|codex [the CLI's own arguments]
"""

import json
import os
import sys

MODEL = "claude-sonnet-5-5"


def log(entry):
    with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def say(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def claude(argv):
    session = (
        argv[argv.index("--resume") + 1] if "--resume" in argv else f"s-{os.getpid()}"
    )
    log({"started": argv, "pid": os.getpid()})
    for line in sys.stdin:
        prompt = json.loads(line)["message"]["content"]
        log({"pid": os.getpid(), "prompt": prompt})
        say(
            {"type": "system", "subtype": "init", "session_id": session, "model": MODEL}
        )
        tool = {
            "type": "tool_use",
            "id": "t1",
            "name": "mcp__annotation_execution__observe",
        }
        say(
            {
                "type": "assistant",
                "uuid": "u1",
                "message": {"content": [{**tool, "input": {}}]},
            }
        )
        result = {"type": "tool_result", "tool_use_id": "t1", "content": '{"ok": true}'}
        say({"type": "user", "message": {"content": [result]}})
        say(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "session_id": session,
                "structured_output": {"kind": "answer", "message": str(os.getpid())},
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
                "modelUsage": {MODEL: {"inputTokens": 10, "outputTokens": 5}},
            }
        )


def codex(argv):
    log({"started": argv, "pid": os.getpid()})
    thread = None
    for line in sys.stdin:
        asked = json.loads(line)
        method, params = asked.get("method"), asked.get("params") or {}
        if method == "initialize":
            say({"id": asked["id"], "result": {"userAgent": "fake"}})
        elif method in ("thread/start", "thread/resume"):
            thread = params.get("threadId") or f"th-{os.getpid()}"
            say({"id": asked["id"], "result": {"thread": {"id": thread}}})
        elif method == "turn/start":
            prompt = params["input"][0]["text"]
            log(
                {"pid": os.getpid(), "prompt": prompt, "schema": params["outputSchema"]}
            )
            say({"id": asked["id"], "result": {"turn": {"id": "turn-1"}}})
            say({"method": "turn/started", "params": {"threadId": thread}})
            if "forbidden" in prompt:
                item = {"type": "commandExecution", "id": "c1", "command": "ls"}
                say({"method": "item/started", "params": {"item": item}})
                continue
            call = {"type": "mcpToolCall", "id": "m1", "tool": "observe", "server": "a"}
            say(
                {
                    "method": "item/started",
                    "params": {"item": {**call, "status": "inProgress"}},
                }
            )
            say(
                {
                    "method": "item/completed",
                    "params": {"item": {**call, "status": "completed"}},
                }
            )
            for tokens in (10, 20):  # one per model call
                last = {
                    "inputTokens": tokens,
                    "cachedInputTokens": 1,
                    "outputTokens": 2,
                    "reasoningOutputTokens": 0,
                    "cacheWriteInputTokens": 0,
                    "totalTokens": tokens + 2,
                }
                usage = {"last": last, "total": last}
                say(
                    {
                        "method": "thread/tokenUsage/updated",
                        "params": {
                            "threadId": thread,
                            "turnId": "turn-1",
                            "tokenUsage": usage,
                        },
                    }
                )
            answer = json.dumps({"kind": "answer", "message": str(os.getpid())})
            say(
                {
                    "method": "item/completed",
                    "params": {
                        "item": {"type": "agentMessage", "id": "a1", "text": answer}
                    },
                }
            )
            say(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": thread,
                        "turn": {"id": "turn-1", "status": "completed"},
                    },
                }
            )


if __name__ == "__main__":
    # The CLIs speak UTF-8 JSON lines on every system (Windows' own is cp932).
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    {"claude": claude, "codex": codex}[sys.argv[1]](sys.argv[2:])

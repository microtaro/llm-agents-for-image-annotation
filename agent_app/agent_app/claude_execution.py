"""Claude Code invocation and its public stream-json boundary."""

import json
import shutil

from .config import base_url
from .errors import ApiError

WORKER_TOOLS = ("task_get", "observe", "save_and_observe")


def claude_argv(
    directory,
    *,
    run_id=None,
    result_id=None,
    settings,
    tools=None,
    headers=None,
    mcp=True,
):
    """tools and headers: for a caller that is not a run's worker (the progress panel's AI).
    mcp=False: no tools at all (the LLM judge of text answers reads only its prompt)."""
    executable = shutil.which("claude")
    if executable is None:
        raise RuntimeError(
            "Claude Code was not found; start the server on a host where it is signed in."
        )
    allowed = set(tools or WORKER_TOOLS)
    config = {
        "mcpServers": {
            "annotation_execution": {
                "type": "http",
                "url": base_url() + "/mcp",
                "headers": headers
                or {
                    "X-Annotation-Run-Id": run_id,
                    "X-Annotation-Result-Id": result_id,
                },
            }
        }
    }
    return [
        executable,
        "-p",
        "--model",
        settings["model"],
        "--effort",
        settings["effort"],
        "--tools",
        "",
        "--strict-mcp-config",
        *(
            [
                "--mcp-config",
                json.dumps(config),
                "--allowedTools",
                ",".join("mcp__annotation_execution__" + n for n in sorted(allowed)),
            ]
            if mcp
            else []
        ),
        "--setting-sources",
        "",
        "--settings",
        json.dumps(
            {"disableAllHooks": True, "fastMode": settings.get("tier") == "fast"}
        ),
        "--disable-slash-commands",
        "--no-chrome",
        "--no-session-persistence",
        "--permission-mode",
        "dontAsk",
        "--output-format",
        "stream-json",
        "--verbose",
        "--json-schema",
        (directory / "schema.json").read_text(encoding="utf-8"),
    ]


class ClaudeStream:
    """Translate actual public messages; never retain thinking or synthesize images."""

    def __init__(self, directory, model):
        self.directory = directory
        self.model = model
        self.calls = {}

    def events(self, event):
        kind = event.get("type")
        if kind == "system":
            if event.get("subtype") == "init":
                if event.get("model") != self.model:
                    raise ValueError("Claude returned a different model")
                return [{"type": "thread.started", "thread_id": event["session_id"]}]
            return []
        if kind == "assistant":
            if event.get("error"):
                # The CLI's own failure as its message (found 2026-10-29: signed out, Claude
                # Code said "Not logged in · Please run /login" and the answer failed later
                # as "model attribution is unavailable").
                said = " ".join(
                    p.get("text", "") for p in event["message"]["content"]
                ).strip()
                raise ApiError(
                    502,
                    "signed_out_claude"
                    if event["error"] == "authentication_failed"
                    else "cli_failed",
                    f"Claude Code: {said or event['error']}",
                )
            result = []
            for index, part in enumerate(event["message"]["content"]):
                if part["type"] == "text":
                    result.append(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "agent_message",
                                "id": f"{event.get('uuid')}:{index}",
                                "text": part["text"],
                            },
                        }
                    )
                elif part["type"] == "tool_use":
                    name = part["name"]
                    if name == "StructuredOutput":
                        continue
                    # A name outside the app's tools (2026-10-29: the model called "look"
                    # without its prefix) is the CLI's to refuse: its error comes back to the
                    # model, which calls again; the answer goes on, the call failed.
                    item = {
                        "type": "mcp_tool_call",
                        "id": part["id"],
                        "tool": name.removeprefix("mcp__annotation_execution__"),
                        "arguments": part["input"],
                        "status": "in_progress",
                    }
                    self.calls[part["id"]] = item
                    result.append({"type": "item.started", "item": item})
                elif part["type"] not in ("thinking", "redacted_thinking"):
                    raise ValueError("Unknown Claude assistant content")
            return result
        if kind == "user":
            result = []
            for part in event["message"]["content"]:
                if part.get("type") != "tool_result":
                    continue
                item = self.calls.pop(part["tool_use_id"], None)
                if item is None:
                    continue  # StructuredOutput has no annotation operation.
                content = part.get("content", [])
                if isinstance(content, str):
                    content = [{"type": "text", "text": content}]
                converted, envelope = [], None
                for block in content:
                    if block.get("type") == "image":
                        source = block["source"]
                        if source["type"] != "base64":
                            raise ValueError("Claude image bytes are unavailable")
                        converted.append(
                            {
                                "type": "image",
                                "data": source["data"],
                                "mimeType": source["media_type"],
                            }
                        )
                    else:
                        converted.append(block)
                        if block.get("type") == "text":
                            try:
                                candidate = json.loads(block["text"])
                                if isinstance(candidate, dict) and "ok" in candidate:
                                    envelope = candidate
                            except ValueError:
                                pass  # External plain text remains in content.
                result.append(
                    {
                        "type": "item.completed",
                        "item": {
                            **item,
                            "status": "failed" if part.get("is_error") else "completed",
                            "result": {
                                "content": converted,
                                "structured_content": envelope,
                                "isError": bool(part.get("is_error")),
                            },
                        },
                    }
                )
            return result
        if kind == "result":
            models = event.get("modelUsage", {})
            if set(models) != {self.model}:
                raise ValueError("Claude usage model attribution is unavailable")
            measured = models[self.model]
            usage = {
                field: measured.get(key)
                for field, key in (
                    ("input_tokens", "inputTokens"),
                    ("output_tokens", "outputTokens"),
                    ("cached_input_tokens", "cacheReadInputTokens"),
                    ("cache_write_input_tokens", "cacheCreationInputTokens"),
                    ("reasoning_output_tokens", "thinkingTokens"),
                )
            }
            # A resumed session's modelUsage counts the whole session; the result's own usage
            # is this turn's (found 2026-10-05: 5991 + 4403 = 10394 on the second turn). Use
            # the turn's numbers when it gives them.
            turn = event.get("usage") or {}
            if isinstance(turn.get("cache_creation_input_tokens"), int):
                usage.update(
                    input_tokens=turn.get("input_tokens"),
                    output_tokens=turn.get("output_tokens"),
                    cached_input_tokens=turn.get("cache_read_input_tokens"),
                    cache_write_input_tokens=turn.get("cache_creation_input_tokens"),
                    reasoning_output_tokens=(
                        turn.get("output_tokens_details") or {}
                    ).get("thinking_tokens", usage["reasoning_output_tokens"]),
                )
            cache = event.get("usage", {}).get("cache_creation", {})
            raw = {
                **usage,
                **{
                    k: cache.get(k)
                    for k in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens")
                },
            }
            result = [
                {
                    "type": "turn.completed",
                    "usage": usage,
                    "usage_raw": raw,
                    "usage_inclusion": {
                        "cached_input_tokens": "external",
                        "cache_write_input_tokens": "external",
                        "reasoning_output_tokens": "output",
                    },
                }
            ]
            if event.get("is_error") or event.get("subtype") != "success":
                result.append(
                    {
                        "type": "turn.failed",
                        "message": event.get("result")
                        or "; ".join(event.get("errors", []))
                        or "Claude execution failed",
                    }
                )
            else:
                final = event.get("structured_output")
                if not isinstance(final, dict):
                    raise ValueError("Claude structured output is missing")
                text = json.dumps(final, ensure_ascii=False)
                (self.directory / "result.json").write_text(text, encoding="utf-8")
                result.append(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "agent_message",
                            "text": text,
                        },
                    }
                )
            return result
        if kind == "rate_limit_event":
            return []
        raise ValueError("Unknown Claude CLI event; external trace incomplete")

"""Run one image's worker CLI and read its events, final answer and usage.

Copied from annotation_server/codex_execution.py (read_usage, infer).
"""

import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

from .claude_execution import ClaudeStream, claude_argv
from .codex_execution import (
    BACKSTOP_SECONDS,
    codex_argv,
    inference_prompt,
    output_schema,
)
from .model_catalog import CLAUDE_MODELS
from .runtime_usage import FIELDS
from .system import stop_supervisor


def read_usage(raw):
    events = []
    position = 0
    first = last = None
    starts = 0
    for line in raw.splitlines(keepends=True):
        position += len(line)
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") in ("item.started", "item.completed") and event.get(
            "item", {}
        ).get("type") not in ("agent_message", "reasoning", "error", "mcp_tool_call"):
            raise ValueError("Codex returned an unexpected tool/action event")
        if event.get("type") == "thread.started":
            starts += 1
            first = (position, hashlib.sha256(line).hexdigest(), event.get("thread_id"))
        if event.get("type") == "turn.completed":
            events.append(event)
            last = (position, hashlib.sha256(line).hexdigest())
    if (
        starts != 1
        or not first
        or not first[2]
        or len(events) != 1
        or not isinstance(events[0].get("usage"), dict)
    ):
        return None, None
    return usage_of(events[0]), {
        "session_id": first[2],
        "start_event": first[0],
        "end_event": last[0],
        "start_event_sha256": first[1],
        "end_event_sha256": last[1],
    }


def usage_of(completed):
    """A turn's usage from its turn.completed event (its usage, and usage_raw and
    usage_inclusion when the reader knows them): the same form for every CLI."""
    values = {
        k: v if type(v := completed["usage"].get(k)) is int and v >= 0 else None
        for k in FIELDS
    }
    return {
        **values,
        "raw": completed.get("usage_raw", values),
        "inclusion": completed.get(
            "usage_inclusion", {k: "unknown" for k in FIELDS[2:]}
        ),
        "missing_reasons": {
            k: "CLI did not return this field" for k, v in values.items() if v is None
        },
    }


async def infer(directory, run, result_id, stop, record):
    (directory / "schema.json").write_text(
        json.dumps(output_schema()), encoding="utf-8"
    )
    model = (run.get("settings") or {}).get("model")
    argv = (claude_argv if model in CLAUDE_MODELS else codex_argv)(
        directory,
        run_id=run["id"],
        result_id=result_id,
        settings=run.get("settings"),
    )
    return await run_cli(
        directory,
        argv,
        inference_prompt(run, result_id),
        model,
        run["settings"]["target_timeout_seconds"],
        stop,
        record,
        stall=run["settings"].get("stall_seconds"),
    )


async def run_cli(directory, argv, prompt, model, limit, stop, record, stall=None):
    """Run a CLI (argv, schema.json already in directory) with prompt; returns the final
    answer, usage and evidence. Shared by run workers and the progress panel's AI.
    stall: seconds the CLI may write nothing before it is stopped (step 24: before, only the
    whole time limit stopped a CLI that hung)."""
    claude = model in CLAUDE_MODELS
    last_output = time.monotonic()
    stream = ClaudeStream(directory, model) if claude else None
    spec = {"timeout": limit + 2 * BACKSTOP_SECONDS, "argv": argv, "prompt": prompt}
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(Path(__file__).with_name("execution_child.py")),
        cwd=directory,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=32 * 1024 * 1024,
    )
    lifecycle = bytearray()
    last_message = None
    last_error = None  # the CLI's own words for a failure ("model is at capacity", ...)
    completed = 0

    async def receive():
        nonlocal last_output
        while line := await process.stdout.readline():
            last_output = time.monotonic()
            incoming = json.loads(line)
            for event in stream.events(incoming) if stream else [incoming]:
                await receive_event(event, None if stream else line)

    async def receive_event(event, original_line):
        nonlocal last_message, completed, last_error
        kind = event.get("type")
        item = event.get("item", {})
        if item.get("type") == "reasoning":
            return
        if kind in ("thread.started", "turn.completed"):
            lifecycle.extend(original_line or (json.dumps(event) + "\n").encode())
            completed += kind == "turn.completed"
        if kind not in (
            "thread.started",
            "turn.started",
            "turn.completed",
            "turn.failed",
            "item.started",
            "item.updated",
            "item.completed",
            "error",
        ):
            raise ValueError("Unknown CLI event; external trace incomplete")
        if kind.startswith("item.") and item.get("type") not in (
            "agent_message",
            "mcp_tool_call",
            "error",
        ):
            await record(
                {
                    "type": "error",
                    "message": "Unexpected action: " + str(item.get("type")),
                }
            )
            raise ValueError("CLI returned a forbidden action")
        await record(event)
        if kind == "error" or item.get("type") == "error":
            last_error = event.get("message") or item.get("message") or last_error
        if item.get("type") == "agent_message" and kind == "item.completed":
            last_message = item["text"]

    async def drain_errors():
        # Private diagnostics stay bounded; never publish or retain the entire CLI log.
        kept = 0
        with (directory / "stderr.private").open("wb") as output:
            while chunk := await process.stderr.read(16384):
                if kept < 1024 * 1024:
                    piece = chunk[: 1024 * 1024 - kept]
                    output.write(piece)
                    kept += len(piece)

    async def watch_cli():
        while stall:
            await asyncio.sleep(min(5, stall))
            if time.monotonic() - last_output > stall:
                return

    reader = asyncio.create_task(receive())
    errors = asyncio.create_task(drain_errors())
    waiter = asyncio.create_task(process.wait())
    stopped = asyncio.create_task(stop.wait())
    silent = asyncio.create_task(watch_cli())
    try:
        process.stdin.write((json.dumps(spec) + "\n").encode())
        await process.stdin.drain()
        process.stdin.close()
        done, _ = await asyncio.wait(
            [reader, waiter, stopped, silent] if stall else [reader, waiter, stopped],
            timeout=limit + BACKSTOP_SECONDS,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stopped in done:
            raise InterruptedError("Stopped.")
        if silent in done:
            raise TimeoutError(f"The CLI wrote nothing for {stall} s; stopped.")
        if not done:
            raise TimeoutError(f"Exceeded the time limit ({limit} s).")
        if reader in done:
            await reader
        code = await waiter
        await reader
        usage, evidence = read_usage(bytes(lifecycle))
        if code != 0 or completed == 0:
            reason = f": {last_error}" if last_error else ""
            raise RuntimeError(
                f"CLI execution failed (exit={code}, completed_turns={completed}){reason}"
            )
        final = (directory / "result.json").read_text(encoding="utf-8")
        if last_message is None or final.strip() != last_message.strip():
            raise ValueError("Final answer does not match the recorded runtime message")
        return json.loads(final), usage, evidence
    except BaseException as exc:
        # Whatever usage the CLI reported before failing, so the image's cost is still
        # recorded; a turn cut off by a stop or the time limit has none (None).
        try:
            exc.usage, exc.evidence = read_usage(bytes(lifecycle))
        except ValueError:
            exc.usage = exc.evidence = None
        if isinstance(exc, (ValueError, KeyError, FileNotFoundError)):
            await record({"type": "trace.incomplete", "message": str(exc)})
        raise
    finally:
        stopped.cancel()
        silent.cancel()
        if process.returncode is None:
            stop_supervisor(process)
        await asyncio.shield(waiter)
        await asyncio.gather(reader, errors, stopped, silent, return_exceptions=True)

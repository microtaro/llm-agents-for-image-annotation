"""The workers' CLIs kept running, one per chat (definition 27; user 2026-10-20: the chats are
used more now, and a CLI started for every message was the wait). A chat's answer with tools
starts its CLI (Claude: claude -p reading stream-json; Codex: codex app-server with one
thread), and the chat's next answers go to the same one, sending only what changed of what the
worker is shown (27.3). At most chat_slots are kept (6, user 2026-10-20): the least recently
used that is not answering goes first, and one unused for 15 minutes goes. Stopping ends the
process; the conversation stays with the CLI, and the next answer starts one going on from it.

A turn is read as inference.run_cli reads one: its time limit, the seconds it may write
nothing, only its answer and its MCP tools (any other action stops it), the model it said.
"""

import asyncio
import hashlib
import json
import logging
import shutil
import tempfile
import time
from pathlib import Path

from .claude_execution import ClaudeStream, claude_argv
from .codex_execution import BACKSTOP_SECONDS, codex_executable, codex_flags
from .inference import usage_of
from .model_catalog import CLAUDE_MODELS
from .system import NEW_GROUP, end_group

logger = logging.getLogger("agent_app.residents")
IDLE_SECONDS = 15 * 60
SWEEP_SECONDS = 60
ENDED = object()  # what the reader puts in the line when the CLI's output ends
KINDS = (
    "thread.started",
    "turn.started",
    "turn.completed",
    "turn.failed",
    "item.started",
    "item.updated",
    "item.completed",
    "error",
)


def _dumped(value):
    return json.dumps(value, ensure_ascii=False)


class Resident:
    """One worker's CLI for one chat, answering one turn at a time."""

    def __init__(self, key, identity, settings, schema, tools, headers, session):
        self.key, self.identity = key, identity
        self.settings, self.schema = settings, schema
        self.tools, self.headers = list(tools), headers
        self.session = session  # the conversation it goes on with; None: a new one
        self.new = session is None  # the first turn of a new conversation
        self.rules_due = session is None
        self.sent = None  # the context as last sent, each item as JSON
        self.compacted = False
        self.used = time.monotonic()
        self.busy = False
        self.directory = Path(tempfile.mkdtemp(prefix="agent-resident-"))
        self.process = None
        self.lines = asyncio.Queue()
        self.last_output = time.monotonic()
        self.tasks = []

    # ---------- the process ----------

    async def _spawn(self, argv):
        self.process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=self.directory,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=32 * 1024 * 1024,
            **NEW_GROUP,  # its own group, ended whole (system.end_group)
        )
        self.tasks = [
            asyncio.create_task(self._read()),
            asyncio.create_task(self._drain_errors()),
        ]

    async def _read(self):
        try:
            while line := await self.process.stdout.readline():
                self.last_output = time.monotonic()
                try:
                    found = json.loads(line)
                except ValueError:
                    continue
                if not self._answered(found):
                    self.lines.put_nowait(found)
        finally:
            self.lines.put_nowait(ENDED)

    def _answered(self, found):
        """A reply to the server's own request (Codex); False for everything else."""
        return False

    async def _drain_errors(self):
        # Private diagnostics stay bounded, as a run's CLI's (inference.run_cli).
        kept = 0
        with (self.directory / "stderr.private").open("wb") as output:
            while chunk := await self.process.stderr.read(16384):
                if kept < 1024 * 1024:
                    piece = chunk[: 1024 * 1024 - kept]
                    output.write(piece)
                    kept += len(piece)

    async def _write(self, message):
        self.process.stdin.write((_dumped(message) + "\n").encode())
        await self.process.stdin.drain()

    def alive(self):
        return self.process is not None and self.process.returncode is None

    async def close(self):
        if self.process is not None and self.process.returncode is None:
            for force in (False, True):
                end_group(self.process.pid, force)
                try:
                    await asyncio.wait_for(self.process.wait(), 5)
                    break
                except TimeoutError:
                    continue
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        shutil.rmtree(self.directory, ignore_errors=True)

    # ---------- one turn ----------

    def _prompt(self, rules, context, message):
        """What this turn sends (27.3): a new conversation the rules and all the context with
        the chat's earlier lines, one going on all the context with the lines since its last
        answer, and a CLI that answered before only the items that changed since, with the
        person's language (definition 68.1)."""
        lines = "earlier" if self.new else "since"
        # Sent every turn, never compared: the chat's lines, new each turn, and the person's
        # language (2026-10-29: told on the first turn only, an answer after tools that answer in
        # English came in English, and the chat went on in it).
        told = {k: context[k] for k in (lines, "language") if context.get(k)}
        items = {
            k: v
            for k, v in context.items()
            if k not in ("earlier", "since", "language")
        }
        # The chat's lines are never compared: each turn's are new to the conversation.
        encoded = {k: _dumped(v) for k, v in items.items()}
        parts = []
        if self.sent is None:
            parts.append("context: " + _dumped({**items, **told}))
        else:
            # An item gone since is sent as null.
            gone = [k for k in self.sent if k not in encoded]
            changed = {
                k: items.get(k)
                for k in [*encoded, *gone]
                if encoded.get(k) != self.sent.get(k)
            } | told
            if changed:
                parts.append(
                    "context (only what changed since your last turn; the rest is as it"
                    " was): " + _dumped(changed)
                )
        parts.append("message: " + _dumped(message))
        head = rules if self.rules_due else ""
        return head + "\n".join(parts) + "\n", encoded

    async def turn(self, rules, context, message, record):
        prompt, encoded = self._prompt(rules, context, message)
        self.busy = True
        try:
            said, usage = await self._turn(prompt, record)
        finally:
            self.busy = False
            self.used = time.monotonic()
        # A compacted conversation may have lost the rules and the context: all again.
        self.new = False
        self.rules_due, self.sent = (True, None) if self.compacted else (False, encoded)
        self.compacted = False
        return said, usage, {"session_id": self.session}

    async def _turn(self, prompt, record):
        limit = self.settings["target_timeout_seconds"]
        stall = self.settings.get("stall_seconds")
        end = time.monotonic() + limit + BACKSTOP_SECONDS
        # What came after the last turn ended (a status) is not this turn's.
        while not self.lines.empty():
            if self.lines.get_nowait() is ENDED:
                raise RuntimeError("CLI execution failed (it had ended)")
        self.last_output = time.monotonic()
        await self._send(prompt)
        message = error = failed = completed = None
        usage = None
        try:
            while completed is None and failed is None:
                now = time.monotonic()
                wait = end - now
                if stall:
                    wait = min(wait, self.last_output + stall - now)
                try:
                    found = await asyncio.wait_for(self.lines.get(), max(wait, 0.01))
                except TimeoutError:
                    if time.monotonic() >= end:
                        raise TimeoutError(
                            f"Exceeded the time limit ({limit} s)."
                        ) from None
                    if stall and time.monotonic() - self.last_output >= stall:
                        raise TimeoutError(
                            f"The CLI wrote nothing for {stall} s; stopped."
                        ) from None
                    continue
                if found is ENDED:
                    reason = f": {error}" if error else ""
                    raise RuntimeError(f"CLI execution failed (it ended){reason}")
                for event in self._events(found):
                    kind = event.get("type")
                    item = event.get("item", {})
                    if kind not in KINDS:
                        raise ValueError("Unknown CLI event; external trace incomplete")
                    if kind.startswith("item.") and item.get("type") not in (
                        "agent_message",
                        "mcp_tool_call",
                        "error",
                    ):
                        await record(
                            {
                                "type": "error",
                                "message": "Unexpected action: "
                                + str(item.get("type")),
                            }
                        )
                        raise ValueError("CLI returned a forbidden action")
                    await record(event)
                    if kind == "thread.started":
                        self.session = event.get("thread_id") or self.session
                    if kind == "error" or item.get("type") == "error":
                        error = event.get("message") or item.get("message") or error
                    if kind == "item.completed" and item.get("type") == "agent_message":
                        message = item["text"]
                    if kind == "turn.completed":
                        completed = event
                        usage = usage_of(event)
                    if kind == "turn.failed":
                        failed = event.get("message") or error or "turn failed"
            if failed is not None:
                raise RuntimeError(f"CLI execution failed: {failed}")
            if message is None:
                raise ValueError("The CLI gave no final answer")
            said = json.loads(message)
            if not isinstance(said, dict):
                raise TypeError("The final answer is not an object")
            return said, usage
        except BaseException as exc:
            exc.usage = usage  # what the CLI reported before failing, for its cost
            raise


class ClaudeResident(Resident):
    """claude -p reading user messages as stream-json: each turn says init, then its
    messages, then a result (as one claude -p run does)."""

    async def start(self):
        (self.directory / "schema.json").write_text(
            _dumped(self.schema), encoding="utf-8"
        )
        argv = [
            a
            for a in claude_argv(
                self.directory,
                settings=self.settings,
                tools=self.tools,
                headers=self.headers,
            )
            if a != "--no-session-persistence"
        ]
        argv += ["--input-format", "stream-json"]
        if self.session:
            argv += ["--resume", self.session]
        await self._spawn(argv)
        self.stream = None

    async def _send(self, prompt):
        self.stream = ClaudeStream(self.directory, self.settings["model"])
        await self._write(
            {"type": "user", "message": {"role": "user", "content": prompt}}
        )

    def _events(self, found):
        if found.get("type") == "system" and found.get("subtype") == "compact_boundary":
            self.compacted = True
        return self.stream.events(found)


class CodexResident(Resident):
    """codex app-server (JSON-RPC over stdio) with one thread: the safety of codex exec
    (codex_flags), the thread read-only and never asking, the answer by outputSchema."""

    async def start(self):
        self.replies = {}
        self.asked = 0
        self.usage = {}
        flags = codex_flags(
            settings=self.settings, tools=self.tools, headers=self.headers
        )
        await self._spawn([codex_executable(), "app-server", *flags])
        await self._call(
            "initialize",
            {"clientInfo": {"name": "llm-agents-for-image-annotation", "version": "1"}},
        )
        await self._write({"method": "initialized"})
        place = {
            "cwd": str(self.directory),
            "approvalPolicy": "never",
            "sandbox": "read-only",
        }
        if self.session:
            found = await self._call(
                "thread/resume",
                {"threadId": self.session, "excludeTurns": True, **place},
            )
        else:
            found = await self._call("thread/start", place)
        self.session = found["thread"]["id"]

    async def _call(self, method, params):
        self.asked += 1
        asked = self.asked
        self.replies[asked] = reply = asyncio.get_running_loop().create_future()
        await self._write({"id": asked, "method": method, "params": params})
        try:
            found = await asyncio.wait_for(reply, 60)
        finally:
            self.replies.pop(asked, None)
        if "error" in found:
            raise RuntimeError(f"{method} failed: {found['error'].get('message')}")
        return found["result"]

    def _answered(self, found):
        if "method" in found or found.get("id") not in self.replies:
            return False
        self.replies[found["id"]].set_result(found)
        return True

    async def _send(self, prompt):
        self.usage = {}
        await self._call(
            "turn/start",
            {
                "threadId": self.session,
                "input": [{"type": "text", "text": prompt}],
                "outputSchema": self.schema,
            },
        )

    def _events(self, found):
        method, params = found.get("method"), found.get("params") or {}
        if "id" in found:
            # The server asks (an approval, an input): never, with these settings.
            raise ValueError(f"The CLI asked for what it may not: {method}")
        if method == "thread/compacted":
            self.compacted = True
        elif method == "thread/tokenUsage/updated":
            # One per model call; the turn's usage is their sum (checked 2026-10-20: it equals
            # the change of the thread's total).
            for key, value in params["tokenUsage"]["last"].items():
                self.usage[key] = self.usage.get(key, 0) + value
        elif method == "error":
            return [{"type": "error", "message": params["error"].get("message")}]
        elif method in ("item/started", "item/completed"):
            return self._item(method, params["item"])
        elif method == "turn/completed":
            turn = params["turn"]
            done = [{"type": "turn.completed", "usage": self._usage()}]
            if turn.get("status") != "completed":
                failure = (turn.get("error") or {}).get("message") or turn.get("status")
                done.append({"type": "turn.failed", "message": failure})
            return done
        return []

    def _item(self, method, item):
        kind = "item.started" if method == "item/started" else "item.completed"
        if item["type"] == "contextCompaction":
            self.compacted = True
            return []
        if item["type"] in ("userMessage", "reasoning"):
            return []
        if item["type"] == "agentMessage":
            if kind == "item.started":
                return []
            return [
                {"type": kind, "item": {"type": "agent_message", "text": item["text"]}}
            ]
        if item["type"] == "mcpToolCall":
            status = {"completed": "completed", "inProgress": "in_progress"}
            return [
                {
                    "type": kind,
                    "item": {
                        "type": "mcp_tool_call",
                        "id": item.get("id"),
                        "tool": item.get("tool"),
                        "arguments": item.get("arguments"),
                        "status": status.get(item.get("status"), "failed"),
                    },
                }
            ]
        return [{"type": kind, "item": {"type": item["type"]}}]  # refused by the reader

    def _usage(self):
        names = {
            "input_tokens": "inputTokens",
            "output_tokens": "outputTokens",
            "cached_input_tokens": "cachedInputTokens",
            "cache_write_input_tokens": "cacheWriteInputTokens",
            "reasoning_output_tokens": "reasoningOutputTokens",
        }
        return {ours: self.usage.get(theirs) for ours, theirs in names.items()}


class Residents:
    """The kept CLIs by chat: (dataset, worker, chat), the reception's with no dataset."""

    def __init__(self, limit):
        self.limit = limit  # how many may be kept: the chat slots
        self.kept = {}
        self.sweeper = asyncio.create_task(self._sweep())

    async def turn(
        self,
        key,
        *,
        settings,
        schema,
        tools,
        headers,
        rules,
        context,
        message,
        session,
        record,
    ):
        """One answer in the chat of key. session: the conversation to go on with when its
        CLI has to be started (a kept one goes on with its own)."""
        identity = hashlib.sha256(
            _dumped(
                [
                    settings["model"],
                    settings.get("effort"),
                    settings.get("tier"),
                    rules,
                    schema,
                    sorted(tools),
                    headers,
                ]
            ).encode()
        ).hexdigest()
        kept = self.kept.get(key)
        if kept is not None and (kept.identity != identity or not kept.alive()):
            await self.stop(key)
            kept = None
        if kept is None:
            await self._make_room()
            made = (
                ClaudeResident if settings["model"] in CLAUDE_MODELS else CodexResident
            )
            kept = made(key, identity, settings, schema, tools, headers, session)
            self.kept[key] = kept
            try:
                await kept.start()
            except BaseException:
                await self.stop(key)
                raise
        try:
            return await kept.turn(rules, context, message, record)
        except BaseException:
            # Stopped, cut off or broken: the CLI goes; the next answer starts one again.
            await self.stop(key)
            raise

    async def _make_room(self):
        while len(self.kept) >= self.limit():
            idle = [r for r in self.kept.values() if not r.busy]
            if not idle:
                return
            await self.stop(min(idle, key=lambda r: r.used).key)

    async def stop(self, key):
        kept = self.kept.pop(key, None)
        if kept is not None:
            await kept.close()

    async def stop_chat(self, agent, chat_id):
        """A chat was deleted: its CLI goes."""
        for key in [k for k in self.kept if k[1:] == (agent, chat_id)]:
            await self.stop(key)

    async def _sweep(self):
        while True:
            await asyncio.sleep(SWEEP_SECONDS)
            now = time.monotonic()
            for key, kept in list(self.kept.items()):
                if not kept.busy and now - kept.used > IDLE_SECONDS:
                    await self.stop(key)

    async def close(self):
        self.sweeper.cancel()
        await asyncio.gather(self.sweeper, return_exceptions=True)
        for key in list(self.kept):
            await self.stop(key)

"""What one image's worker did, from its CLI events, and the check that it did the steps.

Copied from annotation_server/runs.py (record, _envelopes, _check). The check needs: the task
fetched, the whole target seen with nothing drawn, and the final answer given after the whole
saved result was seen as an overlay.
"""

import base64
import hashlib
import re

from . import run_logs
from .annotation_sets import snapshot
from .images import image_info
from .run_queries import made_status
from .views import frame_of, render_view

# CLI messages that mean the sign-in is gone; the remaining images would fail the same way.
AUTH_HINTS = re.compile(
    r"unauthori[sz]ed|\b401\b|refresh token|not logged in|log ?in again|sign in again|"
    r"authenticat|invalid api key|/login",
    re.IGNORECASE,
)
# The least of a view's base64 a cut record must keep to show the view: past a JPEG's header,
# which every view of one size shares (about 600 bytes).
CUT_KEPT = 4096


class Trace:
    """The events of one image's worker, kept in memory (images only as hashes)."""

    def __init__(self, method):
        self.method = method
        self.received = []
        self.failure = None
        self.auth_failure = None

    def take(self, event):
        """Keep one CLI event; return the body to log, or None for reasoning."""
        item = event.get("item", {})
        if event.get("type") == "trace.incomplete":
            self.failure = event.get("message")
        message = (
            event.get("message")
            or (item.get("error") or {}).get("message")
            or item.get("message")
        )
        failed = (
            event.get("type") in ("error", "turn.failed") or item.get("type") == "error"
        )
        if failed and message and AUTH_HINTS.search(str(message)):
            cli = "claude" if self.method == "claude_code_annotation_mcp" else "codex"
            self.auth_failure = f"signed_out_{cli}"
        images = []
        result = run_logs.normalize_result(item.get("result"))
        body = {
            "type": event.get("type"),
            "item_type": item.get("type"),
            "tool": item.get("tool"),
            "arguments": item.get("arguments"),
            "status": item.get("status"),
            "text": item.get("text"),
            "error": item.get("error") or event.get("message"),
            "result": run_logs.strip_images(result, images) if result else None,
            "images": images,
        }
        self.received.append(body)
        if item.get("type") == "reasoning":
            return None
        envelope = None
        if body["result"]:
            content = body["result"].get("structured_content", {})
            envelope = {
                k: content.get(k)
                for k in ("ok", "save_status", "error", "view", "whole")
            }
        return {k: v for k, v in body.items() if k != "result"} | {"envelope": envelope}

    def envelopes(self, tool=None):
        for body in self.received:
            if body["type"] != "item.completed" or body["item_type"] != "mcp_tool_call":
                continue
            if tool and body["tool"] != tool:
                continue
            yield body, (body["result"] or {}).get("structured_content") or {}

    @staticmethod
    def delivered(db, body, frame):
        """The view's bytes are in the CLI's record: whole, or what its cut left at the
        view's start or end (run_logs.CUT), matched against the view drawn again."""
        images = body["images"]
        if any(i.get("sha256") == frame["bytes_sha256"] for i in images):
            return True
        cuts = [i["cut"] for i in images if i.get("cut")]
        if not cuts:
            return False
        sent = base64.b64encode(render_view(db, frame["view_id"])[0]).decode()

        def kept(part, chars, sha):
            return (
                chars >= CUT_KEPT and hashlib.sha256(part.encode()).hexdigest() == sha
            )

        return any(
            kept(sent[: c["head_chars"]], c["head_chars"], c["head_sha256"])
            or kept(sent[-c["tail_chars"] :], c["tail_chars"], c["tail_sha256"])
            for c in cuts
        )

    def frames(self, db, tool=None):
        """(body, envelope, the recorded frame of its view): the AI is told a view's number
        only (definition 29.4), the server's record says what it showed."""
        for body, envelope in self.envelopes(tool):
            for key in ("view", "whole"):
                view = envelope.get(key)
                frame = frame_of(db, view["view_id"]) if view else None
                if frame is not None:
                    yield body, envelope, frame

    def check(self, db, result, answer):
        """(status, final view ID) when the logged MCP traffic shows the steps were done."""
        # Not searched, said by the worker: a failure, never "nothing found", its reason in the
        # worker's own words to be read in the loupe (user 2026-10-16).
        if answer.get("searched") is False:
            raise ValueError(
                answer.get("not_searched_reason")
                or "The worker did not search the image"
            )
        image = image_info(db, result["image_id"])
        full = [0, 0, image["width"], image["height"]]
        if not any(e.get("ok") for _, e in self.envelopes("task_get")):
            raise ValueError("Agent did not fetch the task")
        # The whole target with nothing drawn on it: the plain image, or the agent's own
        # result shown without annotations.
        if not any(
            e.get("ok")
            and v["image_id"] == image["id"]
            and not v["annotation_ids"]
            and list(v["crop_xywh"]) == full
            and self.delivered(db, b, v)
            for b, e, v in self.frames(db, "observe")
        ):
            raise ValueError("The whole target image was not observed")
        set_row, annotations = snapshot(db, result["set_id"])
        ids = sorted(a["id"] for a in annotations)
        expected = made_status(ids)
        if answer.get("status") != expected:
            raise ValueError("Final status does not match the saved result")
        confirmed = None
        for body, envelope, view in self.frames(db):
            if not (
                view["view_id"] == answer.get("view_id")
                and envelope.get("ok")
                and self.delivered(db, body, view)
            ):
                continue
            later = self.received[self.received.index(body) + 1 :]
            if any(b["text"] and b["item_type"] == "agent_message" for b in later):
                confirmed = view
        if confirmed is None:
            raise ValueError("Final image was not delivered before the agent's answer")
        if (
            confirmed["set_id"] != result["set_id"]
            or confirmed["revision"] != set_row["revision"]
            or list(confirmed["crop_xywh"]) != full
            or sorted(confirmed["annotation_ids"]) != ids
        ):
            raise ValueError("Final overlay does not show the whole saved result")
        return expected, confirmed["view_id"]

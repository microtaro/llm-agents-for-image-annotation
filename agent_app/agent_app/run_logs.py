"""Append-only run logs: state changes, MCP calls, agent events, usage and final answers.

Images are never stored: an image in a tool result is replaced by its MIME type and
SHA-256, which is enough to prove which view reached the model.
"""

import base64
import hashlib
import json
import re

from pydantic import Field

from .db import encoded, now
from .errors import Model
from .run_queries import run_row

KINDS = ("state", "tool", "agent", "usage", "final")
PAYLOAD_LIMIT = 64 * 1024


class LogEntry(Model):
    seq: int = Field(description="Exclusive pagination cursor.")
    run_id: str = Field(description="Run identity.")
    result_id: str | None = Field(description="Result (image) the entry belongs to.")
    at: str = Field(description="Server UTC time.")
    kind: str = Field(description="state, tool, agent, usage or final.")
    payload: dict = Field(description="Entry content; images appear only as hashes.")


# Codex's --json record cuts a tool result over 1 MiB in the middle; the model still gets it
# whole (found 2026-10-29: it read the top and the bottom of a 1.6 MB image whose record was
# cut). What is left of an image (its head, its tail, or the head of one and the tail of the
# next) is kept as hashes to be matched against the view drawn again (run_checks.Trace).
CUT = re.compile(r"([A-Za-z0-9+/=]*)…\d+ chars truncated…([A-Za-z0-9+/=]*)")


def strip_images(value, images):
    """Copy of value with image data replaced by {mime_type, sha256}; hashes go to images."""
    if isinstance(value, list):
        return [strip_images(v, images) for v in value]
    if not isinstance(value, dict):
        return value
    if value.get("type") == "image" and isinstance(value.get("data"), str):
        mime = value.get("mimeType", value.get("mime_type"))
        try:
            data = base64.b64decode(value["data"], validate=True)
        except ValueError:
            cut = CUT.fullmatch(value["data"])
            why = "cut by the CLI's record" if cut else "invalid base64"
            ref = {"mime_type": mime, "sha256": None, "unavailable": why}
            if cut:
                ref["cut"] = {
                    "head_sha256": hashlib.sha256(cut[1].encode()).hexdigest(),
                    "head_chars": len(cut[1]),
                    "tail_sha256": hashlib.sha256(cut[2].encode()).hexdigest(),
                    "tail_chars": len(cut[2]),
                }
        else:
            ref = {"mime_type": mime, "sha256": hashlib.sha256(data).hexdigest()}
        images.append(ref)
        return {"type": "image", "image_ref": ref}
    return {k: strip_images(v, images) for k, v in value.items()}


def normalize_result(result):
    """Decode the CLI's JSON-text CallToolResult so structured_content is a dict."""
    if result is None:
        return None
    result = dict(result)
    content = result.get("content")
    if (
        result.get("structured_content") is None
        and isinstance(content, list)
        and len(content) == 1
        and isinstance(content[0], dict)
        and content[0].get("type") == "text"
        and isinstance(content[0].get("text"), str)
    ):
        try:
            decoded = json.loads(content[0]["text"])
        except ValueError:
            decoded = None
        if isinstance(decoded, dict) and "structuredContent" in decoded:
            result.update(decoded)
    envelope = result.get("structured_content") or result.get("structuredContent")
    result["structured_content"] = envelope if isinstance(envelope, dict) else {}
    return result


def append(db, run_id, result_id, kind, payload):
    """Insert one entry (inside the caller's transaction, or on its own)."""
    if kind not in KINDS:
        raise ValueError("Unknown log kind")
    text = encoded(payload)
    if len(text.encode()) > PAYLOAD_LIMIT:
        text = encoded(
            {
                "truncated": True,
                "summary": {
                    k: payload[k]
                    for k in ("tool", "status", "ok", "error", "type")
                    if k in payload
                },
            }
        )
    at = now()
    with db.lock:
        cursor = db.connection.execute(
            "INSERT INTO run_logs(run_id,result_id,at,kind,payload_json) VALUES(?,?,?,?,?)",
            (str(run_id), result_id, at, kind, text),
        )
    return {
        "seq": cursor.lastrowid,
        "run_id": str(run_id),
        "result_id": result_id,
        "at": at,
        "kind": kind,
        "payload": json.loads(text),
    }


def page(db, run_id, after, limit):
    run_row(db, run_id)
    rows = db.execute(
        "SELECT * FROM run_logs WHERE run_id=? AND seq>? ORDER BY seq LIMIT ?",
        (str(run_id), after, limit + 1),
    )
    return {
        "items": [
            {
                "seq": r["seq"],
                "run_id": r["run_id"],
                "result_id": r["result_id"],
                "at": r["at"],
                "kind": r["kind"],
                "payload": json.loads(r["payload_json"]),
            }
            for r in rows[:limit]
        ],
        "next_cursor": rows[limit - 1]["seq"] if len(rows) > limit else None,
    }

"""The dataset's notes (docs/2026-10-09-agent-app-design.md 3.7): what a worker found that the
other workers should know (Grok Bot keeps such facts in one place every bot reads; here a
conversation is one worker's, the data is everyone's, and a note is how a finding travels).
A note changes no data a person relies on, so it is no box; its worker is kept.
"""

from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import StringConstraints

from .datasets import dataset_row
from .db import now
from .errors import Model

router = APIRouter(prefix="/v1")
SHOWN = 20  # notes a worker reads with every answer, newest first


class NoteInput(Model):
    text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]


def note_out(row):
    return {
        "id": row["id"],
        "agent": row["agent"],
        "text": row["text"],
        "created_at": row["created_at"],
    }


def latest_notes(db, dataset_id, limit=SHOWN):
    return [
        note_out(r)
        for r in db.execute(
            "SELECT * FROM notes WHERE dataset_id=? ORDER BY id DESC LIMIT ?",
            (dataset_id, limit),
        )
    ]


@router.get("/datasets/{dataset_id}/notes")
def list_notes_route(request: Request, dataset_id: str):
    db = request.app.state.db
    dataset_row(db, dataset_id)
    return {"notes": latest_notes(db, dataset_id, 200)}


@router.post("/datasets/{dataset_id}/notes", status_code=201)
def add_route(request: Request, dataset_id: str, body: NoteInput):
    db = request.app.state.db
    dataset_row(db, dataset_id)
    # The worker the server bound the call to (its MCP headers), else the person.
    agent = request.headers.get("x-annotation-agent") or "person"
    with db.transaction():
        db.execute(
            "INSERT INTO notes(dataset_id, agent, text, created_at) VALUES(?,?,?,?)",
            (dataset_id, agent, body.text, now()),
        )
    row = db.one("SELECT * FROM notes WHERE id=last_insert_rowid()")
    return note_out(row)

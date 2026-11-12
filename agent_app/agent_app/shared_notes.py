"""What every worker AI gets besides the plan (definition 18.15, user 2026-10-17: scattered, they
can contradict): ① the fixed rules of the work (worker_prompt.yaml, the server's; how to use the
tools and the answer's form) and ② the shared notes for every dataset, kept as versions; the
plan (③) wins where it says otherwise. A run holds the version of the notes it used, as its way
holds the model and effort, so a run of the same way gets the same words.
"""

import hashlib
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import Field

from .actors import who_of
from .db import now
from .errors import Model, not_found

router = APIRouter(prefix="/v1")

RULES = (Path(__file__).parent / "worker_prompt.yaml").read_text(encoding="utf-8")

# The first version: the settings' advice before the notes were versions (Sonnet needed it in
# annotation_server), in words a person and the worker AI both read (user 2026-10-17: the field
# names refs[i] meant nothing on the screen). In English, the worker's language: the database is
# made before anyone's language is known (2026-11-05: Japanese on an English person's plan screen).
FIRST = (
    "Even when the target image is the same as a reference image, look at the whole target image"
    " before annotating. Do not save a reference image's example boxes as the result without"
    " checking them yourself."
)


def latest(db):
    """The notes now: {revision, text, created_at, created_by}, or None."""
    row = db.one("SELECT * FROM shared_notes ORDER BY revision DESC LIMIT 1")
    return dict(row) if row else None


def notes_at(db, revision):
    row = db.one("SELECT * FROM shared_notes WHERE revision=?", (revision,))
    if row is None:
        raise not_found("Shared notes version")
    return dict(row)


def save(db, text, actor):
    """A new version, unless the words are those of the version now."""
    now_kept = latest(db)
    if now_kept and now_kept["text"] == text:
        return now_kept
    revision = (now_kept["revision"] if now_kept else 0) + 1
    with db.transaction():
        db.execute(
            "INSERT INTO shared_notes(revision, text, created_at, created_by)"
            " VALUES(?,?,?,?)",
            (revision, text, now(), actor),
        )
    return notes_at(db, revision)


def worker_gets(db):
    """What a worker AI gets besides the plan, for the workers who write the plan (18.15)."""
    notes = latest(db)
    return {
        "rules": RULES,
        "shared_notes": {"revision": notes["revision"], "text": notes["text"]}
        if notes
        else None,
    }


class NotesInput(Model):
    text: str = Field(max_length=4000)


@router.get("/shared-notes")
def notes_route(request: Request):
    db = request.app.state.db
    return {
        "latest": latest(db),
        "versions": [
            dict(r)
            for r in db.execute(
                "SELECT revision, created_at, created_by FROM shared_notes"
                " ORDER BY revision DESC"
            )
        ],
    }


@router.put("/shared-notes")
def save_route(request: Request, body: NotesInput):
    return save(request.app.state.db, body.text.strip(), who_of(request))


@router.get("/worker-rules")
def rules_route():
    return {"text": RULES, "sha256": hashlib.sha256(RULES.encode()).hexdigest()}

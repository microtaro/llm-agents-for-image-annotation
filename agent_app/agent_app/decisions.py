"""Decisions (definition 21.3): what a press fixed and that changed the facts, who decided it,
who asked for it and the proposal it came from (one at most), only added to. The function that
carries a decision out records it in its own transaction, and what it made holds the
decision's id: a run (runs.decision_id), a stop (runs.stop_decision_id), the rows of what
training uses (uses.decision_id). A person's own press makes no proposal (only a worker's box
waits for a person).
"""

import json
from dataclasses import dataclass

from . import actors
from .db import encoded, new_id, now
from .errors import ApiError


@dataclass(frozen=True)
class By:
    """Who decides, and through what: the proposal a person applies (the server names it in the
    inner call), or the id the server gave a person's own decision to tell it in the chat."""

    who: str
    proposal_id: str | None = None
    decision_id: str | None = None


def by_of(request):
    return By(
        actors.who_of(request),
        request.headers.get("x-annotation-proposal"),
        request.headers.get("x-annotation-decision"),
    )


def record(db, dataset_id, kind, content, by: By, outcome=None):
    """Inside the caller's transaction: the decision added; its id. A proposal it comes from is
    being applied, of the same dataset (a library's decision, dataset_id None, may come from a
    dataset's box: a label renamed), and asked for it."""
    asked = by.who
    if by.proposal_id is not None:
        from .proposals import box_row  # a box is decided by recording its decision

        box = box_row(db, by.proposal_id)
        if box["state"] != "applying" or dataset_id not in (None, box["dataset_id"]):
            raise ApiError(
                409,
                "proposal_not_applying",
                "The decision names a proposal that is not being applied here",
            )
        asked = box["made_by"]
    decision_id = by.decision_id or new_id("dec-")
    db.execute(
        "INSERT INTO decisions(id, dataset_id, kind, content_json, decided_by, requested_by,"
        " proposal_id, outcome_json, decided_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            decision_id,
            dataset_id,
            kind,
            encoded(content),
            by.who,
            asked,
            by.proposal_id,
            encoded(outcome) if outcome is not None else None,
            now(),
        ),
    )
    return decision_id


def decision_out(row):
    return {
        "id": row["id"],
        "dataset_id": row["dataset_id"],
        "kind": row["kind"],
        "content": json.loads(row["content_json"]),
        "decided_by": row["decided_by"],
        "requested_by": row["requested_by"],
        "proposal_id": row["proposal_id"],
        "outcome": json.loads(row["outcome_json"]) if row["outcome_json"] else None,
        "decided_at": row["decided_at"],
    }


def of_box(db, proposal_id):
    """The decision a box was decided by, None before one."""
    return db.one("SELECT * FROM decisions WHERE proposal_id=?", (proposal_id,))


def get_decision(db, decision_id):
    row = db.one("SELECT * FROM decisions WHERE id=?", (decision_id,))
    return decision_out(row) if row else None

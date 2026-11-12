"""Fixing the training data (types design 7.3; DatasetSnapshot): what training gets now (the
adoption, which the marks, the choices and a person's fixes change at once, as a draft) is kept
as one numbered version when a person decides. Training uses the version of that time.

The band shows, before deciding, what the version would hold (the parts of the adoption) and
which images differ from the last version.
"""

import json

from fastapi import APIRouter, Request
from pydantic import Field

from .actors import who_of
from .adoption import adoption
from .datasets import dataset_row
from .db import encoded, now
from .errors import ApiError, Model
from .image_state import image_states
from .images import image_names
from .instructions import latest_basis, latest_revision, requirement
from .run_queries import result_row

router = APIRouter(prefix="/v1")


class FixTrainingInput(Model):
    note: str = Field("", max_length=1000, description="Why it is fixed now; optional.")


def described(db, result_id):
    """A result for a person: whose (a person's fix or the AI's), which model, when; None for
    nothing used."""
    if not result_id:
        return None
    row = result_row(db, result_id)
    settings = json.loads(row["settings_json"]) if row["settings_json"] else {}
    return {
        "result_id": result_id,
        "record_id": row["record_id"],
        "record_number": row["record_number"],
        "record_at": row["record_at"],
        "model": settings.get("model"),
        "by": row["result_by"],
        "record_kind": row["record_kind"],
    }


def _now(db, dataset_id):
    """Each image's result for training now (None: nothing; it is left out or has none)."""
    items = adoption(db, dataset_id)["items"]
    return items, {i["image_id"]: i.get("result_id") for i in items}


def snapshots(db, dataset_id):
    """The dataset's fixed training data, the newest first."""
    return db.execute(
        "SELECT * FROM training_snapshots WHERE dataset_id=? ORDER BY number DESC",
        (dataset_id,),
    )


def _last(db, dataset_id):
    return next(iter(snapshots(db, dataset_id)), None)


def training_state(db, dataset_id):
    """The band: the next number, what it would hold, and what changes from the last one."""
    dataset_row(db, dataset_id)
    if latest_revision(db, dataset_id) is None:
        # Before a version nothing is used, of the images there are (found 2026-10-17: "used
        # 0/0" beside "annotate 0/6" on a dataset copied with its plan as a draft).
        _, states = image_states(db, dataset_id, *latest_basis(db, dataset_id))
        excluded = sum(s["excluded"] for s in states.values())
        return {
            "last": None,
            "next": 1,
            "parts": {"none": len(states) - excluded, "excluded": excluded},
            "used": 0,
            "images": len(states),
            "changed": [],
        }
    _, key, _ = requirement(db, dataset_id)
    items, chosen = _now(db, dataset_id)
    last = _last(db, dataset_id)
    before = json.loads(last["items_json"]) if last else {}
    changed = [
        image_id
        for image_id in chosen
        if (before.get(image_id) if last else None) != chosen[image_id]
    ]
    names = image_names(db, changed)
    parts = {"human": 0, "picked": 0, "rule": 0, "none": 0, "excluded": 0}
    for i in items:
        if i["source"] == "excluded":
            parts["excluded"] += 1
        elif i["source"] != "result":
            parts["none"] += 1
        elif i.get("by") == "human":
            parts["human"] += 1
        elif i.get("picked"):
            parts["picked"] += 1
        else:
            parts["rule"] += 1
    return {
        "requirement_key": key,
        # The fixed version and how many images it holds (Sol 2026-10-13: "used for training
        # 4" was read as what training has, while the fixed version held 0).
        "last": {
            "number": last["number"],
            "created_at": last["created_at"],
            "used": sum(1 for r in before.values() if r),
        }
        if last
        else None,
        "next": (last["number"] + 1) if last else 1,
        "parts": parts,
        "used": sum(1 for r in chosen.values() if r),
        "images": len(items),
        # The images whose result for training differs from the last version (all, before one).
        "changed": [
            {
                "image_id": i,
                "name": names.get(i, i),
                "before": described(db, before.get(i)) if last else None,
                "after": described(db, chosen[i]),
            }
            for i in changed
        ],
    }


def fix_training(db, dataset_id, body: FixTrainingInput, actor):
    dataset_row(db, dataset_id)
    requirement(db, dataset_id)  # no version yet: nothing to fix
    with db.transaction():
        _, chosen = _now(db, dataset_id)
        last = _last(db, dataset_id)
        number = (last["number"] + 1) if last else 1
        db.execute(
            "INSERT INTO training_snapshots(dataset_id,number,created_at,created_by,"
            "items_json,note) VALUES(?,?,?,?,?,?)",
            (dataset_id, number, now(), actor, encoded(chosen), body.note or None),
        )
    return training_state(db, dataset_id)


@router.get("/datasets/{dataset_id}/training")
def state_route(request: Request, dataset_id: str):
    from .run_routes import db_of, no_worker

    no_worker(request)
    return training_state(db_of(request), dataset_id)


@router.post("/datasets/{dataset_id}/training", status_code=201)
def fix_training_route(request: Request, dataset_id: str, body: FixTrainingInput):
    """［学習用データを確定する］: a person's decision; the AI cannot make it."""
    from .run_routes import db_of, no_worker

    no_worker(request)
    if request.headers.get("x-annotation-agent"):
        raise ApiError(403, "agent_scope", "Only a person fixes the training data")
    return fix_training(db_of(request), dataset_id, body, who_of(request))

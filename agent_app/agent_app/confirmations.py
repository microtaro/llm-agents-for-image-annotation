"""What a person checked (definition 85.5): an image's annotation now seen to be right by a
version's criteria, added and never written over. Running by a plan is not checking it (user
2026-10-30: made by the criteria now and checked are two facts). The images' states read it
(image_state).
"""

from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import Field

from . import decisions
from .datasets import check_in_dataset, dataset_row
from .db import new_id, now
from .errors import ApiError, Model, not_found
from .images import image_names

router = APIRouter(prefix="/v1")


class ConfirmInput(Model):
    image_ids: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=80)]],
        Field(min_length=1, max_length=10000),
    ] = Field(
        description="Images of the dataset whose annotation now a person checked."
    )
    revision: int = Field(
        ge=1,
        description="The plan's version by whose criteria they were checked (the latest one"
        " when they are checked for the plan now).",
    )


def checked_by(db, dataset_id):
    """{result id: the versions by whose criteria a person checked it}."""
    found = {}
    for r in db.execute(
        "SELECT result_id, revision FROM confirmations WHERE dataset_id=?",
        (dataset_id,),
    ):
        found.setdefault(r["result_id"], set()).add(r["revision"])
    return found


def confirm(db, dataset_id, body: ConfirmInput, by):
    """The decision (definition 85.5): each image's annotation now, by that version, checked by
    its criteria, in one transaction."""
    # The images' states read what was checked: read at call time.
    from .image_state import image_states
    from .instructions import basis_of, version_payload
    from .run_inputs import refuse_writing

    dataset_row(db, dataset_id)
    payload = version_payload(db, dataset_id, body.revision)
    if payload is None:
        raise not_found("Instruction version")
    for image_id in body.image_ids:
        check_in_dataset(db, dataset_id, image_id)
    with db.transaction():
        refuse_writing(db, dataset_id, body.image_ids)
        _, states = image_states(db, dataset_id, *basis_of(payload))
        missing = [i for i in body.image_ids if states[i]["now"] is None]
        if missing:
            names = image_names(db, missing)
            raise ApiError(
                409,
                "nothing_to_confirm",
                "An image has no annotation by that version to check",
                {"images": [names.get(i, i) for i in missing]},
            )
        content = {"revision": body.revision, "image_ids": body.image_ids}
        outcome = {"images": len(body.image_ids)}
        decision_id = decisions.record(db, dataset_id, "confirm", content, by, outcome)
        for image_id in body.image_ids:
            db.execute(
                "INSERT INTO confirmations(id, dataset_id, image_id, result_id, revision,"
                " decision_id, confirmed_by, confirmed_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    new_id("cnf-"),
                    dataset_id,
                    image_id,
                    states[image_id]["now"]["result_id"],
                    body.revision,
                    decision_id,
                    by.who,
                    now(),
                ),
            )
    return {"images": len(body.image_ids), "revision": body.revision}


@router.post("/datasets/{dataset_id}/confirmations")
def post_confirm(request: Request, dataset_id: str, body: ConfirmInput):
    return confirm(request.app.state.db, dataset_id, body, decisions.by_of(request))

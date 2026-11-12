"""Results carried over (definition 85.15): each image's annotation now by a version of this
dataset or of another one, copied as this dataset's plan's result, as one record (a copy,
reason carry). Only what is missing is filled: an image with an annotation now by the plan is
not written over. Labels are matched by the library's id; an object of a label the plan does
not have is left out, and the values of attributes the plan's label lacks are not copied (the
ones it has and the source lacks stay empty).
"""

from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import Field

from . import decisions
from .copies import copied_objects, copy_result, insert_copy
from .datasets import check_in_dataset, dataset_row, image_ids
from .errors import ApiError, Model, not_found
from .image_state import image_states
from .instructions import basis_of, latest_row, version_payload
from .label_ids import names_in
from .label_rules import check_creates
from .run_inputs import refuse_writing
from .run_queries import made_criteria, next_number

router = APIRouter(prefix="/v1")


class CarryInput(Model):
    from_dataset_id: str = Field(
        min_length=1,
        max_length=80,
        description="The dataset the results come from (this one too, for another version's).",
    )
    from_revision: int = Field(
        ge=1,
        description="Its version: each image's annotation now by that version is carried.",
    )
    image_ids: (
        Annotated[
            list[Annotated[str, Field(min_length=1, max_length=80)]],
            Field(min_length=1, max_length=10000),
        ]
        | None
    ) = Field(None, description="Images of this dataset; null: every image.")


def carry_of(db, dataset_id, body: CarryInput):
    """The carrying worked out, nothing written: the dataset's latest version, the plan's
    definitions, the result each image takes ({image id: source result id}), the images not
    carried by why (none: no annotation there; already: one by the plan here; not_there: not
    an image of that dataset; unfit: breaks the plan's label rules), the objects left out (a
    label the plan does not have) and how many carried are made by other criteria."""
    dataset_row(db, dataset_id)
    row = latest_row(db, dataset_id)
    if row is None:
        raise ApiError(422, "instruction_required", "Create an instruction first")
    source = version_payload(db, body.from_dataset_id, body.from_revision)
    if source is None:
        raise not_found("Instruction version")
    plan = version_payload(db, dataset_id, row["revision"])
    definitions = plan["label_definitions"]
    wanted = body.image_ids or image_ids(db, dataset_id)
    for image_id in wanted:
        check_in_dataset(db, dataset_id, image_id)
    _, mine = image_states(db, dataset_id, *basis_of(plan))
    _, theirs = image_states(db, body.from_dataset_id, *basis_of(source))
    named = names_in(db, body.from_dataset_id, definitions)
    planned = {d["name"] for d in definitions}

    def label_of(result, label):
        # The plan's name of the label (by its id); None when the plan does not have it.
        name = named(result["instruction_revision"], label)
        return name if name in planned else None

    carried, left_out, other = {}, 0, 0
    skipped = dict.fromkeys(("none", "already", "not_there", "unfit"), 0)
    criteria = basis_of(plan)[1]
    for image_id in wanted:
        if image_id not in theirs:
            skipped["not_there"] += 1
        elif mine[image_id]["now"] is not None:
            skipped["already"] += 1
        elif theirs[image_id]["now"] is None:
            skipped["none"] += 1
        else:
            result_id = theirs[image_id]["now"]["result_id"]
            row_of, _, creates, dropped = copied_objects(
                db, result_id, None, label_of, definitions
            )
            try:
                check_creates(definitions, creates)
            except ApiError:
                skipped["unfit"] += 1
                continue
            carried[image_id] = result_id
            left_out += dropped
            other += made_criteria(db, row_of) != criteria
    return {
        "row": row,
        "definitions": definitions,
        "label_of": label_of,
        "carried": carried,
        "skipped": skipped,
        "left_out": left_out,
        "other": other,
        "now": {i: (mine[i]["now"] or {}).get("result_id") for i in wanted},
    }


def carry(db, dataset_id, body: CarryInput, by):
    """The decision (definition 85.15), in one transaction."""
    with db.transaction():
        found = carry_of(db, dataset_id, body)
        if not found["carried"]:
            raise ApiError(
                409,
                "nothing_to_carry",
                "No image takes a result: none there, one here already, or it breaks the plan",
                {"skipped": found["skipped"]},
            )
        refuse_writing(db, dataset_id, list(found["carried"]))
        row, number = found["row"], next_number(db, dataset_id)
        content = body.model_dump(mode="json")
        outcome = {
            "record_number": number,
            "images": len(found["carried"]),
            "skipped": found["skipped"],
        }
        decision_id = decisions.record(db, dataset_id, "carry", content, by, outcome)
        copy_id = insert_copy(
            db,
            dataset_id,
            number,
            "carry",
            {
                "from_dataset_id": body.from_dataset_id,
                "from_revision": body.from_revision,
            },
            (row["revision"], row["requirement_key"]),
            decision_id,
            by.who,
        )
        for position, result_id in enumerate(found["carried"].values()):
            copy_result(
                db,
                copy_id,
                position,
                result_id,
                None,
                found["label_of"],
                found["definitions"],
            )
    return {"record_id": copy_id, **outcome}


@router.post("/datasets/{dataset_id}/carry")
def post_carry(request: Request, dataset_id: str, body: CarryInput):
    return carry(request.app.state.db, dataset_id, body, decisions.by_of(request))

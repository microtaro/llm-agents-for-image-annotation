"""Renaming a label (step 12; user 2026-10-05): typing a new name made another label, so its
masters became incomplete. A label is the library's (definition 26.1), one for every dataset, so
a rename is a decision of the library: the label's name changes, and every dataset that uses
the label (its latest version or its plan's draft) carries everything that names it over, in
one transaction: the next version with the new name when its latest version has the label, the
label's color and the drafts. Run results, references
among them, are records and keep the old name (read with the name now, label_ids.names_now).
"""

import json
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import Field, StringConstraints

from . import decisions
from .datasets import dataset_row
from .db import new_id
from .drafts import plans_held
from .errors import ApiError, Model
from .instructions import INPUT, InstructionInput, latest_row, save_instruction
from .label_colors import move_color
from .label_library import datasets_of, label_named_as, relabel_plan, rename
from .shapes import LABEL_MAX

router = APIRouter(prefix="/v1")
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LABEL_MAX)
]


class RenameInput(Model):
    old: Name = Field(alias="from", description="The label's name now.")
    new: Name = Field(alias="to", description="Its new name.")


def rename_label(db, dataset_id, body: RenameInput, by):
    """A decision of the library (definitions 22.4, 26.1): the label named old in this dataset's
    plan (its latest version or its draft) takes the new name everywhere."""
    old, new = body.old, body.new
    dataset_row(db, dataset_id)
    if not plans_held(db, dataset_id):
        raise ApiError(422, "instruction_required", "Create an instruction first")
    label = label_named(db, dataset_id, old)
    if label is None:
        raise ApiError(404, "not_found", "No such label in the dataset's plan")
    taken = label_named_as(db, new)
    if taken is not None and taken["id"] != label["id"]:
        raise ApiError(409, "label_exists", "A label with the new name already exists")
    changed = []
    # The decision's id first: the versions it makes in every dataset name it (22.1).
    by = replace(by, decision_id=by.decision_id or new_id("dec-"))
    with db.transaction():
        rename(db, label["id"], new)
        for target in datasets_of(db)[label["id"]]:
            changed.append(
                _rename_in(db, target, label["id"], new, by.who, by.decision_id)
            )
        # The library's: it outlives the dataset it was asked in, whose versions are not the
        # only ones it made (2026-10-30 review: deleting that dataset took it from the others).
        decisions.record(
            db,
            None,
            "label",
            {"op": "rename", "label_id": label["id"], "from": old, "to": new},
            by,
            {"datasets": changed},
        )
    here = next(c for c in changed if c["dataset_id"] == dataset_id)
    return {**here, "renamed": {"from": old, "to": new}, "datasets": changed}


def label_named(db, dataset_id, name):
    """The label of that name in the dataset's plan (its latest version or its draft); None."""
    return next(
        (
            d
            for plan in plans_held(db, dataset_id)
            for d in plan["label_definitions"]
            if d["name"] == name
        ),
        None,
    )


def _rename_in(db, dataset_id, label_id, new, actor, decision_id):
    """One dataset's label renamed: the next version when its latest version has it, its color
    and its drafts. revision: the version saved, none for a plan that is a draft only."""
    row = latest_row(db, dataset_id)
    version = json.loads(row["payload_json"]) if row else None
    old = next(
        d["name"]
        for plan in plans_held(db, dataset_id)
        for d in plan["label_definitions"]
        if d.get("id") == label_id
    )
    revision = None
    if version and any(d.get("id") == label_id for d in version["label_definitions"]):
        payload = relabel_plan(version, {old: new})
        revision = save_instruction(
            db,
            dataset_id,
            InstructionInput.model_validate({k: payload[k] for k in INPUT}),
            actor,
            decision_id=decision_id,
            references=payload.get("references"),
            # The latest version renamed (definition 15.1).
            origin={
                "kind": "version",
                "dataset_id": dataset_id,
                "revision": row["revision"],
            },
        )["revision"]
    move_color(db, dataset_id, old, new)
    _rename_in_drafts(db, dataset_id, old, new, actor)
    return {"dataset_id": dataset_id, "revision": revision}


def _rename_in_drafts(db, dataset_id, old, new, actor):
    """A draft keeps what was being made, under the new name and requirement; the plan's draft
    as a write (the draft is its write, definition 11.2)."""
    from .drafts import plan_draft, write_plan
    from .fixes import relabel_fix_drafts

    if plan_draft(db, dataset_id) is not None:
        write_plan(db, dataset_id, lambda plan: relabel_plan(plan, {old: new}), actor)
    # A rename keeps the label's id: the requirement and the results stay.
    relabel_fix_drafts(db, dataset_id, {old: new}, {}, {})


@router.post("/datasets/{dataset_id}/labels/rename")
def post_rename(
    request: Request,
    dataset_id: str,
    body: RenameInput,
):
    return rename_label(
        request.app.state.db, dataset_id, body, decisions.by_of(request)
    )

"""Changing a label in one dataset (definition 79; user 2026-10-29: a dataset had named a library
label wrongly, and renaming the label would change every dataset that uses it). The library's
labels stay as they are, as other tools do (Encord's change class, CVAT's relabel): the
dataset's next version takes the other label, and each image's annotation now is made again
with it, as one record, a label change. The results before stay as records; nothing runs again.
"""

import json
from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import Field, StringConstraints

from . import decisions
from .copies import copy_result, insert_copy
from .datasets import dataset_row, image_ids
from .errors import ApiError, Model
from .image_state import image_states
from .instructions import (
    INPUT,
    InstructionInput,
    latest_row,
    requirement_key,
    save_instruction,
)
from .label_colors import move_color
from .label_ids import names_now
from .label_library import key_of, with_library
from .run_inputs import refuse_writing
from .run_queries import next_number
from .shapes import LABEL_MAX

router = APIRouter(prefix="/v1")
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LABEL_MAX)
]


class LabelChangeInput(Model):
    old: Name = Field(
        alias="from", description="A label of the dataset's latest version."
    )
    new: Name = Field(
        alias="to",
        description="The label it is: one of the plan's, one of the library's or a new one.",
    )


def _taken(definition):
    """How a label is taken, what must agree to merge two (definition 79.2): its parent too
    (2026-10-30: a child changed to another parent's child was kept under the first parent)."""
    return {
        "shape": definition["shape"],
        "parent": definition.get("parent"),
        "attributes": sorted(
            (a["name"], a.get("type"), tuple(a.get("choices") or ()))
            for a in definition.get("attributes") or []
        ),
    }


def change_of(db, dataset_id, old, new):
    """The change worked out, nothing written: the latest version and its label old, the next
    version's content (the library's labels, definition 26.1) with its requirement, the label
    it takes there, and the images' annotations now. Raises the refusals of definition 79.2."""
    row = latest_row(db, dataset_id)
    if row is None:
        raise ApiError(422, "instruction_required", "Create an instruction first")
    version = json.loads(row["payload_json"])
    definitions = version["label_definitions"]
    label = next((d for d in definitions if d["name"] == old), None)
    if label is None:
        raise ApiError(
            404, "not_found", "No such label in the dataset's latest version"
        )
    if key_of(new) == key_of(old):
        raise ApiError(422, "same_label", "The label is that one already")
    there = next((d for d in definitions if key_of(d["name"]) == key_of(new)), None)
    for field, value in _taken(there).items() if there else ():
        if value != _taken(label)[field]:
            raise ApiError(
                422,
                "label_definition_differs",
                "The label is taken another way in the plan",
                {"label": there["name"], "field": field},
            )
    changed = []
    for d in definitions:
        if d is label:
            if there is not None:
                continue
            # Without its id: the label of that name (the library's, else a new one).
            d = {k: v for k, v in d.items() if k != "id"} | {"name": new}
        if d.get("parent") == old:
            d = {**d, "parent": there["name"] if there else new}
        changed.append(d)
    # With ids now, so the version saved has these (label_ids.with_ids keeps an id given).
    planned = with_library(db, {**version, "label_definitions": changed}, definitions)
    to = planned["label_definitions"][
        changed.index(
            next(d for d in changed if d["name"] == (there or {}).get("name"))
        )
        if there
        else definitions.index(label)
    ]
    # Every image's annotation now by the version's requirement, whatever criteria.
    _, states = image_states(db, dataset_id, row["requirement_key"], None)
    return {
        "row": row,
        "references": version.get("references") or [],
        "label": label,
        "to": to,
        "planned": planned,
        "requirement_key": requirement_key(planned["label_definitions"]),
        "now": {i: s["now"] for i, s in states.items() if s["now"] is not None},
    }


def change_label(db, dataset_id, body: LabelChangeInput, by):
    """The decision (definition 79.3), in one transaction."""
    dataset_row(db, dataset_id)
    found = change_of(db, dataset_id, body.old, body.new)
    images = image_ids(db, dataset_id)
    refuse_writing(db, dataset_id, images)
    row, label, to, now_of = found["row"], found["label"], found["to"], found["now"]
    revision, key = row["revision"] + 1, found["requirement_key"]
    # A reference's result that is not its image's annotation now first, so the annotation now
    # made again is the image's newest (image_state).
    held = {n["result_id"] for n in now_of.values()}
    sources = [
        (p["result_id"], p["revision"])
        for p in found["references"]
        if p["result_id"] not in held
    ] + [(n["result_id"], None) for n in now_of.values()]
    name = names_now(db, dataset_id)
    with db.transaction():
        number = next_number(db, dataset_id)
        content = {
            "op": "change",
            "from": label["name"],
            "to": to["name"],
            "from_id": label["id"],
            "to_id": to["id"],
        }
        outcome = {"revision": revision, "record_number": number, "images": len(now_of)}
        decision_id = decisions.record(db, dataset_id, "label", content, by, outcome)
        copy_id = insert_copy(
            db,
            dataset_id,
            number,
            "label",
            {"from": label["name"], "to": to["name"]},
            (revision, key),
            decision_id,
            by.who,
        )

        def relabeled(source, named):
            # The label as the version named it now; the changed one takes the other.
            now_named = name(source["instruction_revision"], named)
            return to["name"] if now_named == label["name"] else now_named

        made = {
            result_id: copy_result(
                db,
                copy_id,
                position,
                result_id,
                at,
                relabeled,
                found["planned"]["label_definitions"],
            )
            for position, (result_id, at) in enumerate(sources)
        }
        references = [{**p, **made[p["result_id"]]} for p in found["references"]]
        planned = {**found["planned"], "references": references}
        saved = save_instruction(
            db,
            dataset_id,
            InstructionInput.model_validate({k: planned[k] for k in INPUT}),
            by.who,
            decision_id=decision_id,
            references=references,
            origin={
                "kind": "version",
                "dataset_id": dataset_id,
                "revision": row["revision"],
            },
        )
        if (saved["revision"], saved["requirement_key"]) != (revision, key):
            raise RuntimeError(
                "The version saved is not the one the change was made for"
            )
        _relabel_drafts(db, dataset_id, found, made, key, by.who)
        move_color(db, dataset_id, label["name"], to["name"])
    return {
        "dataset_id": dataset_id,
        "revision": revision,
        "record_id": copy_id,
        "record_number": number,
        "images": len(now_of),
        "changed": {"from": label["name"], "to": to["name"]},
    }


def _relabel_drafts(db, dataset_id, found, made, key, actor):
    """The plan's draft takes the change; a person's fix being made, its label, the result it
    is made from (the one made again) and the requirement (definition 79.3)."""
    from .drafts import plan_draft, write_plan
    from .fixes import relabel_fix_drafts

    if plan_draft(db, dataset_id) is not None:
        write_plan(
            db, dataset_id, lambda plan: _plan_changed(db, plan, found, made), actor
        )
    relabel_fix_drafts(
        db,
        dataset_id,
        {found["label"]["name"]: found["to"]["name"]},
        {found["row"]["requirement_key"]: key},
        {old: m["result_id"] for old, m in made.items()},
    )


def _plan_changed(db, plan, found, made):
    """A plan's draft with the label changed as in the version (its own labels kept)."""
    old = found["label"]["name"]
    there = next(
        (d for d in plan["label_definitions"] if d["name"] == found["to"]["name"]), None
    )
    definitions = []
    for d in plan["label_definitions"]:
        if d["name"] == old:
            if there is not None:
                continue
            d = {k: v for k, v in d.items() if k != "id"} | {
                "name": found["to"]["name"],
                "id": found["to"]["id"],
            }
        if d.get("parent") == old:
            d = {**d, "parent": found["to"]["name"]}
        definitions.append(d)
    references = [
        {**p, **made[p["result_id"]]} if p.get("result_id") in made else p
        for p in plan.get("references") or []
    ]
    return {**plan, "label_definitions": definitions, "references": references}


@router.post("/datasets/{dataset_id}/labels/change")
def post_change(request: Request, dataset_id: str, body: LabelChangeInput):
    return change_label(
        request.app.state.db, dataset_id, body, decisions.by_of(request)
    )

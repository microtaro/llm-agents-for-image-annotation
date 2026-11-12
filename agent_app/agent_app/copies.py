"""Results copied from others as one record (definition 79, 85.15): a label changed in one
dataset (reason label) or results carried from another requirement or dataset (reason carry).
Each result made is a copy of one, written as any annotation is (annotation_sets.fill, the
plan's label rules), and keeps what it was copied from (copy_results). Records are read in
run_queries.
"""

import base64

from .annotation_sets import fill, new_set, snapshot
from .db import encoded, new_id, now
from .label_rules import fitting
from .run_queries import insert_result, made_criteria, result_row
from .shapes import Create


def insert_copy(db, dataset_id, number, reason, content, version, decision_id, who):
    """Inside the caller's transaction: the record of a copy numbered number (next_number,
    taken before its decision says it), of the version (revision, requirement key) it is made
    for; its id."""
    copy_id = new_id("cpy-")
    revision, key = version
    db.execute(
        "INSERT INTO copies(id,dataset_id,number,instruction_revision,requirement_key,"
        "decision_id,reason,content_json,copied_by,copied_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            copy_id,
            dataset_id,
            number,
            revision,
            key,
            decision_id,
            reason,
            encoded(content),
            who,
            now(),
        ),
    )
    return copy_id


def _create_geometry(db, annotation):
    """An annotation's geometry as a create takes it (a mask as its stored PNG)."""
    if annotation["mask_sha256"]:
        data = db.files.read("masks", annotation["mask_sha256"])
        return {"type": "mask", "png_base64": base64.b64encode(data).decode()}
    return annotation["geometry"]


def copied_objects(db, result_id, revision, label_of, definitions):
    """What copying a result (its set at revision; None: as it is now) makes, nothing written:
    (its row, its objects kept, the creates, how many were left out). Each object is named
    label_of(source row, its label) and left out when that is None (its parts then have no
    parent); it keeps its number and the values the plan's label reads (label_rules.fitting)."""
    source = result_row(db, result_id)
    _, objects = snapshot(db, source["set_id"], revision)
    defined = {d["name"]: d for d in definitions}
    kept = []
    for a in objects:
        label = label_of(source, a["label"])
        if label is not None:
            kept.append((a, label))
    ids = {a["id"] for a, _ in kept}
    creates = [
        Create.model_validate(
            {
                "op": "create",
                "ref": a["id"],
                "label": label,
                "geometry": _create_geometry(db, a),
                "parent": a["parent_id"] if a["parent_id"] in ids else None,
                "attributes": fitting(defined.get(label), a["attributes"]) or None,
            }
        )
        for a, label in kept
    ]
    return source, kept, creates, len(objects) - len(kept)


def copy_result(db, copy_id, position, result_id, revision, label_of, definitions):
    """A result copied from another into the record (copied_objects), written by the plan's
    definitions (annotation_sets.fill). {result_id, set_id, revision} of it."""
    source, kept, creates, _ = copied_objects(
        db, result_id, revision, label_of, definitions
    )
    set_id = new_set(db, source["image_id"], after=source["set_id"])
    fill(db, set_id, creates, definitions, [a["number"] for a, _ in kept])
    made = insert_result(
        db, "copy", copy_id, source["image_id"], set_id, position, creates
    )
    db.execute(
        "INSERT INTO copy_results(result_id, from_result_id, from_by, from_criteria)"
        " VALUES(?,?,?,?)",
        (made, result_id, source["result_by"], made_criteria(db, source)),
    )
    return {"result_id": made, "set_id": set_id, "revision": 1}

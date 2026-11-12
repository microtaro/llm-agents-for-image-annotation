"""Adoption, computed from rules each time; what a person decided about an image's use is added
as a decision, never written over (definition 19: a result chosen, back to the rule, not used,
used again), and the images' states read the last ones (image_state.use_now).
"""

from . import decisions
from .annotation_sets import set_state
from .datasets import check_in_dataset, dataset_row
from .image_state import image_states
from .instructions import latest_basis, requirement
from .label_ids import names_now
from .run_queries import result_row


def record_use(
    db, dataset_id, image_id, kind, result_id=None, decision_id=None, fix_id=None
):
    """Inside the caller's transaction: one row of what training uses for the image added, a
    decision's (pick a result, rule, out, in) or a person's fix made (fix); the one place they
    are written (definition 21.3)."""
    db.execute(
        "INSERT INTO uses(dataset_id, image_id, kind, result_id, decision_id, fix_id)"
        " VALUES(?,?,?,?,?,?)",
        (dataset_id, image_id, kind, result_id, decision_id, fix_id),
    )


def mark_image(db, dataset_id, image_id, excluded, by):
    with db.transaction():
        dataset_row(db, dataset_id)
        check_in_dataset(db, dataset_id, image_id)
        kind = "out" if excluded else "in"
        decision_id = decisions.record(
            db, dataset_id, "use", {"op": kind, "image_id": image_id}, by
        )
        record_use(db, dataset_id, image_id, kind, decision_id=decision_id)
    return {"image_id": image_id, "excluded": excluded, "decision_id": decision_id}


def adoption(db, dataset_id):
    """Per image, in order: excluded; the result a person chose (types design 7.2), while it is
    of the requirement; the newest successful result of the requirement; else stale or none (the master step was taken out, types
    design 6). A choice made before a newer result says so (newer). Read from the images'
    states (image_state.py, definition 14): the one place the rule is applied."""
    dataset_row(db, dataset_id)
    _, key, _ = requirement(db, dataset_id)
    _, states = image_states(db, dataset_id, *latest_basis(db, dataset_id))
    items = []
    for state in states.values():
        now = state["now"]
        item = {"image_id": state["image_id"], "source": state["used"]}
        if state["used"] == "excluded":
            # What it would use once taken back, to be seen while deciding (user 2026-10-16:
            # left out, the gallery showed not even its annotation).
            if now is not None:
                item["would_result_id"] = now["result_id"]
        elif state["used"] == "result":
            item.update(
                result_id=now["result_id"],
                run_id=now["run_id"],
                model=now["model"],
                picked=now["picked"],
                by=now["by"],
                newer=now["newer"],
            )
        items.append(item)
    return {
        "requirement_key": key,
        "items": items,
        "breakdown": _breakdown(items),
        # The images a person chose for (types design 7.2: said in the breakdown).
        "picked": sum(bool(i.get("picked")) for i in items),
    }


def _breakdown(items):
    """How many images each source gives, a result's per run (data-model 8.3)."""
    counts = {}
    for item in items:
        group = (item["source"], item.get("run_id"), item.get("model"))
        counts[group] = counts.get(group, 0) + 1
    return [
        {"source": source, "run_id": run_id, "model": model, "count": count}
        for (source, run_id, model), count in counts.items()
    ]


def adopted_annotations(db, dataset_id):
    """What training reads: the adopted annotations of each image that has any source, each
    label named as the plan names it now (definition 23.4)."""
    name = names_now(db, dataset_id)
    out = []
    for item in adoption(db, dataset_id)["items"]:
        if item["source"] != "result":
            continue
        made = result_row(db, item["result_id"])
        state = set_state(db, made["set_id"])
        annotations = [
            {**a, "label": name(made["instruction_revision"], a["label"])}
            for a in state["annotations"]
        ]
        out.append({**item, "image": state["image"], "annotations": annotations})
    return {"items": out}

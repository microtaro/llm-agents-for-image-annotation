"""What the decisions of definition 22.2 other than a run and a mark show and stand on: stopping a
record, choosing an image's result, adding and taking out images, renaming or changing a label,
renaming a dataset, making and deleting a dataset. Registered with the rest in box_facts.FACTS
and CHANGED (the one place for a decision's facts); each gives (preview, premise) and what
changed by name.
"""

import json

from .datasets import check_in_dataset, dataset_row, image_ids
from .errors import invalid
from .image_state import image_states
from .images import image_from, scan_paths
from .instructions import latest_basis, latest_row
from .label_library import datasets_of, names
from .run_queries import (
    GOING,
    record_results,
    result_counts,
    result_row,
    run_number,
    run_row,
)


def _names(db, image_ids):
    from .images import image_names

    return image_names(db, image_ids)


def stop_facts(db, dataset_id, args):
    run = run_row(db, args.get("run_id"))
    if run["dataset_id"] != dataset_id:
        raise invalid("The record is of another dataset")
    found = result_counts(r["status"] for r in record_results(db, run["id"]))
    preview = {
        "run_id": run["id"],
        "run_number": run_number(db, run["id"]),
        "status": run["status"],
        "done": found["total"] - found["waiting"],
        "left": found["waiting"],
    }
    return preview, {"going": run["status"] in GOING}


def stop_changed(db, dataset_id, args, before, after):
    return {"kind": "ended", "run_number": run_number(db, args.get("run_id"))}


def pick_facts(db, dataset_id, args):
    """Which result training uses for an image: now, and after (a record's, or the rule's)."""
    image_id, result_id = args.get("image_id"), args.get("result_id")
    check_in_dataset(db, dataset_id, image_id)
    _, states = image_states(db, dataset_id, *latest_basis(db, dataset_id))
    state = states[image_id]
    now = state["now"]
    after = None
    if result_id is not None:
        row = result_row(db, result_id)
        if (row["dataset_id"], row["image_id"]) != (dataset_id, image_id):
            raise invalid("The result is not of this image of the dataset")
        after = row["record_number"]
    preview = {
        "image": {"id": image_id, "name": _names(db, [image_id]).get(image_id)},
        "now_run": now["record_number"] if now else None,
        "after_run": after,
        # Back to the rule: the newest success is used.
        "rule": result_id is None,
        "excluded_now": state["excluded"],
    }
    premise = {
        "now": now["result_id"] if now else None,
        "excluded": state["excluded"],
    }
    return preview, premise


def pick_changed(db, dataset_id, args, before, after):
    from .box_facts import _results_named

    image_id = args.get("image_id")
    if before.get("excluded") != after.get("excluded"):
        name = _names(db, [image_id]).get(image_id, image_id)
        return {"kind": "excluded", "image": name}
    return {
        "kind": "results",
        "images": _results_named(db, [image_id], {image_id: after.get("now")}),
    }


def _held(db, dataset_id):
    return set(image_ids(db, dataset_id))


def _found(db, args):
    """The image files the paths hold (as the screen's scan counts them), and how many of them
    were imported before with the other origin (a photograph or a made image): those keep
    their own (images.store_image, definition 52), so the box says so before it is decided.
    Paths with no image file are refused now (found 2026-10-19: a box said "import 2 images",
    and deciding it imported none)."""
    found = scan_paths(args.get("paths") or [])
    # A path not there is said as such (the reception's test 2026-10-29: a folder not found was
    # refused as "no image file", and said so).
    missing = [s["path"] for s in found["skipped"] if s["reason"] == "not_found"]
    if missing:
        raise invalid("These paths are not found", paths=missing)
    if not found["count"]:
        raise invalid("No image file in the paths", paths=args.get("paths"))
    made = "generated" if args.get("generated_how") else "real"
    kept = sum(
        1
        for f in found["files"]
        if (row := image_from(db, f["path"])) and row["origin"] != made
    )
    return {
        "paths": args.get("paths"),
        "found": found["count"],
        "kept": kept,
        "skipped": len(found["skipped"]),
    }


def add_facts(db, dataset_id, args):
    """How many image files the paths hold, and how many of them would import."""
    dataset_row(db, dataset_id)
    return {**_found(db, args), "images_now": len(_held(db, dataset_id))}, {}


def remove_facts(db, dataset_id, args):
    """The images by name, how many of them training uses now; their results stay."""
    ids = list(dict.fromkeys(args.get("image_ids") or []))
    held = _held(db, dataset_id)
    for image_id in ids:
        check_in_dataset(db, dataset_id, image_id)
    _, states = image_states(db, dataset_id, *latest_basis(db, dataset_id))
    names = _names(db, ids)
    preview = {
        "images": [{"id": i, "name": names.get(i, i)} for i in ids],
        "used_now": sum((states.get(i) or {}).get("used") == "result" for i in ids),
    }
    return preview, {"present": sorted(i for i in ids if i in held)}


def remove_changed(db, dataset_id, args, before, after):
    gone = [i for i in before["present"] if i not in after["present"]]
    names = _names(db, gone)
    return {"kind": "removed", "names": [names.get(i, i) for i in gone]}


def label_facts(db, dataset_id, args):
    """The names before and after and the datasets whose plans it changes (a label is the
    library's, definition 26.1)."""
    from .label_rename import label_named

    dataset_id = args.get("dataset_id") or dataset_id
    old = args.get("from")
    label = label_named(db, dataset_id, old)
    if label is None:
        raise invalid("No such label in the dataset's plan", label=old)
    latest = latest_row(db, dataset_id)
    preview = {
        "from": old,
        "to": args.get("to"),
        "datasets": len(datasets_of(db)[label["id"]]),
    }
    return preview, {"revision": latest["revision"] if latest else None}


def confirm_facts(db, dataset_id, args):
    """Images checked by a version's criteria (definition 85.5): how many, how many of them are
    annotations made by other criteria, the version; it stands on each image's annotation now
    by that version."""
    from .instructions import basis_of, version_payload

    dataset_id = args.get("dataset_id") or dataset_id
    wanted = args.get("image_ids") or []
    for image_id in wanted:
        check_in_dataset(db, dataset_id, image_id)
    payload = version_payload(db, dataset_id, args.get("revision"))
    if payload is None:
        raise invalid("No such version of the dataset's plan")
    _, states = image_states(db, dataset_id, *basis_of(payload))
    now = {i: states[i]["now"] for i in wanted}
    preview = {
        "images": len(wanted),
        "other": sum(1 for n in now.values() if n and n["other"]),
        "revision": args.get("revision"),
    }
    return preview, {"now": {i: n["result_id"] if n else None for i, n in now.items()}}


def carry_facts(db, dataset_id, args):
    """Results carried over (definition 85.15): how many images take one, the ones that do not
    by why, the objects left out, how many are made by other criteria than the plan's, where
    they come from; it stands on each image's annotation now here and there."""
    from .carry import CarryInput, carry_of

    dataset_id = args.get("dataset_id") or dataset_id
    body = CarryInput.model_validate(
        {k: v for k, v in args.items() if k != "dataset_id"}
    )
    found = carry_of(db, dataset_id, body)
    preview = {
        "images": len(found["carried"]),
        "skipped": found["skipped"],
        "left_out": found["left_out"],
        "other": found["other"],
        "from": {
            "dataset_id": body.from_dataset_id,
            "name": dataset_row(db, body.from_dataset_id)["name"],
            "revision": body.from_revision,
        },
        "revision": found["row"]["revision"],
    }
    return preview, {"now": found["now"], "carried": found["carried"]}


def carry_changed(db, dataset_id, args, before, after):
    from .box_facts import _results_named

    changed = [i for i, r in before["now"].items() if after["now"].get(i) != r]
    return {"kind": "results", "images": _results_named(db, changed, after["now"])}


def confirm_changed(db, dataset_id, args, before, after):
    from .box_facts import _results_named

    changed = [i for i, r in before["now"].items() if after["now"].get(i) != r]
    return {
        "kind": "results",
        "images": _results_named(db, changed, after["now"]),
    }


def label_changed(db, dataset_id, args, before, after):
    return {"kind": "revision", "revision": after.get("revision")}


def change_facts(db, dataset_id, args):
    """A label of this dataset changed (definition 79.5): the labels, whether the one it takes
    is the plan's or the library's already, the images made again and those with no annotation
    now, and the version it makes; it stands on the version and each image's annotation now."""
    from .label_change import change_of

    dataset_id = args.get("dataset_id") or dataset_id
    found = change_of(db, dataset_id, args.get("from"), args.get("to"))
    version = json.loads(found["row"]["payload_json"])
    preview = {
        "from": found["label"]["name"],
        "to": found["to"]["name"],
        "in_plan": any(
            d["id"] == found["to"]["id"] for d in version["label_definitions"]
        ),
        "in_library": found["to"]["id"] in names(db),
        "images": len(found["now"]),
        "without": len(_held(db, dataset_id)) - len(found["now"]),
        "next_revision": found["row"]["revision"] + 1,
    }
    premise = {
        "revision": found["row"]["revision"],
        "results": {i: n["result_id"] for i, n in sorted(found["now"].items())},
    }
    return preview, premise


def rename_facts(db, dataset_id, args):
    name = dataset_row(db, dataset_id)["name"]
    return {"from": name, "to": args.get("name")}, {"name": name}


def rename_changed(db, dataset_id, args, before, after):
    return {"kind": "renamed", "name": after.get("name")}


def create_facts(db, dataset_id, args):
    preview = {
        "name": args.get("name"),
        "purpose": args.get("purpose"),
        **_found(db, args),
    }
    return preview, {}


def _sources(db, dataset_ids):
    return [
        {
            "id": i,
            "number": dataset_row(db, i)["number"],
            "name": dataset_row(db, i)["name"],
            "images": len(_held(db, i)),
        }
        for i in dict.fromkeys(dataset_ids)
    ]


def from_facts(db, dataset_id, args):
    """The datasets it is made of by name, and its images (each once)."""
    ids = args.get("dataset_ids") or []
    sources = _sources(db, ids)
    images = set().union(*(_held(db, i) for i in ids)) if ids else set()
    preview = {
        "name": args.get("name"),
        "purpose": args.get("purpose"),
        "sources": sources,
        "images": len(images),
        "instruction": bool(args.get("instruction")) and len(sources) == 1,
    }
    return preview, {"images": {s["id"]: s["images"] for s in sources}}


def from_changed(db, dataset_id, args, before, after):
    changed = [i for i, n in before["images"].items() if after["images"].get(i) != n]
    return {
        "kind": "sources",
        "names": [dataset_row(db, i)["name"] for i in changed],
    }


def import_facts(db, dataset_id, args):
    """What the folder written out holds (definition 60.3): its datasets by name and images."""
    from .dataset_import import written_in

    found = written_in(args.get("path") or "") or {}
    datasets = found.get("datasets", []) if found.get("kind") == "app" else []
    if found.get("kind") == "coco":
        # One dataset the person named, its first version made from the JSON (60.11).
        datasets = [{"name": args.get("name") or "", "images": found["images"]}]
    preview = {
        "path": args.get("path"),
        "datasets": [{"name": d["name"], "images": d["images"]} for d in datasets],
        "images": sum(d["images"] for d in datasets),
    }
    return preview, {}


def delete_facts(db, dataset_id, args):
    """What deleting it removes (as the library asks before deleting)."""
    from .dataset_admin import deletion_counts

    target = args.get("dataset_id")
    found = deletion_counts(db, target)
    preview = {
        "dataset": {
            "id": target,
            "number": dataset_row(db, target)["number"],
            "name": dataset_row(db, target)["name"],
        },
        **{
            k: found[k]
            for k in (
                "images",
                "runs",
                "trials",
                "instructions",
                "freed_images",
                "unrecoverable",
                "active_run",
            )
        },
    }
    premise = {
        k: found[k] for k in ("images", "runs", "trials", "instructions", "active_run")
    }
    return preview, premise


def delete_changed(db, dataset_id, args, before, after):
    return {"kind": "dataset", "name": dataset_row(db, args.get("dataset_id"))["name"]}

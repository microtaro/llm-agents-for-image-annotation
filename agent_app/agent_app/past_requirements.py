"""What the images of a dataset were annotated for before, in other datasets (definition 26.5):
one entry per requirement (its key: the library's labels and how each is taken), with the
purpose of the dataset that last annotated for it, the plan to start from (that dataset's
version), how much of these images it covers, its ways of running, and each image's annotation
of it. A plan of another dataset holding these images that never ran is one too, with nothing
annotated (34.2: the existing plans of these images). The interview starts from it (25.2-12,
34.2). Read only.
"""

import json
from collections import defaultdict

from fastapi import APIRouter, Request

from .annotation_sets import current
from .datasets import dataset_row, image_ids, shared_with
from .image_state import image_states
from .instructions import latest_rows, version_payload
from .label_colors import dataset_colors
from .label_ids import names_now
from .label_library import names
from .run_queries import SUCCESS, dataset_results, results_of_images
from .usage import per_image, way_key

router = APIRouter(prefix="/v1")


def _library_named(definitions, library):
    """A requirement's labels by the library's names, each with how it is taken."""
    named = {d["name"]: library.get(d["id"], d["name"]) for d in definitions}
    return [
        {
            "id": d["id"],
            "name": named[d["name"]],
            "shape": d["shape"],
            "parent": named.get(d.get("parent")),
            "attributes": [
                {k: a.get(k) for k in ("name", "type", "choices")}
                for a in d.get("attributes") or []
            ],
        }
        for d in definitions
    ]


def past_requirements(db, dataset_id, with_objects=True):
    """{example_image, requirements}: the requirements other datasets annotated these images
    for, the most images first. A requirement: its labels, purpose, images, fixed (images a
    person fixed), datasets, ways (the AI's: model, effort, images, results, datasets,
    cost_per_result, newest) and by_image (each image's annotation: its annotation now in the
    datasets that annotated for it, the newest).
    example_image: of the images most requirements annotated, the one with the most objects."""
    dataset_row(db, dataset_id)
    rows = [
        r
        for r in results_of_images(db, image_ids(db, dataset_id))
        if r["dataset_id"] != dataset_id and r["status"] in SUCCESS
    ]
    library = names(db)
    readers = {}
    groups = defaultdict(list)
    for row in rows:
        groups[row["requirement_key"]].append(row)
    found = []
    for key, records in groups.items():
        newest = records[-1]
        ways = defaultdict(list)
        for r in records:
            if r["record_kind"] == "run":
                ways[way_key(json.loads(r["settings_json"]))].append(r)
        # Each image's annotation of it: its annotation now in each dataset that annotated
        # for it (image_state, S1: a person's choice or fix first), the newest of those (user
        # 2026-10-29: the newest way's AI result was taken over a person's fix).
        held = {r["image_id"] for r in records}
        by_image = {}
        for annotated in dict.fromkeys(r["dataset_id"] for r in records):
            for image_id, state in image_states(db, annotated, key, None)[1].items():
                now = state["now"]
                if now is None or image_id not in held:
                    continue
                if (
                    image_id not in by_image
                    or now["record_at"] > by_image[image_id][1]["record_at"]
                ):
                    by_image[image_id] = (annotated, now)
        objects = {}
        for image_id, (annotated, now) in by_image.items():
            if annotated not in readers:
                readers[annotated] = names_now(db, annotated)
            name = readers[annotated]
            objects[image_id] = [
                {
                    **{k: a[k] for k in ("id", "parent_id", "attributes", "number")},
                    "label": name(now["revision"], a["label"]),
                    **({"geometry": a["geometry"]} if with_objects else {}),
                }
                for a in (current(db, now["set_id"]) if now["set_id"] else [])
            ]
        made_by = version_payload(
            db, newest["dataset_id"], newest["instruction_revision"]
        )
        labels = _library_named(made_by["label_definitions"], library)
        drawn = dataset_colors(db, newest["dataset_id"])
        found.append(
            {
                "requirement_key": key,
                "labels": labels,
                # The colors of the dataset that last annotated for it (the colors are a
                # dataset's, DESIGN.md 6).
                "colors": {
                    label["name"]: drawn[label["name"]]
                    for label in labels
                    if label["name"] in drawn
                },
                "purpose": dataset_row(db, newest["dataset_id"])["purpose"],
                # The plan it was annotated with last: where a draft starts from (34.2).
                "plan": {
                    "dataset_id": newest["dataset_id"],
                    "dataset_name": dataset_row(db, newest["dataset_id"])["name"],
                    "revision": newest["instruction_revision"],
                },
                "images": len({r["image_id"] for r in records}),
                "fixed": len(
                    {r["image_id"] for r in records if r["result_by"] == "human"}
                ),
                "datasets": len({r["dataset_id"] for r in records}),
                "ways": [
                    _way(settings, way)
                    for settings, way in sorted(
                        ways.items(),
                        key=lambda kv: (
                            -len({r["image_id"] for r in kv[1]}),
                            -len(kv[1]),
                        ),
                    )
                ],
                "by_image": objects,
            }
        )
    found += _never_ran(db, dataset_id, library, {f["requirement_key"] for f in found})
    found.sort(key=lambda f: (-f["images"], -f["fixed"]))
    counted = defaultdict(lambda: [0, 0])
    for f in found:
        for image_id, objs in f["by_image"].items():
            counted[image_id][0] += 1
            counted[image_id][1] += len(objs)
    example = max(counted, key=lambda i: counted[i], default=None)
    return {"example_image": example, "requirements": found}


def _never_ran(db, dataset_id, library, known):
    """The plans of other datasets holding these images that never ran (their latest version;
    no result succeeded there): what these images were planned for, nothing annotated yet."""
    found = {}
    # The other datasets holding these images where no result succeeded.
    others = {
        s["dataset_id"]
        for s in shared_with(db, [dataset_id])
        if not any(r["status"] in SUCCESS for r in dataset_results(db, s["dataset_id"]))
    }
    for row in latest_rows(db):
        if row["dataset_id"] not in others:
            continue
        dataset = dataset_row(db, row["dataset_id"])
        definitions = json.loads(row["payload_json"])["label_definitions"]
        key = row["requirement_key"]
        if key in known:
            continue
        labels = _library_named(definitions, library)
        drawn = dataset_colors(db, row["dataset_id"])
        found[key] = {  # a newer plan of the same requirement replaces
            "requirement_key": key,
            "labels": labels,
            "colors": {
                l["name"]: drawn[l["name"]] for l in labels if l["name"] in drawn
            },
            "purpose": dataset["purpose"],
            "plan": {
                "dataset_id": row["dataset_id"],
                "dataset_name": dataset["name"],
                "revision": row["revision"],
            },
            "images": 0,
            "fixed": 0,
            "datasets": 1,
            "ways": [],
            "by_image": {},
        }
    return list(found.values())


def _way(key, records):
    # USD per image by the one place (usage.per_image; definition 84): a record with no cost is
    # not counted as free.
    mean, _ = per_image(records)
    return {
        "model": key[0],
        "effort": key[1],
        "images": len({r["image_id"] for r in records}),
        "results": len(records),
        "datasets": len({r["dataset_id"] for r in records}),
        # USD per result (one image annotated once), not the way's total.
        "cost_per_result": float(round(mean, 4)) if mean is not None else None,
        "newest": records[-1]["record_at"],
    }


@router.get("/datasets/{dataset_id}/plan/past")
def get_past(request: Request, dataset_id: str, objects: bool = True):
    """objects=false: each image's objects without their places (what a worker reads)."""
    return past_requirements(request.app.state.db, dataset_id, objects)

"""How each plan version and way of running was used (S2, definition 15.2), from the facts in
one place: the AI's runs of it (a person's fix is not a use of the plan; Astra 2026-10-17 P06:
"used 7 times" was 6 fixes), the images they ended on, and the images whose annotation now is
its result as it came or as a person fixed it. Each count says its unit (runs or images).

Where a plan came from (definition 15.1) is kept on the version, the draft and its writes:
blank, or a version of this dataset or another; None when not recorded (before 10-17). The
lineage follows it both ways. Read only.
"""

import json
from decimal import Decimal

from .datasets import dataset_row, dataset_rows
from .image_state import image_states
from .run_queries import (
    ENDED,
    SUCCESS,
    dataset_results,
    dataset_runs,
    is_trial,
    of_version,
    requirement_results,
)

COUNTS = (
    "runs",
    "trials",
    "images",
    "trial_images",
    "succeeded",
    "failed",
    "adopted",
    "fixed",
)


def origin_of(row):
    """Where the plan of a row (a version, a draft or a write) was started from."""
    if row is None or row["from_kind"] is None:
        return None
    if row["from_kind"] == "blank":
        return {"kind": "blank"}
    return {
        "kind": "version",
        "dataset_id": row["from_dataset_id"],
        "revision": row["from_revision"],
    }


def _bucket_counts(bucket):
    images = bucket["images"]
    return {
        "runs": bucket["runs"],
        "trials": bucket["trials"],
        "images": len(images),
        # The samples are counted in images, as people see them (definition 39.1).
        "trial_images": len(bucket["trial_images"]),
        "succeeded": len(bucket["succeeded"]),
        "failed": len(images - bucket["succeeded"]),
        "adopted": len(bucket["adopted"]),
        "fixed": len(bucket["fixed"]),
    }


def empty():
    return {**{k: 0 for k in COUNTS}, "ways": []}


def way_key(settings):
    """A way of running beside its plan version, as every count and comparison tells it
    (definition 11.1, 18.15): the model, the effort and the shared notes' version."""
    return (
        settings.get("model"),
        settings.get("effort"),
        settings.get("shared_revision"),
    )


def cost_way(settings):
    """The way a cost is told by: the model and its effort (way_key without the shared notes'
    version, which costs nothing; user 2026-10-29: by way, the model and its effort)."""
    return way_key(settings)[:2]


def per_image(rows):
    """What one image cost by these results (each one image annotated once, a cost recorded):
    (the mean in USD, how many); (None, 0) for none. The one place every cost per image is told
    by (the box's estimate, the earlier plans' ways, a worker's limit; definition 84)."""
    costs = [
        Decimal(str(usd))
        for r in rows
        if (usd := (json.loads(r["cost_json"]) if r["cost_json"] else {}).get("usd"))
        is not None
    ]
    if not costs:
        return None, 0
    return sum(costs, Decimal(0)) / len(costs), len(costs)


def expected_cost(db, dataset_id, requirement_key, way):
    """What one image is expected to cost by a way (cost_way) (definition 84; user 2026-10-30):
    the AI's successes of this dataset by that way, else those of the plan's requirement by that
    way in every dataset. {per_image_usd, results, from: None, or the datasets it came from} or
    None when none ran so."""

    def of_way(results):
        return [
            r
            for r in results
            if r["record_kind"] == "run"
            and r["status"] in SUCCESS
            and cost_way(json.loads(r["settings_json"])) == tuple(way)
        ]

    found = of_way(dataset_results(db, dataset_id))
    elsewhere = False
    if not per_image(found)[1] and requirement_key:
        elsewhere = True
        found = of_way(requirement_results(db, requirement_key))
    mean, count = per_image(found)
    if mean is None:
        return None
    datasets = sorted({r["dataset_id"] for r in found})
    return {
        "per_image_usd": mean,
        "results": count,
        "from": [
            {
                "dataset_id": d,
                "name": dataset_row(db, d)["name"],
            }
            for d in datasets
        ]
        if elsewhere
        else None,
    }


def version_usage(db, dataset_id):
    """{revision: the use of the version} for the versions the AI ran; a version never run is
    not in it (empty() is its use). Each use has the eight counts and its ways (model and
    effort) with the same counts."""
    # The version's type imports this one: read at call time.
    from .instructions import latest_basis

    runs = {}
    for r in dataset_runs(db, dataset_id):
        if not of_version(r):
            continue
        settings = json.loads(r["settings_json"])
        runs[r["id"]] = (
            ("version", r["instruction_revision"]),
            ("way", r["instruction_revision"], *way_key(settings)),
            is_trial(settings),
        )
    buckets = {}

    def of(key):
        return buckets.setdefault(
            key,
            {
                "runs": 0,
                "trials": 0,
                "images": set(),
                "trial_images": set(),
                "succeeded": set(),
                "adopted": set(),
                "fixed": set(),
            },
        )

    for version, way, trial in runs.values():
        for key in (version, way):
            of(key)["runs"] += 1
            of(key)["trials"] += trial
    run_of, fixed_from = {}, {}
    for r in dataset_results(db, dataset_id):
        run_of[r["id"]] = r["run_id"]
        if r["fixed_from"]:
            fixed_from[r["id"]] = r["fixed_from"]
        run = runs.get(r["run_id"])
        if run is None or r["status"] not in ENDED:
            continue
        for key in run[:2]:
            of(key)["images"].add(r["image_id"])
            if run[2]:
                of(key)["trial_images"].add(r["image_id"])
            if r["status"] in SUCCESS:
                of(key)["succeeded"].add(r["image_id"])
    _, states = image_states(db, dataset_id, *latest_basis(db, dataset_id))
    for image_id, state in states.items():
        now = state["now"]
        if now is None or state["used"] != "result":
            continue
        # A person's fix counts for the AI's result it was made from (a fix of a fix too).
        result_id, seen = now["result_id"], set()
        while result_id in fixed_from and result_id not in seen:
            seen.add(result_id)
            result_id = fixed_from[result_id]
        run = runs.get(run_of.get(result_id))
        if run is None:
            continue
        for key in run[:2]:
            of(key)["fixed" if now["by"] == "human" else "adopted"].add(image_id)
    found = {}
    for key, bucket in buckets.items():
        if key[0] == "version":
            found.setdefault(key[1], empty()).update(_bucket_counts(bucket))
    for key, bucket in buckets.items():
        if key[0] == "way":
            found.setdefault(key[1], empty())["ways"].append(
                {
                    "model": key[2],
                    "effort": key[3],
                    "shared_revision": key[4],
                    **_bucket_counts(bucket),
                }
            )
    return found


def lineage(db, dataset_id, revision, cache=None):
    """The version's line: based_on (the versions it came from, nearest first) with start
    (why that stops: "blank", None when not recorded, "missing" when that version is gone),
    and derived (the versions made from it, in any dataset, each with its use) with
    derived_total (their uses added)."""
    cache = {} if cache is None else cache

    def use(d, r):
        if d not in cache:
            cache[d] = version_usage(db, d)
        return cache[d].get(r, empty())

    names = {r["id"]: r["name"] for r in dataset_rows(db)}
    from .instructions import all_versions  # instructions counts each version's use

    rows = {(r["dataset_id"], r["revision"]): r for r in all_versions(db)}
    based_on, start, key = [], None, (dataset_id, revision)
    while True:
        origin = origin_of(rows.get(key))
        if origin is None or origin["kind"] == "blank":
            start = origin and "blank"
            break
        key = (origin["dataset_id"], origin["revision"])
        if key in rows and key not in {
            (b["dataset_id"], b["revision"]) for b in based_on
        }:
            based_on.append(
                {"dataset_id": key[0], "name": names.get(key[0]), "revision": key[1]}
            )
            continue
        start = "missing"
        break
    children = {}
    for k, row in rows.items():
        origin = origin_of(row)
        if origin and origin["kind"] == "version":
            children.setdefault((origin["dataset_id"], origin["revision"]), []).append(
                k
            )
    derived, waiting, seen = [], list(children.get((dataset_id, revision), [])), set()
    while waiting:
        k = waiting.pop(0)
        if k in seen or k == (dataset_id, revision):
            continue
        seen.add(k)
        derived.append(
            {
                "dataset_id": k[0],
                "name": names.get(k[0]),
                "revision": k[1],
                "usage": use(*k),
            }
        )
        waiting.extend(children.get(k, []))
    total = {c: sum(d["usage"][c] for d in derived) for c in COUNTS}
    return {
        "based_on": based_on,
        "start": start,
        "derived": derived,
        "derived_total": total,
    }

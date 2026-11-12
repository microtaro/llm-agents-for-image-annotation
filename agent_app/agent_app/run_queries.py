"""Reading runs and their results, and the task a worker gets for one image.

Copied from annotation_server/runs.py and datasets.py (step 2 design 2).
"""

import json

from .annotation_sets import label_counts, set_row, set_state
from .costs import sum_api_costs
from .datasets import dataset_row
from .db import new_id, now
from .decisions import get_decision
from .errors import not_found
from .label_ids import names_now

# A result's status (results.status): made, found or not (SUCCESS); failed; interrupted, its run
# stopped before it; or still to be made (WAITING). The one place they are named (fact
# inventory 4).
SUCCESS = ("detected", "not_detected")
PROCESSED = (*SUCCESS, "failed")  # the worker did it
ENDED = (*PROCESSED, "interrupted")  # nothing more happens to it
WAITING = ("pending", "running")
# A run's status (runs.status) while it is going: decided and not ended.
GOING = ("queued", "running", "stopping")
# A result with its record, a run, a person's fix or one taken in (the view result_records,
# definition 21.4, 60.11).
RESULTS_SQL = "SELECT * FROM result_records r "


def of_version(row):
    """A record (or its result) of a saved version; a draft's trial of before 10-13 was not
    (definition 1: only a version's results count)."""
    return row["instruction_revision"] > 0


def of_requirement(row, key):
    """A record (or its result) of a version of the requirement key: what the images' states,
    training and the person's choices are judged by (S1, definition 35.7)."""
    return of_version(row) and row["requirement_key"] == key


def status_facts(status):
    """What a result's status says, as the server counts it (the screen does not make it again):
    made (SUCCESS) and still to be made (WAITING)."""
    return {"succeeded": status in SUCCESS, "waiting": status in WAITING}


def is_trial(settings):
    """A run is a trial, the plan's samples (definition 38.1), when its settings say so."""
    return "trial_instruction" in settings


def made_status(objects):
    """The status of a result made at once (a person's fix, one taken in, a label change): found
    or not, as its objects say (issue #4 F-12: an empty fix was "detected")."""
    return "detected" if objects else "not_detected"


def result_counts(statuses):
    """A record's results counted by their statuses: total, processed, succeeded, waiting."""
    statuses = list(statuses)
    return {
        "total": len(statuses),
        "processed": sum(s in PROCESSED for s in statuses),
        "succeeded": sum(s in SUCCESS for s in statuses),
        "waiting": sum(s in WAITING for s in statuses),
    }


def record_results(db, record_id):
    """A record's results (result_records), in its order: the one place they are read."""
    return db.execute(
        RESULTS_SQL + "WHERE r.record_id=? ORDER BY r.position", (str(record_id),)
    )


def dataset_results(db, dataset_id):
    """Every result of the dataset's records, in the records' numbers' order (the wall clock can
    step back; a later number is newer)."""
    return db.execute(
        RESULTS_SQL + "WHERE r.dataset_id=? ORDER BY r.record_number, r.position",
        (dataset_id,),
    )


def requirement_results(db, requirement_key):
    """Every dataset's results of the requirement, the oldest first."""
    return db.execute(
        RESULTS_SQL + "WHERE r.requirement_key=? ORDER BY r.record_at",
        (requirement_key,),
    )


def results_of_images(db, image_ids):
    """The results of these images in every dataset, the oldest first."""
    marks = ",".join("?" * len(image_ids))
    return db.execute(
        RESULTS_SQL + f"WHERE r.image_id IN ({marks}) ORDER BY r.record_at",
        tuple(image_ids),
    )


def insert_result(db, kind, record_id, image_id, set_id, position, objects):
    """The result of a record made at once (kind: fix, import or copy) of an image, with its
    objects made in set_id; its id."""
    result_id = new_id("res-")
    db.execute(
        f"INSERT INTO results(id,{kind}_id,image_id,set_id,position,status,started_at,"
        "elapsed_ms) VALUES(?,?,?,?,?,?,?,0)",
        (result_id, record_id, image_id, set_id, position, made_status(objects), now()),
    )
    return result_id


def dataset_runs(db, dataset_id):
    """Every run of the dataset, in their numbers' order."""
    return db.execute(
        "SELECT * FROM runs WHERE dataset_id=? ORDER BY number", (dataset_id,)
    )


def going(db, dataset_ids):
    """Whether a run of these datasets is going."""
    marks = ",".join("?" * len(dataset_ids))
    return (
        db.one(
            f"SELECT 1 FROM runs WHERE dataset_id IN ({marks})"
            f" AND status IN ({','.join('?' * len(GOING))})",
            (*dataset_ids, *GOING),
        )
        is not None
    )


def has_run(db, dataset_id, run_id):
    return (
        db.one("SELECT 1 FROM runs WHERE dataset_id=? AND id=?", (dataset_id, run_id))
        is not None
    )


def has_result(db, dataset_id, result_id):
    return (
        db.one(RESULTS_SQL + "WHERE r.dataset_id=? AND r.id=?", (dataset_id, result_id))
        is not None
    )


def run_row(db, run_id):
    row = db.one("SELECT * FROM runs WHERE id=?", (str(run_id),))
    if row is None:
        raise not_found("Run")
    return row


def result_row(db, result_id):
    row = db.one(RESULTS_SQL + "WHERE r.id=?", (str(result_id),))
    if row is None:
        raise not_found("Result")
    return row


def record_row(db, record_id):
    """A record (definition 21.4, 60.11, 79, 85.15): a run, a person's fix, one taken in or a
    copy (a label change, relabel, or results carried over, carry), with its dataset and
    number."""
    row = db.one(
        "SELECT 'run' AS kind, id, dataset_id, number FROM runs WHERE id=?"
        " UNION ALL SELECT 'fix', id, dataset_id, number FROM fixes WHERE id=?"
        " UNION ALL SELECT 'import', id, dataset_id, number FROM imports WHERE id=?"
        " UNION ALL SELECT CASE reason WHEN 'label' THEN 'relabel' ELSE 'carry' END, id,"
        " dataset_id, number FROM copies WHERE id=?",
        (str(record_id),) * 4,
    )
    if row is None:
        raise not_found("Record")
    return row


def run_number(db, run_id):
    """A run's record number in its dataset, 1 for the first (user 2026-10-13: "the one before"
    did not say which; records are named by number). Kept when the record is made."""
    found = db.one("SELECT number FROM runs WHERE id=?", (str(run_id),))
    return found[0] if found else None


def next_number(db, dataset_id):
    """The number of a record made now: after every record of the dataset (one line of numbers,
    definition 21.4; a number is never given again)."""
    found = db.one(
        "SELECT max(n) FROM (SELECT number AS n FROM runs WHERE dataset_id=?"
        " UNION ALL SELECT number FROM fixes WHERE dataset_id=?"
        " UNION ALL SELECT number FROM imports WHERE dataset_id=?"
        " UNION ALL SELECT number FROM copies WHERE dataset_id=?)",
        (dataset_id,) * 4,
    )
    return (found[0] or 0) + 1


def result_ref(db, row, name=None):
    """One result in a list: which record (a run, or a person's fix), model and image, how it
    went, how many annotations of each label (named now, definition 23.4; name: names_now of
    its dataset, read once for a list)."""
    name = name or names_now(db, row["dataset_id"])
    settings = json.loads(row["settings_json"]) if row["settings_json"] else {}
    cost = json.loads(row["cost_json"]) if row["cost_json"] else None
    labels = label_counts(db, row["set_id"])
    return {
        "result_id": row["id"],
        # Its record: a run, or a person's fix (run_id then none).
        "record_id": row["record_id"],
        "record_number": row["record_number"],
        "run_id": row["run_id"],
        "by": row["result_by"],
        "record_kind": row["record_kind"],
        # A try (a few images of a version, run from Plan).
        "trial": is_trial(settings),
        "record_at": row["record_at"],
        "image_id": row["image_id"],
        "model": settings.get("model"),
        "effort": settings.get("effort"),
        "instruction_revision": row["instruction_revision"],
        "requirement_key": row["requirement_key"],
        "status": row["status"],
        **status_facts(row["status"]),
        "message": row["message"],
        "elapsed_ms": row["elapsed_ms"],
        "cost_usd": (cost or {}).get("usd"),
        "cost_jpy": (cost or {}).get("jpy"),
        "annotation_count": sum(labels.values()),
        "label_counts": {
            name(row["instruction_revision"], label): n for label, n in labels.items()
        },
        "revision": set_row(db, row["set_id"])["revision"],
    }


def record_state(db, row, kind, going, succeeded):
    """What every record says alike, by the plan's requirement now: of a version, of an earlier
    requirement (2026-10-30 review: a record other than a run said it was not, whatever it was
    of), and whether its images may use its results for training (definition 19.5, 17.2: a run
    of the requirement now that ended with some made; [記録 n を使う] takes a run's)."""
    # The version's type counts each version's runs: read at call time.
    from .instructions import latest_requirement

    now_key = latest_requirement(db, row["dataset_id"])
    of_now = of_requirement(row, now_key)
    return {
        "of_version": of_version(row),
        "usable": kind == "run" and not going and of_now and succeeded > 0,
        "earlier": of_version(row) and not of_now,
    }


def get_run(db, run_id, version=0):
    with db.lock:
        row = run_row(db, run_id)
        results = record_results(db, run_id)
        costs = [json.loads(r["cost_json"]) for r in results if r["cost_json"]]
        found = result_counts(r["status"] for r in results)
        going = row["status"] in GOING
        return {
            "id": row["id"],
            "kind": "run",
            "number": row["number"],
            "dataset_id": row["dataset_id"],
            "status": row["status"],
            "going": going,
            **record_state(db, row, "run", going, found["succeeded"]),
            "instruction_revision": row["instruction_revision"],
            # Its way of running (plan version, model, effort; definition 11.1).
            "recipe_id": row["recipe_id"],
            "requirement_key": row["requirement_key"],
            "requested": json.loads(row["requested_json"]),
            "worker_prompt_sha256": row["worker_prompt_sha256"],
            "settings": json.loads(row["settings_json"]),
            "budget_per_image_usd": row["budget_per_image_usd"],
            # Who decided it and who asked for it (definition 21.3).
            "decision": get_decision(db, row["decision_id"]),
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "elapsed_ms": row["elapsed_ms"],
            "error": row["error"],
            "error_code": row["error_code"],
            # A trial: a few images of the version, run from ① (user 2026-10-13).
            "trial": is_trial(json.loads(row["settings_json"])),
            **{k: v for k, v in found.items() if k != "waiting"},
            "cost": sum_api_costs(costs) if costs else None,
            "version": version,
        }


def _made_at_once(db, row, kind):
    """What a record made at once (a person's fix, one taken in, a label change) says in a run's
    shape: no trial, no cost, its results counted."""
    found = result_counts(r["status"] for r in record_results(db, row["id"]))
    return {
        "going": False,
        **record_state(db, row, kind, False, found["succeeded"]),
        "trial": False,
        **{k: v for k, v in found.items() if k != "waiting"},
        "cost": None,
    }


def get_fix(db, fix_id):
    """A person's fix as a record (definition 21.4), in a run's shape where they mean the same
    (number, when, the version and requirement, how it went), with what it fixed."""
    row = db.one("SELECT * FROM fixes WHERE id=?", (str(fix_id),))
    if row is None:
        raise not_found("Fix")
    made = _made_at_once(db, row, "fix")
    return {
        "id": row["id"],
        "kind": "fix",
        "number": row["number"],
        "dataset_id": row["dataset_id"],
        "status": "succeeded",
        "instruction_revision": row["instruction_revision"],
        "requirement_key": row["requirement_key"],
        "settings": {},
        "started_at": row["fixed_at"],
        "ended_at": row["fixed_at"],
        **made,
        "fixed_by": row["fixed_by"],
        "from_result_id": row["from_result_id"],
        "image_id": row["image_id"],
    }


def get_import(db, import_id):
    """A record taken in (definition 60.11), in a run's shape where they mean the same, with
    the file it came from."""
    row = db.one("SELECT * FROM imports WHERE id=?", (str(import_id),))
    if row is None:
        raise not_found("Record taken in")
    made = _made_at_once(db, row, "import")
    return {
        "id": row["id"],
        "kind": "import",
        "number": row["number"],
        "dataset_id": row["dataset_id"],
        "status": "succeeded",
        "instruction_revision": row["instruction_revision"],
        "requirement_key": row["requirement_key"],
        "settings": {},
        "started_at": row["imported_at"],
        "ended_at": row["imported_at"],
        **made,
        "imported_by": row["imported_by"],
        "source": json.loads(row["source_json"]),
    }


def get_copy(db, copy_id):
    """A copy (definition 79, 85.15) as a record, in a run's shape where they mean the same: a
    label change (kind relabel, with the label it changed) or results carried over (kind carry,
    with the dataset and version they came from), and the decision."""
    row = db.one("SELECT * FROM copies WHERE id=?", (str(copy_id),))
    if row is None:
        raise not_found("Copy")
    kind = "relabel" if row["reason"] == "label" else "carry"
    made = _made_at_once(db, row, kind)
    return {
        "id": row["id"],
        "kind": kind,
        "number": row["number"],
        "dataset_id": row["dataset_id"],
        "status": "succeeded",
        "instruction_revision": row["instruction_revision"],
        "requirement_key": row["requirement_key"],
        "settings": {},
        "started_at": row["copied_at"],
        "ended_at": row["copied_at"],
        **made,
        "copied_by": row["copied_by"],
        **json.loads(row["content_json"]),
        "decision_id": row["decision_id"],
    }


def get_record(db, record_id, version=0):
    """A record, a run, a person's fix, one taken in or a label change (definition 21.4,
    60.11, 79)."""
    kind = record_row(db, record_id)["kind"]
    if kind == "fix":
        return get_fix(db, record_id)
    if kind == "import":
        return get_import(db, record_id)
    if kind in ("relabel", "carry"):
        return get_copy(db, record_id)
    return get_run(db, record_id, version)


def list_records(db, dataset_id, version=0):
    """Every record of the dataset, runs, person's fixes, ones taken in and copies, the newest
    number first."""
    dataset_row(db, dataset_id)
    rows = db.execute(
        "SELECT id FROM runs WHERE dataset_id=? UNION ALL"
        " SELECT id FROM fixes WHERE dataset_id=? UNION ALL"
        " SELECT id FROM imports WHERE dataset_id=? UNION ALL"
        " SELECT id FROM copies WHERE dataset_id=?",
        (str(dataset_id),) * 4,
    )
    records = [get_record(db, r["id"], version) for r in rows]
    return {"records": sorted(records, key=lambda r: -r["number"])}


def list_runs(db, dataset_id, version=0):
    """Newest first. Runs are ordered by their row, not started_at: the wall clock can step
    back (observed 2026-09-29 on WSL), which would put a newer run first."""
    dataset_row(db, dataset_id)
    rows = db.execute(
        "SELECT id FROM runs WHERE dataset_id=? ORDER BY rowid DESC", (str(dataset_id),)
    )
    return {"runs": [get_run(db, r["id"], version) for r in rows]}


def list_results(db, run_id):
    name = names_now(db, run_row(db, run_id)["dataset_id"])
    return {"results": [result_ref(db, r, name) for r in record_results(db, run_id)]}


def get_result(db, result_id, revision=None):
    """A result and its annotations, now or at a revision (what a view of it drew)."""
    row = result_row(db, result_id)
    return {**result_ref(db, row), **set_state(db, row["set_id"], revision)}


def requested_items(definitions):
    """What a run asks for: each label with its shape and attribute names."""
    return [
        {
            "label": d["name"],
            "shape": d["shape"],
            "attributes": [a["name"] for a in d.get("attributes", [])],
        }
        for d in definitions
    ]


def task_from(db, instruction, settings, image_id):
    """What a worker gets for one image from an instruction's content (a version, a trial
    run's draft, or a draft shown on the screen): the same function for all three. Each
    reference's objects are its result's at the revision the plan points at, named as the plan
    names its labels (references.resolved)."""
    from .references import resolved

    definitions = instruction["label_definitions"]
    references = (resolved(db, instruction) or {}).get("references") or []
    return {
        "view_max_side": settings["worker_view_max_side"],
        "labels": [d["name"] for d in definitions],
        "label_colors": settings.get("label_colors", {}),
        "label_definitions": definitions,
        "instruction_text": instruction["text"],
        "leave_out": instruction["leave_out"],
        "refs": [
            {
                "index": index,
                "image_id": r["image_id"],
                "note": r.get("note", ""),
                "set_id": r["set_id"],
                "revision": r["revision"],
                "annotations": r["annotations"],
            }
            for index, r in enumerate(references)
            if r["image_id"] != image_id
        ],
    }


def made_criteria(db, row):
    """The criteria a result was made by (definition 85.3): its record's plan's, a trial's own
    or its version's (instructions.criteria_key); one carried over, the one's it was copied
    from (85.15; a label change's is its version's, 85.13)."""
    from .instructions import criteria_key  # the version's type imports this one

    if row["record_kind"] == "carry":
        return row["copied_criteria"]
    settings = json.loads(row["settings_json"]) if row["settings_json"] else {}
    return criteria_key(
        ran_plan(db, row["dataset_id"], row["instruction_revision"], settings)
    )


def ran_plan(db, dataset_id, revision, settings):
    """The plan a record was made with (definition 11.3, held by value): a trial's own (an older
    trial, or the draft it started from, of no version: revision 0), else its version's; {} for
    a version gone."""
    if "trial_instruction" in settings:
        return settings["trial_instruction"]
    # The version's type imports this one (through usage): read at call time.
    from .instructions import version_payload

    return version_payload(db, dataset_id, revision) or {}


def task(db, run, result):
    """What the worker must do for one image: labels and their definitions, colors, the
    instruction text and the references. The target's own reference is left out: it is the
    answer (data-model 9.2: a master is never shown as a reference). A trial carries its
    version's instruction (an older trial, the draft it was started from)."""
    settings = run["settings"]
    instruction = ran_plan(db, run["dataset_id"], run["instruction_revision"], settings)
    return {
        **task_from(db, instruction, settings, result["image_id"]),
        "dataset_id": run["dataset_id"],
        "run_id": run["id"],
        "result_id": result["id"],
        "image_id": result["image_id"],
    }

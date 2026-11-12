"""The state of each image of a dataset, from the facts, in one place (S1, definition 14): the
result that is its annotation now, whether training uses it, what was last tried, the failures
after the last success, and whether one is being made. The gallery's views, the loupe, a box's
preview, the adoption, the progress and the workers read it; none decides it again (found
2026-10-17: the same image had a result on a card and "no objects" in the loupe).

The rule is the adoption's (types design 7.2): a person's choice while it is a success of the
requirement, else the newest such success; a newer success does not replace a choice (definition
10, 19). What a person decided is read from the decisions added (use_now). Read only.
"""

import json

from .confirmations import checked_by
from .datasets import image_ids
from .images import image_names
from .run_queries import (
    SUCCESS,
    WAITING,
    dataset_results,
    is_trial,
    made_criteria,
    of_requirement,
    of_version,
    run_number,
)


def result_of(row):
    """A result as the states hold it, with its record's facts: a run's (model, trial) or a
    person's fix's (by human; definition 21.4)."""
    settings = json.loads(row["settings_json"]) if row["settings_json"] else {}
    cost = json.loads(row["cost_json"]) if row["cost_json"] else {}
    return {
        "result_id": row["id"],
        "record_id": row["record_id"],
        "record_number": row["record_number"],
        "run_id": row["run_id"],
        "status": row["status"],
        "set_id": row["set_id"],
        "message": row["message"],
        "revision": row["instruction_revision"],
        "model": settings.get("model"),
        "by": row["result_by"],
        "record_kind": row["record_kind"],
        "trial": is_trial(settings),
        "record_at": row["record_at"],
        "elapsed_ms": row["elapsed_ms"],
        "cost_usd": cost.get("usd"),
    }


def use_now(db, dataset_id):
    """{image id: {"pick": the result a person chose or None, "excluded": bool}} from what
    training uses, added (definition 19.4, 21.3): the last pick, rule or fix (a person's fix
    made is used, the rule of definition 5), and the last out or in. Choosing
    does not change whether the image is used (annotating, a record chosen does not take a left
    out image back). Every image of the dataset, in its order."""
    found = {i: {"pick": None, "excluded": False} for i in image_ids(db, dataset_id)}
    for r in db.execute(
        "SELECT image_id, kind, result_id FROM uses WHERE dataset_id=? ORDER BY id",
        (dataset_id,),
    ):
        now = found.get(r["image_id"])
        if now is None:  # taken out of the dataset since
            continue
        if r["kind"] in ("pick", "rule", "fix"):
            now["pick"] = r["result_id"]
        else:
            now["excluded"] = r["kind"] == "out"
    return found


def image_states(db, dataset_id, against, criteria):
    """{image id: state} in the dataset's order, judged by the requirement against and the
    criteria (definition 35.7, 85.4: given by whoever looks, a plan's or the latest version's,
    never chosen here; user 2026-10-22: "now" chosen inside showed the latest version's results
    while another plan was being made; criteria None: judged by the requirement only). A state:
    image_id, excluded, now (the result of that requirement that is its annotation, with picked
    and newer, and by the criteria: made by them ("this") or by others ("other"), and checked
    by a person by them; both None when judged by the requirement only; None), used ("result",
    "excluded", "stale": only results of other requirements, or "none"), earlier (the newest
    of those; None), latest (the newest result of the requirement in any state; None),
    failures (after the last success: per version and the newest reason; None) and running."""
    key = against
    newest, latest, successes, earlier, failed = {}, {}, {}, {}, {}
    rows_of = {}  # a success's id -> its row, to read the criteria it was made by
    running = {}  # image id -> the run that holds it (its result still to be written)
    # Records in their numbers' order (the wall clock can step back); a later one is newer.
    for row in dataset_results(db, dataset_id):
        image_id = row["image_id"]
        if row["status"] in WAITING:
            running[image_id] = row["run_id"]
        if not of_version(row):
            continue
        if not of_requirement(row, key):
            if row["status"] in SUCCESS:
                earlier[image_id] = result_of(row)  # the newest, in the records' order
            continue
        result = result_of(row)
        latest[image_id] = result
        if row["status"] in SUCCESS:
            newest[image_id] = result
            successes[row["id"]] = result
            rows_of[row["id"]] = row
            failed.pop(image_id, None)
        elif row["status"] == "failed":
            failed.setdefault(image_id, []).append(result)
    by_criteria = _by_criteria(db, dataset_id, criteria)
    states = {}
    for image_id, mine in use_now(db, dataset_id).items():
        picked = successes.get(mine["pick"])
        now = picked or newest.get(image_id)
        if now is not None:
            now = {
                **now,
                "picked": picked is not None,
                "newer": picked is not None and newest[image_id] is not picked,
                **by_criteria(rows_of[now["result_id"]]),
            }
        if mine["excluded"]:
            used = "excluded"
        elif now is not None:
            used = "result"
        elif image_id in earlier:
            used = "stale"
        else:
            used = "none"
        rows = failed.get(image_id)
        failures = None
        if rows:
            parts = {}
            for r in rows:
                parts[r["revision"]] = parts.get(r["revision"], 0) + 1
            failures = {
                "parts": [{"revision": v, "count": c} for v, c in parts.items()],
                "reason": rows[-1]["message"] or "",
            }
        states[image_id] = {
            "image_id": image_id,
            "excluded": mine["excluded"],
            "now": now,
            "used": used,
            "latest": latest.get(image_id),
            # The newest success of an earlier requirement (what "stale" stands on), else None.
            "earlier": earlier.get(image_id),
            "failures": failures,
            "running": image_id in running,
            # The record that holds it (the lock of definition 18.13), else None.
            "writing": {
                "run_id": running[image_id],
                "run_number": run_number(db, running[image_id]),
            }
            if image_id in running
            else None,
        }
    return key, states


def _by_criteria(db, dataset_id, criteria):
    """A function (a success's row) -> {criteria, checked, other} of it by the criteria
    (definition 85.4): made by them ("this") or by others ("other"); checked by a person by
    them (a person's fix made by them, or a check of it by a version of them; running by a plan
    is not checking it); other: made by others and not checked, not done by them. All None when
    judged by the requirement only."""
    from .instructions import criteria_key, version_payload  # it imports this one

    if criteria is None:
        return lambda _row: {"criteria": None, "checked": None, "other": None}
    of_revision = {}
    checks = checked_by(db, dataset_id)

    def criteria_of(revision):
        if revision not in of_revision:
            of_revision[revision] = criteria_key(
                version_payload(db, dataset_id, revision)
            )
        return of_revision[revision]

    def judged(row):
        # Each result's own (a carried record holds results made by several criteria, 85.15;
        # 2026-10-30: kept by record, the first image's was said of every image).
        mine = made_criteria(db, row) == criteria
        checked = (row["record_kind"] == "fix" and mine) or any(
            criteria_of(r) == criteria for r in checks.get(row["id"], ())
        )
        return {
            "criteria": "this" if mine else "other",
            "checked": checked,
            "other": not mine and not checked,
        }

    return judged


def state_counts(states):
    """How many of the images are in each state (definition 57, 85.4): annotating's question
    (done: a success of the requirement made by the criteria or checked by them; other: one
    made by others and not checked; else working, failed, only another requirement's, none, one
    each), checked by a person, and training's (used, whatever criteria; left out). The
    library's card, the annotating and the training screens count them so, each by the basis
    its plan names."""
    counts = dict.fromkeys(
        (
            "images",
            "done",
            "other",
            "checked",
            "running",
            "failed",
            "stale",
            "none",
            "used",
            "excluded",
        ),
        0,
    )
    for s in states.values():
        counts["images"] += 1
        now = s["now"]
        if now is not None:
            counts["checked"] += bool(now["checked"])
        if now is not None and now["other"]:
            counts["other"] += 1
        elif now is not None:
            counts["done"] += 1
        elif s["running"]:
            counts["running"] += 1
        elif s["failures"]:
            counts["failed"] += 1
        elif s["earlier"]:
            counts["stale"] += 1
        else:
            counts["none"] += 1
        counts["used"] += s["used"] == "result"
        counts["excluded"] += s["excluded"]
    return counts


def writing(db, dataset_id, image_ids):
    """The images of image_ids a decided run holds (its result there is still to be written,
    waiting in the line or being made), from the images' states (S1): the lock of definition
    18.13, from the decision until the result is written. By name, with the record."""
    if not image_ids:
        return []
    # Held whatever plan is looked by (definition 49.1: by none).
    _, states = image_states(db, dataset_id, None, None)
    held = [i for i in image_ids if (states.get(i) or {}).get("writing")]
    if not held:
        return []
    names = image_names(db, held)
    return [
        {
            "image_id": i,
            "name": names.get(i, i),
            "run_number": states[i]["writing"]["run_number"],
        }
        for i in held
    ]

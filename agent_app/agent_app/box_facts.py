"""What a proposal shows and stands on (step 24 design 3.6). preview: the target by name, its
state now, what applying changes and the cost's basis, for the person and the judging AI alike
(Sol's box test 2026-10-08: deciding needs the state now, the reason, the state after and the
values). premise: a fingerprint of what the decision stood on, compared when it is applied, so
a decision made before the data changed is stopped (notify check: a change during an answer
does not reach that answer).
"""

import json

from . import data_facts
from .actions import DECISIONS
from .adoption import adoption
from .datasets import check_in_dataset, dataset_rows
from .draft_diff import plan_changes
from .drafts import plan_basis, same_version, write_row
from .errors import invalid
from .image_state import image_states, writing
from .images import image_names
from .instructions import (
    latest_basis,
    latest_revision,
    latest_row,
    version_payload,
    version_row,
)
from .run_inputs import default_choice, last_ai_run, start_targets
from .run_queries import (
    SUCCESS,
    WAITING,
    dataset_results,
    dataset_runs,
    is_trial,
    record_results,
    result_row,
    run_number,
    run_row,
)
from .usage import (
    COUNTS,
    empty,
    expected_cost,
    lineage,
    origin_of,
    version_usage,
    way_key,
)


def _latest_results(db, dataset_id, image_ids):
    """Each image's newest result in the dataset (any record): its id and status."""
    found = {}
    for r in dataset_results(db, dataset_id):
        if r["image_id"] in image_ids:
            found[r["image_id"]] = {"id": r["id"], "status": r["status"]}
    return found


def _adopted(db, dataset_id):
    """Each image's adoption; before the first version nothing is adopted (found 2026-10-13:
    the adoption asked for a version)."""
    if latest_row(db, dataset_id) is None:
        return {}
    items = adoption(db, dataset_id)["items"]
    return {i["image_id"]: i["source"] for i in items}


def last_way(db, dataset_id):
    """The way the dataset last ran (plan version, model, effort; a person's fix is not one):
    what a decision to run is compared with (definition 11.10)."""
    row = last_ai_run(db, dataset_id)
    if row is None:
        return None
    settings = json.loads(row["settings_json"])
    return {
        "revision": row["instruction_revision"],
        "model": settings.get("model"),
        "effort": settings.get("effort"),
        # The shared notes it added (definition 18.15).
        "shared_revision": settings.get("shared_revision"),
        # Named by its record's number on the screen, not "the last one" (user 2026-10-17).
        "run_number": run_number(db, row["id"]),
    }


def box_plan(db, dataset_id, args):
    """The plan the box runs, by value (definition 11.4, 11.10): the draft write (who wrote it
    when, the version it makes) or the version, and what it says differently from the way the
    dataset last ran; how often the same way ran."""
    write_id, revision = args.get("draft_write_id"), args.get("revision")
    if write_id is not None:
        write = write_row(db, dataset_id, write_id)
        payload = json.loads(write["payload_json"])
        same = same_version(db, dataset_id, payload)
        latest = latest_revision(db, dataset_id)
        shown = {
            "kind": "write",
            "write_id": write_id,
            "written_by": write["written_by"],
            "written_at": write["written_at"],
            # A version of the same content runs (as version_from_write makes it); else the
            # next one is made.
            "revision": same,
            "next_revision": None if same is not None else (latest or 0) + 1,
        }
        revision = shown["revision"]
    else:
        payload = version_payload(db, dataset_id, revision)
        version = version_row(db, dataset_id, revision)
        shown = {
            "kind": "version",
            "revision": revision,
            "written_by": version["created_by"] if version else None,
            "written_at": version["created_at"] if version else None,
            "next_revision": None,
        }
    way = last_way(db, dataset_id)
    shown["against"] = way
    if way is None:
        shown["first"] = True
        shown["same_way"] = False
        shown["changes"] = None
    else:
        before = version_payload(db, dataset_id, way["revision"])
        changes = plan_changes(before, payload) if before is not None else None
        model_effort = {
            k: [way[k], args.get(k)]
            for k in ("model", "effort")
            if way[k] != args.get(k)
        }
        # The shared notes are a part of the way (definition 18.15).
        if way.get("shared_revision") != args.get("shared_revision"):
            model_effort["shared"] = [
                way.get("shared_revision"),
                args.get("shared_revision"),
            ]
        shown["first"] = False
        shown["changes"] = (
            {**(changes or {}), **model_effort} if changes or model_effort else None
        )
        shown["same_way"] = shown["changes"] is None
    # How the way was used, as every count of it is made (S2, definition 15.2).
    ways = (
        (version_usage(db, dataset_id).get(revision) or empty())["ways"]
        if revision is not None
        else []
    )
    used = next(
        (
            w
            for w in ways
            if (w["model"], w["effort"], w["shared_revision"]) == way_key(args)
        ),
        None,
    )
    shown["recipe"] = {k: used[k] if used else 0 for k in COUNTS}
    return shown


def plan_now_of(db, box):
    """A waiting run's preview as it reads now, all of it (Sol 2026-10-17: the box kept "kept as
    version 3 when it runs" after a trial had made version 3 of the same write; issue #5-5: the
    images' rows stayed as made while the plan and the card were made now). Computed when read,
    never kept: the box holds only its values."""
    preview = dict(box["preview"] or {})
    if box["state"] != "open" or box["tool"] != "run_start":
        return preview
    args = box["args"]
    if args.get("draft_write_id") is None and args.get("revision") is None:
        return preview
    return run_facts(db, box["dataset_id"], args)[0]


def _image_now(image_id, name, state):
    """An image as the box shows it now, from its state (definition 14): the status of the
    result that is its annotation (else of the last one tried), whether training uses it, and
    the failures since (Astra 2026-10-17 P02: the newest result's "failed" was shown with
    "used for training" from the adoption, two time points in one line)."""
    if state is None:
        return {"id": image_id, "name": name, "result": None, "adopted": None}
    result = state["now"] or state["latest"]
    return {
        "id": image_id,
        "name": name,
        # Results only of an earlier requirement are said so, as the gallery says it
        # (Sol 2026-10-13: "has a result" here, "no annotation" there).
        "result": "stale" if state["used"] == "stale" else (result or {}).get("status"),
        "adopted": state["used"],
        "failures": state["failures"],
    }


def _trials_of(db, dataset_id, revision, way):
    """The trials of a way, per image its newest result (the trial's result a decision to run
    the rest stands on, 12.3)."""
    found = {}
    for run in dataset_runs(db, dataset_id):
        settings = json.loads(run["settings_json"])
        if (
            run["instruction_revision"] != revision
            or not is_trial(settings)
            or way_key(settings) != way
        ):
            continue
        for r in record_results(db, run["id"]):
            found[r["image_id"]] = {"result_id": r["id"], "status": r["status"]}
    names = image_names(db, list(found))
    return [{"image_id": i, "name": names.get(i, i), **v} for i, v in found.items()]


def run_card(db, dataset_id, args, plan, ids, states, estimate, estimated_from=None):
    """The decision card of a run (definition 16.1): what it fixes, what happens and what it
    stands on, the blanks and its weight, from the facts (S1, S2, the plan's line)."""
    trial = bool(args.get("trial"))
    model = args.get("model") or default_choice(db)[0]
    effort = args.get("effort") or default_choice(db)[1]
    revision = plan.get("revision")
    against = plan.get("against") if plan.get("kind") else last_way(db, dataset_id)
    redo = [i for i in ids if (states.get(i) or {}).get("now") is not None]
    # A person's choice stays when a newer result is made (definition 10, 19.6).
    kept = [i for i in redo if states[i]["now"]["picked"]]
    if revision is not None:
        version = version_usage(db, dataset_id).get(revision) or empty()
        key = way_key({**args, "model": model, "effort": effort})
        way = next(
            (
                w
                for w in version["ways"]
                if (w["model"], w["effort"], w["shared_revision"]) == key
            ),
            {k: 0 for k in COUNTS},
        )
        line = lineage(db, dataset_id, revision)
        trials = _trials_of(db, dataset_id, revision, key)
    else:
        # A new version from a write: what it stands on is where the write was started from.
        version = way = None
        write = write_row(db, dataset_id, plan.get("write_id"))
        origin = origin_of(write)
        if origin and origin["kind"] == "version":
            names = {r["id"]: r["name"] for r in dataset_rows(db)}
            origin = {**origin, "name": names.get(origin["dataset_id"])}
        line = {"origin": origin}
        if origin and origin["kind"] == "version":
            line.update(
                lineage(db, origin["dataset_id"], origin["revision"]),
                origin_usage=version_usage(db, origin["dataset_id"]).get(
                    origin["revision"]
                )
                or empty(),
            )
        trials = []
    blanks = [
        name
        for name, empty_ in (
            ("first_run", against is None),
            ("not_tried", not trials),
            ("no_estimate", estimate is None),
        )
        if empty_
    ]
    return {
        "decision": "run_trial" if trial else "run",
        "weight": "light" if trial else "heavy",
        "fixes": {
            "plan": {
                k: plan.get(k)
                for k in (
                    "kind",
                    "write_id",
                    "revision",
                    "next_revision",
                    "written_by",
                    "written_at",
                )
            },
            "model": model,
            "effort": effort,
            # The shared notes for every worker AI the run adds (definition 18.15).
            "shared_revision": args.get("shared_revision"),
            "against": against,
            "changes": plan.get("changes"),
        },
        "happens": {
            "images": len(ids),
            "new": len(ids) - len(redo),
            "redo": len(redo),
            "replaces": [i for i in redo if i not in kept],
            "kept": kept,
            # A success becomes the image's annotation and training uses it unless the image
            # is left out or a person chose its result, a trial's too (S1; Astra 2026-10-17: a
            # trial's card did not say so).
            "used_after": [
                i
                for i in ids
                if not (states.get(i) or {}).get("excluded") and i not in kept
            ],
            # Annotations made by other criteria than the plan's and not checked (definition
            # 85.6): by this plan they are not done, though training still uses them; how many
            # the run makes again.
            "other": _other_criteria(states, ids),
            "estimate_usd": estimate,
            # The datasets of the same plan the estimate came from, when none ran it here.
            "estimate_from": estimated_from,
            "budget_per_image_usd": args["budget_per_image_usd"],
            # Images another decided run holds (definition 18.13): deciding is refused until
            # it ends; the card says so when it is opened.
            "held": writing(db, dataset_id, ids),
        },
        "grounds": {"way": way, "version": version, "line": line, "trials": trials},
        "blanks": blanks,
    }


def run_facts(db, dataset_id, args):
    ids = start_targets(
        db,
        dataset_id,
        args.get("image_ids"),
        bool(args.get("trial")),
        args.get("revision"),
        args.get("draft_write_id"),
    )
    names = image_names(db, ids)
    latest = _latest_results(db, dataset_id, set(ids))
    # The images by the plan the run follows (definition 36.1): what is new or done again.
    judged_by = plan_basis(
        db, dataset_id, args.get("revision"), args.get("draft_write_id")
    )
    _, states = image_states(db, dataset_id, *judged_by)
    model = args.get("model") or default_choice(db)[0]
    plan = (
        box_plan(db, dataset_id, args)
        if args.get("draft_write_id") is not None or args.get("revision") is not None
        else {
            "kind": None,
            "revision": latest_revision(db, dataset_id),
            "next_revision": None,
        }
    )
    # What one image costs by the run's way (usage.expected_cost, the one place; definition 84).
    effort = args.get("effort") or default_choice(db)[1]
    expected = expected_cost(db, dataset_id, judged_by[0], (model, effort))
    average = expected["per_image_usd"] if expected else None
    basis = expected["results"] if expected else 0
    estimated_from = expected["from"] if expected else None
    preview = {
        "images": [_image_now(i, names.get(i, i), states.get(i)) for i in ids],
        "model": model,
        "effort": effort,
        "budget_per_image_usd": args["budget_per_image_usd"],
        "trial": bool(args.get("trial")),
        # The plan the run follows, held by the box (Sol 2026-10-08: not seen in the box).
        "plan": plan,
        "revision": plan["revision"] or plan["next_revision"],
        "draft": plan["kind"] == "write" and plan["revision"] is None,
        "estimate_usd": str(round(average * len(ids), 4)) if average else None,
        "estimate_basis": {
            "per_image_usd": str(round(average, 4)),
            "results": basis,
            # None ran it here: the datasets of the same plan it came from (definition 84).
            "from": estimated_from,
        }
        if average
        else None,
        # Cheap but unsure in reading (user 2026-10-09): the screen asks to check more by eye.
        "warning": "haiku_accuracy" if "haiku" in (model or "") else None,
    }
    # What deciding needs, in one form for every screen (definition 16.1).
    preview["card"] = run_card(
        db, dataset_id, args, plan, ids, states, preview["estimate_usd"], estimated_from
    )
    # The plan is held by value: a new version since does not make the box old.
    premise = {"results": {i: (latest.get(i) or {}).get("id") for i in ids}}
    return preview, premise


def _other_criteria(states, ids):
    """{images, in_run}: the images whose annotation now was made by other criteria and not
    checked, and how many of them the run takes."""
    other = {i for i, s in states.items() if s["now"] is not None and s["now"]["other"]}
    return {"images": len(other), "in_run": len(other & set(ids))}


def mark_facts(db, dataset_id, args):
    """Not used or used again: an image (its use), or a record used (definition 19.5: its images
    use its results; definition 54: never "not used")."""
    _, states = image_states(db, dataset_id, *latest_basis(db, dataset_id))
    preview = {"target": args.get("target"), "excluded": args.get("excluded")}
    if args.get("target") == "image":
        image_id = args.get("image_id")
        check_in_dataset(db, dataset_id, image_id)
        adopted = _adopted(db, dataset_id)
        counted = [s for s in adopted.values() if s == "result"]
        now_out = states[image_id]["excluded"]
        counts = len(counted)
        after = counts
        if args.get("excluded") and adopted.get(image_id) == "result":
            after -= 1
        preview.update(
            image={"id": image_id, "name": image_names(db, [image_id]).get(image_id)},
            excluded_now=now_out,
            adopted_now=counts,
            adopted_after=after if args.get("excluded") else None,
            images=len(adopted),
        )
        latest = _latest_results(db, dataset_id, {image_id})
        premise = {
            "excluded": now_out,
            "result": (latest.get(image_id) or {}).get("id"),
        }
        return preview, premise
    run = run_row(db, args.get("run_id"))
    if run["dataset_id"] != dataset_id:
        raise invalid("The record is of another dataset")
    made = {
        r["image_id"]: r
        for r in record_results(db, run["id"])
        if r["image_id"] in states
    }
    names = image_names(db, list(made))
    rows = []
    for image_id, result in made.items():
        now = states[image_id]["now"]
        if (now is not None and now["run_id"] == run["id"]) or result[
            "status"
        ] not in SUCCESS:
            continue
        rows.append(
            {
                "id": image_id,
                "name": names.get(image_id, image_id),
                "now_run": now["record_number"] if now else None,
                "after_run": run_number(db, run["id"]),
            }
        )
    preview.update(
        run_id=run["id"],
        # Named by its number on the screen (user 2026-10-17: never "this record").
        run_number=run_number(db, run["id"]),
        rows=rows,
    )
    # What each of its images uses now.
    premise = {
        "now": {
            i: states[i]["now"]["result_id"] if states[i]["now"] else None for i in made
        }
    }
    return preview, premise


FACTS = {
    "run_start": run_facts,
    "run_stop": data_facts.stop_facts,
    "mark": mark_facts,
    "pick": data_facts.pick_facts,
    "confirm": data_facts.confirm_facts,
    "carry": data_facts.carry_facts,
    "dataset_add_images": data_facts.add_facts,
    "dataset_remove_images": data_facts.remove_facts,
    "label_rename": data_facts.label_facts,
    "label_change": data_facts.change_facts,
    "dataset_rename": data_facts.rename_facts,
    "dataset_create": data_facts.create_facts,
    "dataset_from": data_facts.from_facts,
    "dataset_import": data_facts.import_facts,
    "dataset_delete": data_facts.delete_facts,
}


def _results_named(db, image_ids, results):
    """The images by name, each with the record its result now is from and whether that record
    is still annotating it (its result is made, waiting, when the run is decided)."""
    names = image_names(db, image_ids)
    out = []
    for image_id in image_ids:
        found = result_row(db, results[image_id]) if results.get(image_id) else None
        out.append(
            {
                "name": names.get(image_id, image_id),
                "record_number": found["record_number"] if found else None,
                "going": bool(found) and found["status"] in WAITING,
            }
        )
    return out


def run_changed(db, dataset_id, args, before, after):
    changed = [i for i, r in before["results"].items() if after["results"].get(i) != r]
    return {"kind": "results", "images": _results_named(db, changed, after["results"])}


def mark_changed(db, dataset_id, args, before, after):
    if args.get("target") != "image":
        changed = [i for i, r in before["now"].items() if after["now"].get(i) != r]
        names = image_names(db, changed)
        return {"kind": "use", "names": [names.get(i, i) for i in changed]}
    image_id = args.get("image_id")
    if before.get("excluded") != after.get("excluded"):
        name = image_names(db, [image_id]).get(image_id, image_id)
        done = after.get("excluded") == bool(args.get("excluded"))
        return {"kind": "done" if done else "excluded", "image": name}
    return {
        "kind": "results",
        "images": _results_named(db, [image_id], {image_id: after.get("result")}),
    }


# What changed between a decision's premise and now, next to the premise each type stands on.
CHANGED = {
    "run_start": run_changed,
    "run_stop": data_facts.stop_changed,
    "mark": mark_changed,
    "pick": data_facts.pick_changed,
    "confirm": data_facts.confirm_changed,
    "carry": data_facts.carry_changed,
    "dataset_add_images": None,  # stands on nothing that changes
    "dataset_remove_images": data_facts.remove_changed,
    "label_rename": data_facts.label_changed,
    "label_change": data_facts.label_changed,
    "dataset_rename": data_facts.rename_changed,
    "dataset_create": None,
    "dataset_from": data_facts.from_changed,
    "dataset_import": None,
    "dataset_delete": data_facts.delete_changed,
}
assert set(FACTS) == set(CHANGED) == set(DECISIONS), "Every decision has its facts"


def what_changed(db, dataset_id, tool, args, before, after):
    """What changed under a waiting decision, by name (definition 18.13): the images with a
    newer result (and the record of it), the plan kept or written again, an image or a record
    not used or used again, or what an image of a record uses."""
    return CHANGED[tool](db, dataset_id, args, before, after)


def facts(db, dataset_id, tool, args):
    """(preview, premise) of a decision."""
    return FACTS[tool](db, dataset_id, args)

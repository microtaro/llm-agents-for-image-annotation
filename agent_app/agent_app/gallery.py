"""What the gallery shows per image for one view: images, a run's results (or the version's,
newest per image), what training gets, or the adoption (docs/2026-10-05-app-step6-design.md 3;
the master and inspection views were taken out, types design 6). Read only.
"""

import json
from collections import Counter

from .annotation_sets import current
from .datasets import dataset_row, image_rows
from .errors import invalid
from .image_state import image_states, result_of, state_counts
from .instructions import basis_of
from .label_colors import current_labels, dataset_colors
from .label_ids import names_now
from .label_rules import unfilled
from .run_queries import (
    GOING,
    ran_plan,
    record_results,
    record_row,
    run_row,
    status_facts,
)

VIEWS = ("images", "run", "production", "adoption")


def _shapes(db, result, name):
    """The annotations a card draws: label (named now, definition 23.4), geometry,
    attributes."""
    return [
        {
            "id": a["id"],
            "label": name(result["revision"], a["label"]),
            "geometry": a["geometry"],
            "attributes": a["attributes"],
            "parent_id": a["parent_id"],
            "number": a["number"],
        }
        for a in current(db, result["set_id"])
    ]


def _record_items(db, dataset_id, record_id, name):
    """One record's results (a run's, or a person's fix's: definition 21.4), per image."""
    if record_row(db, record_id)["dataset_id"] != dataset_id:
        raise invalid("The record is of another dataset")
    results = {r["image_id"]: result_of(r) for r in record_results(db, record_id)}

    def item(image_id):
        result = results.get(image_id)
        if result is None:
            return {"kind": "not_in_run"}, []
        return _badge_of(result), _shapes(db, result, name)

    return item


def _badge_of(result):
    """A card's badge for one result of the images' states: its state and where it came from."""
    return {
        "kind": result["status"],
        **status_facts(result["status"]),
        "result_id": result["result_id"],
        # Its record (a run, or a person's fix), by number and the version it was made with
        # (user 2026-10-14: which version a result came from was seen only in the loupe).
        "record_id": result["record_id"],
        "record_number": result["record_number"],
        "record_revision": result["revision"],
        "record_at": result["record_at"],
        "model": result["model"],
        "trial": result["trial"],
        "elapsed_ms": result["elapsed_ms"],
        "cost_usd": result["cost_usd"],
        "by": result["by"],
        "record_kind": result["record_kind"],
    }


def _version_items(db, states, name):
    """③ (and ①) with no run chosen: per image, its annotation now (a person's choice, else
    the newest success of the requirement), else its newest result in any state, as the
    images' states say it (image_state.py, definition 14). The cards then show what the map
    counts (user 2026-10-07: "4 runs · with a result 2/20" over the cards of the last run,
    with one success)."""

    def item(image_id):
        state = states[image_id]
        now = state["now"]
        result = now or state["latest"]
        if result is None:
            return {"kind": "no_result"}, []
        badge = _badge_of(result)
        if now is not None:
            # By the criteria it is judged by (definition 85.4).
            badge.update(
                criteria=now["criteria"], checked=now["checked"], other=now["other"]
            )
        return badge, _shapes(db, result, name)

    return item


def _production_items(db, states, name):
    """② with no run chosen: what training gets, as the adoption (excluded, the result now),
    and for an image with none of them its newest result's state (failed, running…) so what
    is left to run shows."""
    adopted = _adoption_items(db, states, name)

    def item(image_id):
        badge, shapes = adopted(image_id)
        state = states[image_id]
        found = state["latest"]
        if state["used"] == "excluded":
            # Left out, with or without a result: the card's mark is ✓ (ran) or empty (types
            # design 17.1).
            return {**badge, "ran": "result_id" in badge}, shapes
        if state["used"] == "result" or found is None:
            return ({"kind": "no_result"} if state["used"] == "none" else badge), shapes
        return {
            "kind": found["status"],
            **status_facts(found["status"]),
            "result_id": found["result_id"],
            "record_id": found["record_id"],
            "record_number": found["record_number"],
            "record_revision": found["revision"],
            "record_at": found["record_at"],
            "model": found["model"],
            "trial": found["trial"],
        }, []

    return item


def _adoption_items(db, states, name):
    def item(image_id):
        state = states[image_id]
        now = state["now"]
        badge = {"kind": state["used"]}
        shown = None
        if now is not None and state["used"] in ("excluded", "result"):
            # Left out: the record it would use, shown with its objects (user 2026-10-16).
            badge.update(
                result_id=now["result_id"],
                record_id=now["record_id"],
                record_number=now["record_number"],
                record_revision=now["revision"],
                record_at=now["record_at"],
                model=now["model"],
                trial=now["trial"],
                by=now["by"],
                record_kind=now["record_kind"],
                # By the criteria it is judged by (definition 85.4).
                criteria=now["criteria"],
                checked=now["checked"],
                other=now["other"],
            )
            if state["used"] == "result":
                # A person's fix, a person's choice, a newer result than the choice (7.2).
                badge.update(picked=now["picked"], newer=now["newer"])
            shown = now
        return badge, _shapes(db, shown, name) if shown else []

    return item


def gallery(db, dataset_id, view, plan, record_id=None):
    """The images of a view with their states judged by the plan (a version's, a draft
    write's, the latest version's, given by whoever looks: definition 35.7, 36.1, 85.4): its
    requirement and criteria, and its attributes not filled (85.17). {}: a blank plan's (no
    plan yet, or one not begun), by which every result is another plan's (49.1)."""
    dataset_row(db, dataset_id)
    if view not in VIEWS:
        raise invalid("view must be images, run, production or adoption")
    key, criteria = basis_of(plan)
    definitions = plan.get("label_definitions")
    # The images' states, read once and the same for every view (definition 14).
    _, states = image_states(db, dataset_id, key, criteria)
    name = names_now(db, dataset_id)
    if view == "run" and record_id:
        item = _record_items(db, dataset_id, record_id, name)
    elif view == "run":
        item = _version_items(db, states, name)
    elif view == "production":
        item = _production_items(db, states, name)
    elif view == "adoption":
        item = _adoption_items(db, states, name)
    else:
        # The images view: each image as it is, judged by no plan's results.

        def item(_image_id):
            return {"kind": "none"}, []

    if not (view == "run" and record_id) and view != "images":
        plain = item

        def item(image_id):
            badge, shapes = plain(image_id)
            failures = states[image_id]["failures"]
            if failures:
                badge = {**badge, "failures": failures}
            # The plan's attributes its annotation now has no value of (definition 85.17).
            now = states[image_id]["now"]
            if definitions and now is not None:
                objects = (
                    shapes
                    if badge.get("result_id") == now["result_id"]
                    else _shapes(db, now, name)
                )
                missing = unfilled(definitions, objects)
                if missing:
                    badge = {**badge, "unfilled": missing}
            return badge, shapes

    images = image_rows(db, dataset_id)
    # For an image with only an earlier requirement's results, the newest of them with its
    # record and version (user 2026-10-13: "the earlier requirement" and "the one before" did
    # not say which), from the images' states (issue #4 F-06: counted here apart).
    earlier = {i: s["earlier"] for i, s in states.items() if s["earlier"]}
    items = []
    for image in images:
        badge, shapes = item(image["id"])
        if badge.get("kind") == "no_result" and image["id"] in earlier:
            # Only an earlier requirement's result: said so in ① as in ② (Sol 2026-10-14).
            badge = {"kind": "stale"}
        if badge.get("kind") == "stale" and image["id"] in earlier:
            # Its record too (Sol 2026-10-14: a trial of version 1 showed no record number nor
            # "trial" on its card, as the list and the loupe do).
            found = earlier[image["id"]]
            badge = {
                **badge,
                "earlier_revision": found["revision"],
                "record_id": found["record_id"],
                "record_number": found["record_number"],
                "record_revision": found["revision"],
                "record_at": found["record_at"],
                "model": found["model"],
                "trial": found["trial"],
            }
        items.append(
            {
                "image": {
                    "id": image["id"],
                    "name": image["name"],
                    "width": image["width"],
                    "height": image["height"],
                    "origin": image["origin"],
                    "source_path": image["source_path"],
                    "excluded": states[image["id"]]["excluded"],
                },
                "badge": badge,
                "annotations": shapes,
            }
        )
    # The legend: today's labels and those drawn here, not every name a label ever had
    # (found 2026-10-05: a label renamed and back kept its passing name in the legend).
    shown = current_labels(db, dataset_id) | {
        a["label"] for item in items for a in item["annotations"]
    }
    return {
        "view": view,
        "record_id": record_id,
        "requirement_key": key,
        # The images in each state by the requirement judged by (definition 57), as the
        # dataset's card counts them.
        "counts": state_counts(states),
        # For each attribute of the plan, the images it is not filled in (85.17): counted
        # here, where the attributes are seen, not on the card.
        "unfilled": dict(
            Counter(n for i in items for n in i["badge"].get("unfilled", ()))
        ),
        "label_colors": {
            label: color
            for label, color in dataset_colors(db, dataset_id, shown).items()
            if label in shown
        },
        "items": items,
        "missing_labels": _missing_labels(db, dataset_id, view, record_id, items, name),
    }


def _missing_labels(db, dataset_id, view, record_id, items, name):
    """A record's plan's labels none of its results has (definition 38.5: samples show only
    what their images have, so a label a plan defines may be in none of them); [] for the
    other views, and while the record is still annotating (test 10-28: every run of the test
    said a label was missing before the samples were done)."""
    if view != "run" or not record_id:
        return []
    if (
        record_row(db, record_id)["kind"] == "run"
        and run_row(db, record_id)["status"] in GOING
    ):
        return []
    row = next(iter(record_results(db, record_id)), None)
    if row is None or row["instruction_revision"] is None:
        return []
    revision = row["instruction_revision"]
    drawn = {a["label"] for item in items for a in item["annotations"]}
    # The record's own plan: a trial of a draft has no version (found 2026-10-27: reading
    # version 0 failed the record's whole gallery).
    settings = json.loads(row["settings_json"]) if row["settings_json"] else {}
    labels = ran_plan(db, dataset_id, revision, settings).get("label_definitions") or []
    return [n for n in (name(revision, d["name"]) for d in labels) if n not in drawn]

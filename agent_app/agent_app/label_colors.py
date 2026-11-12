"""Label colors per dataset (DESIGN.md 6): a label gets the first palette color not yet used,
in the order labels first appear in the instruction, and keeps it until a person changes or
resets it. A run copies the colors when it starts, so its worker always sees the same ones.
"""

import json
import re

from pydantic import Field

from .datasets import dataset_row
from .drafts import plan_draft, plans_held
from .errors import Model, invalid
from .imaging import PALETTE
from .instructions import version_rows

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ColorsInput(Model):
    colors: dict[str, str] = Field(description="Label -> #RRGGBB.")


def _plan_labels(db, dataset_id):
    """Every label of the dataset's instruction versions and then its draft, in the order
    they first appear (found 2026-10-05: a trial of a draft's new label had no color)."""
    seen = []
    rows = [
        *version_rows(db, dataset_id),
        *(r for r in (plan_draft(db, dataset_id),) if r),
    ]
    for row in rows:
        for definition in json.loads(row["payload_json"])["label_definitions"]:
            if definition["name"] not in seen:
                seen.append(definition["name"])
    return seen


def current_labels(db, dataset_id):
    """The labels of the latest instruction version and of the draft."""
    return {
        d["name"]
        for plan in plans_held(db, dataset_id)
        for d in plan["label_definitions"]
    }


def dataset_colors(db, dataset_id, drawn=()):
    """Label -> color for every label; labels without one get theirs now (and keep it).
    drawn: labels shown that no instruction names now (an old run's) get one
    too, else they would be drawn in the fallback color (Astra 2026-10-07)."""
    wanted = [*_plan_labels(db, dataset_id), *sorted(drawn)]
    stored = _stored(db, dataset_id)
    # Read only when every label has its color: opening a gallery takes no write lock
    # (review 2026-10-07: every GET began BEGIN IMMEDIATE, waiting on a run's writes).
    if all(label in stored for label in wanted):
        return stored
    with db.transaction():
        stored = _stored(db, dataset_id)
        for label in wanted:
            if label in stored:
                continue
            used = set(stored.values())
            color = next(
                (c for c in PALETTE if c not in used),
                PALETTE[len(stored) % len(PALETTE)],
            )
            stored[label] = color
            db.execute(
                "INSERT INTO label_colors(dataset_id, label, color) VALUES(?,?,?)",
                (dataset_id, label, color),
            )
    return stored


def of_result(db, row):
    """The colors a result is drawn in (a row of result_records): its run's, copied when it
    started so its worker sees the same ones; a person's fix or a record taken in has no run,
    the dataset's now (review 2026-10-28 B#12: a worker looking at a fix failed)."""
    if row["settings_json"]:
        return json.loads(row["settings_json"])["label_colors"]
    return dataset_colors(db, row["dataset_id"])


def _stored(db, dataset_id):
    return {
        r["label"]: r["color"]
        for r in db.execute(
            "SELECT label, color FROM label_colors WHERE dataset_id=?", (dataset_id,)
        )
    }


def move_color(db, dataset_id, old, new):
    """A label's color goes with it to the name it takes, unless that name has one; the old
    name's goes (definition 79.3; 26.1 a rename, 79 a change)."""
    if db.one(
        "SELECT 1 FROM label_colors WHERE dataset_id=? AND label=?", (dataset_id, new)
    ):
        db.execute(
            "DELETE FROM label_colors WHERE dataset_id=? AND label=?", (dataset_id, old)
        )
        return
    db.execute(
        "UPDATE label_colors SET label=? WHERE dataset_id=? AND label=?",
        (new, dataset_id, old),
    )


def set_colors(db, dataset_id, body: ColorsInput):
    dataset_row(db, dataset_id)
    for label, color in body.colors.items():
        if not HEX.match(color):
            raise invalid("A color is #RRGGBB", label=label, color=color)
    with db.transaction():
        for label, color in body.colors.items():
            db.execute(
                "INSERT INTO label_colors(dataset_id, label, color) VALUES(?,?,?)"
                " ON CONFLICT(dataset_id, label) DO UPDATE SET color=excluded.color",
                (dataset_id, label, color.upper()),
            )
    return {"colors": dataset_colors(db, dataset_id)}


def reset_colors(db, dataset_id):
    """Back to the palette in the instruction's order."""
    dataset_row(db, dataset_id)
    with db.transaction():
        db.execute("DELETE FROM label_colors WHERE dataset_id=?", (dataset_id,))
    return {"colors": dataset_colors(db, dataset_id)}

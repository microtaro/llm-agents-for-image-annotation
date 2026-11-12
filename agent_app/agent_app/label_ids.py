"""A label's own id (definition 23, 20.2; issue #4 F-01: a label was told apart only by its name,
so renaming it made every earlier result one of another requirement). The id is given where a
plan's content is written (with_ids), and a result, kept with the names of the version that made
it, is read with the names now (names_now).
"""

import json
import uuid


def new_label_id():
    return "lbl-" + uuid.uuid4().hex[:8]


def with_ids(definitions, before=()):
    """The label definitions each with an id: its own when it has one (one copied from another
    dataset's plan too), else that of the label of the same name before (the plan now), else a
    new one. An id given twice in one plan is another label the second time."""
    by_name = {d["name"]: d["id"] for d in before or () if d.get("id")}
    seen, out = set(), []
    for d in definitions:
        label_id = d.get("id") or by_name.get(d["name"]) or new_label_id()
        if label_id in seen:
            label_id = new_label_id()
        seen.add(label_id)
        out.append({**d, "id": label_id})
    return out


def _ids_at(db, dataset_id):
    """revision -> {name: id} of each version of the dataset."""
    from .instructions import version_rows  # instructions gives labels their ids

    ids_at = {}
    for row in version_rows(db, dataset_id):
        definitions = json.loads(row["payload_json"])["label_definitions"]
        ids_at[row["revision"]] = {d["name"]: d["id"] for d in definitions}
    return ids_at


def names_now(db, dataset_id):
    """A function (version, name) -> the name now: a result keeps the names of the version that
    made it; its label is the id that name had in that version, named as the library names it
    now (definition 26.1: every version's label is the library's)."""
    return names_in(db, dataset_id, [])


def names_in(db, dataset_id, definitions):
    """A function (version, name) -> the name a plan's definitions give the label a result of
    that version names (by the label's id: a reference is read in the plan it is in, definition
    38.1); a label the plan does not have, as the library names it now."""
    from .label_library import names

    ids_at = _ids_at(db, dataset_id)
    name_of = {**names(db), **{d["id"]: d["name"] for d in definitions if d.get("id")}}

    def name(revision, label):
        label_id = ids_at.get(revision, {}).get(label)
        return name_of.get(label_id, label)

    return name

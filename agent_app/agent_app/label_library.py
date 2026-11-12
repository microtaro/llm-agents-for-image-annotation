"""The labels of the whole library (definition 26.1): a label is one thing for every dataset, told
apart by its id; its name (one per label) is the library's. A plan points at a library label by
its id and says how it is taken there (shape, attributes, parent). A word a person said the
label is (an alias) finds it too. A label new to the library enters it when a version is made
of the plan that has it (a draft only holds it).
"""

import unicodedata

from fastapi import APIRouter, Request

from .db import now
from .errors import not_found
from .label_ids import with_ids

router = APIRouter(prefix="/v1")


def key_of(name):
    """The key a name or an alias is found by: NFKC, without the spaces around it."""
    return unicodedata.normalize("NFKC", name or "").strip()


def _names_and_keys(db):
    names = {r["id"]: r["name"] for r in db.execute("SELECT id, name FROM labels")}
    by_key = {
        r["name_key"]: r["id"] for r in db.execute("SELECT id, name_key FROM labels")
    }
    for r in db.execute("SELECT alias_key, label_id FROM label_aliases"):
        by_key.setdefault(r["alias_key"], r["label_id"])
    return names, by_key


def names(db):
    """id -> the library's name of every label."""
    return _names_and_keys(db)[0]


def relabel_plan(payload, renames):
    """A plan's content with the names changed by renames wherever a name says a label: the
    definitions and their parents. Its references are results, records that keep the names of
    the version that made them and are read with the names now (references.resolved)."""
    if not renames:
        return payload
    out = dict(payload)
    out["label_definitions"] = [
        {
            **d,
            "name": renames.get(d["name"], d["name"]),
            "parent": renames.get(d.get("parent"), d.get("parent")),
        }
        for d in payload.get("label_definitions") or []
    ]
    return out


def with_library(db, payload, before=()):
    """A plan's content with each label the library's (26.1): a label with a library id keeps
    it and takes the library's name; else a name or an alias the library has is that label;
    else the label of the same name in the plan before, else a new label (not yet in the
    library). The names a label takes are changed everywhere in the content."""
    library_names, by_key = _names_and_keys(db)
    renames, resolved = {}, []
    for d in payload.get("label_definitions") or []:
        label_id = d.get("id") if d.get("id") in library_names else None
        if label_id is None:
            label_id = by_key.get(key_of(d["name"]))
        if label_id is not None:
            name = library_names[label_id]
            if name != d["name"]:
                renames[d["name"]] = name
            resolved.append({**d, "id": label_id})
        else:
            resolved.append(d)
    out = relabel_plan({**payload, "label_definitions": resolved}, renames)
    out["label_definitions"] = with_ids(out["label_definitions"], before)
    return out


def register(db, definitions, actor):
    """The labels of a version new to the library enter it (26.1). Their names are no label's
    of the library: with_library made each name the library has its label."""
    library_names = names(db)
    for d in definitions:
        if d["id"] in library_names:
            continue
        db.execute(
            "INSERT INTO labels(id, name, name_key, description, created_at, created_by)"
            " VALUES(?,?,?,?,?,?)",
            (
                d["id"],
                d["name"],
                key_of(d["name"]),
                d.get("description") or "",
                now(),
                actor,
            ),
        )


def add_alias(db, label_id, word, actor):
    """A word a person said is this label (a question answered, 26.4): found by it from then on.
    A word that is already a name or another label's alias is left as it is."""
    if db.one("SELECT 1 FROM labels WHERE id=?", (label_id,)) is None:
        raise not_found("Label")
    key = key_of(word)
    if not key or db.one("SELECT 1 FROM labels WHERE name_key=?", (key,)):
        return
    db.execute(
        "INSERT OR IGNORE INTO label_aliases(alias_key, alias, label_id, created_at, created_by)"
        " VALUES(?,?,?,?,?)",
        (key, word.strip(), label_id, now(), actor),
    )


def datasets_of(db):
    """label id -> the datasets that use it, in their latest version or their plan's draft (a
    rename changes those; test C12 10-28: a dataset whose plan was copied had a draft only)."""
    from .drafts import every_plan_held  # a plan takes the library's labels

    out = {}
    for dataset_id, plan in every_plan_held(db):
        for d in plan["label_definitions"]:
            using = out.setdefault(d.get("id"), [])
            if dataset_id not in using:
                using.append(dataset_id)
    return out


def list_labels(db):
    uses = datasets_of(db)
    aliases = {}
    for r in db.execute(
        "SELECT label_id, alias FROM label_aliases ORDER BY created_at"
    ):
        aliases.setdefault(r["label_id"], []).append(r["alias"])
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "aliases": aliases.get(r["id"], []),
            "description": r["description"],
            "datasets": len(uses.get(r["id"], [])),
        }
        for r in db.execute("SELECT * FROM labels ORDER BY name")
    ]


def label_named_as(db, name):
    """The library's label of that name (as names are compared, key_of), None."""
    return db.one("SELECT * FROM labels WHERE name_key=?", (key_of(name),))


def rename(db, label_id, name):
    """The library's label takes the name, in every dataset that has it (26.1)."""
    db.execute(
        "UPDATE labels SET name=?, name_key=? WHERE id=?",
        (name, key_of(name), label_id),
    )


def label_row(db, label_id):
    row = db.one("SELECT * FROM labels WHERE id=?", (label_id,))
    if row is None:
        raise not_found("Label")
    return row


@router.get("/labels")
def get_labels(request: Request):
    return {"items": list_labels(request.app.state.db)}


@router.get("/labels/{label_id}")
def get_label(request: Request, label_id: str):
    db = request.app.state.db
    row = label_row(db, label_id)
    item = next(i for i in list_labels(db) if i["id"] == row["id"])
    return {**item, "dataset_ids": datasets_of(db).get(label_id, [])}

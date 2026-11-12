"""Taking in a folder written out (definition 60.3, the 4th thing to do): what it holds is found
from its files (the scan before taking in tells it; the person does not choose it). One
decision of the library per dataset made.

- This app's form (dataset_export.FORMAT, its app.json's history): each dataset folder (the one chosen,
  or the folders directly in it) becomes a new dataset, its plan's versions and draft, its annotation records
  (AI runs, people's fixes), what training uses and its fixed versions as they were. The images
  are the same images by their bytes (identical bytes are one image); every other id is new. A
  label is the library's label of its id or its name now (label_library.with_library), else a
  new one; a version keeps the names it was made with (it is a record; 2026-10-30: taken in, an
  earlier version took the names now) and where it was started from in the same dataset. A
  version's requirement is computed again from its labels, and its runs and fixes follow it. A
  name the library has gets " (2)", " (3)"... One decision of the library per dataset.
- COCO's JSON (a file directly in the folder holding images, annotations and categories, as
  this app, COCO Annotator and FiftyOne write it): a new dataset named and purposed by the
  person, its first version made from the categories and one record taken in (coco_import.py).
"""

import json
from dataclasses import replace
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import Field

from . import decisions
from .actors import SERVER
from .config import APP, REPO
from .dataset_export import FORMAT, VERSION
from .datasets import GeneratedOrigin, Name, Purpose, insert_dataset, insert_images
from .db import encoded, log, new_id
from .decisions import By, by_of
from .drafts import take_in_plan_draft
from .errors import ApiError, Model
from .images import store_image
from .instructions import requirement_key
from .label_library import register, with_library
from .system import THIS_COMPUTER

router = APIRouter(prefix="/v1")


class DatasetImportInput(Model):
    path: str = Field(
        min_length=1,
        max_length=4096,
        description=f"A folder {THIS_COMPUTER} written out: this app's form (a dataset's"
        " folder, or a folder holding datasets' folders) or COCO's JSON with its images.",
    )
    name: Name | None = Field(
        None,
        description="COCO: the new dataset's name (this app's form keeps its own).",
    )
    purpose: Purpose | None = Field(
        None, description="COCO: what it is for, fixed once made."
    )
    origin: GeneratedOrigin | None = Field(
        None,
        description="COCO: null for photographed images; generated images say how.",
    )


def _read_document(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _document(folder):
    """A folder's dataset.json when it is this app's form, with its app.json's history under
    "app" (definition 60.14), else None. A folder of an earlier form held "app" in its
    dataset.json: it is kept, so taking it in says which form it is (_store_files)."""
    document = _read_document(folder / "dataset.json")
    if not (isinstance(document, dict) and document.get("format") == FORMAT):
        return None
    history = _read_document(folder / "app.json")
    if (
        isinstance(history, dict)
        and history.get("format") == FORMAT
        and history.get("version") == document.get("version")
    ):
        document["app"] = history.get("app")
    return document if isinstance(document.get("app"), dict) else None


def _app_folders(path):
    """The datasets' folders of this app's form: the one given, or those directly in it."""
    if _document(path) is not None:
        return [path]
    try:
        return sorted(
            p for p in path.iterdir() if p.is_dir() and _document(p) is not None
        )
    except OSError:
        return []


def _coco(path):
    """A COCO JSON's file directly in the folder, read as one: (its name, the document)."""
    for file in sorted(path.glob("*.json")):
        try:
            document = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(document, dict) and {
            "images",
            "annotations",
            "categories",
        } <= set(document):
            return file.name, document
    return None


def written_in(raw):
    """What a folder written out holds, or None (a folder of images, or nothing written)."""
    try:
        path = Path(raw).expanduser().resolve(strict=True)
    except (OSError, ValueError):
        return None
    if not path.is_dir():
        return None
    folders = _app_folders(path)
    if folders:
        datasets = []
        for folder in folders:
            document = _document(folder)
            datasets.append(
                {
                    "folder": str(folder),
                    "name": document["dataset"]["name"],
                    "purpose": document["dataset"]["purpose"],
                    "images": len(document["images"]),
                    "revision": max(
                        (i["revision"] for i in document["app"]["instructions"]),
                        default=None,
                    ),
                    "records": sum(
                        len(document["app"].get(k, []))
                        for k in ("runs", "fixes", "imports", "copies")
                    ),
                }
            )
        return {"kind": "app", "path": str(path), "datasets": datasets}
    found = _coco(path)
    if found:
        name, document = found
        return {
            "kind": "coco",
            "path": str(path),
            "file": name,
            "images": len(document["images"]),
            "annotations": len(document["annotations"]),
            "categories": [c.get("name") for c in document["categories"]][:50],
        }
    return None


def _insert(db, table, row, columns):
    """A row written out, its JSON columns (*_json, written as the JSON they hold) as text."""
    keys = [k for k in row if k in columns]
    db.execute(
        f"INSERT INTO {table}({','.join(keys)}) VALUES({','.join('?' * len(keys))})",
        [
            encoded(row[k]) if k.endswith("_json") and row[k] is not None else row[k]
            for k in keys
        ],
    )


def _name(db, name):
    """The dataset's name, or with " (2)", " (3)"... when the library has it (as a folder written
    out; 2026-11-05: "（取り込み）" was Japanese on an English person's screen)."""
    taken = {r["name"] for r in db.execute("SELECT name FROM datasets")}
    candidate, n = name, 1
    while candidate in taken:
        n += 1
        candidate = f"{name} ({n})"
    return candidate


def _taken_labels(db, app, actor):
    """{a label's id where it was written: its label here}: the library's labels the plans name,
    each the library's by its id, else by its name now or an alias, else entered new (26.1)."""
    written = app["library_labels"]
    taken = with_library(
        db,
        {
            "label_definitions": [
                {"id": w["id"], "name": w["name"], "description": w["description"]}
                for w in written
            ]
        },
    )["label_definitions"]
    register(db, taken, actor)
    return {w["id"]: d["id"] for w, d in zip(written, taken)}


def _plan(payload, ids, labels):
    """A plan's content with its labels the library's here, named as it was made, its
    references at the new results; (the content, its requirement key computed again)."""
    payload = {
        **payload,
        "label_definitions": [
            {**d, "id": labels[d["id"]]} for d in payload.get("label_definitions") or []
        ],
    }
    payload["references"] = [
        {
            **p,
            "result_id": ids[p["result_id"]],
            "set_id": ids.get(p.get("set_id"), p.get("set_id")),
        }
        for p in payload.get("references") or []
        if p.get("result_id") in ids
    ]
    return payload, requirement_key(payload.get("label_definitions") or [])


def _store_files(db, folder, document):
    """One dataset's images and masks of this app's form, stored before its records are (outside
    the transaction, as making a dataset does): the same bytes are the same image, so the ids
    the records name stay right."""
    if document.get("version") != VERSION:
        raise ApiError(
            422,
            "written_version",
            "The folder was written by another version of the app",
            {"folder": str(folder), "version": document.get("version")},
        )
    app = document["app"]
    # The images its records name that it no longer held are stored too, not made its images.
    for image in [*app["images"], *app["record_images"]]:
        origin = None
        if image.get("origin") == "generated":
            origin = {"kind": "generated", "how": image.get("origin_json") or {}}
        stored = store_image(
            db,
            (folder / image["file"]).read_bytes(),
            image["name"],
            str(folder / image["file"]),
            origin,
        )
        if stored["id"] != image["id"]:
            raise ApiError(
                422,
                "written_changed",
                "An image file differs from the one written",
                {"file": image["file"]},
            )
    for sha in {a["mask_sha256"] for a in app["annotations"] if a.get("mask_sha256")}:
        if db.files.put("masks", (folder / "masks" / f"{sha}.png").read_bytes()) != sha:
            raise ApiError(
                422,
                "written_changed",
                "A mask differs from the one written",
                {"file": sha},
            )


def _take_in(db, folder, document, decision_id, actor):
    """One dataset of this app's form (its "app" part), new in the library, inside the import's
    transaction and of its decision; {id, name, images} and where it came from."""
    app = document["app"]
    # Every id but an image's is new.
    ids = {}
    for table, prefix in (
        ("runs", ""),
        ("fixes", ""),
        ("imports", "imp-"),
        ("copies", "cpy-"),
        ("results", "res-"),
        ("annotation_sets", "set-"),
        ("annotations", "ann-"),
        ("recipes", "rec-"),
    ):
        for row in app.get(table, []):
            ids[row["id"]] = new_id(prefix)
    dataset_id = new_id()
    name = _name(db, document["dataset"]["name"])
    # A number of this library's (definition 61), not the one it had where it was written.
    insert_dataset(db, dataset_id, name, document["dataset"]["purpose"], decision_id)
    files = {
        image["id"]: str(folder / image["file"])
        for image in sorted(app["images"], key=lambda i: i["position"])
    }
    insert_images(db, dataset_id, list(files), files, decision_id)
    labels = _taken_labels(db, app, actor)

    def origin(row):
        # Where it was started from: a version of this dataset is one here; another dataset's
        # was not taken in with it (unknown here, as before 10-17).
        if (
            row["from_kind"] == "version"
            and row["from_dataset_id"] != app["dataset"]["id"]
        ):
            return {"from_kind": None, "from_dataset_id": None, "from_revision": None}
        return {
            "from_kind": row["from_kind"],
            "from_dataset_id": dataset_id if row["from_kind"] == "version" else None,
            "from_revision": row["from_revision"],
        }

    keys = {}
    for row in app["instructions"]:
        payload, key = _plan(row["payload_json"], ids, labels)
        keys[row["requirement_key"]] = key
        _insert(
            db,
            "instructions",
            {
                **row,
                "dataset_id": dataset_id,
                "payload_json": payload,
                "requirement_key": key,
                # Made here by the decision that takes the dataset in (22.1).
                "decision_id": decision_id,
                "draft_write_id": None,
                **origin(row),
            },
            db.columns("instructions"),
        )
    for row in app["drafts"]:
        payload, _ = _plan(row["payload_json"], ids, labels)
        where = origin(row)
        take_in_plan_draft(
            db,
            dataset_id,
            payload,
            row["written_by"],
            (where["from_kind"], where["from_dataset_id"], where["from_revision"]),
            row["updated_at"],
        )

    # A run or a fix of a requirement no version holds now (a draft's trial) keeps its key.
    def key_now(old):
        return keys.get(old, old)

    for row in app["recipes"]:
        _insert(
            db,
            "recipes",
            {**row, "id": ids[row["id"]], "dataset_id": dataset_id},
            db.columns("recipes"),
        )
    for row in app["runs"]:
        _insert(
            db,
            "runs",
            {
                **row,
                "id": ids[row["id"]],
                "dataset_id": dataset_id,
                "requirement_key": key_now(row["requirement_key"]),
                "recipe_id": ids.get(row.get("recipe_id")),
                "decision_id": None,
                "stop_decision_id": None,
            },
            db.columns("runs"),
        )
    for row in app["imports"]:
        _insert(
            db,
            "imports",
            {
                **row,
                "id": ids[row["id"]],
                "dataset_id": dataset_id,
                "requirement_key": key_now(row["requirement_key"]),
            },
            db.columns("imports"),
        )
    for row in app["copies"]:
        _insert(
            db,
            "copies",
            {
                **row,
                "id": ids[row["id"]],
                "dataset_id": dataset_id,
                "requirement_key": key_now(row["requirement_key"]),
                "decision_id": None,
            },
            db.columns("copies"),
        )
    for row in app["annotation_sets"]:
        _insert(
            db,
            "annotation_sets",
            {**row, "id": ids[row["id"]]},
            db.columns("annotation_sets"),
        )
    for row in app["annotations"]:
        _insert(
            db,
            "annotations",
            {
                **row,
                "id": ids[row["id"]],
                "set_id": ids[row["set_id"]],
                "parent_id": ids.get(row.get("parent_id")),
            },
            db.columns("annotations"),
        )
    # Fixes and results name each other (a fix's result, the result it was fixed from):
    # the fixes first without it, then the results, then each fix's from.
    for row in app["fixes"]:
        _insert(
            db,
            "fixes",
            {
                **row,
                "id": ids[row["id"]],
                "dataset_id": dataset_id,
                "from_result_id": None,
                "requirement_key": key_now(row["requirement_key"]),
            },
            db.columns("fixes"),
        )
    for row in app["results"]:
        _insert(
            db,
            "results",
            {
                **row,
                "id": ids[row["id"]],
                "run_id": ids.get(row.get("run_id")),
                "fix_id": ids.get(row.get("fix_id")),
                "import_id": ids.get(row.get("import_id")),
                "copy_id": ids.get(row.get("copy_id")),
                "set_id": ids[row["set_id"]],
                "final_view_id": None,
            },
            db.columns("results"),
        )
    for row in app["copy_results"]:
        # One copied from another dataset's result was not taken in with it: let go.
        _insert(
            db,
            "copy_results",
            {
                **row,
                "result_id": ids[row["result_id"]],
                "from_result_id": ids.get(row.get("from_result_id")),
            },
            db.columns("copy_results"),
        )
    for row in app["fixes"]:
        if row.get("from_result_id") in ids:
            db.execute(
                "UPDATE fixes SET from_result_id=? WHERE id=?",
                (ids[row["from_result_id"]], ids[row["id"]]),
            )
    for row in app["uses"]:
        _insert(
            db,
            "uses",
            {
                "dataset_id": dataset_id,
                "image_id": row["image_id"],
                "kind": row["kind"],
                "result_id": ids.get(row.get("result_id")),
                "fix_id": ids.get(row.get("fix_id")),
                "decision_id": None,
            },
            db.columns("uses"),
        )
    for row in app["confirmations"]:
        _insert(
            db,
            "confirmations",
            {
                **row,
                "id": new_id("cnf-"),
                "dataset_id": dataset_id,
                "result_id": ids[row["result_id"]],
                "decision_id": None,
            },
            db.columns("confirmations"),
        )
    for row in app["training_snapshots"]:
        items = {
            image: ids.get(result, result)
            for image, result in row["items_json"].items()
        }
        _insert(
            db,
            "training_snapshots",
            {**row, "dataset_id": dataset_id, "items_json": items},
            db.columns("training_snapshots"),
        )
    for row in app["label_colors"]:
        _insert(
            db,
            "label_colors",
            {**row, "dataset_id": dataset_id},
            db.columns("label_colors"),
        )
    return {
        "id": dataset_id,
        "name": name,
        "images": len(app["images"]),
        "path": str(folder),
        "purpose": document["dataset"]["purpose"],
        "exported_at": document.get("exported_at"),
    }


# The sample datasets beside a clone of the public repository (its samples/).
SAMPLES = REPO / "samples"


def take_in_samples(db):
    """A clone of the public repository starts with its sample datasets, as the zip does (user
    2026-11-11: it should start with the samples taken in): taken in when the app's own database
    was made by this start and the samples are beside it. Not again later, so datasets a person
    deleted stay deleted; not from a zip (its database comes made) nor in tests (a database of
    their own)."""
    if not (db.created and db.path == APP / "agent.db" and SAMPLES.is_dir()):
        return
    try:
        import_written(db, DatasetImportInput(path=str(SAMPLES)), By(SERVER))
    except (ApiError, OSError, ValueError):
        # The app starts all the same, the library empty; Take in takes them in by hand.
        log.exception("The sample datasets were not taken in from %s", SAMPLES)


def import_written(db, body: DatasetImportInput, by):
    """The datasets of a folder written out, each new in the library: this app's form as they
    were, or COCO's JSON as one dataset named by the person."""
    from .coco_import import import_coco

    path = Path(body.path).expanduser()
    folders = _app_folders(path) if path.is_dir() else []
    if folders:
        written = [(f, _document(f)) for f in folders]
        for folder, document in written:
            _store_files(db, folder, document)
        # One decision, every dataset of the folder or none (reviews 2026-10-28 A#1, B#9: each
        # dataset recorded the same decision again, the second failed and the first stayed).
        decision_id = by.decision_id or new_id("dec-")
        with db.transaction():
            made = [
                _take_in(db, folder, document, decision_id, by.who)
                for folder, document in written
            ]
            decisions.record(
                db,
                None,
                "dataset",
                {"op": "import", "path": str(path), "datasets": made},
                replace(by, decision_id=decision_id),
                {"datasets": [{"id": m["id"], "name": m["name"]} for m in made]},
            )
        return {"datasets": [{k: m[k] for k in ("id", "name", "images")} for m in made]}
    found = _coco(path) if path.is_dir() else None
    if found is None:
        raise ApiError(
            422,
            "not_written",
            "The folder holds nothing written out (this app's form or COCO's JSON)",
            {"path": body.path},
        )
    if not (body.name and body.purpose):
        raise ApiError(
            422,
            "coco_name_required",
            "A dataset taken in from COCO's JSON is named and purposed by the person",
            {"path": body.path},
        )
    return {"datasets": [import_coco(db, path, found[0], body, by)]}


@router.post("/library/import")
def import_route(request: Request, body: DatasetImportInput):
    return import_written(request.app.state.db, body, by_of(request))

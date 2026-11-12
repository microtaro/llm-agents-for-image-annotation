"""Datasets: one purpose each (fixed once made), and the images they hold (step 1 design 7).

The same images can be in several datasets; images are never copied (data-model 3).
"""

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from . import decisions
from .db import new_id, now
from .errors import ApiError, Model, invalid, not_found
from .images import image_row, import_paths, source_paths, stored_totals
from .system import THIS_COMPUTER

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Purpose = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
ImageId = Annotated[str, StringConstraints(pattern=r"^img-[0-9a-f]{64}$")]


class GeneratedOrigin(Model):
    kind: Literal["generated"]
    how: dict = Field(
        description="How it was made: tool, prompt, settings, source crops (data-model 2)."
    )


Paths = Annotated[
    list[Annotated[str, Field(min_length=1, max_length=4096)]],
    Field(max_length=1000),
]


class DatasetInput(Model):
    name: Name
    purpose: Purpose = Field(
        description="What the dataset is for, in one line; fixed once made."
    )
    image_ids: Annotated[list[ImageId], Field(max_length=10000)] = Field(
        default_factory=list
    )
    paths: Paths = Field(
        default_factory=list,
        description=f"Image files or folders {THIS_COMPUTER} (images directly inside) to"
        " import and add; each image keeps the file it came from.",
    )
    origin: GeneratedOrigin | None = Field(
        None, description="Null for photographed images; generated images say how."
    )


class ImportToDatasetInput(Model):
    paths: Annotated[Paths, Field(min_length=1)]
    origin: GeneratedOrigin | None = None


class DatasetPatch(Model):
    name: Name | None = None
    purpose: str | None = Field(None, description="Refused: the purpose never changes.")


class AddImagesInput(Model):
    image_ids: Annotated[list[ImageId], Field(min_length=1, max_length=10000)]
    source_path: str | None = Field(
        None, max_length=4096, description="Where these images came from."
    )


class RemoveImagesInput(Model):
    image_ids: Annotated[list[ImageId], Field(min_length=1, max_length=10000)]


def remove_images(db, dataset_id, body: RemoveImagesInput, by):
    """Take images out of the dataset (DESIGN.md: 取り除く), a decision (definition 22.4). The
    images and their run results stay, and who took which out when, by which decision, is kept
    (definition 21.5). Refused while a run of the dataset is active."""
    from .fixes import delete_fix_draft  # a fix is of a dataset's image

    with db.transaction():
        dataset_row(db, dataset_id)
        from .run_queries import going  # a record is of a dataset

        if going(db, [dataset_id]):
            raise ApiError(409, "run_active", "Stop the dataset's run first")
        decision_id = decisions.record(
            db,
            dataset_id,
            "images",
            {"op": "remove", "image_ids": list(dict.fromkeys(body.image_ids))},
            by,
        )
        removed = []
        for image_id in dict.fromkeys(body.image_ids):
            if has_image(db, dataset_id, image_id):
                db.execute(
                    "INSERT INTO dataset_image_removals(dataset_id, image_id, removed_by,"
                    " removed_at, decision_id) VALUES(?,?,?,?,?)",
                    (dataset_id, image_id, by.who, now(), decision_id),
                )
                db.execute(
                    "DELETE FROM dataset_images WHERE dataset_id=? AND image_id=?",
                    (dataset_id, image_id),
                )
                delete_fix_draft(db, dataset_id, image_id)
                removed.append(image_id)
    return {"removed": removed}


def image_id_of(db, dataset_id, value):
    """An image of the dataset by its id, or by its name (a worker names images by name and the
    server turns it into the id, memory no-coordinate-math-for-ai; issue #3 U-06). A name of
    two images is refused, as it does not say which (issue #4 F-16); one of none is not in the
    dataset. The one place a name becomes an id."""
    if not isinstance(value, str) or has_image(db, dataset_id, value):
        return value
    found = [r["id"] for r in image_rows(db, dataset_id) if r["name"] == value]
    if len(found) > 1:
        raise invalid(
            f"{value} names {len(found)} images of this dataset; give the id",
            image=value,
        )
    if not found:
        raise invalid("No such image in this dataset", image=value)
    return found[0]


def insert_dataset(db, dataset_id, name, purpose, decision_id):
    """A dataset made now, with the next number (definition 61: one line in the library, never
    given again, a deleted one's neither); in the caller's transaction. Every way of making one
    (made, copied, of others, taken in) comes here."""
    number = db.one("UPDATE dataset_numbers SET last=last+1 RETURNING last")["last"]
    db.execute(
        "INSERT INTO datasets(id,number,name,purpose,created_at,decision_id)"
        " VALUES(?,?,?,?,?,?)",
        (dataset_id, number, name, purpose, now(), decision_id),
    )
    return number


def dataset_rows(db):
    """Every dataset as stored, the newest first."""
    return db.execute("SELECT * FROM datasets ORDER BY created_at DESC")


def dataset_row(db, dataset_id):
    row = db.one("SELECT * FROM datasets WHERE id=?", (dataset_id,))
    if row is None:
        raise not_found("Dataset")
    return row


def image_rows(db, dataset_id):
    """The dataset's images in its order: each image's row (images) with its place in the
    dataset (position, added_at, source_path: the file this dataset took it from). The one
    place the dataset's images are read (fact inventory 3)."""
    return db.execute(
        "SELECT i.*, d.position, d.added_at, d.source_path FROM dataset_images d"
        " JOIN images i ON i.id=d.image_id WHERE d.dataset_id=? ORDER BY d.position",
        (dataset_id,),
    )


def source_folder(db, row):
    """The folder an image of the dataset (an image_rows row) came from: of the file the
    dataset took it from, else (taken from the library by its id) of the image's own file, the
    first by name; None for an image of no file. What the card counts and the sheets group by
    (definition 42.1; 2026-10-30: the card read the first and the sheets the second, and 7
    images of the library were grouped apart)."""
    path = row["source_path"] or next(iter(source_paths(db, row["id"])), None)
    return str(Path(path).parent) if path else None


def image_ids(db, dataset_id):
    """The dataset's images' ids in its order."""
    return [
        r["image_id"]
        for r in db.execute(
            "SELECT image_id FROM dataset_images WHERE dataset_id=? ORDER BY position",
            (dataset_id,),
        )
    ]


def image_count(db, dataset_id):
    return db.one(
        "SELECT count(*) FROM dataset_images WHERE dataset_id=?", (dataset_id,)
    )[0]


def has_image(db, dataset_id, image_id):
    return (
        db.one(
            "SELECT 1 FROM dataset_images WHERE dataset_id=? AND image_id=?",
            (dataset_id, image_id),
        )
        is not None
    )


def shared_with(db, dataset_ids):
    """The other datasets holding images of these, by name: how many of the images and their
    bytes, each image once per dataset (found 2026-10-15: two chosen datasets with the same
    images counted the size twice). What deleting these keeps."""
    marks = ",".join("?" * len(dataset_ids))
    return [
        {
            "dataset_id": r["dataset_id"],
            "name": r["name"],
            "images": r["images"],
            "bytes": r["bytes"],
        }
        for r in db.execute(
            "SELECT s.dataset_id, ds.name, count(*) AS images, sum(i.byte_size) AS bytes"
            " FROM (SELECT DISTINCT d2.dataset_id, d1.image_id FROM dataset_images d1"
            " JOIN dataset_images d2 ON d2.image_id=d1.image_id"
            f" AND d2.dataset_id NOT IN ({marks}) WHERE d1.dataset_id IN ({marks})) s"
            " JOIN datasets ds ON ds.id=s.dataset_id JOIN images i ON i.id=s.image_id"
            " GROUP BY s.dataset_id ORDER BY ds.name",
            (*dataset_ids, *dataset_ids),
        )
    ]


def images_only_in(db, dataset_ids):
    """The images of these datasets that no other dataset holds (id, byte_size): deleting them
    all frees these."""
    marks = ",".join("?" * len(dataset_ids))
    return db.execute(
        "SELECT i.id, i.byte_size FROM images i WHERE i.id IN (SELECT image_id FROM"
        f" dataset_images WHERE dataset_id IN ({marks})) AND NOT EXISTS (SELECT 1 FROM"
        f" dataset_images d WHERE d.image_id=i.id AND d.dataset_id NOT IN ({marks}))",
        (*dataset_ids, *dataset_ids),
    )


def insert_images(db, dataset_id, ids, source_path, decision_id):
    """Add images not yet in the dataset at the end, by the decision that adds them: the one
    place an image enters a dataset (made, copied, of others, taken in, added). source_path:
    one path for all, or a dict image_id -> the file it came from."""
    held = set(image_ids(db, dataset_id))
    position = db.one(
        "SELECT COALESCE(MAX(position), -1) AS p FROM dataset_images WHERE dataset_id=?",
        (dataset_id,),
    )["p"]
    added, already = [], []
    for image_id in dict.fromkeys(ids):
        if image_id in held:
            already.append(image_id)
            continue
        if image_row(db, image_id) is None:
            raise ApiError(
                422, "invalid_input", "Image does not exist", {"image_id": image_id}
            )
        position += 1
        db.execute(
            "INSERT INTO dataset_images(dataset_id,image_id,position,added_at,source_path,"
            "decision_id) VALUES(?,?,?,?,?,?)",
            (
                dataset_id,
                image_id,
                position,
                now(),
                source_path.get(image_id)
                if isinstance(source_path, dict)
                else source_path,
                decision_id,
            ),
        )
        added.append(image_id)
    return {"added": added, "already": already}


def _import(db, paths, origin):
    """Import files and folders; (image IDs in order, image_id -> its file, skipped). A file of
    the same content as one before it is one image: said as skipped, with the one it is
    (definition 76; 2026-10-29: 11 files made 9 images, and nothing said why)."""
    imported = import_paths(db, paths, origin.model_dump() if origin else None)
    files, same = {}, []
    for f in imported["files"]:
        if f["image_id"] in files and files[f["image_id"]] != f["path"]:
            same.append(
                {
                    "path": f["path"],
                    "reason": "same_content",
                    "as": Path(files[f["image_id"]]).name,
                }
            )
        files.setdefault(f["image_id"], f["path"])
    return list(files), files, [*imported["skipped"], *same]


def _reasons(skipped):
    """How many files were refused for each reason."""
    counts = {}
    for item in skipped:
        counts[item["reason"]] = counts.get(item["reason"], 0) + 1
    return counts


def create_dataset(db, body: DatasetInput, by):
    """A dataset made, a decision of the library (definition 22.4): the dataset holds it."""
    ids, files, skipped = (
        _import(db, body.paths, body.origin) if body.paths else ([], {}, [])
    )
    if body.paths and not ids and not body.image_ids:
        # Nothing could be imported: say why instead of making an empty dataset (found
        # 2026-10-05: "made (0 images)" with every image refused).
        raise ApiError(
            422,
            "nothing_imported",
            "No image could be imported; the dataset was not made",
            {"skipped": skipped[:50], "reasons": _reasons(skipped)},
        )
    dataset_id = new_id()
    with db.transaction():
        decision_id = decisions.record(
            db,
            None,
            "dataset",
            {
                "op": "create",
                "name": body.name,
                "purpose": body.purpose,
                "paths": body.paths,
                "image_ids": body.image_ids,
                "origin": body.origin.model_dump() if body.origin else None,
            },
            by,
            {"id": dataset_id, "name": body.name},
        )
        insert_dataset(db, dataset_id, body.name, body.purpose, decision_id)
        insert_images(db, dataset_id, [*body.image_ids, *ids], files, decision_id)
    return {**get_dataset(db, dataset_id), "skipped": skipped}


def import_to_dataset(db, dataset_id, body: ImportToDatasetInput, by):
    """Images added from files, a decision of the dataset (definition 22.4)."""
    dataset_row(db, dataset_id)
    ids, files, skipped = _import(db, body.paths, body.origin)
    with db.transaction():
        origin = body.origin.model_dump() if body.origin else None
        decision_id = decisions.record(
            db,
            dataset_id,
            "images",
            {"op": "add", "paths": body.paths, "origin": origin},
            by,
        )
        return {
            **insert_images(db, dataset_id, ids, files, decision_id),
            "skipped": skipped,
        }


def add_images(db, dataset_id, body: AddImagesInput, by):
    with db.transaction():
        dataset_row(db, dataset_id)
        decision_id = decisions.record(
            db, dataset_id, "images", {"op": "add", "image_ids": body.image_ids}, by
        )
        return insert_images(
            db, dataset_id, body.image_ids, body.source_path, decision_id
        )


def patch_dataset(db, dataset_id, body: DatasetPatch, by):
    """The name changed, a decision (definition 22.4); the purpose never changes."""
    if body.purpose is not None:
        raise ApiError(
            422,
            "purpose_immutable",
            "A dataset's purpose never changes; make another dataset with the same images",
        )
    with db.transaction():
        row = dataset_row(db, dataset_id)
        if body.name is not None and body.name != row["name"]:
            decisions.record(
                db,
                dataset_id,
                "dataset",
                {"op": "rename", "from": row["name"], "to": body.name},
                by,
            )
            db.execute("UPDATE datasets SET name=? WHERE id=?", (body.name, dataset_id))
    return get_dataset(db, dataset_id)


def _last_at(db, dataset_id):
    """When it was last worked on (definition 57): its newest plan write, version, run, fix or
    decision, else when it was made. Talk is no work on it."""
    return db.one(
        "SELECT max(t) FROM (SELECT created_at t FROM datasets WHERE id=:d"
        " UNION ALL SELECT written_at FROM draft_writes WHERE dataset_id=:d"
        " UNION ALL SELECT created_at FROM instructions WHERE dataset_id=:d"
        " UNION ALL SELECT coalesce(ended_at, started_at) FROM runs WHERE dataset_id=:d"
        " UNION ALL SELECT fixed_at FROM fixes WHERE dataset_id=:d"
        " UNION ALL SELECT imported_at FROM imports WHERE dataset_id=:d"
        " UNION ALL SELECT copied_at FROM copies WHERE dataset_id=:d"
        " UNION ALL SELECT decided_at FROM decisions WHERE dataset_id=:d)",
        {"d": dataset_id},
    )[0]


def _card(db, row):
    # The version's type imports this one (a dataset is checked there): read at call time.
    from .instructions import latest_row

    latest = latest_row(db, row["id"])
    images = image_rows(db, row["id"])
    folders = {}
    for r in images:
        folder = source_folder(db, r)
        folders[folder] = folders.get(folder, 0) + 1
    return {
        "id": row["id"],
        # What people call it by, "#12" (definition 61).
        "number": row["number"],
        "name": row["name"],
        "purpose": row["purpose"],
        "created_at": row["created_at"],
        "image_count": len(images),
        # Where the images came from, per folder (null: added without a path).
        "sources": [{"folder": f, "count": n} for f, n in folders.items()],
        "latest_revision": latest["revision"] if latest else None,
        "requirement_key": latest["requirement_key"] if latest else None,
        # What the latest version puts on the images, each label and how it is taken.
        "labels": [
            # What information each holds (user 2026-10-28): its shape, the label it is in, the
            # names of its attributes.
            {
                "name": d["name"],
                "shape": d["shape"],
                "parent": d.get("parent"),
                "attributes": [a["name"] for a in d.get("attributes") or []],
            }
            for d in json.loads(latest["payload_json"])["label_definitions"]
        ]
        if latest
        else [],
        "last_at": _last_at(db, row["id"]),
        # The library's card (user 2026-10-15): a few images to know it by, its size, and
        # the datasets it shares images with (what deleting it would keep).
        "thumbnails": [r["id"] for r in images[:4]],
        "bytes": sum(r["byte_size"] for r in images),
        "shared": shared_with(db, [row["id"]]),
    }


def list_datasets(db):
    return {
        "datasets": [_card(db, r) for r in dataset_rows(db)],
        # Every image imported, once each (shared by the datasets that use it).
        "stored": stored_totals(db),
    }


def get_dataset(db, dataset_id):
    row = dataset_row(db, dataset_id)
    images = image_rows(db, dataset_id)
    from .image_state import use_now

    decided = use_now(db, dataset_id)
    return {
        **_card(db, row),
        "images": [
            {
                "image_id": r["id"],
                "name": r["name"],
                "width": r["width"],
                "height": r["height"],
                "position": r["position"],
                "added_at": r["added_at"],
                "source_path": r["source_path"],
                "excluded": decided[r["id"]]["excluded"],
            }
            for r in images
        ],
    }


def check_in_dataset(db, dataset_id, image_id):
    if not has_image(db, dataset_id, image_id):
        raise not_found("Image of this dataset")

"""Annotation sets: the annotations of one image in one place (a run's result now; masters
later), versioned per atomic batch. Copied from annotation_server/store.py (step 2 design 2).
"""

import hashlib
import json
from types import SimpleNamespace

from .coordinates import check_same_image, to_original_geometry, view_frame
from .db import encoded, new_id, now
from .errors import ApiError, invalid, not_found
from .geometry import validate_geometry
from .images import image_info
from .label_rules import check_batch, check_creates
from .shapes import Batch

MAX_ANNOTATIONS = 1000


def attribute_values(attributes):
    """An annotation's attribute values; null means no value, so it is left out."""
    return {k: v for k, v in (attributes or {}).items() if v is not None}


def new_set(db, image_id, after=None):
    """An empty set at revision 0 (inside the caller's transaction). after: the set it carries on
    (a fix's, the result it was fixed from), whose last numbers it keeps, so a number taken out
    there is not given again here (user 2026-10-27: the highest number taken out of a fix was
    given to the object added)."""
    set_id = new_id("set-")
    numbers = set_row(db, after)["numbers_json"] if after else "{}"
    db.execute(
        "INSERT INTO annotation_sets(id,image_id,revision,numbers_json) VALUES(?,?,0,?)",
        (set_id, image_id, numbers),
    )
    _save_revision(db, set_id, 0)
    return set_id


def set_row(db, set_id):
    row = db.one("SELECT * FROM annotation_sets WHERE id=?", (set_id,))
    if row is None:
        raise not_found("Annotation set")
    return dict(row)


def label_counts(db, set_id):
    """How many objects of each label the set holds now (the label as its record named it)."""
    return {
        r["label"]: r["n"]
        for r in db.execute(
            "SELECT label, count(*) AS n FROM annotations WHERE set_id=? GROUP BY label",
            (set_id,),
        )
    }


def current(db, set_id):
    return [
        {
            "id": r["id"],
            "label": r["label"],
            "geometry": json.loads(r["geometry_json"]),
            "mask_sha256": r["mask_sha256"],
            "parent_id": r["parent_id"],
            "attributes": json.loads(r["attributes_json"]),
            "number": r["number"],
        }
        for r in db.execute(
            "SELECT * FROM annotations WHERE set_id=? ORDER BY label, number, id",
            (set_id,),
        )
    ]


def _save_revision(db, set_id, revision):
    db.execute(
        "INSERT INTO set_revisions VALUES(?,?,?,?)",
        (set_id, revision, encoded(current(db, set_id)), now()),
    )


def snapshot(db, set_id, revision=None):
    """(set row, annotations) at the current or a past revision."""
    with db.lock:
        row = set_row(db, set_id)
        if revision is None or revision == row["revision"]:
            return row, current(db, set_id)
        saved = db.one(
            "SELECT snapshot_json FROM set_revisions WHERE set_id=? AND revision=?",
            (set_id, revision),
        )
        if saved is None:
            raise ApiError(
                404,
                "revision_not_found",
                "This revision does not exist for the annotation set",
                {"current_revision": row["revision"]},
            )
        return {**row, "revision": revision}, json.loads(saved[0])


def set_state(db, set_id, revision=None):
    """The set as the API returns it: masks as URLs, coordinates in original pixels."""
    row, annotations = snapshot(db, set_id, revision)
    public = []
    for ann in annotations:
        geometry = dict(ann["geometry"])
        if geometry["type"] == "mask":
            geometry["mask_url"] = f"/v1/masks/{ann['mask_sha256']}"
        public.append(
            {
                "id": ann["id"],
                "label": ann["label"],
                "geometry": geometry,
                "parent_id": ann["parent_id"],
                "attributes": ann["attributes"],
                "number": ann.get("number"),
            }
        )
    return {
        "image": image_info(db, row["image_id"]),
        "revision": row["revision"],
        "annotations": public,
        "coordinate_system": "original_image_pixels",
    }


def _conflict(revision):
    return ApiError(
        409,
        "revision_conflict",
        "Fetch the current annotations before editing",
        {"current_revision": revision},
    )


def _from_view(db, image_id, batch):
    frame = view_frame(db, batch.coordinate_view_id)
    check_same_image(frame, image_id)
    # Only what was given: an update that leaves out its parent or values keeps them (review
    # 2026-10-28 C#2: they were written back as null, and null clears).
    body = batch.model_dump(mode="json", exclude_unset=True)
    for operation in body["operations"]:
        if "geometry" in operation:
            operation["geometry"] = to_original_geometry(operation["geometry"], frame)
    return Batch.model_validate(body)


def _replayed(db, set_id, batch, body_sha):
    if batch.request_id is None:
        return None
    replay = db.one(
        "SELECT body_sha256,response_json FROM batch_requests WHERE set_id=? AND request_id=?",
        (set_id, str(batch.request_id)),
    )
    if replay is None:
        return None
    if replay[0] != body_sha:
        raise ApiError(
            409,
            "idempotency_conflict",
            "This request_id was used with a different batch",
        )
    return json.loads(replay[1])


def _prepare(db, set_id, batch):
    """Each operation as (op, id, label, geometry, mask bytes, parent, attributes), checked
    against the set now; IDs first, since a parent may be the ref of a create."""
    row = set_row(db, set_id)
    image = image_info(db, row["image_id"])
    if batch.base_revision != row["revision"]:
        raise _conflict(row["revision"])
    known = {a["id"]: a for a in current(db, set_id)}
    refs, created_ids, deleted, changed = {}, [], set(), set()
    for operation in batch.operations:
        if operation.op == "create":
            ann_id = new_id("ann-")
            created_ids.append(ann_id)
            if operation.ref is not None:
                if operation.ref in refs:
                    raise invalid("A ref can name one create per batch")
                refs[operation.ref] = ann_id
            continue
        if operation.id in changed:
            raise invalid("A batch cannot modify the same ID more than once")
        changed.add(operation.id)
        if operation.id not in known:
            raise not_found("Annotation of this set")
        if operation.op == "delete":
            deleted.add(operation.id)

    def parent_of(value, ann_id):
        if value is None:
            return None
        found = refs.get(value) or (
            value if value in known and value not in deleted else None
        )
        if found is None:
            raise invalid(
                "parent must be an annotation of this image or a ref of this batch",
                parent=value,
            )
        if found == ann_id:
            raise invalid("An annotation cannot be its own parent")
        return found

    prepared = []
    creates = iter(created_ids)
    for operation in batch.operations:
        if operation.op == "delete":
            prepared.append(("delete", operation.id, None, None, None, None, None))
            continue
        ann_id = next(creates) if operation.op == "create" else operation.id
        before = known.get(ann_id, {})
        geometry, mask = validate_geometry(
            operation.geometry, image["width"], image["height"]
        )
        # An update keeps the parent and attributes it does not name.
        given = operation.model_fields_set
        parent = (
            parent_of(operation.parent, ann_id)
            if operation.op == "create" or "parent" in given
            else before.get("parent_id")
        )
        attributes = (
            attribute_values(operation.attributes)
            if operation.op == "create" or "attributes" in given
            else before.get("attributes") or {}
        )
        prepared.append(
            (operation.op, ann_id, operation.label, geometry, mask, parent, attributes)
        )
    if len(known) + len(created_ids) - len(deleted) > MAX_ANNOTATIONS:
        raise invalid(f"A set can contain at most {MAX_ANNOTATIONS} annotations")
    return prepared, created_ids, refs, deleted


def reading_order(geometry):
    """Where an object comes when reading the image: top to bottom, then left to right."""
    if geometry["type"] == "polygon":
        xs = [p[0] for p in geometry["points"]]
        ys = [p[1] for p in geometry["points"]]
        return (min(ys), min(xs))
    x, y = (geometry.get("xywh") or geometry.get("bbox_xywh"))[:2]
    return (y, x)


def _object_numbers(db, set_id, prepared, given):
    """Numbers for the creates of a write: given ones kept, the rest the next free number of
    their label in reading order. Numbers are per label and never given twice in a set."""
    last = json.loads(set_row(db, set_id)["numbers_json"])
    for _, ann_id, label, *_rest in prepared:
        if given.get(ann_id) is not None:
            last[label] = max(last.get(label, 0), given[ann_id])
    numbers = dict(given)
    creates = [p for p in prepared if p[0] == "create" and given.get(p[1]) is None]
    for _, ann_id, label, geometry, *_rest in sorted(
        creates, key=lambda p: reading_order(p[3])
    ):
        last[label] = last.get(label, 0) + 1
        numbers[ann_id] = last[label]
    db.execute(
        "UPDATE annotation_sets SET numbers_json=? WHERE id=?", (encoded(last), set_id)
    )
    return numbers


def _save_operations(db, set_id, prepared, deleted, revision, given=None):
    """Save prepared operations and the next revision (inside the caller's transaction).
    A mask is new PNG bytes, or the SHA-256 of a stored mask (a copy).
    given: annotation id -> number to keep (a copy); other creates get the next numbers."""
    masks = {
        ann_id: mask if isinstance(mask, str) else db.files.put("masks", mask)
        for _, ann_id, _, _, mask, *_ in prepared
        if mask is not None
    }
    numbers = _object_numbers(db, set_id, prepared, given or {})
    for op, ann_id, label, geometry, _, parent, attributes in prepared:
        if op == "delete":
            db.execute(
                "DELETE FROM annotations WHERE id=? AND set_id=?", (ann_id, set_id)
            )
            continue
        values = (
            label,
            geometry["type"],
            json.dumps(geometry),
            masks.get(ann_id),
            None if parent in deleted else parent,
            encoded(attributes),
        )
        if op == "create":
            db.execute(
                "INSERT INTO annotations(id,set_id,label,kind,geometry_json,mask_sha256,"
                "parent_id,attributes_json,number) VALUES(?,?,?,?,?,?,?,?,?)",
                (ann_id, set_id, *values, numbers.get(ann_id)),
            )
        else:
            db.execute(
                "UPDATE annotations SET label=?,kind=?,geometry_json=?,mask_sha256=?,"
                "parent_id=?,attributes_json=? WHERE id=? AND set_id=?",
                (*values, ann_id, set_id),
            )
    # Children of a deleted annotation stay, without a parent.
    for ann_id in deleted:
        db.execute(
            "UPDATE annotations SET parent_id=NULL WHERE set_id=? AND parent_id=?",
            (set_id, ann_id),
        )
    db.execute("UPDATE annotation_sets SET revision=? WHERE id=?", (revision, set_id))
    _save_revision(db, set_id, revision)


def apply_batch(db, set_id, batch: Batch, definitions):
    """Apply one atomic batch, refused before anything is saved when it breaks the plan's label
    definitions (label_rules).

    Returns the set state plus created_ids and created_refs. The same request_id with the
    same body returns the committed response again; a different body conflicts.
    """
    body_sha = hashlib.sha256(
        encoded(batch.model_dump(mode="json")).encode()
    ).hexdigest()
    with db.lock:
        replay = _replayed(db, set_id, batch, body_sha)
        if replay is not None:
            return replay
        if batch.coordinate_view_id:
            batch = _from_view(db, set_row(db, set_id)["image_id"], batch)
        check_batch(definitions, current(db, set_id), batch)
        prepared, created_ids, refs, deleted = _prepare(db, set_id, batch)
        with db.transaction():
            _save_operations(db, set_id, prepared, deleted, batch.base_revision + 1)
            response = {
                **set_state(db, set_id),
                "created_ids": created_ids,
                "created_refs": refs,
            }
            if batch.request_id is not None:
                db.execute(
                    "INSERT INTO batch_requests VALUES(?,?,?,?)",
                    (set_id, str(batch.request_id), body_sha, encoded(response)),
                )
    return response


def fill(db, set_id, creates, definitions, numbers=None):
    """Fill a new, empty set with create operations in one revision (any number up to
    MAX_ANNOTATIONS; a parent is the ref of another create), following the plan's label
    definitions (2026-10-30: a label change wrote a child under another label's parent, the
    writers each checking or not). Inside the caller's transaction."""
    check_creates(definitions, creates)
    batch = SimpleNamespace(base_revision=0, operations=creates)
    prepared, created_ids, _, deleted = _prepare(db, set_id, batch)
    # numbers[i] belongs to creates[i]; created_ids are in the same order.
    given = {
        ann_id: n for ann_id, n in zip(created_ids, numbers or []) if n is not None
    }
    _save_operations(db, set_id, prepared, deleted, 1, given)


def number_missing(db):
    """Give numbers to annotations saved before numbers existed (once, at start): per set and
    label, in reading order after the numbers already given."""
    sets = [
        r[0]
        for r in db.execute(
            "SELECT DISTINCT set_id FROM annotations WHERE number IS NULL"
        )
    ]
    for set_id in sets:
        with db.transaction():
            last = json.loads(set_row(db, set_id)["numbers_json"])
            rows = db.execute("SELECT * FROM annotations WHERE set_id=?", (set_id,))
            for r in rows:
                if r["number"] is not None:
                    last[r["label"]] = max(last.get(r["label"], 0), r["number"])
            missing = [r for r in rows if r["number"] is None]
            missing.sort(key=lambda r: reading_order(json.loads(r["geometry_json"])))
            for r in missing:
                last[r["label"]] = last.get(r["label"], 0) + 1
                db.execute(
                    "UPDATE annotations SET number=? WHERE id=?",
                    (last[r["label"]], r["id"]),
                )
            db.execute(
                "UPDATE annotation_sets SET numbers_json=? WHERE id=?",
                (encoded(last), set_id),
            )

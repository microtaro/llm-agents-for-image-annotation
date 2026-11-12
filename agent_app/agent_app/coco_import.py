"""Taking in COCO's JSON (definition 60.11, A): a new dataset of its images, its first version
made from its categories (a label each, by its name the library's; a box when its objects have
boxes only, else an outline), and one record taken in (the third kind, neither the AI's nor a
person's fix) of that version, holding each image's objects, so they are the images' annotations
now: shown, used for training and written out as the other records' are.

An object becomes a box (segmentation empty), an outline (one polygon the app can hold), or a
mask (several polygons, a polygon the app cannot hold, or RLE, plain or compressed). Its values
are its "attributes" (or "metadata") of text and numbers. An image with no object has no result
(COCO does not say whether nothing is there). What cannot be taken in is counted and said, never
guessed (an image not found, an object out of its image).
"""

import base64
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw
from pydantic import ValidationError

from . import decisions
from .annotation_sets import fill, new_set
from .datasets import insert_dataset, insert_images
from .db import encoded, new_id, now
from .errors import ApiError
from .geometry import validate_geometry
from .images import store_image
from .instructions import InstructionInput, save_instruction, version_payload
from .run_queries import insert_result, next_number
from .shapes import LABEL_MAX, Create

MAX_OBJECTS = (
    1000  # an image's set holds at most this many (annotation_sets.MAX_ANNOTATIONS)
)


def _image_file(folder, file_name):
    """The image a COCO image names, in the folder or its images/ or data/ (COCO Annotator's and
    FiftyOne's places); never one outside the folder (review 2026-10-28 B#8: an absolute path
    or ".." read an image from anywhere), a path written elsewhere found by its name."""
    name, inside = Path(file_name), folder.resolve()
    for base in (folder, folder / "images", folder / "data"):
        for candidate in (base / name, base / name.name):
            if candidate.is_file() and candidate.resolve().is_relative_to(inside):
                return candidate
    return None


def _rle_counts(counts):
    """COCO's compressed run-length string as its counts (pycocotools' rleFrString)."""
    out, p = [], 0
    while p < len(counts):
        x, k, more = 0, 0, True
        while more:
            c = ord(counts[p]) - 48
            x |= (c & 0x1F) << (5 * k)
            more = bool(c & 0x20)
            p += 1
            k += 1
            if not more and c & 0x10:
                x |= -1 << (5 * k)
        if len(out) > 2:
            x += out[-2]
        out.append(x)
    return out


def _mask_png(width, height, segmentation):
    """A mask's PNG (0 and 255) from COCO's segmentation: polygons drawn, or RLE read column by
    column; None when it holds no pixel."""
    if isinstance(segmentation, dict):
        counts = segmentation["counts"]
        if isinstance(counts, str):
            counts = _rle_counts(counts)
        # Each run cut to what the image has left (review 2026-10-28 B#7: a huge count was made
        # whole first and took the memory).
        total = width * height
        pixels, on = bytearray(), False
        for run in counts:
            pixels.extend(
                bytes([255 if on else 0]) * max(0, min(run, total - len(pixels)))
            )
            if len(pixels) == total:
                break
            on = not on
        pixels = pixels.ljust(total, b"\0")
        mask = Image.frombytes("L", (height, width), bytes(pixels)).transpose(
            Image.Transpose.TRANSPOSE
        )
    else:
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        for polygon in segmentation:
            if len(polygon) >= 6:
                draw.polygon(list(zip(polygon[0::2], polygon[1::2])), fill=255)
    if mask.getbbox() is None:
        return None
    out = io.BytesIO()
    mask.save(out, "PNG")
    return out.getvalue()


def _attribute_values(annotation):
    """An object's values: its attributes (or metadata) of text and numbers, names cut to 32."""
    found = annotation.get("attributes") or annotation.get("metadata") or {}
    values = {}
    for name, value in found.items() if isinstance(found, dict) else ():
        if isinstance(value, bool):
            value = "true" if value else "false"
        if isinstance(value, (str, int, float)) and str(name).strip():
            values[str(name).strip()[:32]] = value
    return values


def _coco_geometry(annotation, width, height, shape):
    """The geometry to take in for one COCO object of a label of shape (None: none)."""
    segmentation = annotation.get("segmentation")
    if not segmentation:
        x, y, w, h = annotation["bbox"]
        # A box running a little past the image (rounding in other tools) is kept inside it.
        x, y = max(0.0, x), max(0.0, y)
        w, h = min(w, width - x), min(h, height - y)
        if shape == "polygon":
            # Of a label with outlines: the box as one (its corners), as the label takes it.
            corners = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
            return {"type": "polygon", "points": corners}
        return {"type": "bbox", "xywh": [x, y, w, h]}
    if (
        isinstance(segmentation, list)
        and len(segmentation) == 1
        and len(segmentation[0]) >= 6
    ):
        flat = segmentation[0]
        polygon = {
            "type": "polygon",
            "points": [list(p) for p in zip(flat[0::2], flat[1::2])],
        }
        try:
            validate_geometry(
                Create.model_validate(
                    {"op": "create", "label": "x", "geometry": polygon}
                ).geometry,
                width,
                height,
            )
            return polygon
        except (ApiError, ValidationError):
            pass  # drawn as a mask instead (it keeps the shape)
    png = _mask_png(width, height, segmentation)
    if png is None:
        return None
    return {"type": "mask", "png_base64": base64.b64encode(png).decode()}


def coco_definitions(document):
    """The first version's labels from COCO's categories: a box for a category whose objects
    have boxes only, else an outline; its attributes the values its objects have (a number when
    every value is one, else text)."""
    shapes, values = {}, {}
    for a in document["annotations"]:
        c = a.get("category_id")
        shapes[c] = shapes.get(c, "bbox") if not a.get("segmentation") else "polygon"
        for name, value in _attribute_values(a).items():
            values.setdefault(c, {}).setdefault(name, set()).add(type(value).__name__)
    definitions = []
    for category in document["categories"]:
        c = category["id"]
        if c not in shapes:
            continue  # a category no object has is no label of the plan
        definitions.append(
            {
                "name": str(category["name"]).strip()[:LABEL_MAX],
                "shape": shapes[c],
                "description": "",
                "attributes": [
                    {
                        "name": name,
                        "type": "number" if kinds <= {"int", "float"} else "text",
                        "choices": None,
                        "description": "",
                    }
                    for name, kinds in sorted(values.get(c, {}).items())
                ],
            }
        )
    return definitions


def import_coco(db, folder, file_name, body, by):
    """A new dataset of a COCO JSON's images, its first version, and one record taken in."""
    document = json.loads((folder / file_name).read_text(encoding="utf-8"))
    origin = body.origin.model_dump() if body.origin else None
    found, missing = {}, []
    for image in document["images"]:
        path = _image_file(folder, image["file_name"])
        if path is None:
            missing.append(image["file_name"])
            continue
        found[image["id"]] = (
            store_image(db, path.read_bytes(), path.name, str(path), origin),
            path,
        )
    if not found:
        raise ApiError(
            422,
            "nothing_imported",
            "No image of the COCO JSON was found beside it",
            {"skipped": [{"path": m, "reason": "not_found"} for m in missing[:50]]},
        )
    categories = {
        c["id"]: str(c["name"]).strip()[:LABEL_MAX] for c in document["categories"]
    }
    definitions = coco_definitions(document)
    objects = {}
    for a in document["annotations"]:
        objects.setdefault(a.get("image_id"), []).append(a)
    dataset_id = new_id()
    skipped = {"images": len(missing), "objects": 0}
    unannotated = 0
    with db.transaction():
        decision_id = decisions.record(
            db,
            None,
            "dataset",
            {
                "op": "import",
                "format": "coco",
                "path": str(folder / file_name),
                "name": body.name,
                "purpose": body.purpose,
            },
            by,
            {"id": dataset_id, "name": body.name},
        )
        insert_dataset(db, dataset_id, body.name, body.purpose, decision_id)
        files = {}
        for stored, path in found.values():
            files.setdefault(stored["id"], str(path))
        insert_images(db, dataset_id, list(files), files, decision_id)
        version = save_instruction(
            db,
            dataset_id,
            InstructionInput.model_validate(
                {"text": "", "label_definitions": definitions, "leave_out": []}
            ),
            by.who,
            decision_id=decision_id,
        )
        record_id = new_id("imp-")
        db.execute(
            "INSERT INTO imports(id,dataset_id,number,instruction_revision,requirement_key,"
            "source_json,imported_by,imported_at) VALUES(?,?,?,?,?,?,?,?)",
            (
                record_id,
                dataset_id,
                next_number(db, dataset_id),
                version["revision"],
                version["requirement_key"],
                encoded({"format": "coco", "path": str(folder / file_name)}),
                by.who,
                now(),
            ),
        )
        # The plan names a label as the library does (save_instruction): the objects take it.
        saved = version_payload(db, dataset_id, version["revision"])[
            "label_definitions"
        ]
        named = {
            before["name"]: after["name"] for before, after in zip(definitions, saved)
        }
        shape = {d["name"]: d["shape"] for d in saved}
        for position, (coco_id, (stored, _)) in enumerate(found.items(), start=1):
            width, height = stored["width"], stored["height"]
            creates = []
            for a in objects.get(coco_id, [])[:MAX_OBJECTS]:
                label = named.get(categories.get(a.get("category_id")))
                geometry = (
                    _coco_geometry(a, width, height, shape[label]) if label else None
                )
                try:
                    create = Create.model_validate(
                        {
                            "op": "create",
                            "label": label or "",
                            "geometry": geometry,
                            "attributes": _attribute_values(a) or None,
                        }
                    )
                    validate_geometry(create.geometry, width, height)
                except (ApiError, ValidationError, TypeError):
                    skipped["objects"] += 1
                    continue
                creates.append(create)
            skipped["objects"] += max(0, len(objects.get(coco_id, [])) - MAX_OBJECTS)
            if not creates:
                # No object: COCO does not say whether nothing is there or nothing was
                # annotated yet, so the image is left without a result (2026-10-28: an image
                # never annotated came back as "annotated, nothing there").
                unannotated += 1
                continue
            set_id = new_set(db, stored["id"])
            fill(db, set_id, creates, saved)
            insert_result(
                db, "import", record_id, stored["id"], set_id, position, creates
            )
    return {
        "id": dataset_id,
        "name": body.name,
        "images": len(found),
        "skipped": skipped,
        "unannotated": unannotated,
    }

"""One image of many (definition 25.2-18): a label's sheet (crops of its annotations, the ones a
person fixed first, from several datasets) and a dataset's sheets (all its images, 16 a page, in
an order spread over the folders they came from; definition 42), each tile numbered in a band
under it. A person and a worker look at one image instead of many; the numbers say which image
each tile is. A sheet is made once for the same facts (the annotations or images it shows) and
kept in the files by its SHA-256.
"""

import hashlib
import json
from io import BytesIO
from itertools import zip_longest
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from PIL import Image, ImageDraw, ImageFont

from .annotation_sets import current
from .datasets import dataset_row, image_rows, source_folder
from .db import encoded, now
from .errors import invalid, not_found
from .image_state import image_states
from .images import image_file, image_names
from .imaging import rgb, shown_image
from .instructions import latest_requirement
from .label_ids import names_now
from .label_library import datasets_of, label_row
from .run_queries import result_row

router = APIRouter(prefix="/v1")
MOST = 16
COLUMNS = 4
BAND = 24
# 1024 wide, the long side an AI is given (settings worker_view_max_side's most).
LABEL_TILE = (256, 256)
IMAGE_TILE = (256, 171)  # photos are 3:2 more often than not


def _evenly(items):
    """The items in an order spread over them (van der Corput: the first, the middle, the
    quarters, ...), so its first part is taken from all of them."""
    size = 1 << max(len(items) - 1, 0).bit_length()
    bits = size.bit_length() - 1
    order = {}
    for j in range(size):
        at = int(format(j, f"0{bits}b")[::-1], 2) if bits else 0
        order.setdefault(at * len(items) // size, None)
    return [items[i] for i in order]


def spread(groups):
    """Every item once, from each group in turn (every group is seen early), each group's in an
    order spread over it (definition 42.1): any first part of it is taken from all of them."""
    evenly = [_evenly(items) for items in groups.values()]
    return [x for row in zip_longest(*evenly) for x in row if x is not None]


def _draw(tiles, size):
    width, height = size
    rows = (len(tiles) + COLUMNS - 1) // COLUMNS
    out = Image.new(
        "RGB", (COLUMNS * width, max(rows, 1) * (height + BAND)), (250, 251, 252)
    )
    draw = ImageDraw.Draw(out)
    font = ImageFont.load_default(size=16)
    for index, picture in enumerate(tiles):
        picture.thumbnail((width - 4, height - 4), Image.Resampling.LANCZOS)
        x, y = (index % COLUMNS) * width, (index // COLUMNS) * (height + BAND)
        out.paste(
            picture,
            (x + (width - picture.width) // 2, y + (height - picture.height) // 2),
        )
        draw.text((x + 6, y + height + 3), str(index + 1), fill=(60, 70, 84), font=font)
    data = BytesIO()
    out.save(data, format="JPEG", quality=85)
    return data.getvalue()


def _kept(db, kind, facts, make):
    """The sheet of these facts: made once, then read (its tiles and its file)."""
    key = hashlib.sha256(encoded({"kind": kind, "facts": facts}).encode()).hexdigest()
    row = db.one("SELECT sha256, tiles_json FROM sheets WHERE key=?", (key,))
    if row is None:
        data, tiles = make()
        sha256 = db.files.put("sheets", data, "jpg")
        with db.transaction():
            db.execute(
                "INSERT OR IGNORE INTO sheets(key, sha256, tiles_json, created_at)"
                " VALUES(?,?,?,?)",
                (key, sha256, encoded(tiles), now()),
            )
        row = {"sha256": sha256, "tiles_json": encoded(tiles)}
    tiles = json.loads(row["tiles_json"])
    # Each tile's image by its name, read now: the name is how a worker names an image.
    names = image_names(db, [t["image_id"] for t in tiles])
    return {
        "image": f"/v1/sheets/{row['sha256']}",
        "tiles": [{**t, "name": names.get(t["image_id"])} for t in tiles],
    }


def _tile_image(db, image_id, cache):
    if image_id not in cache:
        cache[image_id] = rgb(shown_image(image_file(db, image_id)[0]))
    return cache[image_id]


def _box(geometry, width, height):
    """The part of the image an object takes, with a margin (an image label: all of it)."""
    if geometry["type"] == "polygon":
        xs, ys = zip(*geometry["points"])
        x, y, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    else:
        x, y, w, h = geometry["xywh"]
    margin = 0.06 * max(w, h)
    return (
        max(0, int(x - margin)),
        max(0, int(y - margin)),
        min(width, int(x + w + margin)),
        min(height, int(y + h + margin)),
    )


def label_objects(db, label_id):
    """The label's annotations its sheet shows: in each dataset whose latest version has it
    (datasets_of, as the library counts them), each image's annotation now as its gallery shows
    it (image_state, S1; user 2026-10-29: results no image's annotation any more, of a label
    taken out of a plan, showed on), those a person fixed first, then the newest, an image
    once, from each dataset in turn (MOST of them), as (result, annotation)."""
    label_name = label_row(db, label_id)["name"]
    found = []  # (the result's row, its objects of the label)
    for dataset_id in datasets_of(db).get(label_id, []):
        key = latest_requirement(db, dataset_id)
        if key is None:
            continue
        name = names_now(db, dataset_id)
        for state in image_states(db, dataset_id, key, None)[1].values():
            if state["now"] is None:
                continue
            r = result_row(db, state["now"]["result_id"])
            objects = [
                a
                for a in current(db, r["set_id"])
                if name(r["instruction_revision"], a["label"]) == label_name
            ]
            if objects:
                found.append((r, objects))
    found.sort(key=lambda f: f[0]["record_at"], reverse=True)
    found.sort(key=lambda f: f[0]["result_by"] == "ai")
    groups, seen = {}, set()
    for r, objects in found:
        if r["image_id"] not in seen:
            seen.add(r["image_id"])
            groups.setdefault(r["dataset_id"], []).extend((r, a) for a in objects)
    return spread(groups)[:MOST]


def label_sheet(db, label_id):
    """Crops of the label's annotations (label_objects)."""
    picked = label_objects(db, label_id)
    facts = [[r["id"], a["id"]] for r, a in picked]

    def draw_sheet():
        cache, tiles = {}, []
        for r, a in picked:
            picture = _tile_image(db, r["image_id"], cache)
            tiles.append(picture.crop(_box(a["geometry"], *picture.size)))
        return _draw(tiles, LABEL_TILE), [
            {
                "n": n,
                "image_id": r["image_id"],
                "dataset_id": r["dataset_id"],
                "result_id": r["id"],
                "by": r["result_by"],
            }
            for n, (r, _) in enumerate(picked, 1)
        ]

    return _kept(db, "label", facts, draw_sheet)


def dataset_order(db, dataset_id):
    """The dataset's images in the order its sheets show them: from each folder they came from
    in turn (datasets.source_folder, as its card counts them), spread over each (definition
    42.1)."""
    dataset_row(db, dataset_id)
    groups = {}
    for r in image_rows(db, dataset_id):
        groups.setdefault(source_folder(db, r), []).append(r["id"])
    return spread(groups)


def dataset_sheet(db, dataset_id, page=1):
    """One page of the dataset's images (MOST of dataset_order; definition 42.2): every page
    together is every image once."""
    order = dataset_order(db, dataset_id)
    pages = max(1, -(-len(order) // MOST))
    if page > pages:
        raise invalid(f"The dataset's sheets are pages 1 to {pages}", pages=pages)
    picked = order[(page - 1) * MOST : page * MOST]

    def draw_sheet():
        cache = {}
        tiles = [_tile_image(db, i, cache) for i in picked]
        return _draw(tiles, IMAGE_TILE), [
            {"n": n, "image_id": i} for n, i in enumerate(picked, 1)
        ]

    sheet = _kept(db, "dataset", picked, draw_sheet)
    return {**sheet, "page": page, "pages": pages, "count": len(order)}


@router.get("/labels/{label_id}/sheet")
def get_label_sheet(request: Request, label_id: str):
    return label_sheet(request.app.state.db, label_id)


@router.get("/datasets/{dataset_id}/sheet")
def get_dataset_sheet(
    request: Request, dataset_id: str, page: Annotated[int, Query(ge=1)] = 1
):
    return dataset_sheet(request.app.state.db, dataset_id, page)


@router.get("/sheets/{sha256}")
def get_sheet(request: Request, sha256: str):
    db = request.app.state.db
    if db.one("SELECT 1 FROM sheets WHERE sha256=?", (sha256,)) is None:
        raise not_found("Sheet")
    return Response(
        db.files.read("sheets", sha256),
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=31536000, immutable"},
    )

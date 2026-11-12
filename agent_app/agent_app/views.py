"""Views: images shown to an AI or a person, recorded so a coordinate measured on one can
be turned back into original pixels. Copied from annotation_server/store.py (step 2 design 2).

The bytes are never stored; a recorded view can be drawn again from its request.
"""

import hashlib
import json
import math
import uuid

from fastapi.responses import Response

from .annotation_sets import snapshot
from .coordinates import check_same_image, to_original_crop, view_frame, with_margin
from .db import encoded, now
from .errors import ApiError, invalid
from .images import image_file, image_info
from .imaging import RENDERER, label_color, render
from .model_catalog import WORKER_VIEW_MAX_PIXELS, WORKER_VIEW_MAX_SIDE
from .settings import read_settings
from .shapes import CROP_MARGIN, ViewRequest


def view_side(db):
    """The long side of what an AI is shown outside a run: the setting a run takes too
    (definition 30.1)."""
    return read_settings(db)["worker_view_max_side"]


def sized_for_ai(body: ViewRequest, limit):
    """Every view goes to an AI: no bigger than any model takes in as it is, so the bytes
    arrive as they were sent and a coordinate on them is one on the recorded view (definition
    29.3; model_catalog.WORKER_VIEW_MAX_PIXELS). limit: the view size (a run's, else
    view_side), the default too."""
    wanted = body.max_side if "max_side" in body.model_fields_set else limit
    return body.model_copy(
        update={
            "max_side": min(wanted, limit, WORKER_VIEW_MAX_SIDE),
            "max_pixels": min(
                body.max_pixels or WORKER_VIEW_MAX_PIXELS, WORKER_VIEW_MAX_PIXELS
            ),
        }
    )


def around(geometries, width, height):
    """The crop holding every shape (how a reference is shown, in a run and in the plan); its
    margin is the one every crop gets (create_view)."""
    xs, ys = [], []
    for g in geometries:
        if g["type"] == "bbox":
            x, y, w, h = g["xywh"]
            xs += [x, x + w]
            ys += [y, y + h]
        else:
            xs += [p[0] for p in g["points"]]
            ys += [p[1] for p in g["points"]]
    x0, y0 = max(0, math.floor(min(xs))), max(0, math.floor(min(ys)))
    x1, y1 = min(width, math.ceil(max(xs))), min(height, math.ceil(max(ys)))
    return (x0, y0, x1 - x0, y1 - y0)


def frame_of(db, view_id):
    """A recorded view's whole frame (crop, scale, what it drew, its bytes' hash), or None."""
    row = db.one("SELECT frame_json FROM views WHERE id=?", (str(view_id),))
    return json.loads(row[0]) if row else None


def view_response(data, frame):
    """A view as the HTTP API returns it: the image, its whole frame in a header."""
    return Response(
        data,
        media_type="image/jpeg",
        headers={"x-annotation-view": json.dumps(frame, ensure_ascii=True)},
    )


def _render(db, image_id, annotations, request, colors):
    drawable = [
        {
            **a,
            "mask_png": db.files.read("masks", a["mask_sha256"])
            if a.get("mask_sha256")
            else None,
        }
        for a in annotations
    ]
    return render(image_file(db, image_id)[0], drawable, request, colors)


def create_view(
    db,
    image_id,
    request,
    *,
    set_id=None,
    run_id=None,
    result_id=None,
    colors=None,
    names=None,
):
    """Render and record a view. colors: label -> "#RRGGBB" (a run's own colors); labels
    without one get their palette color. names: annotation id -> the name it is shown by, when
    that is not the name it was saved with (a reference, as the plan names its labels now: a
    result keeps the names of the version that made it, label_ids.names_in); it is drawn in that
    name's color (2026-11-10: a reference chosen before its label was renamed was drawn in the
    old name's color, not the one its worker is told). The frame keeps the colors by the names
    saved, so the view draws again the same (render_view)."""
    if request.crop_xywh is not None:
        # In original pixels, with its margin (definition 30.1): the margin in the pixels the
        # crop is measured in, else the default of the original.
        image = image_info(db, image_id)
        crop, mx = request.crop_xywh, request.margin
        my = mx
        if request.coordinate_view_id is not None:
            source = view_frame(db, request.coordinate_view_id)
            check_same_image(source, image_id)
            crop = to_original_crop(crop, source, image["width"], image["height"])
            if mx is not None:
                mx, my = mx / source["scale_xy"][0], my / source["scale_xy"][1]
        if mx is None:
            mx = my = CROP_MARGIN
        request = request.model_copy(
            update={
                "crop_xywh": with_margin(crop, mx, my, image["width"], image["height"]),
                "coordinate_view_id": None,
                "margin": 0,
            }
        )
    annotations = []
    revision = None
    if set_id is not None:
        row, annotations = snapshot(db, set_id, request.revision)
        revision = row["revision"]
        if row["image_id"] != image_id:
            raise invalid("Set belongs to another image")
    if request.annotation_ids is not None:
        missing = set(request.annotation_ids) - {a["id"] for a in annotations}
        if missing:
            raise ApiError(404, "not_found", "Annotation is not in this set")
        annotations = [a for a in annotations if a["id"] in request.annotation_ids]
    if not request.overlay:
        annotations = []
    colors = {
        a["label"]: (colors or {}).get(shown) or label_color(shown)
        for a in annotations
        for shown in ((names or {}).get(a["id"], a["label"]),)
    }
    data, frame = _render(db, image_id, annotations, request, colors)
    view_id = str(uuid.uuid4())
    frame = {
        "view_id": view_id,
        "image_id": image_id,
        "set_id": set_id,
        "revision": revision,
        **frame,
        "label_colors": colors,
        "bytes_sha256": hashlib.sha256(data).hexdigest(),
        "renderer": RENDERER,
    }
    with db.transaction():
        db.execute(
            "INSERT INTO views(id,image_id,set_id,revision,request_json,frame_json,run_id,"
            "result_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                view_id,
                image_id,
                set_id,
                revision,
                encoded(request.model_dump(mode="json")),
                encoded(frame),
                run_id,
                result_id,
                now(),
            ),
        )
    return data, frame


def render_view(db, view_id):
    """Draw a recorded view again from the image file and the set at its revision."""
    row = db.one("SELECT * FROM views WHERE id=?", (str(view_id),))
    if row is None:
        raise ApiError(404, "view_not_found", "View does not exist")
    request = ViewRequest.model_validate(json.loads(row["request_json"]))
    frame = json.loads(row["frame_json"])
    annotations = []
    if row["set_id"] is not None and request.overlay:
        _, annotations = snapshot(db, row["set_id"], row["revision"])
        annotations = [a for a in annotations if a["id"] in frame["annotation_ids"]]
    # The recorded crop is already in original pixels.
    request = request.model_copy(
        update={"crop_xywh": tuple(frame["crop_xywh"]), "coordinate_view_id": None}
    )
    data, _ = _render(db, row["image_id"], annotations, request, frame["label_colors"])
    return data, frame

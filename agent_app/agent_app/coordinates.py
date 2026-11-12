"""Convert coordinates measured on a returned view back to original-image pixels.

AI clients see shrunken or cropped images. They send positions in the pixels of
the image they looked at plus its view_id; the server does the conversion so no
model has to apply crop offsets and scales itself.
"""

import math

from .errors import ApiError


def view_frame(db, view_id):
    """Crop and scale of a recorded view, by its ID."""
    from .views import frame_of  # a view's frame is the view's

    meta = frame_of(db, view_id)
    if meta is None:
        raise ApiError(404, "view_not_found", "Coordinate view does not exist")
    return {
        "view_id": str(view_id),
        "image_id": meta["image_id"],
        "crop_xywh": tuple(meta["crop_xywh"]),
        "scale_xy": tuple(meta["scale_xy"]),
    }


def shrunk(frame):
    """Whether a view has fewer pixels than the part of the original it shows (definition
    32.7)."""
    return min(frame["scale_xy"]) < 1


def check_same_image(frame, image_id):
    if frame["image_id"] != image_id:
        raise ApiError(
            422, "view_image_mismatch", "Coordinate view belongs to another image"
        )


def _point(frame, x, y):
    cx, cy, _, _ = frame["crop_xywh"]
    sx, sy = frame["scale_xy"]
    return round(cx + x / sx, 2), round(cy + y / sy, 2)


def to_original_geometry(geometry, frame):
    """Bbox/polygon dict in view pixels -> the same geometry in original pixels."""
    if geometry["type"] == "bbox":
        x, y, w, h = geometry["xywh"]
        sx, sy = frame["scale_xy"]
        ox, oy = _point(frame, x, y)
        return {**geometry, "xywh": [ox, oy, round(w / sx, 2), round(h / sy, 2)]}
    if geometry["type"] == "polygon":
        return {
            **geometry,
            "points": [list(_point(frame, x, y)) for x, y in geometry["points"]],
        }
    raise ApiError(422, "invalid_input", "Mask geometry must use original pixels")


def to_view_geometry(geometry, frame):
    """Bbox/polygon dict in original pixels -> the same geometry in the view's pixels (what
    the AI is shown with a view, definition 29.1); a mask has no coordinates to show."""
    cx, cy, _, _ = frame["crop_xywh"]
    sx, sy = frame["scale_xy"]
    if geometry["type"] == "bbox":
        x, y, w, h = geometry["xywh"]
        return {
            "type": "bbox",
            "xywh": [
                round((x - cx) * sx, 1),
                round((y - cy) * sy, 1),
                round(w * sx, 1),
                round(h * sy, 1),
            ],
        }
    if geometry["type"] == "polygon":
        return {
            "type": "polygon",
            "points": [
                [round((x - cx) * sx, 1), round((y - cy) * sy, 1)]
                for x, y in geometry["points"]
            ],
        }
    return {"type": "mask"}


def to_original_crop(crop, frame, width, height):
    """Integer crop in view pixels -> integer crop in original pixels, clipped."""
    x, y, w, h = crop
    left, top = _point(frame, x, y)
    right, bottom = _point(frame, x + w, y + h)
    x0, y0 = max(0, math.floor(left)), max(0, math.floor(top))
    x1, y1 = min(width, math.ceil(right)), min(height, math.ceil(bottom))
    if x1 <= x0 or y1 <= y0:
        raise ApiError(400, "invalid_input", "crop must lie inside the original image")
    return (x0, y0, x1 - x0, y1 - y0)


def with_margin(crop, mx, my, width, height):
    """A crop in original pixels with room added on every side (mx left and right, my above
    and below), inside the image (definition 30.1)."""
    x, y, w, h = crop
    x0, y0 = max(0, math.floor(x - mx)), max(0, math.floor(y - my))
    x1, y1 = min(width, math.ceil(x + w + mx)), min(height, math.ceil(y + h + my))
    return (x0, y0, x1 - x0, y1 - y0)

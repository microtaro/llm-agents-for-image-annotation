"""Checks of saved shapes: bboxes and polygons inside the image, masks as 0/255 PNGs.

Copied from annotation_server/imaging.py.
"""

import base64
import binascii
import warnings
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from .errors import ApiError
from .images import MAX_PIXELS
from .shapes import Bbox, Mask, Polygon

MAX_MASK_BYTES = 8 * 1024 * 1024


def decode_mask(data: bytes) -> Image.Image:
    """A mask PNG: single-frame 8-bit L without transparency, at most MAX_MASK_BYTES."""
    if len(data) > MAX_MASK_BYTES:
        raise ApiError(413, "payload_too_large", "PNG exceeds the byte limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                w, h = source.size
                if source.format != "PNG":
                    raise ApiError(
                        400, "unsupported_image", "Only PNG input is supported"
                    )
                if w * h > MAX_PIXELS:
                    raise ApiError(
                        413, "payload_too_large", "Image dimensions exceed the limit"
                    )
                if source.n_frames != 1 or 274 in source.getexif():
                    raise ApiError(
                        400,
                        "unsupported_image",
                        "Animation and EXIF orientation are unsupported",
                    )
                if source.mode != "L":
                    raise ApiError(
                        400, "unsupported_image", "Unsupported PNG color mode"
                    )
                if "transparency" in source.info:
                    raise ApiError(
                        400, "invalid_geometry", "Mask must not contain transparency"
                    )
                source.load()
                return source.copy()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ApiError(
            413, "payload_too_large", "Image dimensions exceed the limit"
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise ApiError(400, "unsupported_image", "Cannot decode PNG") from exc


def cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def touches(a, b, c, d):
    ab_c, ab_d, cd_a, cd_b = (
        cross(a, b, c),
        cross(a, b, d),
        cross(c, d, a),
        cross(c, d, b),
    )
    if ((ab_c > 0 > ab_d) or (ab_d > 0 > ab_c)) and (
        (cd_a > 0 > cd_b) or (cd_b > 0 > cd_a)
    ):
        return True
    for value, p, q, r in (
        (ab_c, a, b, c),
        (ab_d, a, b, d),
        (cd_a, c, d, a),
        (cd_b, c, d, b),
    ):
        if (
            value == 0
            and min(p[0], q[0]) <= r[0] <= max(p[0], q[0])
            and min(p[1], q[1]) <= r[1] <= max(p[1], q[1])
        ):
            return True
    return False


def validate_geometry(geometry, width: int, height: int):
    """Return JSON geometry plus optional original mask PNG bytes."""

    def refuse(message):
        raise ApiError(400, "invalid_geometry", message)

    if isinstance(geometry, Bbox):
        x, y, w, h = geometry.xywh
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
            refuse(
                "bbox must lie inside the original image and have positive dimensions"
            )
    elif isinstance(geometry, Polygon):
        points = geometry.points
        n = len(points)
        if any(x < 0 or y < 0 or x > width or y > height for x, y in points):
            refuse("polygon must lie inside the original image")
        for i, b in enumerate(points):
            a, c = points[i - 1], points[(i + 1) % n]
            if b == c or (
                cross(a, b, c) == 0
                and (a[0] - b[0]) * (c[0] - b[0]) + (a[1] - b[1]) * (c[1] - b[1]) > 0
            ):
                refuse(
                    "polygon has duplicate adjacent points or overlapping adjacent edges"
                )
        area = sum(
            a[0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * a[1]
            for i, a in enumerate(points)
        )
        if area == 0:
            refuse("polygon must have positive area")
        for i in range(n):
            a, b = points[i], points[(i + 1) % n]
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue
                if touches(a, b, points[j], points[(j + 1) % n]):
                    refuse("polygon must not self-intersect or touch nonadjacent edges")
    elif isinstance(geometry, Mask):
        if len(geometry.png_base64) > ((MAX_MASK_BYTES + 2) // 3) * 4:
            raise ApiError(413, "payload_too_large", "Mask exceeds the byte limit")
        try:
            data = base64.b64decode(geometry.png_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ApiError(400, "invalid_geometry", "Invalid mask base64") from exc
        mask = decode_mask(data)
        if mask.size != (width, height):
            refuse("mask dimensions must match the original image")
        histogram = mask.histogram()
        bounds = mask.getbbox()
        if sum(histogram[1:255]) or bounds is None:
            refuse("mask must be nonempty and contain only 0 and 255")
        x, y, right, bottom = bounds
        return {
            "type": "mask",
            "width": width,
            "height": height,
            "bbox_xywh": [x, y, right - x, bottom - y],
        }, data
    return geometry.model_dump(mode="json"), None

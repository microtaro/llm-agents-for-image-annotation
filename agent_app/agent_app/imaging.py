"""Views: a crop of an image, shrunk, with annotations drawn in their labels' colors.

Copied from annotation_server/imaging.py; every annotation of a label has its label's color
(no per-annotation style).
"""

import hashlib
from io import BytesIO

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from .errors import ApiError
from .geometry import decode_mask
from .shapes import MAX_ZOOM, ViewRequest

# Recorded with every view; a view re-rendered by another renderer may differ slightly.
RENDERER = "pil-3"
LINE_WIDTH = 2
FILL_OPACITY = 0.25
# Label colors, given in the order labels first appear in a dataset's instructions; ten
# colors that stay apart from each other on photos. Reused from the start after ten.
# Blue and orange first: a pair color-blind people tell apart too. Red last: the screen uses
# red for failures, and red after green was hard to tell apart (order changed 2026-09-29).
PALETTE = (
    "#4363D8",
    "#F58231",
    "#3CB44B",
    "#911EB4",
    "#42D4F4",
    "#F032E6",
    "#FFE119",
    "#BFEF45",
    "#9A6324",
    "#E6194B",
)


def shown_image(data: bytes):
    """An original image file as it is shown: EXIF rotation applied, mapped onto RGB,
    RGBA or 8-bit L the same way every time (images.decode checked it on import)."""
    with Image.open(BytesIO(data)) as source:
        return normalize_mode(ImageOps.exif_transpose(source))


def normalize_mode(image):
    """Map any decoded mode onto RGB, RGBA or 8-bit L (grayscale)."""
    if image.mode in ("RGB", "L") and "transparency" in image.info:
        return image.convert("RGBA")
    if image.mode in ("RGB", "RGBA", "L"):
        return image
    if image.mode == "1":
        return image.convert("L")
    if image.mode.startswith("I") or image.mode == "F":
        # 16-bit/float grayscale: the brightest value becomes white, so 12-bit
        # sensor data stored in 16 bits does not come out nearly black.
        wide = image.convert("F")
        top = wide.getextrema()[1] or 1
        return wide.point(lambda v: v * 255 / top).convert("L")
    if image.mode in ("LA", "PA") or "transparency" in image.info:
        return image.convert("RGBA")
    return image.convert("RGB")


def rgb(image):
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        return background
    return image.convert("RGB")


def label_color(label):
    """The palette color of a label (label colors are not chosen per dataset yet)."""
    return PALETTE[hashlib.sha256(label.encode()).digest()[0] % len(PALETTE)]


def ink(hex_color):
    return tuple(bytes.fromhex(hex_color[1:]))


def render(data: bytes, annotations: list[dict], request: ViewRequest, colors):
    """Draw a view. colors maps label -> "#RRGGBB"; a label without one gets label_color."""
    original = rgb(shown_image(data))
    iw, ih = original.size
    x, y, w, h = request.crop_xywh or (0, 0, iw, ih)
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > iw or y + h > ih:
        raise ApiError(400, "invalid_input", "crop must lie inside the original image")
    # The whole image is only shrunk; a crop is enlarged too, at most MAX_ZOOM times
    # (definition 30.1).
    zoom = 1 if (x, y, w, h) == (0, 0, iw, ih) else MAX_ZOOM
    ratio = min(zoom, request.max_side / max(w, h))
    if request.max_pixels and w * h * ratio * ratio > request.max_pixels:
        ratio = (request.max_pixels / (w * h)) ** 0.5
    ow, oh = max(1, round(w * ratio)), max(1, round(h * ratio))
    if request.max_pixels and ow * oh > request.max_pixels:
        ow, oh = max(1, int(w * ratio)), max(1, int(h * ratio))
    crop = (x, y, x + w, y + h)
    output = original.crop(crop).resize((ow, oh), Image.Resampling.LANCZOS)

    def to_output(px, py):
        """An original-pixel point on the output."""
        return ((px - x) * ow / w, (py - y) * oh / h)

    drawn = []
    if request.overlay:
        for ann in annotations:
            drawn.append(ann["id"])
            geometry = ann["geometry"]
            color = colors.get(ann["label"]) or label_color(ann["label"])
            width = LINE_WIDTH
            # Boxes and polygons are drawn on the output in its own pixels (pil-3), so the cost
            # follows the output size, not the original's. Sides outside a crop fall off the
            # canvas instead of making false edges at the crop.
            if geometry["type"] == "bbox":
                bx, by, bw, bh = geometry["xywh"]
                (left, top), (right, bottom) = (
                    to_output(bx, by),
                    to_output(bx + bw, by + bh),
                )
                ImageDraw.Draw(output).rectangle(
                    (left, top, max(left, right - 1), max(top, bottom - 1)),
                    outline=ink(color),
                    width=width,
                )
                continue
            if geometry["type"] == "polygon":
                points = [to_output(*point) for point in geometry["points"]]
                # Only the polygon's own area of the output is worked on.
                left = max(0, int(min(px for px, _ in points)) - 1)
                top = max(0, int(min(py for _, py in points)) - 1)
                right = min(ow, int(max(px for px, _ in points)) + 2)
                bottom = min(oh, int(max(py for _, py in points)) + 2)
                if right <= left or bottom <= top:
                    continue
                local = [(px - left, py - top) for px, py in points]
                area = (right - left, bottom - top)
                fill = Image.new("L", area)
                ImageDraw.Draw(fill).polygon(local, fill=255)
                # The outline is the inner half of a line twice as wide along the boundary.
                line = Image.new("L", area)
                ImageDraw.Draw(line).line(
                    local + [local[0]], fill=255, width=2 * width, joint="curve"
                )
                paint = Image.new("RGB", area, ink(color))
                opacity = FILL_OPACITY
                output.paste(
                    paint,
                    (left, top),
                    mask=fill.point(
                        lambda value, opacity=opacity: round(value * opacity)
                    ),
                )
                output.paste(paint, (left, top), mask=ImageChops.multiply(fill, line))
                continue
            plane = decode_mask(ann["mask_png"])
            # Determine the true boundary before cropping. Holes stay transparent.
            # Large downscales need not create a huge quadratic kernel.
            reduced = plane.resize(
                (max(1, round(iw * ratio)), max(1, round(ih * ratio))),
                Image.Resampling.NEAREST,
            )
            inner = (
                ImageOps.expand(reduced, border=width, fill=0)
                .filter(ImageFilter.MinFilter(2 * width + 1))
                .crop((width, width, reduced.width + width, reduced.height + width))
            )
            edge_small = ImageChops.subtract(reduced, inner)
            edge = edge_small.resize(plane.size, Image.Resampling.NEAREST)
            fill = plane.crop(crop).resize((ow, oh), Image.Resampling.NEAREST)
            output.paste(
                ink(color),
                mask=fill.point(lambda value: round(value * FILL_OPACITY)),
            )
            output.paste(
                ink(color),
                mask=edge.crop(crop).resize((ow, oh), Image.Resampling.NEAREST),
            )
    buffer = BytesIO()
    output.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue(), {
        "crop_xywh": [x, y, w, h],
        "output_size": [ow, oh],
        "scale_xy": [ow / w, oh / h],
        "annotation_ids": drawn,
    }

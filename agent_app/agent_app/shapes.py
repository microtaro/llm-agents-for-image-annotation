"""Shapes and the requests that write or show them. Geometry is in original-image pixels, or in
the pixels of a view the AI looked at when its coordinate_view_id is given (the server turns
those into original pixels; an AI always gives them, definition 29.2).

Copied from annotation_server/schemas.py without per-annotation styles: a label's color
draws every annotation of it (docs/2026-10-05-app-step2-design.md 2).
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictInt, field_validator

from .errors import Model

Number = Annotated[float, Field(strict=True)]
Point = tuple[Number, Number]
# One attribute value of an annotation (label definitions, 2026-10-01): text, a number or none.
AttributeValue = (
    Annotated[str, Field(max_length=2000)]
    | Annotated[int, Field(strict=True)]
    | Annotated[float, Field(strict=True, allow_inf_nan=False)]
    | None
)


# A label's name, everywhere a label is named (issue #4 F-05: 64 in the plan, 128 in a result).
LABEL_MAX = 64
# How a crop is shown to an AI (definition 30.1, user 2026-10-21): room added on every side, in
# original pixels unless given, and enlarged at most this many times up to the view size.
CROP_MARGIN = 20
MAX_ZOOM = 8


class ExecutionSelection(Model):
    model: str | None = Field(
        None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
        description="Requested execution model. Null uses the server default; does not change global configuration.",
    )
    effort: str | None = Field(
        None,
        min_length=1,
        max_length=32,
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Requested reasoning effort, validated against the selected model. Null uses medium (or the model's own default without medium).",
    )
    tier: str | None = Field(
        None,
        min_length=1,
        max_length=32,
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="A faster tier from the model's speeds (fast mode). Null runs at the standard speed.",
    )


class Bbox(Model):
    type: Literal["bbox"] = Field(
        description="Geometry discriminator: axis-aligned bbox."
    )
    xywh: tuple[Number, Number, Number, Number] = Field(
        description="[x, y, width, height] in the pixels of the image measured on (its view_id given with them; original-image pixels when none). Top-left origin; x/y >= 0, width/height > 0; entire box inside image. Finite numbers only, not strings or booleans."
    )


class Polygon(Model):
    type: Literal["polygon"] = Field(
        description="Geometry discriminator: one polygon exterior."
    )
    points: Annotated[list[Point], Field(min_length=3, max_length=2048)] = Field(
        description="Ordered [x,y] vertices in the pixels of the image measured on (its view_id given with them; original-image pixels when none), inside image. Single exterior with nonzero area, no self-intersections, overlapping edges or nonadjacent edge contact. Do not repeat the first vertex at the end or duplicate adjacent vertices. Saved without rounding. Use mask for holes or disconnected components."
    )


class Mask(Model):
    type: Literal["mask"] = Field(
        description="Geometry discriminator: binary segmentation mask."
    )
    png_base64: str = Field(
        description="Strict base64 of a real PNG file (no data-URL prefix), <= 8 MiB decoded. Must have exactly the original image width/height, 8-bit grayscale L mode, only 0 (background) and 255 (target), at least one target pixel. No transparency, animation or EXIF orientation. Holes and disconnected components are preserved. Normal responses use MaskOutput; export returns this input form."
    )


Geometry = Annotated[Bbox | Polygon | Mask, Field(discriminator="type")]


class Labeled(Model):
    label: str = Field(
        description=f"Target label, trimmed on input; 1 to {LABEL_MAX} characters after trimming."
    )
    geometry: Geometry = Field(
        description="Complete geometry, in the pixels of the batch's coordinate_view_id. Required together with label, including updates."
    )
    parent: str | None = Field(
        None,
        max_length=64,
        description="The annotation it belongs to: an existing annotation ID of this image or the ref of a create in this batch; only an annotation of the label's parent label (label_definitions). Null for none. An update that omits it keeps its parent.",
    )
    attributes: dict[str, AttributeValue] | None = Field(
        None,
        description="Attribute values by name, as the label's attributes define them (text, number or one of the choices); null for an unknown value. An update that omits it keeps its values.",
    )

    @field_validator("label")
    @classmethod
    def label_length(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= LABEL_MAX:
            raise ValueError(
                f"label must contain 1 to {LABEL_MAX} characters after trimming"
            )
        return value


class Create(Labeled):
    op: Literal["create"] = Field(
        description="Create an annotation; server assigns a new stable ID."
    )
    ref: str | None = Field(
        None,
        min_length=1,
        max_length=64,
        description="Optional name of this new annotation inside the batch, so another operation of the batch can give it as parent. created_refs maps it to the new ID.",
    )


class Update(Labeled):
    op: Literal["update"] = Field(
        description="Replace label and entire geometry, retaining this annotation ID. Other annotations remain unchanged."
    )
    id: str = Field(
        description="Existing annotation ID from the latest image state; must belong to this image."
    )


class Delete(Model):
    op: Literal["delete"] = Field(description="Delete this annotation only.")
    id: str = Field(
        description="Existing annotation ID from the latest image state; must belong to this image."
    )


Operation = Annotated[Create | Update | Delete, Field(discriminator="op")]
Revision = Annotated[StrictInt, Field(ge=0)]


class Batch(Model):
    request_id: UUID | None = Field(
        None,
        description="Optional idempotency key. Same image/key/body returns committed response without a new revision; different body conflicts.",
    )
    base_revision: Revision = Field(
        description="Current image revision from the latest GET/upload/apply response; required optimistic concurrency token. On 409 fetch current state and reconsider edits; never automatically resend the stale batch."
    )
    coordinate_view_id: UUID | None = Field(
        None,
        description="The view_id of the image you measured on; every create/update geometry in this batch is in its pixels and the server converts them. Not allowed when the batch contains mask geometry.",
    )
    operations: Annotated[list[Operation], Field(min_length=1, max_length=100)] = Field(
        description="Ordered atomic batch: all succeed or none are saved. Each existing ID may be updated/deleted only once per batch. At most 1000 annotations may remain on the image. Untargeted annotations are preserved."
    )


class ViewRequest(Model):
    revision: Revision | None = Field(
        None,
        description="Revision of the annotations to draw; null/default draws the current revision. Ignored for a plain image view.",
    )
    overlay: bool = Field(
        True,
        description="Default true: draw saved annotations. False: observe image/crop without annotation graphics; metadata annotation_ids is empty.",
    )
    crop_xywh: tuple[StrictInt, StrictInt, StrictInt, StrictInt] | None = Field(
        None,
        description="Integer [x,y,width,height] in the pixels of the image named by coordinate_view_id, inside it with positive dimensions. Null/default means the entire original image.",
    )
    max_side: Annotated[StrictInt, Field(ge=64, le=2048)] = Field(
        1600,
        description=f"Output long side in pixels (an AI's views get at most the view size). The whole image is only shrunk; a crop is shrunk or enlarged (at most {MAX_ZOOM}x) to it.",
    )
    max_pixels: Annotated[StrictInt, Field(ge=4096)] | None = Field(
        None,
        description="Maximum output pixels (width x height); shrink only. Inside a run, every worker's views get the size no model scales down.",
    )
    annotation_ids: list[str] | None = Field(
        None,
        description="Null/default selects all saved annotations; [] selects none; otherwise only these IDs. Unknown or other-image IDs return 404 even when overlay=false.",
    )
    coordinate_view_id: UUID | None = Field(
        None,
        description="The view_id of the image crop_xywh is measured on; the server converts it. Ignored when crop_xywh is null (whole image).",
    )
    margin: Annotated[StrictInt, Field(ge=0, le=1024)] | None = Field(
        None,
        description=f"Room added on every side of crop_xywh, in the pixels it is measured in; null: {CROP_MARGIN} pixels of the original image. Ignored without a crop.",
    )

"""Inputs of the worker's MCP tools and the result envelope every tool returns.

Copied from annotation_server/mcp_schemas.py (worker tools only, step 2 design 5).
"""

from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import Field, StrictInt, model_validator

from .errors import Model
from .shapes import Batch, ViewRequest


class Seen(Model):
    """An image as the AI is told it (seen.seen, definition 29.1): never where it was cut from
    or its scale; its coordinates are its own pixels."""

    view_id: str = Field(
        description="This image's number: give it as coordinate_view_id (view_id) with"
        " coordinates measured on it."
    )
    image_id: str = Field(description="Image shown.")
    output_size: tuple[int, int] = Field(description="[width, height] of this image.")
    shrunk: bool = Field(
        description="true: this image has fewer pixels than the part of the original it"
        " shows; a crop small enough comes back not shrunk."
    )
    drawn: list[dict] = Field(
        description="What is drawn on it (id or label, attributes), each geometry in this"
        " image's pixels."
    )


def batch_measured(batch):
    """A batch's created and changed shapes are measured on an image the AI saw (masks are
    whole-image pictures, not coordinates)."""
    measured(
        batch.coordinate_view_id,
        [
            o.geometry
            for o in batch.operations
            if o.op != "delete" and o.geometry.type != "mask"
        ],
        "batch.coordinate_view_id",
    )


def measured(view_id, geometries, what):
    """Coordinates an AI gives are in the pixels of an image it saw: refuse them without its
    view_id (definition 29.2)."""
    if view_id is None and any(g is not None for g in geometries):
        raise ValueError(
            f"{what}: give the view_id of the image you measured on; coordinates are in its"
            " pixels"
        )


class ObserveTarget(Model):
    image_id: str | None = Field(None, description="The plain image (your target).")
    result_id: str | None = Field(None, description="Your result.")

    @model_validator(mode="after")
    def one_target(self):
        if (self.image_id is None) == (self.result_id is None):
            raise ValueError("Give image_id or result_id")
        return self


class ObserveInput(Model):
    target: ObserveTarget = Field(
        description="What to look at: {image_id} or {result_id}."
    )
    view: ViewRequest = Field(
        default_factory=ViewRequest,
        description="Crop/size/overlay. A crop is in the pixels of the image named by coordinate_view_id; it comes back with a margin around it, enlarged (up to 8x) or shrunk to view_max_side. max_side defaults to the run's view_max_side and never exceeds it. Display the returned image; HTTP success alone is not observation.",
    )

    @model_validator(mode="after")
    def crop_measured(self):
        measured(self.view.coordinate_view_id, [self.view.crop_xywh], "view.crop_xywh")
        return self


class OverlayOptions(Model):
    crop_xywh: tuple[StrictInt, StrictInt, StrictInt, StrictInt] | None = (
        ViewRequest.model_fields["crop_xywh"]
    )
    max_side: Annotated[StrictInt, Field(ge=64, le=2048)] = ViewRequest.model_fields[
        "max_side"
    ]
    coordinate_view_id: UUID | None = ViewRequest.model_fields["coordinate_view_id"]
    margin: Annotated[StrictInt, Field(ge=0, le=1024)] | None = (
        ViewRequest.model_fields["margin"]
    )

    @model_validator(mode="after")
    def crop_measured(self):
        measured(self.coordinate_view_id, [self.crop_xywh], "view.crop_xywh")
        return self


class TaskGetInput(Model):
    run_id: UUID = Field(description="Your run ID.")
    result_id: str = Field(description="Your result ID.")


class SaveAndObserveInput(Model):
    result_id: str = Field(description="Your result ID.")
    batch: Batch = Field(
        description="Atomic edits to your result. Set coordinate_view_id to the view you measured on; geometry in that view's pixels. A fresh UUID request_id per batch."
    )
    view: OverlayOptions = Field(
        default_factory=OverlayOptions,
        description="Overlay returned after saving; max_side defaults to the run's view_max_side and never exceeds it.",
    )

    @model_validator(mode="after")
    def geometry_measured(self):
        batch_measured(self.batch)
        return self


class ToolError(Model):
    code: str = Field(description="Original API error code or an MCP-side code.")
    message: str = Field(description="Failure and recovery context.")
    details: dict = Field(default_factory=dict, description="API error details.")


Payload = TypeVar("Payload")


class Envelope(Model, Generic[Payload]):
    ok: bool = Field(description="True only when the whole operation succeeded.")
    save_status: Literal["not_attempted", "saved", "unknown"] = Field(
        description="saved: the write committed, even if a later step failed; not_attempted: nothing was written; unknown: read state before retrying a write."
    )
    data: Payload | None = Field(None, description="Result of the operation.")
    view: Seen | None = Field(None, description="The returned image, if any.")
    whole: Seen | None = Field(
        None,
        description="After a write whose view is a crop: the whole image too (definition 32.1,"
        " 7: what was written is seen whole before going on).",
    )
    reference_views: list[Seen] = Field(
        default_factory=list,
        description="task_get only: one image per reference, its example objects drawn, in refs order.",
    )
    error: ToolError | None = Field(None, description="Structured failure.")
    next_actions: list[str] = Field(description="Tool names to use next.")

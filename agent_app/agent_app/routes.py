"""The /v1 HTTP entry points (step 1 design 7). Routes only call the modules."""

from typing import Annotated

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import Field

from . import dataset_admin, datasets, images, instructions
from .decisions import by_of
from .errors import Model
from .run_routes import db_of

router = APIRouter(prefix="/v1")


class ImportInput(Model):
    paths: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=4096)]],
        Field(min_length=1, max_length=1000),
    ]
    origin: datasets.GeneratedOrigin | None = Field(
        None, description="Null for photographed images; generated images say how."
    )


@router.post("/images/import")
def import_images(request: Request, body: ImportInput):
    origin = body.origin.model_dump() if body.origin else None
    return images.import_paths(db_of(request), body.paths, origin)


@router.get("/images/{image_id}")
def get_image(request: Request, image_id: str):
    return images.image_info(db_of(request), image_id)


@router.get("/images/{image_id}/file")
def get_image_file(request: Request, image_id: str):
    data, media_type = images.image_file(db_of(request), image_id)
    return Response(data, media_type=media_type)


@router.post("/datasets")
def create_dataset_route(request: Request, body: datasets.DatasetInput):
    return datasets.create_dataset(db_of(request), body, by_of(request))


@router.get("/datasets")
def list_datasets_route(request: Request):
    return datasets.list_datasets(db_of(request))


@router.get("/datasets/{dataset_id}")
def get_dataset_route(request: Request, dataset_id: str):
    return datasets.get_dataset(db_of(request), dataset_id)


@router.patch("/datasets/{dataset_id}")
def patch_dataset_route(request: Request, dataset_id: str, body: datasets.DatasetPatch):
    return datasets.patch_dataset(db_of(request), dataset_id, body, by_of(request))


@router.post("/datasets/{dataset_id}/images/import")
def import_to_dataset_route(
    request: Request, dataset_id: str, body: datasets.ImportToDatasetInput
):
    return datasets.import_to_dataset(db_of(request), dataset_id, body, by_of(request))


@router.post("/datasets/{dataset_id}/images")
def add_images_route(request: Request, dataset_id: str, body: datasets.AddImagesInput):
    return datasets.add_images(db_of(request), dataset_id, body, by_of(request))


@router.post("/datasets/{dataset_id}/images/remove")
def remove_images_route(
    request: Request, dataset_id: str, body: datasets.RemoveImagesInput
):
    return datasets.remove_images(db_of(request), dataset_id, body, by_of(request))


# No route saves a version by itself (user 2026-10-28, review A#4): a version is made when a run
# of the plan is decided (definition 22.1), a person's or an AI's decision alike.


@router.get("/datasets/{dataset_id}/instructions")
def list_instructions_route(request: Request, dataset_id: str):
    return instructions.list_instructions(db_of(request), dataset_id)


@router.get("/datasets/{dataset_id}/instructions/{revision}/diff")
def instruction_diff(request: Request, dataset_id: str, revision: str):
    return instructions.version_diff(db_of(request), dataset_id, revision)


@router.get("/datasets/{dataset_id}/instructions/{revision}")
def get_instruction_route(request: Request, dataset_id: str, revision: str):
    from .references import resolved

    db = db_of(request)
    return resolved(db, instructions.get_instruction(db, dataset_id, revision))


@router.post("/datasets/{dataset_id}/copy", status_code=201)
def copy_dataset_route(
    request: Request,
    dataset_id: str,
    body: dataset_admin.CopyInput,
):
    return dataset_admin.copy_dataset(db_of(request), dataset_id, body, by_of(request))


@router.post("/datasets/from", status_code=201)
def make_from_datasets_route(
    request: Request,
    body: dataset_admin.FromDatasetsInput,
):
    """A new dataset from the images of chosen datasets (the library's making)."""
    return dataset_admin.make_from_datasets(db_of(request), body, by_of(request))


@router.post("/datasets/deletion")
def deletion_preview_many(request: Request, body: dataset_admin.DeletionInput):
    """What deleting several datasets together would remove (the library's tidying)."""
    return dataset_admin.deletion_preview(db_of(request), body.dataset_ids)


@router.get("/datasets/{dataset_id}/deletion")
def deletion_preview_route(request: Request, dataset_id: str):
    return dataset_admin.deletion_counts(db_of(request), dataset_id)


@router.delete("/datasets/{dataset_id}")
def delete_dataset_route(request: Request, dataset_id: str):
    return dataset_admin.delete_dataset(db_of(request), dataset_id, by_of(request))

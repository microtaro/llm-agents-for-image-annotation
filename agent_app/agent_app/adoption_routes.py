"""The /v1 entry points of an image's use (not used, used again) and adoption
(docs/2026-10-05-app-step3-design.md 6-7; kept apart when the masters' routes were taken out,
types design 6, 2026-10-13). A run's worker may use none of them.
"""

from fastapi import APIRouter, Request

from . import adoption
from .decisions import by_of
from .run_routes import db_of, no_worker

router = APIRouter(prefix="/v1")


@router.post("/datasets/{dataset_id}/images/{image_id}/exclude")
def exclude_image(request: Request, dataset_id: str, image_id: str):
    no_worker(request)
    return adoption.mark_image(
        db_of(request), dataset_id, image_id, True, by_of(request)
    )


@router.post("/datasets/{dataset_id}/images/{image_id}/include")
def include_image(request: Request, dataset_id: str, image_id: str):
    no_worker(request)
    return adoption.mark_image(
        db_of(request), dataset_id, image_id, False, by_of(request)
    )


@router.get("/datasets/{dataset_id}/adoption")
def get_adoption(request: Request, dataset_id: str):
    no_worker(request)
    return adoption.adoption(db_of(request), dataset_id)


@router.get("/datasets/{dataset_id}/adoption/annotations")
def adopted_annotations_route(request: Request, dataset_id: str):
    no_worker(request)
    return adoption.adopted_annotations(db_of(request), dataset_id)

"""The /v1 entry points only people's screens use: thumbnails, a folder preview, the
gallery and the overall map (docs/2026-10-05-app-step6-design.md 3)."""

from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from PIL import Image
from starlette.concurrency import run_in_threadpool

from .datasets import Paths, check_in_dataset
from .drafts import plan_of
from .errors import Model
from .gallery import gallery
from .image_state import image_states
from .images import image_file, scan_paths
from .imaging import rgb, shown_image
from .instructions import latest_basis, latest_row
from .label_colors import ColorsInput, dataset_colors, reset_colors, set_colors
from .label_ids import names_now
from .native_picker import PickedFolder, PickFolderInput, pick_folder
from .progress import progress
from .run_queries import (
    SUCCESS,
    dataset_results,
    of_requirement,
    of_version,
    result_ref,
)
from .run_routes import db_of, no_worker

router = APIRouter(prefix="/v1")


class ScanInput(Model):
    paths: Paths


def _thumbnail(db, image_id, max_side):
    data, _ = image_file(db, image_id)
    picture = rgb(shown_image(data))
    picture.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    out = BytesIO()
    picture.save(out, format="JPEG", quality=85)
    return out.getvalue()


@router.get("/images/{image_id}/thumbnail")
async def thumbnail(
    request: Request,
    image_id: str,
    max_side: Annotated[int, Query(ge=32, le=2048)] = 320,
):
    no_worker(request)
    data = await run_in_threadpool(_thumbnail, db_of(request), image_id, max_side)
    # An image ID names its bytes, so a thumbnail of it never changes.
    headers = {"Cache-Control": "max-age=31536000, immutable"}
    return Response(data, media_type="image/jpeg", headers=headers)


@router.post("/local-images/scan")
def scan(request: Request, body: ScanInput):
    no_worker(request)
    from .dataset_import import written_in

    # A folder written out is told by what it holds (definition 60.3): the first one found.
    written = next((w for w in map(written_in, body.paths) if w), None)
    return {**scan_paths(body.paths), "written": written}


@router.post("/local-images/select", response_model=PickedFolder)
def select(request: Request, body: PickFolderInput):
    """A folder chosen in the Windows window on the server's desktop (definition 43); the
    request waits while the window is open."""
    no_worker(request)
    return pick_folder(body)


@router.get("/datasets/{dataset_id}/gallery")
def get_gallery(
    request: Request,
    dataset_id: str,
    view: str = "images",
    record_id: str | None = None,
    write: int | None = None,
    revision: int | None = None,
    blank: bool = False,
):
    """record_id: one record's results (a run's or a person's fix's), in the view run. write,
    revision or blank: the plan the images are judged by (a draft write, a version, a plan not
    begun), else the plan now (the draft, else the latest version; definition 36.1, 49.1)."""
    no_worker(request)
    db = db_of(request)
    plan = plan_of(db, dataset_id, revision, write, blank)
    return gallery(db, dataset_id, view, plan, record_id)


@router.get("/datasets/{dataset_id}/progress")
def get_progress(request: Request, dataset_id: str):
    no_worker(request)
    return progress(db_of(request), dataset_id)


@router.get("/datasets/{dataset_id}/label-colors")
def get_label_colors(
    request: Request,
    dataset_id: str,
    write: int | None = None,
    revision: int | None = None,
    blank: bool = False,
):
    """Every label's color, what is drawn takes; with a plan (a draft write, a version or a
    blank one), its labels' only: what a screen judged by that plan draws (definition 37.3). A
    label keeps its color in every plan."""
    no_worker(request)
    db = db_of(request)
    if write is None and revision is None and not blank:
        return {"colors": dataset_colors(db, dataset_id)}
    plan = plan_of(db, dataset_id, revision, write, blank)
    names = [d["name"] for d in plan.get("label_definitions", [])]
    found = dataset_colors(db, dataset_id, drawn=names)
    return {"colors": {name: found[name] for name in names}}


@router.put("/datasets/{dataset_id}/label-colors")
def put_label_colors(request: Request, dataset_id: str, body: ColorsInput):
    no_worker(request)
    return set_colors(db_of(request), dataset_id, body)


@router.post("/datasets/{dataset_id}/label-colors/reset")
def post_reset_colors(request: Request, dataset_id: str):
    no_worker(request)
    return reset_colors(db_of(request), dataset_id)


@router.get("/datasets/{dataset_id}/images/{image_id}/results")
def image_results(request: Request, dataset_id: str, image_id: str):
    """Every record's result of one image of the dataset (a run's or a person's fix's), the
    newest record first."""
    no_worker(request)
    db = db_of(request)
    rows = [
        r
        for r in reversed(dataset_results(db, dataset_id))
        if r["image_id"] == image_id
    ]
    # Which one is the image's annotation now and whether training uses it, from its state
    # (S1; user 2026-10-13: in the loupe, each record is looked at on the image first, then
    # chosen; the one in use says so).
    check_in_dataset(db, dataset_id, image_id)
    _, states = image_states(db, dataset_id, *latest_basis(db, dataset_id))
    state = states[image_id]
    now = state["now"]["result_id"] if state["now"] else None
    latest = latest_row(db, dataset_id)
    name = names_now(db, dataset_id)
    return {
        "results": [
            {
                **result_ref(db, r, name),
                "now": r["id"] == now,
                "used": r["id"] == now and state["used"] == "result",
                # Why training cannot use it, if it cannot (Sol 2026-10-13: "an earlier
                # requirement or failed" named two reasons for one record).
                "cannot": None
                if r["status"] in SUCCESS
                and latest
                and of_requirement(r, latest["requirement_key"])
                else "failed"
                if r["status"] not in SUCCESS
                else "draft"
                if not of_version(r)
                else "requirement",
            }
            for r in rows
        ]
    }

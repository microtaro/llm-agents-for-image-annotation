"""The /v1 entry points of runs, results, views and settings (step 2 design 5).

A run's worker is told apart by the X-Annotation-Run-Id / X-Annotation-Result-Id headers the
server gave its CLI: it may read its task, write and view its own result and view its target
image, nothing else.
"""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from . import images, label_colors, run_logs, run_queries, settings
from .annotation_sets import apply_batch
from .codex_execution import execution_models, worker_prompt
from .decisions import by_of
from .errors import ApiError
from .run_schemas import RunInput
from .shapes import Batch, ViewRequest
from .views import (
    around,
    create_view,
    render_view,
    sized_for_ai,
    view_response,
    view_side,
)

router = APIRouter(prefix="/v1")


def db_of(request: Request):
    return request.app.state.db


def runs_of(request: Request):
    return request.app.state.runs


def worker(request: Request):
    run_id = request.headers.get("x-annotation-run-id")
    return (run_id, request.headers.get("x-annotation-result-id")) if run_id else None


def no_worker(request: Request):
    if worker(request):
        raise ApiError(403, "run_scope", "A run's worker cannot use this route")


def own_result(request: Request, result_id, *, write):
    """The worker's (run ID, result ID) for its own result; None for other readers."""
    caller = worker(request)
    if caller is None:
        if write:
            raise ApiError(
                403, "run_scope", "Only the run's worker writes into a result"
            )
        return None
    if caller[1] != result_id:
        raise ApiError(403, "run_scope", "Only your own result is allowed")
    runs_of(request).check_worker(*caller, write=write)
    return caller


def worker_size(request: Request, caller, body: ViewRequest):
    """Inside a run the image size setting is the default and the most a view gets; outside
    one, what every AI takes in as it is (views.sized_for_ai)."""
    if caller is None:
        return sized_for_ai(body, view_side(db_of(request)))
    return sized_for_ai(
        body,
        runs_of(request).execution(caller[0]).run["settings"]["worker_view_max_side"],
    )


# ---------- runs ----------


@router.get("/run-models")
async def run_models(request: Request):
    no_worker(request)
    return await run_in_threadpool(execution_models)


@router.put("/datasets/{dataset_id}/runs/{run_id}", status_code=201)
async def start_run(
    request: Request,
    dataset_id: str,
    run_id: UUID,
    body: RunInput,
):
    no_worker(request)
    state, _ = await runs_of(request).start(
        dataset_id, str(run_id), body, by_of(request)
    )
    return state


@router.get("/datasets/{dataset_id}/runs")
def list_runs_route(request: Request, dataset_id: str):
    no_worker(request)
    return run_queries.list_runs(db_of(request), dataset_id, runs_of(request).version)


@router.get("/records/{record_id}")
def get_record_route(request: Request, record_id: str):
    """A record: a run, or a person's fix (definition 21.4)."""
    no_worker(request)
    return run_queries.get_record(db_of(request), record_id, runs_of(request).version)


@router.get("/runs/{run_id}")
def get_run_route(request: Request, run_id: str):
    no_worker(request)
    return run_queries.get_run(db_of(request), run_id, runs_of(request).version)


@router.post("/runs/{run_id}/stop")
def stop_run(request: Request, run_id: str):
    no_worker(request)
    return runs_of(request).request_stop(run_id, by_of(request))


@router.get("/runs/{run_id}/wait")
async def wait_run(
    request: Request,
    run_id: str,
    after_version: int | None = Query(None, ge=0),
    timeout: int = Query(20, ge=0, le=25),
):
    """Return when the run's status or an image's result changes, not on every log line, so
    a polling agent spends about one call per finished image."""
    no_worker(request)
    db, manager = db_of(request), runs_of(request)

    def digest():
        # Only the states, at every wake (review 2026-10-07: every result's columns and
        # settings were read to take their states).
        return run_queries.run_row(db, run_id)["status"], tuple(
            r["status"] for r in run_queries.record_results(db, run_id)
        )

    state = run_queries.get_run(db, run_id, manager.version)
    if after_version is None or not timeout or not state["going"]:
        return state
    seen = digest()
    loop = asyncio.get_running_loop()
    deadline, version = loop.time() + timeout, after_version
    while (remaining := deadline - loop.time()) > 0:
        version = await manager.wait_change(version, remaining)
        if digest() != seen:
            break
    return run_queries.get_run(db, run_id, manager.version)


@router.get("/runs/{run_id}/results")
def run_results(request: Request, run_id: str):
    no_worker(request)
    return run_queries.list_results(db_of(request), run_id)


@router.get("/runs/{run_id}/logs")
def run_log_page(
    request: Request,
    run_id: str,
    after: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
):
    no_worker(request)
    return run_logs.page(db_of(request), run_id, after, limit)


# ---------- results ----------


@router.get("/results/{result_id}")
def get_result_route(
    request: Request, result_id: str, revision: int | None = Query(None, ge=0)
):
    own_result(request, result_id, write=False)
    return run_queries.get_result(db_of(request), result_id, revision)


@router.get("/results/{result_id}/task")
def result_task(request: Request, result_id: str):
    caller = own_result(request, result_id, write=False)
    if caller is None:
        raise ApiError(403, "run_scope", "Only the run's worker reads its task")
    return runs_of(request).image(*caller).task_info


@router.post("/results/{result_id}/references/{index}/views")
def reference_view(request: Request, result_id: str, index: int, body: ViewRequest):
    """One reference of the worker's task: its set at the revision the plan points at, drawn;
    without a crop, around its objects (the margin every crop gets)."""
    caller = own_result(request, result_id, write=False)
    if caller is None:
        raise ApiError(403, "run_scope", "Only the run's worker reads its references")
    manager = runs_of(request).execution(caller[0])
    found = [
        r for r in manager.image(caller[1]).task_info["refs"] if r["index"] == index
    ]
    if not found:
        raise ApiError(404, "not_found", "Reference is not in your task")
    reference = found[0]
    db = db_of(request)
    if body.crop_xywh is None and reference["annotations"]:
        image = images.image_info(db, reference["image_id"])
        body = body.model_copy(
            update={
                "crop_xywh": around(
                    [a["geometry"] for a in reference["annotations"]],
                    image["width"],
                    image["height"],
                ),
                # Original pixels, whatever view the worker named.
                "coordinate_view_id": None,
            }
        )
    data, frame = create_view(
        db,
        reference["image_id"],
        worker_size(request, caller, body).model_copy(
            update={"overlay": True, "revision": reference["revision"]}
        ),
        set_id=reference["set_id"],
        run_id=caller[0],
        result_id=result_id,
        colors=manager.run["settings"]["label_colors"],
        # Its objects as the plan names them, the names its worker reads (references.resolved).
        names={a["id"]: a["label"] for a in reference["annotations"]},
    )
    return view_response(data, frame)


@router.post("/results/{result_id}/annotations")
def write_result(request: Request, result_id: str, body: Batch):
    caller = own_result(request, result_id, write=True)
    row = run_queries.result_row(db_of(request), result_id)
    manager = runs_of(request).execution(caller[0])
    return apply_batch(
        db_of(request),
        row["set_id"],
        body,
        manager.image(caller[1]).task_info["label_definitions"],
    )


@router.post("/results/{result_id}/views")
def result_view(request: Request, result_id: str, body: ViewRequest):
    caller = own_result(request, result_id, write=False)
    db = db_of(request)
    row = run_queries.result_row(db, result_id)
    data, frame = create_view(
        db,
        row["image_id"],
        worker_size(request, caller, body),
        set_id=row["set_id"],
        run_id=row["run_id"] if caller else None,
        result_id=result_id,
        colors=label_colors.of_result(db, row),
    )
    return view_response(data, frame)


# ---------- images, views and masks ----------


@router.post("/images/{image_id}/views")
def image_view(request: Request, image_id: str, body: ViewRequest):
    caller = worker(request)
    manager = runs_of(request)
    if caller:
        manager.check_worker(*caller, write=False)
        if image_id != manager.image(*caller).task_info["image_id"]:
            raise ApiError(403, "run_scope", "Image is outside the target")
    data, frame = create_view(
        db_of(request),
        image_id,
        worker_size(request, caller, body).model_copy(
            update={"overlay": False, "annotation_ids": None}
        ),
        run_id=caller[0] if caller else None,
        result_id=caller[1] if caller else None,
    )
    return view_response(data, frame)


@router.get("/views/{view_id}/image")
def view_image(request: Request, view_id: str):
    no_worker(request)
    return view_response(*render_view(db_of(request), view_id))


@router.get("/masks/{sha256}")
def mask(request: Request, sha256: str):
    no_worker(request)
    if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
        raise ApiError(404, "not_found", "Mask does not exist")
    try:
        data = db_of(request).files.read("masks", sha256)
    except FileNotFoundError as exc:
        raise ApiError(404, "not_found", "Mask does not exist") from exc
    return Response(data, media_type="image/png")


# ---------- settings ----------


@router.get("/settings")
def get_settings(request: Request):
    no_worker(request)
    return _settings_view(settings.read_settings(db_of(request)))


@router.get("/storage")
def get_storage(request: Request):
    """The database's and the files' size, for the settings (user 2026-10-28)."""
    no_worker(request)
    return db_of(request).storage()


@router.put("/settings")
def put_settings(request: Request, body: settings.SettingsInput):
    no_worker(request)
    return _settings_view(settings.write_settings(db_of(request), body))


def _settings_view(current):
    """The settings and what the screen shows with them: the worker prompt, each number's range,
    the groups they are shown in and this machine's facts (the software's version, user
    2026-10-29; the memory free, 2026-10-30)."""
    return {
        **current,
        "worker_prompt": worker_prompt(current),
        "ranges": settings.ranges(),
        "groups": settings.GROUPS,
        "machine": settings.machine(),
    }

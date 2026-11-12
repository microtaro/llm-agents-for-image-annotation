"""The /v1 entry points of drafts and read-only SQL (docs/2026-10-05-app-step4-design.md 3-4)."""

import json
from typing import Any

from fastapi import APIRouter, Request

from . import drafts
from .actors import who_of
from .draft_diff import draft_changes, payload_diff, plan_changes
from .errors import Model
from .instructions import latest_revision, version_payload
from .references import resolved
from .run_routes import db_of, no_worker

router = APIRouter(prefix="/v1")
INSTRUCTION = "/datasets/{dataset_id}/drafts/instruction"


@router.get("/datasets/{dataset_id}/drafts")
def list_drafts_route(request: Request, dataset_id: str):
    no_worker(request)
    return drafts.list_drafts(db_of(request), dataset_id)


@router.put(INSTRUCTION)
def write_instruction_draft(
    request: Request,
    dataset_id: str,
    body: drafts.InstructionDraft,
):
    no_worker(request)
    return drafts.write_plan_draft(
        db_of(request),
        dataset_id,
        "instruction",
        "",
        body,
        who_of(request),
        job_id=request.headers.get("x-annotation-job"),
    )


@router.get(INSTRUCTION)
def read_instruction_draft(request: Request, dataset_id: str):
    no_worker(request)
    return drafts.read_plan_draft(db_of(request), dataset_id)


@router.get(INSTRUCTION + "/writes/{write_id}")
def read_draft_write(request: Request, dataset_id: str, write_id: int):
    """One write of the plan's draft as it was written (a decision holds it by value; its plan
    is shown from it, not from the draft now: Sol 2026-10-17)."""
    no_worker(request)
    db = db_of(request)
    row = drafts.write_row(db, dataset_id, write_id)
    if row is None:
        from .errors import not_found

        raise not_found("Draft write")
    return {
        "dataset_id": dataset_id,
        "write_id": row["id"],
        "written_by": row["written_by"],
        "updated_at": row["written_at"],
        **resolved(db_of(request), json.loads(row["payload_json"])),
    }


@router.get(INSTRUCTION + "/diff")
def instruction_draft_diff(request: Request, dataset_id: str):
    """What the draft changed since the latest version (step 19 design 4)."""
    no_worker(request)
    return draft_changes(db_of(request), dataset_id)


class CompareInput(Model):
    """Two contents of the instruction (text, label_definitions, references); old may be
    null (nothing before)."""

    old: dict[str, Any] | None = None
    new: dict[str, Any]


@router.post(INSTRUCTION + "/compare")
def compare_instruction_contents(request: Request, dataset_id: str, body: CompareInput):
    """How one content differs from another, e.g. a draft the AI wrote from the draft before
    it (step 19: the change of one answer, not all since the version)."""
    no_worker(request)
    return payload_diff(body.old, body.new)


@router.delete(INSTRUCTION)
def delete_instruction_draft(request: Request, dataset_id: str):
    no_worker(request)
    return drafts.delete_plan_draft(db_of(request), dataset_id)


@router.get("/datasets/{dataset_id}/plan-history")
def plan_history_route(request: Request, dataset_id: str):
    """The plan's versions and the draft's writes with their requests (types design 20.3)."""
    return drafts.plan_history(db_of(request), dataset_id)


class FromVersionInput(Model):
    revision: int


@router.post(INSTRUCTION + "/from-version")
def draft_from_version(request: Request, dataset_id: str, body: FromVersionInput):
    """Back to a version's plan: the draft written with it (types design 20.2)."""
    no_worker(request)
    return drafts.from_version(
        db_of(request), dataset_id, str(body.revision), who_of(request)
    )


@router.get("/runs/{run_id}/plan-now")
def run_plan_now(request: Request, run_id: str):
    """A record's way (plan version, model, effort) and what the plan says now differently
    from its version (definition 11.10: looking at results to decide what next)."""
    from .run_queries import run_row

    db = db_of(request)
    run = run_row(db, run_id)
    settings = json.loads(run["settings_json"])
    version = version_payload(db, run["dataset_id"], run["instruction_revision"])
    now_ = drafts.plan_now(db, run["dataset_id"])
    return {
        "revision": run["instruction_revision"],
        "model": settings.get("model"),
        "effort": settings.get("effort"),
        "now": {
            "draft": drafts.draft_write_id(db, run["dataset_id"]) is not None,
            "revision": latest_revision(db, run["dataset_id"]),
        },
        "changes": plan_changes(version, now_) if version and now_ else None,
    }

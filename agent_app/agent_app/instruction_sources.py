"""Starting an instruction from an earlier dataset's, and what a worker would receive (step 14
design 5-6). User 2026-10-05: once data piles up, starting from a similar past instruction and
rewriting it for the new set becomes the usual way; the screen and what the worker gets must
come from the same thing.
"""

import json

from fastapi import APIRouter, Query, Request
from pydantic import Field

from . import settings as app_settings
from .actors import who_of
from .codex_execution import worker_prompt
from .datasets import dataset_row, image_ids
from .drafts import CONTENT, plan_draft, start_plan
from .errors import ApiError, Model, not_found
from .instructions import (
    check_definitions,
    latest_row,
    latest_rows,
    requirement_key,
    version_row,
)
from .label_colors import dataset_colors
from .run_queries import task_from
from .usage import empty, lineage, version_usage

router = APIRouter(prefix="/v1")


def sources(db, query=""):
    """The latest instruction version of every dataset, newest first, with what it asks and
    how it was used, its own and that of the versions made from it (S2, definition 15.2; 12.3:
    each place to start from with how it was used)."""
    words = [w for w in query.lower().split() if w]
    found = []
    uses = {}
    for row in reversed(latest_rows(db)):
        dataset = dataset_row(db, row["dataset_id"])
        payload = json.loads(row["payload_json"])
        labels = [
            {
                "name": d["name"],
                "shape": d["shape"],
                "parent": d.get("parent"),
                "attributes": [a["name"] for a in d.get("attributes", [])],
            }
            for d in payload["label_definitions"]
        ]
        text = " ".join(
            [dataset["name"], dataset["purpose"], *(lab["name"] for lab in labels)]
        ).lower()
        if not all(w in text for w in words):
            continue
        if row["dataset_id"] not in uses:
            uses[row["dataset_id"]] = version_usage(db, row["dataset_id"])
        line = lineage(db, row["dataset_id"], row["revision"], uses)
        found.append(
            {
                "dataset_id": row["dataset_id"],
                "name": dataset["name"],
                "purpose": dataset["purpose"],
                "revision": row["revision"],
                "created_at": row["created_at"],
                "labels": labels,
                "references": len(payload.get("references", [])),
                "usage": uses[row["dataset_id"]].get(row["revision"]) or empty(),
                "derived_total": line["derived_total"],
            }
        )
    return {"sources": found}


class FromInput(Model):
    dataset_id: str = Field(
        description="The dataset whose instruction version to copy."
    )
    revision: int | None = Field(None, description="Null copies the latest version.")


def instruction_from(db, dataset_id, body: FromInput, actor):
    """Copy another dataset's instruction (text and label definitions) into this dataset's
    instruction draft; references point at other images and are not copied. Refused over an
    existing draft."""
    dataset_row(db, dataset_id)
    if body.dataset_id == dataset_id:
        raise ApiError(422, "invalid_input", "Choose another dataset")
    row = (
        version_row(db, body.dataset_id, body.revision)
        if body.revision
        else latest_row(db, body.dataset_id)
    )
    if row is None:
        raise not_found("Instruction version")
    check_definitions(json.loads(row["payload_json"])["label_definitions"])
    with db.transaction():
        if plan_draft(db, dataset_id) is not None:
            raise ApiError(
                409,
                "draft_exists",
                "The instruction draft already has changes; save or delete it first",
            )
        # A write like any (a decision to run points at one), started from that version
        # (definition 15.1, 16.2).
        start_plan(
            db,
            dataset_id,
            {
                "kind": "other",
                "dataset_id": body.dataset_id,
                "revision": row["revision"],
            },
            actor,
        )
    return {"copied_from": {"dataset_id": body.dataset_id, "revision": row["revision"]}}


def worker_view(db, dataset_id, draft):
    """The worker prompt and the task for the dataset's first image, from the latest version
    or the draft: built by the same functions a run uses."""
    dataset_row(db, dataset_id)
    row = plan_draft(db, dataset_id) if draft else latest_row(db, dataset_id)
    if row is None:
        raise not_found("Instruction draft" if draft else "Instruction version")
    content = json.loads(row["payload_json"])
    instruction = {k: content[k] for k in CONTENT}
    settings = app_settings.read_settings(db)
    chosen = dataset_colors(db, dataset_id)
    settings["label_colors"] = {
        d["name"]: chosen.get(d["name"]) for d in instruction["label_definitions"]
    }
    first = next(iter(image_ids(db, dataset_id)), None)
    return {
        "worker_prompt": worker_prompt(settings),
        "task": task_from(db, instruction, settings, first),
        "requirement_key": requirement_key(instruction["label_definitions"]),
    }


@router.get("/instruction-sources")
def get_sources(request: Request, q: str = ""):
    return sources(request.app.state.db, q)


@router.post("/datasets/{dataset_id}/instruction-from", status_code=201)
def post_from(
    request: Request,
    dataset_id: str,
    body: FromInput,
):
    return instruction_from(request.app.state.db, dataset_id, body, who_of(request))


@router.get("/datasets/{dataset_id}/worker-view")
def get_worker_view(request: Request, dataset_id: str, draft: bool = Query(False)):
    return worker_view(request.app.state.db, dataset_id, draft)

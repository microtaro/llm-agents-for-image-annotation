"""The plan's references (definition 38.1): for an image, a result of it chosen as the plan's
example, an AI's (a sample's or a run's) or a person's fix, at its set's revision. Only the workers
and people's fixes write annotations; the steward and a person choose which result is an example,
in the plan's draft (no decision). A reference image's annotation is that result, so runs and
samples leave the image out (run_inputs.start_targets), and a worker never gets the reference of
the image it annotates (run_queries.task_from).
"""

from fastapi import APIRouter, Request
from pydantic import Field

from .actors import who_of
from .annotation_sets import set_row, set_state
from .datasets import check_in_dataset
from .errors import ApiError, Model, invalid, not_found
from .instructions import requirement_key
from .label_ids import names_in
from .run_queries import SUCCESS, of_requirement, result_row

router = APIRouter(prefix="/v1")
MAX_REFERENCES = 10


class ReferenceInput(Model):
    result_id: str = Field(
        description="The result taken as the image's example: an AI's (a sample's or a run's)"
        " or a person's fix of this image, of the plan's labels now."
    )
    note: str = Field("", max_length=1000, description="What this example shows.")


def resolved(db, payload):
    """A plan's content with each reference's objects read from its result's set at the revision
    it points at, named as the plan names its labels (a result keeps the names of the version
    that made it: label_ids.names_in)."""
    if not payload or not payload.get("references"):
        return payload
    definitions = payload.get("label_definitions") or []
    references = []
    for p in payload["references"]:
        row = result_row(db, p["result_id"])
        name = names_in(db, row["dataset_id"], definitions)
        annotations = set_state(db, p["set_id"], p["revision"])["annotations"]
        references.append(
            {
                **p,
                "annotations": [
                    {**a, "label": name(row["instruction_revision"], a["label"])}
                    for a in annotations
                ],
            }
        )
    return {**payload, "references": references}


def pointer(plan, image_id):
    return next(
        (p for p in (plan or {}).get("references") or [] if p["image_id"] == image_id),
        None,
    )


def get_reference(db, dataset_id, image_id):
    """The plan's reference of the image (the plan now), with its objects."""
    from .drafts import plan_now

    plan = plan_now(db, dataset_id)
    found = pointer(plan, image_id)
    if found is None:
        raise not_found("Reference")
    return resolved(db, {**plan, "references": [found]})["references"][0]


def reference_set(db, dataset_id, image_id, result_id, note, actor, job_id=None):
    """The image's reference made the result (one per image: an earlier one is replaced). The
    result is of this image in this dataset, annotated by the plan's labels now."""
    from .drafts import plan_now, write_plan

    check_in_dataset(db, dataset_id, image_id)
    with db.transaction():
        plan = plan_now(db, dataset_id)
        if plan is None:
            raise ApiError(
                422, "instruction_required", "Write the plan's draft before this"
            )
        row = result_row(db, result_id)
        if row["dataset_id"] != dataset_id or row["image_id"] != image_id:
            raise invalid("The result is not of this image in this dataset")
        if row["status"] not in SUCCESS:
            raise invalid("The result has no annotation to take as an example")
        if not of_requirement(row, requirement_key(plan["label_definitions"])):
            raise ApiError(
                422,
                "requirement_mismatch",
                "The labels changed since that result: take a result of the plan now",
            )
        entries = [p for p in plan.get("references") or [] if p["image_id"] != image_id]
        if len(entries) >= MAX_REFERENCES:
            raise invalid(f"A plan has at most {MAX_REFERENCES} references")
        entry = {
            "image_id": image_id,
            "result_id": result_id,
            "set_id": row["set_id"],
            "revision": set_row(db, row["set_id"])["revision"],
            "note": note,
        }
        write_plan(
            db,
            dataset_id,
            lambda p: {**p, "references": [*entries, entry]},
            actor,
            job_id,
        )
    return entry


def reference_unset(db, dataset_id, image_id, actor, job_id=None):
    """The image's reference taken out of the plan (its result stays, a record)."""
    from .drafts import plan_now, write_plan

    with db.transaction():
        if pointer(plan_now(db, dataset_id), image_id) is None:
            raise not_found("Reference")
        write_plan(
            db,
            dataset_id,
            lambda p: {
                **p,
                "references": [x for x in p["references"] if x["image_id"] != image_id],
            },
            actor,
            job_id,
        )
    return {"deleted": True}


@router.get("/datasets/{dataset_id}/images/{image_id}/reference")
def get_reference_route(request: Request, dataset_id: str, image_id: str):
    return get_reference(request.app.state.db, dataset_id, image_id)


@router.put("/datasets/{dataset_id}/images/{image_id}/reference")
def set_reference_route(
    request: Request, dataset_id: str, image_id: str, body: ReferenceInput
):
    return reference_set(
        request.app.state.db,
        dataset_id,
        image_id,
        body.result_id,
        body.note,
        who_of(request),
        job_id=request.headers.get("x-annotation-job"),
    )


@router.delete("/datasets/{dataset_id}/images/{image_id}/reference")
def delete_reference_route(request: Request, dataset_id: str, image_id: str):
    return reference_unset(
        request.app.state.db,
        dataset_id,
        image_id,
        who_of(request),
        job_id=request.headers.get("x-annotation-job"),
    )

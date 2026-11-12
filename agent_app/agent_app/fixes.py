"""A person's fix of a result, and the result a person chose for training (types design 7.1,
7.2). A fix is its own thing, one more annotation record of the image (definition 21.4): who
fixed which result when, its record's number, and its result with the fixed annotations; made,
the rule uses it for training. A choice holds when a newer result is made (definition 10: the
newer one is said); another choice or "back to the rule" changes it. Every choice is a decision
(decisions.record) whose rows of what training uses are added, never written over (19, 21.3).

The fix is written in a draft on the server first (DESIGN.md 4: a draft and a save), as the
instruction's draft is.
"""

import json
from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import Field

from . import decisions
from .actors import who_of
from .adoption import record_use
from .annotation_sets import fill, new_set
from .datasets import check_in_dataset, dataset_row
from .db import encoded, new_id, now
from .decisions import by_of
from .errors import ApiError, Model, invalid, not_found
from .image_state import image_states, use_now
from .instructions import latest_basis, requirement
from .label_rules import check_creates, fitting
from .run_queries import (
    SUCCESS,
    insert_result,
    next_number,
    of_requirement,
    record_results,
    result_row,
    run_row,
)
from .shapes import Create, Labeled

router = APIRouter(prefix="/v1")


class FixAnnotation(Labeled):
    number: int | None = Field(
        None,
        ge=1,
        description="The object's number to keep (from the result it came from).",
    )
    ref: str | None = Field(
        None,
        min_length=1,
        max_length=64,
        description="Name of this annotation in the list, so another one can give it as parent.",
    )


class FixInput(Model):
    from_result_id: str = Field(description="The result the fix started from.")
    annotations: Annotated[list[FixAnnotation], Field(max_length=1000)]


class FixDraft(FixInput):
    if_updated_at: str | None = Field(
        None, description="The updated_at you read; another write since then is a 409."
    )


class PickInput(Model):
    result_id: str


def to_creates(annotations):
    """The annotations as create operations, each ref naming one and each parent another's
    ref (the label definitions are checked where they are written, annotation_sets.fill)."""
    labels = {a.ref: a.label for a in annotations if a.ref}
    if len(labels) != len([a for a in annotations if a.ref]):
        raise invalid("Each ref names one annotation")
    creates = []
    for a in annotations:
        if a.parent is not None and a.parent not in labels:
            raise invalid(
                "parent must be the ref of another annotation", parent=a.parent
            )
        creates.append(
            Create.model_validate({**a.model_dump(exclude={"number"}), "op": "create"})
        )
    return creates


def fixed_creates(definitions, annotations):
    """What a fix saves of its annotations (to_creates): only the values the plan reads. A fix
    may start from a result of another version, with an attribute since taken off or changed
    (definition 85.17; label_rules.fitting, as copying does)."""
    by_name = {d["name"]: d for d in definitions}
    return [
        c.model_copy(
            update={"attributes": fitting(by_name.get(c.label), c.attributes) or None}
        )
        for c in to_creates(annotations)
    ]


def _source(db, dataset_id, image_id, result_id, key):
    """The result a fix starts from or a choice names: of this image, this dataset and the
    current requirement, and successful (a run's or a person's fix's)."""
    row = result_row(db, result_id)
    if row["image_id"] != image_id or row["dataset_id"] != dataset_id:
        raise invalid("The result is of another image")
    if not of_requirement(row, key):
        raise ApiError(
            409, "requirement_mismatch", "The result was made for another requirement"
        )
    if row["status"] not in SUCCESS:
        raise ApiError(409, "result_not_succeeded", "Only a successful result")
    return row


def create_fix(db, dataset_id, image_id, body: FixInput, who):
    """A person's fix (definition 21.4): the fix, its result with the fixed annotations, and the
    fix made entering what training uses (the rule uses a person's fix; not a decision). Returns
    the result that was the image's annotation before (its undo chooses it again, definition
    19.2: a fix starts from a success, so there always is one)."""
    dataset_row(db, dataset_id)
    check_in_dataset(db, dataset_id, image_id)
    revision, key, definitions = requirement(db, dataset_id)
    _source(db, dataset_id, image_id, body.from_result_id, key)
    creates = fixed_creates(definitions, body.annotations)
    _, states = image_states(db, dataset_id, *latest_basis(db, dataset_id))
    before = states[image_id]["now"]["result_id"]
    fix_id, at = new_id("fix-"), now()
    with db.transaction():
        number = next_number(db, dataset_id)
        db.execute(
            "INSERT INTO fixes(id, dataset_id, image_id, from_result_id, requirement_key,"
            " instruction_revision, fixed_by, fixed_at, number) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                fix_id,
                dataset_id,
                image_id,
                body.from_result_id,
                key,
                revision,
                who,
                at,
                number,
            ),
        )
        set_id = new_set(
            db, image_id, after=result_row(db, body.from_result_id)["set_id"]
        )
        fill(db, set_id, creates, definitions, [a.number for a in body.annotations])
        result_id = insert_result(db, "fix", fix_id, image_id, set_id, 0, creates)
        record_use(db, dataset_id, image_id, "fix", result_id, fix_id=fix_id)
    return {
        "fix_id": fix_id,
        "number": number,
        "result_id": result_id,
        "before": before,
    }


def _chosen(db, dataset_id, image_id, result_id):
    """The result a person chooses: of this image, this dataset and the requirement now, and a
    success."""
    dataset_row(db, dataset_id)
    check_in_dataset(db, dataset_id, image_id)
    _, key, _ = requirement(db, dataset_id)
    _source(db, dataset_id, image_id, result_id, key)


def switch_to(db, dataset_id, image_id, result_id, by):
    """［この記録にする］ while annotating (user 2026-10-16: the record made the image's
    annotation; 2026-10-19: chosen by its button, a press only shows it): chosen, as for
    training, whether the image is used or not as it was; no record is made. Returns the one a
    person chose before (None: the rule's), to choose it again."""
    _chosen(db, dataset_id, image_id, result_id)
    before = use_now(db, dataset_id)[image_id]["pick"]
    content = {"op": "pick", "image_id": image_id, "result_id": result_id}
    with db.transaction():
        decision_id = decisions.record(db, dataset_id, "use", content, by)
        record_use(db, dataset_id, image_id, "pick", result_id, decision_id)
    return {"result_id": result_id, "before": before, "decision_id": decision_id}


def choose(db, dataset_id, image_id, result_id, by):
    """A result chosen for training: a left-out image is used again (the button says "use for
    training")."""
    _chosen(db, dataset_id, image_id, result_id)
    excluded = use_now(db, dataset_id)[image_id]["excluded"]
    content = {"op": "pick", "image_id": image_id, "result_id": result_id}
    with db.transaction():
        decision_id = decisions.record(db, dataset_id, "use", content, by)
        if excluded:
            record_use(db, dataset_id, image_id, "in", decision_id=decision_id)
        record_use(db, dataset_id, image_id, "pick", result_id, decision_id)
    return {"image_id": image_id, "result_id": result_id, "decision_id": decision_id}


def back_to_rule(db, dataset_id, by, image_ids=None):
    """The images (all: none given) a person chose for go back to the rule's result."""
    dataset_row(db, dataset_id)
    chosen = [
        i
        for i, v in use_now(db, dataset_id).items()
        if v["pick"] and (image_ids is None or i in image_ids)
    ]
    with db.transaction():
        decision_id = decisions.record(
            db, dataset_id, "use", {"op": "rule", "image_ids": chosen}, by
        )
        for image_id in chosen:
            record_use(db, dataset_id, image_id, "rule", decision_id=decision_id)
    return {"dataset_id": dataset_id, "decision_id": decision_id}


def _record_of_now(db, run_id):
    """A record of the plan's requirement now (a version's, not a draft's trial), whose images'
    use a person decides."""
    run = run_row(db, run_id)
    _, key, _ = requirement(db, run["dataset_id"])
    if not of_requirement(run, key):
        raise ApiError(
            409, "requirement_mismatch", "The run was made for another requirement"
        )
    return run


def use_run(db, run_id, by):
    """［記録 n を使う］: the run's images use its results for training (17.2: only those
    images; the others stay as they are), and are used again if they were left out."""
    dataset_id = _record_of_now(db, run_id)["dataset_id"]
    rows = [r for r in record_results(db, run_id) if r["status"] in SUCCESS]
    decided = use_now(db, dataset_id)
    with db.transaction():
        decision_id = decisions.record(
            db, dataset_id, "use", {"op": "use_run", "run_id": run_id}, by
        )
        for r in rows:
            if decided[r["image_id"]]["excluded"]:
                record_use(db, dataset_id, r["image_id"], "in", decision_id=decision_id)
            record_use(db, dataset_id, r["image_id"], "pick", r["id"], decision_id)
    return {"run_id": run_id, "images": len(rows)}


# ---------- the draft of a fix ----------


def fix_draft(db, dataset_id, image_id):
    """A person's fix of the image being made, as stored, None without one: the one place it
    is read (fact inventory 6; the plan's draft is drafts.plan_draft)."""
    return db.one(
        "SELECT * FROM drafts WHERE dataset_id=? AND kind='fix' AND image_id=?",
        (dataset_id, image_id),
    )


def fix_drafts(db, dataset_id):
    """Every fix of the dataset being made, as stored."""
    return db.execute(
        "SELECT * FROM drafts WHERE dataset_id=? AND kind='fix'", (dataset_id,)
    )


def relabel_fix_drafts(db, dataset_id, names, keys, results):
    """The fixes being made take a label's change (definition 26.1 a rename, 79.3 a change):
    their objects' labels by names (old -> new), the result each is made from by results (old
    id -> new id) and the requirement by keys (old -> new)."""
    for row in fix_drafts(db, dataset_id):
        payload = json.loads(row["payload_json"])
        for a in payload.get("annotations") or []:
            a["label"] = names.get(a.get("label"), a.get("label"))
        payload["from_result_id"] = results.get(
            payload["from_result_id"], payload["from_result_id"]
        )
        db.execute(
            "UPDATE drafts SET payload_json=?, requirement_key=? WHERE dataset_id=?"
            " AND kind='fix' AND image_id=?",
            (
                encoded(payload),
                keys.get(row["requirement_key"], row["requirement_key"]),
                dataset_id,
                row["image_id"],
            ),
        )


def _draft_out(row):
    return {
        "image_id": row["image_id"],
        "written_by": row["written_by"],
        "updated_at": row["updated_at"],
        **json.loads(row["payload_json"]),
    }


def write_fix_draft(db, dataset_id, image_id, body: FixDraft, actor):
    dataset_row(db, dataset_id)
    check_in_dataset(db, dataset_id, image_id)
    _, key, definitions = requirement(db, dataset_id)
    _source(db, dataset_id, image_id, body.from_result_id, key)
    # A draft is refused as its save would be.
    check_creates(definitions, fixed_creates(definitions, body.annotations))
    payload = body.model_dump(exclude={"if_updated_at"}, mode="json")
    with db.transaction():
        old = fix_draft(db, dataset_id, image_id)
        if body.if_updated_at is not None and (
            old is None or old["updated_at"] != body.if_updated_at
        ):
            raise ApiError(409, "draft_conflict", "The draft changed since you read it")
        db.execute(
            "INSERT INTO drafts(dataset_id,kind,image_id,requirement_key,payload_json,"
            "written_by,updated_at,created_at) VALUES(?,'fix',?,?,?,?,?,?)"
            " ON CONFLICT(dataset_id,kind,image_id) DO UPDATE SET"
            " requirement_key=excluded.requirement_key, payload_json=excluded.payload_json,"
            " written_by=excluded.written_by, updated_at=excluded.updated_at",
            (dataset_id, image_id, key, encoded(payload), actor, now(), now()),
        )
        return _draft_out(fix_draft(db, dataset_id, image_id))


def read_fix_draft(db, dataset_id, image_id):
    row = fix_draft(db, dataset_id, image_id)
    if row is None:
        raise not_found("Draft")
    return _draft_out(row)


def delete_fix_draft(db, dataset_id, image_id):
    """Fixing stopped: its draft goes; none is nothing to delete, not an error (user 2026-10-27:
    stopping a fix that changed nothing was a 404)."""
    with db.transaction():
        found = fix_draft(db, dataset_id, image_id) is not None
        db.execute(
            "DELETE FROM drafts WHERE dataset_id=? AND kind='fix' AND image_id=?",
            (dataset_id, image_id),
        )
    return {"deleted": found}


def save_fix_draft(db, dataset_id, image_id, actor):
    draft = read_fix_draft(db, dataset_id, image_id)
    body = FixInput.model_validate(
        {k: draft[k] for k in ("from_result_id", "annotations")}
    )
    made = create_fix(db, dataset_id, image_id, body, actor)
    delete_fix_draft(db, dataset_id, image_id)
    return made


# ---------- routes (a person's; a run's worker may use none of them) ----------


def _person(request):
    """A person's operation: neither a run's worker nor a worker of the talk (they ask the
    person to fix or choose; types design 7.1)."""
    from .run_routes import no_worker

    no_worker(request)
    if request.headers.get("x-annotation-agent"):
        raise ApiError(403, "agent_scope", "Only a person fixes or chooses a result")
    return request.app.state.db


IMAGE = "/datasets/{dataset_id}/images/{image_id}"


@router.post(IMAGE + "/fixes", status_code=201)
def fix_image_route(
    request: Request,
    dataset_id: str,
    image_id: str,
    body: FixInput,
):
    return create_fix(_person(request), dataset_id, image_id, body, who_of(request))


@router.get(IMAGE + "/drafts/fix")
def read_draft_route(request: Request, dataset_id: str, image_id: str):
    """The image's fix draft, or null without one: the loupe asks for every image it opens, so
    none is not an error (user 2026-10-27: a 404 in the console at every loupe)."""
    row = fix_draft(_person(request), dataset_id, image_id)
    return _draft_out(row) if row else None


@router.put(IMAGE + "/drafts/fix")
def write_draft_route(
    request: Request,
    dataset_id: str,
    image_id: str,
    body: FixDraft,
):
    return write_fix_draft(
        _person(request), dataset_id, image_id, body, who_of(request)
    )


@router.delete(IMAGE + "/drafts/fix")
def delete_draft_route(request: Request, dataset_id: str, image_id: str):
    return delete_fix_draft(_person(request), dataset_id, image_id)


@router.post(IMAGE + "/drafts/fix/save", status_code=201)
def save_draft_route(request: Request, dataset_id: str, image_id: str):
    return save_fix_draft(_person(request), dataset_id, image_id, who_of(request))


@router.post(IMAGE + "/switch")
def switch_route(
    request: Request,
    dataset_id: str,
    image_id: str,
    body: PickInput,
):
    """An earlier record made the image's annotation again (chosen; no record made)."""
    return switch_to(
        _person(request), dataset_id, image_id, body.result_id, by_of(request)
    )


@router.put(IMAGE + "/adoption")
def choose_route(
    request: Request,
    dataset_id: str,
    image_id: str,
    body: PickInput,
):
    return choose(
        _person(request), dataset_id, image_id, body.result_id, by_of(request)
    )


@router.delete(IMAGE + "/adoption")
def back_route(request: Request, dataset_id: str, image_id: str):
    return back_to_rule(_person(request), dataset_id, by_of(request), [image_id])


@router.post("/datasets/{dataset_id}/adoption/latest")
def all_latest_route(request: Request, dataset_id: str):
    """［すべて最新に］: every person's choice goes; the rule's newest result for each."""
    return back_to_rule(_person(request), dataset_id, by_of(request))


@router.post("/runs/{run_id}/use")
def use_run_route(request: Request, run_id: str):
    """［記録 n を使う］ (a worker's box of it is the tool mark, a run, not excluded)."""
    return use_run(_person(request), run_id, by_of(request))

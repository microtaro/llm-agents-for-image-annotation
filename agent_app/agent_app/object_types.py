"""The types of the things on the right (types design 2, 3): each with the fields a set of it is
asked by, read through the functions that read it today. A worker's answer may carry a "show"
(a type with an id or conditions); the server checks it here (the fields, the values, that it is
within the dataset) and counts it, and the screen shows that set on the right. A worker reads
the same types by the same conditions (the tool read, definition 51): what it can show, it can
read, and the facts of a type are read here once for both.

The ways of showing are the screen's, fixed per type; a worker never makes a screen.
"""

import json
from typing import Annotated, Literal, get_args, get_origin

from fastapi import APIRouter, Request
from pydantic import Field, ValidationError

from . import instructions
from .datasets import dataset_row, image_id_of
from .drafts import plan_draft, plan_of
from .errors import ApiError, Model, invalid, not_found
from .gallery import gallery
from .label_ids import names_now
from .label_library import list_labels
from .past_requirements import past_requirements
from .run_queries import (
    GOING,
    RESULTS_SQL,
    list_records,
    record_results,
    record_row,
    result_ref,
)
from .settings import GROUPS, explained
from .sheets import label_objects
from .training import described

router = APIRouter(prefix="/v1")
Ids = Annotated[list[str], Field(max_length=200)]


# ---------- the conditions of each type ----------


class ImageWhere(Model):
    name: str | None = Field(
        None, max_length=200, description="Part of the image's name."
    )
    ids: Ids | None = Field(None, description="Images by id or name.")
    # As the screen's filters: failed and interrupted (stopped by a cost cap or a person) apart
    # (Astra 2026-10-20: "no image failed" beside "the failed images: 1", an interrupted one).
    result: Literal["none", "ok", "failed", "interrupted", "human"] | None = None
    picked: bool | None = None
    newer: bool | None = None
    other: bool | None = Field(
        None,
        description="Its annotation now was made by other criteria than the plan's (what it"
        " leaves out) and no person checked it (definition 85.4, 85.16).",
    )
    unfilled: bool | None = Field(
        None,
        description="Its annotation now has an object with no value the plan can read of one"
        " of its label's attributes (definition 85.17: an attribute added keeps the boxes).",
    )
    excluded: bool | None = None
    run: str | None = Field(None, description="The images of this annotation record.")
    # The plan the images' states are judged by (definition 35.7): a draft write's or a
    # version's, else the plan now (the draft, else the latest version). An image has a result
    # when it has one of that plan's requirement; one of another requirement's is "stale".
    write: int | None = Field(
        None, description="Judge the images by this draft write's plan."
    )
    revision: int | None = Field(
        None, description="Judge the images by this version's plan."
    )
    # A plan not begun (definition 49.1): no image has its result; each is another plan's.
    blank: bool | None = Field(
        None,
        description="true: judge the images by a blank plan (one not begun yet): no image has"
        " its result, each result is another plan's.",
    )
    # What is shown on each (definition 36.2): the plan's result drawn, or the image alone.
    drawn: bool | None = Field(
        None, description="false: the images alone, no annotation drawn on them."
    )


class VersionWhere(Model):
    latest: bool | None = None
    revision: int | None = None
    # Other datasets' plans to start from (definition 51.2; the tool instruction_sources).
    others: bool | None = Field(
        None,
        description="true: the other datasets' latest versions and how each was used (at the"
        " library: every dataset's).",
    )
    query: str | None = Field(
        None, max_length=200, description="With others: words their plans are found by."
    )


class DraftWhere(Model):
    pass


class RunWhere(Model):
    ids: Ids | None = None
    state: Literal["going", "ended", "failed", "stopped"] | None = None
    trial: bool | None = None
    version: int | None = None
    model: str | None = None
    kind: Literal["run", "fix", "import", "relabel", "carry"] | None = None


class ResultWhere(Model):
    ids: Ids | None = None
    image: str | None = None
    run: str | None = None
    version: int | None = None
    by: Literal["ai", "human", "import"] | None = None
    adopted: bool | None = None


class ProposalWhere(Model):
    ids: Ids | None = None
    state: (
        Literal[
            "open",
            "decided",
            "all",
            "applied",
            "declined",
            "failed",
            "withdrawn",
        ]
        | None
    ) = None
    image: str | None = None
    agent: str | None = None
    step: str | None = None
    chat: int | None = None


class SnapshotWhere(Model):
    n: int | None = None


class DatasetWhere(Model):
    name: str | None = None


class RequirementWhere(Model):
    image: str | None = Field(
        None,
        max_length=200,
        description="The image the requirements are shown on; else the example image.",
    )


class LabelWhere(Model):
    name: str | None = Field(
        None, max_length=200, description="Part of the label's name or of an alias."
    )


class SettingsWhere(Model):
    group: Literal[(*(name for name, _ in GROUPS), "machine")] | None = Field(
        None,
        description="One group of the settings screen, or machine (this machine's facts).",
    )


# ---------- reading ----------


def _image_ids(db, dataset_id, names):
    """Images named by id or name, within the dataset (datasets.image_id_of: the AI never turns
    a name into an id; memory no-coordinate-math-for-ai). An unknown one is an error."""
    return [image_id_of(db, dataset_id, name) for name in names]


def _images(db, dataset_id, w: ImageWhere):
    plan = plan_of(db, dataset_id, w.revision, w.write, bool(w.blank))
    items = gallery(db, dataset_id, "production", plan)["items"]
    if w.ids is not None:
        wanted = set(_image_ids(db, dataset_id, w.ids))
        items = [i for i in items if i["image"]["id"] in wanted]
    if w.name:
        items = [i for i in items if w.name in i["image"]["name"]]
    if w.result is not None:

        def result_group(item):
            badge = item["badge"]
            if badge["kind"] == "result" or badge.get("succeeded"):
                return "human" if badge.get("by") == "human" else "ok"
            if badge["kind"] == "excluded":
                return "ok" if badge.get("ran") else "none"
            if badge["kind"] in ("failed", "interrupted"):
                return badge["kind"]
            return "none"

        items = [i for i in items if result_group(i) == w.result]
    for field in ("picked", "newer", "other", "unfilled"):
        value = getattr(w, field)
        if value is not None:
            items = [i for i in items if bool(i["badge"].get(field)) == value]
    if w.excluded is not None:
        items = [i for i in items if i["image"]["excluded"] == w.excluded]
    if w.run is not None:
        _run_in(db, dataset_id, w.run)
        of_run = {r["image_id"] for r in record_results(db, w.run)}
        items = [i for i in items if i["image"]["id"] in of_run]
    if w.drawn is False:
        items = [{**i, "annotations": []} for i in items]
    return items


def _run_in(db, dataset_id, record_id):
    """A record (a run or a person's fix) of this dataset."""
    if record_row(db, record_id)["dataset_id"] != dataset_id:
        raise not_found("Annotation record of this dataset")


def _versions(db, dataset_id, w: VersionWhere):
    if w.others or w.query or dataset_id is None:
        # Other datasets' latest versions (at the library, every dataset's), as instructions
        # are started from them (definition 51.2).
        from .instruction_sources import sources

        return [
            s
            for s in sources(db, w.query or "")["sources"]
            if s["dataset_id"] != dataset_id
        ]
    rows = [
        {**r, **_version_story(db, dataset_id, r["revision"])}
        for r in instructions.list_instructions(db, dataset_id)["instructions"]
    ]
    if w.latest:
        rows = rows[:1]
    if w.revision is not None:
        rows = [r for r in rows if r["revision"] == w.revision]
    return rows


def _version_story(db, dataset_id, revision):
    """How a version came about (user 2026-10-13: how versions relate was hard to see, and to
    reuse one the talk it came from is wanted): what changed from the version before, and the
    worker's talk of the box whose decision made it (none for a person's own press; 2026-10-30:
    it was looked for among the boxes that saved a version, which are no more, so it was never
    found)."""
    from .agent_chat import asked_between  # a version's talk is a worker's
    from .draft_diff import plan_changes
    from .proposals import box_of_decision

    # What it says differently from the version before, as a decision and a record say it
    # (2026-10-30: only its labels and text were said, so a version that took a reference was
    # "nothing changed").
    changes = (
        plan_changes(
            instructions.version_payload(db, dataset_id, revision - 1),
            instructions.version_payload(db, dataset_id, revision),
        )
        if revision > 1
        else None
    )

    def made_from(number):
        row = instructions.version_row(db, dataset_id, number)
        return box_of_decision(db, row["decision_id"]) if row else None

    saved = made_from(revision)
    # The person's words that led to it (user 2026-10-14: how it was asked for): the lines
    # of its talk after the version before was decided there, up to this box's request.
    asks = []
    if saved and saved["chat_id"] and saved["from_event_id"]:
        before = made_from(revision - 1)
        after = (
            int(before["from_event_id"])
            if before
            and before["chat_id"] == saved["chat_id"]
            and before["from_event_id"]
            else 0
        )
        asks = [
            {"id": r["id"], "text": r["text"], "at": r["created_at"]}
            for r in asked_between(
                db, saved["chat_id"], after, int(saved["from_event_id"])
            )
        ]
    return {
        "from_previous": changes,
        "talk": {
            "agent": saved["agent"],
            "chat_id": saved["chat_id"],
            "line": asks[0]["id"] if asks else None,
        }
        if saved and saved["chat_id"]
        else None,
        "asks": asks,
    }


def _drafts(db, dataset_id, w: DraftWhere):
    """The plan now (definition 51.2): its content, who decided each item and the next to
    ask, its writes with the request each answered, and when and by whom it was written."""
    from .drafts import plan_history
    from .plan_state import plan_state

    row = plan_draft(db, dataset_id)
    return [
        {
            **plan_state(db, dataset_id),
            "writes": plan_history(db, dataset_id)["writes"],
            "updated_at": row["updated_at"] if row else None,
            "written_by": row["written_by"] if row else None,
        }
    ]


def _runs(db, dataset_id, w: RunWhere):
    """The records: runs, a person's fixes, ones taken in and label changes (definition 21.4,
    60.11, 79), by number."""
    rows = list_records(db, dataset_id)["records"]
    if w.ids is not None:
        rows = [r for r in rows if r["id"] in w.ids]
    if w.state is not None:
        groups = {
            "going": GOING,
            "ended": ("succeeded",),
            "failed": ("failed", "interrupted"),
            "stopped": ("stopped",),
        }
        rows = [r for r in rows if r["status"] in groups[w.state]]
    if w.trial is not None:
        rows = [r for r in rows if r["trial"] == w.trial]
    if w.version is not None:
        rows = [r for r in rows if r["instruction_revision"] == w.version]
    if w.model is not None:
        rows = [r for r in rows if r["settings"].get("model") == w.model]
    if w.kind is not None:
        rows = [r for r in rows if r["kind"] == w.kind]
    return rows


def _results(db, dataset_id, w: ResultWhere):
    rows = db.execute(
        RESULTS_SQL + "WHERE r.dataset_id=? ORDER BY r.record_number DESC",
        (dataset_id,),
    )
    name = names_now(db, dataset_id)
    out = [result_ref(db, r, name) for r in rows]
    if w.ids is not None:
        out = [r for r in out if r["result_id"] in w.ids]
    if w.image is not None:
        image_id = _image_ids(db, dataset_id, [w.image])[0]
        out = [r for r in out if r["image_id"] == image_id]
    if w.run is not None:
        _run_in(db, dataset_id, w.run)
        out = [r for r in out if r["record_id"] == w.run]
    if w.version is not None:
        out = [r for r in out if r["instruction_revision"] == w.version]
    if w.by is not None:
        out = [r for r in out if r["by"] == w.by]
    if w.adopted is not None:
        used = {
            i["badge"].get("result_id")
            # What training uses: by the latest version (36.1).
            for i in gallery(
                db,
                dataset_id,
                "production",
                instructions.latest_payload(db, dataset_id),
            )["items"]
            if i["badge"]["kind"] == "result"
        }
        out = [r for r in out if (r["result_id"] in used) == w.adopted]
    return out


def _proposals(db, dataset_id, w: ProposalWhere):
    from .proposals import list_proposals

    rows = list_proposals(db, dataset_id)["proposals"]
    if w.ids is not None:
        rows = [p for p in rows if p["id"] in w.ids]
    state = w.state or "all"
    if state == "decided":
        rows = [p for p in rows if p["state"] != "open"]
    elif state != "all":
        rows = [p for p in rows if p["state"] == state]
    if w.image is not None:
        image_id = _image_ids(db, dataset_id, [w.image])[0]

        def names_image(p):
            args = p["args"]
            return (
                image_id in (args.get("image_ids") or [])
                or args.get("image_id") == image_id
            )

        rows = [p for p in rows if names_image(p)]
    if w.agent is not None:
        rows = [p for p in rows if p["agent"] == w.agent]
    if w.step is not None:
        rows = [p for p in rows if p["step"] == w.step]
    if w.chat is not None:
        rows = [p for p in rows if p["chat_id"] == w.chat]
    return rows


def _snapshots(db, dataset_id, w: SnapshotWhere):
    from .training import snapshots  # the fixed data is training's

    rows = snapshots(db, dataset_id)
    out = [
        {
            "number": r["number"],
            "created_at": r["created_at"],
            "created_by": r["created_by"],
            "note": r["note"],
            "used": sum(1 for v in json.loads(r["items_json"]).values() if v),
            # What the version holds: each image and the result it uses (none: left out).
            "items": [
                {"image_id": image_id, "result": described(db, result_id)}
                for image_id, result_id in json.loads(r["items_json"]).items()
            ],
        }
        for r in rows
    ]
    return [r for r in out if w.n is None or r["number"] == w.n]


def _datasets(db, dataset_id, w: DatasetWhere):
    """At the library every dataset; in one, its summary (definition 51.2: what the tool
    dataset_get put together)."""
    from .datasets import list_datasets

    rows = (
        list_datasets(db)["datasets"]
        if dataset_id is None
        else [_dataset_summary(db, dataset_id)]
    )
    return [r for r in rows if not w.name or w.name in r["name"]]


def _dataset_summary(db, dataset_id):
    """One dataset as a worker first reads it: its images, the latest version, what training
    uses, its recent runs and drafts, where it stands on the map, the person's turns in it
    (issue #3 U-11) and the plan now as a draft (Astra 2026-10-17)."""
    from .adoption import adoption
    from .agents import agent_list
    from .datasets import get_dataset
    from .drafts import list_drafts, read_plan_draft
    from .progress import progress
    from .run_queries import list_runs

    def unless_none(read):
        try:
            return read()
        except ApiError as exc:
            if exc.status in (404, 422):
                return None
            raise

    return {
        **get_dataset(db, dataset_id),
        "instruction": unless_none(
            lambda: instructions.get_instruction(db, dataset_id, "latest")
        ),
        "adoption": unless_none(lambda: adoption(db, dataset_id)["breakdown"]),
        "recent_runs": list_runs(db, dataset_id)["runs"][:5],
        "drafts": list_drafts(db, dataset_id)["drafts"],
        "map": progress(db, dataset_id).get("overall"),
        "turns": {
            a["agent"]: {k: a[k] for k in ("boxes", "questions", "trouble") if a[k]}
            for a in agent_list(db, dataset_id)["agents"]
        },
        "draft": read_plan_draft(db, dataset_id),
    }


def _requirements(db, dataset_id, w: RequirementWhere):
    """What the dataset's images were annotated for in other datasets (definition 26.5), each
    shown on the same image."""
    found = past_requirements(db, dataset_id)
    image = (
        _image_ids(db, dataset_id, [w.image])[0] if w.image else found["example_image"]
    )
    return [{**r, "image_id": image} for r in found["requirements"]]


def _labels(db, dataset_id, w: LabelWhere):
    """The library's labels (definition 26.1), by a part of their name or of an alias."""
    return [
        label
        for label in list_labels(db)
        if not w.name
        or w.name in label["name"]
        or any(w.name in a for a in label["aliases"])
    ]


def _settings(db, dataset_id, w: SettingsWhere):
    """The app's settings, read only (definition 71): the same at the library and in a dataset."""
    return explained(db, w.group)


# The id field of one object of each type, for "id" (one thing) rather than conditions.
TYPES = {
    "image": (ImageWhere, _images, lambda i: i["image"]["id"]),
    "version": (VersionWhere, _versions, lambda r: str(r["revision"])),
    "draft": (DraftWhere, _drafts, lambda r: "draft"),
    "run": (RunWhere, _runs, lambda r: r["id"]),
    "result": (ResultWhere, _results, lambda r: r["result_id"]),
    "proposal": (ProposalWhere, _proposals, lambda p: p["id"]),
    "snapshot": (SnapshotWhere, _snapshots, lambda r: str(r["number"])),
    "dataset": (DatasetWhere, _datasets, lambda r: r["id"]),
    "requirement": (RequirementWhere, _requirements, lambda r: r["requirement_key"]),
    "label": (LabelWhere, _labels, lambda r: r["id"]),
    "settings": (SettingsWhere, _settings, lambda r: r["key"]),
}


def where_of(kind, where):
    """The conditions as the type's model; an unknown field or value is refused."""
    if kind not in TYPES:
        raise invalid("No such type", type=kind)
    try:
        return TYPES[kind][0].model_validate(where or {})
    except ValidationError as exc:
        raise invalid(
            "Not a condition of this type",
            type=kind,
            errors=[
                e["msg"] + " " + ".".join(map(str, e["loc"])) for e in exc.errors()
            ],
        ) from exc


# The types read at the library, of no dataset (definition 51.4): every dataset, the labels
# (one for every dataset), every dataset's latest version and the app's settings (71).
LIBRARY_TYPES = ("dataset", "label", "version", "settings")


def query(db, dataset_id, kind, where=None, object_id=None):
    """A set of one type by its conditions, in a dataset or at the library (None)."""
    if dataset_id is not None:
        dataset_row(db, dataset_id)
    elif kind not in LIBRARY_TYPES:
        raise ApiError(
            422,
            "dataset_required",
            f"A {kind} is of one dataset: give the dataset",
            {"library_types": list(LIBRARY_TYPES)},
        )
    model = where_of(kind, where)
    _, read, ident = TYPES[kind]
    items = read(db, dataset_id, model)
    if object_id is not None:
        # An image named by its name is that image, by its id (a link compares ids).
        if kind == "image":
            object_id = _image_ids(db, dataset_id, [object_id])[0]
        items = [i for i in items if ident(i) == str(object_id)]
        if not items:
            raise not_found(f"{kind} of this dataset")
    return {
        "type": kind,
        "where": model.model_dump(exclude_none=True),
        "id": object_id,
        "count": len(items),
        "items": items,
    }


def pairs(where):
    """A worker's conditions as [{field, value}] pairs (its answer's strict schema) to a dict:
    "true"/"false" as booleans, digits as numbers, ids as a list split at commas."""
    out = {}
    for pair in where or []:
        field, value = pair["field"], pair["value"]
        if field == "ids":
            out[field] = [v.strip() for v in value.split(",") if v.strip()]
        elif value in ("true", "false"):
            out[field] = value == "true"
        elif value.isdigit() and field in ("revision", "version", "n", "chat", "write"):
            out[field] = int(value)
        else:
            out[field] = value
    return out


def check_show(db, dataset_id, show):
    """A worker's show checked and counted: {type, id, where, count, title}, and for one
    image or result pointed at, where it opens (definition 59.2): image_id, and a result's
    record {id, trial, revision}. The count is of what the right shows (definition 39.1): one
    record pointed at shows its images, and one library label the objects other datasets
    annotated with it (its sheet), so they are counted; else the things found. Raises ApiError
    when the type, a field, a value or the scope is wrong, or when the right would show nothing
    (definition 41.1)."""
    kind = show.get("type")
    where = pairs(show.get("where"))
    object_id = show.get("id") or None
    # One thing in a list of one is that thing pointed at, as by its id (definition 59.2).
    if (
        object_id is None
        and kind in TYPES
        and "ids" in TYPES[kind][0].model_fields
        and len(where.get("ids") or []) == 1
    ):
        object_id = where.pop("ids")[0]
    found = query(db, dataset_id, kind, where, object_id)
    one = found["count"] and found["id"] is not None
    if one and kind == "run":
        count = found["items"][0]["total"]
    elif one and kind == "label":
        count = len(label_objects(db, found["id"]))
    else:
        count = found["count"]
    if not count:
        # A link to nothing (user 2026-10-23: "（0枚）", the names of three images joined in
        # name, a part of one name; 10-27: a label no dataset annotated, compared with nothing):
        # refused, so the worker says it again (agent_answer).
        raise ApiError(
            422,
            "show_empty",
            "The show finds nothing to show; check its conditions (name is a part of one"
            " name; several images by name or id go in ids, separated by commas; a library"
            " label shows the objects other datasets annotated with it)",
            {"type": kind, "where": found["where"]},
        )
    checked = {
        "type": kind,
        "id": found["id"],
        "where": found["where"],
        "count": count,
        "title": (show.get("title") or "")[:80],
    }
    # One image or result opens large (definition 59.2): its image, a result at its record by
    # the version it ran.
    if one and kind == "image":
        checked["image_id"] = found["id"]
    elif one and kind == "result":
        result = found["items"][0]
        checked["image_id"] = result["image_id"]
        checked["record"] = {
            "id": result["record_id"],
            "trial": result["trial"],
            "revision": result["instruction_revision"],
        }
    return checked


def _condition_values(annotation):
    """The values a condition takes, said in a prompt: a choice's, true|false, or a list."""
    args = [a for a in get_args(annotation) if a is not type(None)]
    if get_origin(annotation) is Literal:
        return list(get_args(annotation))
    if annotation is bool or args == [bool]:
        return ["true", "false"]
    for arg in args:
        found = _condition_values(arg)
        if found:
            return found
    if get_origin(annotation) is list:
        return ["a comma list"]
    return []


def types_words():
    """The types and each one's conditions, from the types themselves (the one place; issue
    #3 U-14: the prompts listed them by hand, and one named a state no box has any more):
    what a worker shows and what it reads say them alike (definition 51)."""
    said = []
    for kind, (model, _, _) in TYPES.items():
        fields = []
        for name, info in model.model_fields.items():
            values = _condition_values(info.annotation)
            fields.append(f"{name} ({'|'.join(values)})" if values else name)
        said.append(f"{kind}: {', '.join(fields) if fields else 'no field'}")
    return f"type is one of {', '.join(TYPES)}; their fields: {'; '.join(said)}."


def show_words():
    """What a worker's show may say, per type, from the types' conditions."""
    return (
        f"{types_words()} Give id for one thing (one image, or one result, opens large on"
        " the right: the loupe), else where as [{field, value}] with only those fields. Images"
        " are judged"
        " by a plan (write: a draft write, revision: a version, blank: true for a plan not"
        " begun yet; none: the plan now, the draft if there is one): an image is drawn with a"
        " result only of that plan's requirement, so give revision to show what a version"
        " made, none for the plan being made, and blank when the talk is of another plan not"
        " begun yet (before its start is chosen), so no result of the plan now is shown as"
        " its."
    )


def show_schema():
    """The show of a worker's answer (strict: every field given)."""
    return {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": list(TYPES)},
            "id": {"type": ["string", "null"]},
            "where": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["field", "value"],
                    "additionalProperties": False,
                },
            },
            "title": {"type": "string"},
        },
        "required": ["type", "id", "where", "title"],
        "additionalProperties": False,
    }


# ---------- routes ----------


@router.get("/datasets/{dataset_id}/objects/{kind}")
def objects_route(request: Request, dataset_id: str, kind: str):
    """A set of one type by its conditions, given as the query (ids as a comma list)."""
    from .run_routes import db_of, no_worker

    no_worker(request)
    where = pairs([{"field": k, "value": v} for k, v in request.query_params.items()])
    return query(db_of(request), dataset_id, kind, where)


@router.get("/datasets/{dataset_id}/objects/{kind}/{object_id}")
def object_route(request: Request, dataset_id: str, kind: str, object_id: str):
    from .run_routes import db_of, no_worker

    no_worker(request)
    found = query(db_of(request), dataset_id, kind, None, object_id)
    if found["count"] != 1:
        raise ApiError(409, "not_one", "More than one object has this id")
    return found["items"][0]


@router.get("/objects/{kind}")
def library_objects_route(request: Request, kind: str):
    """A set of a library's type (LIBRARY_TYPES) by its conditions (definition 51.4)."""
    from .run_routes import db_of, no_worker

    no_worker(request)
    where = pairs([{"field": k, "value": v} for k, v in request.query_params.items()])
    return query(db_of(request), None, kind, where)


@router.get("/objects/{kind}/{object_id}")
def library_object_route(request: Request, kind: str, object_id: str):
    from .run_routes import db_of, no_worker

    no_worker(request)
    found = query(db_of(request), None, kind, None, object_id)
    if found["count"] != 1:
        raise ApiError(409, "not_one", "More than one object has this id")
    return found["items"][0]


@router.get("/object-types")
def types_route():
    """Each type's conditions and actions (the screen's buttons come from the actions)."""
    from .actions import action_listing

    actions = action_listing()
    return {
        kind: {
            "where": list(model.model_fields),
            "actions": actions.get(kind, []),
        }
        for kind, (model, _, _) in TYPES.items()
    }

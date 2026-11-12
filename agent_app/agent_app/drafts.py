"""Drafts kept on the server, so a person and the AI read and write the same one
(docs/2026-10-05-app-step4-design.md 3). The plan's draft is one per dataset and is the plan as
it is now: there is no saving, every write is kept (draft_writes) and a trial or a run makes a
version of the write it is decided on, the draft going when it is still that write
(version_from_write, definition 11.2). A person's fix of a result has its own draft (fixes.py).
"""

import json

from pydantic import Field

from . import instructions
from .actors import PERSON
from .datasets import dataset_row
from .db import encoded, now
from .errors import ApiError, invalid, not_found
from .label_library import with_library
from .references import resolved
from .usage import origin_of


class InstructionDraft(instructions.InstructionInput):
    if_updated_at: str | None = Field(
        None, description="The updated_at you read; another write since then is a 409."
    )


class PlanSays(instructions.InstructionInput):
    """What a plan says, as two plans are compared: a draft started blank has no label yet (a
    version has one; copy 2026-10-22: compared as a version's input, the blank plan's state
    failed)."""

    label_definitions: list[instructions.LabelDefinition] = Field(
        max_length=instructions.MAX_LABELS
    )


def plan_draft(db, dataset_id):
    """The plan's draft as stored, None without one: the one place it is read (fact inventory
    6; a person's fix being made is the other kind of draft, fixes.fix_draft)."""
    return db.one(
        "SELECT * FROM drafts WHERE dataset_id=? AND kind='instruction'", (dataset_id,)
    )


def write_row(db, dataset_id, write_id):
    """One write of the dataset's plan as stored, None when it has none of that id."""
    return db.one(
        "SELECT * FROM draft_writes WHERE id=? AND dataset_id=?", (write_id, dataset_id)
    )


def writes_of(db, dataset_id):
    """Every write of the dataset's plan as stored, oldest first."""
    return db.execute(
        "SELECT * FROM draft_writes WHERE dataset_id=? ORDER BY id", (dataset_id,)
    )


def plans_held(db, dataset_id):
    """The plans the dataset holds now: its latest version's content and its draft's, those it
    has (a label of either is the dataset's: a rename or a change reaches both, 26.1, 79.3)."""
    return [
        json.loads(r["payload_json"])
        for r in (instructions.latest_row(db, dataset_id), plan_draft(db, dataset_id))
        if r
    ]


def every_plan_held(db):
    """(dataset id, content) of every dataset's plans held now (plans_held of each)."""
    return [
        (r["dataset_id"], json.loads(r["payload_json"]))
        for r in [
            *instructions.latest_rows(db),
            *db.execute("SELECT * FROM drafts WHERE kind='instruction'"),
        ]
    ]


def _public(db, row):
    """A draft as the API returns it: its references' objects read from their results
    (definition 38.1)."""
    return {
        "dataset_id": row["dataset_id"],
        "kind": row["kind"],
        "image_id": row["image_id"] or None,
        "requirement_key": row["requirement_key"],
        "written_by": row["written_by"],
        "updated_at": row["updated_at"],
        # The write that is its content: a decision to run points at it (definition 11.2).
        "write_id": row["write_id"],
        # Where it was started from (definition 15.1).
        "from": origin_of(row),
        **resolved(db, json.loads(row["payload_json"])),
    }


def plan_now(db, dataset_id):
    """The plan's content as it is now: the draft's, else the latest version's; None before
    either."""
    row = plan_draft(db, dataset_id) or instructions.latest_row(db, dataset_id)
    return json.loads(row["payload_json"]) if row else None


def _start_here(db, dataset_id):
    """A draft begun with none before starts from the plan now (plan_now): the latest
    version, else blank."""
    latest = instructions.latest_revision(db, dataset_id)
    if latest is None:
        return {"kind": "blank"}
    return {"kind": "version", "dataset_id": dataset_id, "revision": latest}


def write_plan(
    db,
    dataset_id,
    change,
    actor,
    job_id=None,
    if_updated_at=None,
    origin=None,
    from_event_id=None,
):
    """One write of the plan's draft (types design 20.3): change(the plan now) gives the whole
    content, kept as a write the draft points at, in one transaction. The write keeps where the
    draft was started from (definition 15.1): origin when given (back to a version, another
    dataset's), else the draft's, else the plan now; and the question it answered. A person's
    own write (not an answer) is told in the steward's chat (26.4)."""
    with db.transaction():
        dataset_row(db, dataset_id)
        old = plan_draft(db, dataset_id)
        # Where the plan was before this write: what a person's write is told against (26.4).
        before_at = plan_at(db, dataset_id)
        if origin is None:
            origin = origin_of(old) if old is not None else _start_here(db, dataset_id)
        where = (
            (origin["kind"], origin.get("dataset_id"), origin.get("revision"))
            if origin
            else (None, None, None)
        )
        if if_updated_at is not None and (
            old is None or old["updated_at"] != if_updated_at
        ):
            raise ApiError(
                409,
                "draft_conflict",
                "The draft changed since you read it; read it again",
                {"updated_at": old["updated_at"] if old else None},
            )
        before = plan_now(db, dataset_id)
        payload = change(before)
        # Each label is the library's (definition 26.1): its id, else the library's label of its
        # name or alias, else the one of its name in the plan now (23.2), else a new label.
        if payload.get("label_definitions") is not None:
            payload = with_library(
                db, payload, (before or {}).get("label_definitions") or ()
            )
        _put(db, dataset_id, payload, actor, where, job_id, from_event_id)
        from .plan_questions import outdate_questions, tell_right

        outdate_questions(db, dataset_id, from_event_id)
        if actor == PERSON and from_event_id is None:
            tell_right(db, dataset_id, before_at, payload)
        return _public(db, plan_draft(db, dataset_id))


def _put(
    db, dataset_id, payload, actor, where, job_id=None, from_event_id=None, at=None
):
    """The one place the plan's draft is written (definition 11.1): the write kept and the draft
    pointing at it, in the caller's transaction. where: (kind, dataset id, revision) it was
    started from. Returns the write's id."""
    at = at or now()
    db.execute(
        "INSERT INTO draft_writes(dataset_id,payload_json,written_by,job_id,written_at,"
        "from_kind,from_dataset_id,from_revision,from_event_id)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (
            dataset_id,
            encoded(payload),
            actor,
            job_id or None,
            at,
            *where,
            from_event_id,
        ),
    )
    write_id = db.one("SELECT last_insert_rowid()")[0]
    db.execute(
        "INSERT INTO drafts(dataset_id,kind,image_id,requirement_key,payload_json,"
        "written_by,updated_at,created_at,write_id,from_kind,from_dataset_id,from_revision)"
        " VALUES(?,'instruction','',?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(dataset_id,kind,image_id)"
        " DO UPDATE SET requirement_key=excluded.requirement_key,"
        " payload_json=excluded.payload_json, written_by=excluded.written_by,"
        " updated_at=excluded.updated_at, write_id=excluded.write_id,"
        " from_kind=excluded.from_kind, from_dataset_id=excluded.from_dataset_id,"
        " from_revision=excluded.from_revision",
        (dataset_id, None, encoded(payload), actor, at, at, write_id, *where),
    )
    return write_id


def take_in_plan_draft(db, dataset_id, payload, actor, where, at):
    """The plan's draft of a dataset taken in (definition 60.3): its content as one write, by
    whom and when it was written there, started from where (2026-10-30: a draft taken in with
    no write made the dataset's progress a 500)."""
    _put(db, dataset_id, payload, actor, where, at=at)


def write_plan_draft(db, dataset_id, kind, image_id, body, actor, job_id=None):
    """Replace the draft's text, labels and what it leaves out in one write; each write is
    kept (types design 20.3). The references are chosen by their own entries (references), so
    a write of the rest keeps them (11.2, 38.1)."""
    payload = body.model_dump(exclude={"if_updated_at"}, mode="json")
    instructions.check_definitions(payload["label_definitions"])

    def change(plan):
        return {**payload, "references": (plan or {}).get("references") or []}

    return write_plan(db, dataset_id, change, actor, job_id, body.if_updated_at)


def read_plan_draft(db, dataset_id):
    """The plan's draft, or None without one: the screens ask for it whenever they open, so
    none is not an error (user 2026-10-27: a 404 in the console at every plan screen)."""
    row = plan_draft(db, dataset_id)
    return _public(db, row) if row else None


def delete_plan_draft(db, dataset_id):
    with db.transaction():
        if plan_draft(db, dataset_id) is None:
            raise not_found("Draft")
        db.execute(
            "DELETE FROM drafts WHERE dataset_id=? AND kind='instruction'",
            (dataset_id,),
        )
    return {"deleted": True}


def list_drafts(db, dataset_id):
    """The dataset's drafts, the newest first: the plan's and each fix being made."""
    from .fixes import fix_drafts  # a fix is checked against the plan's requirement

    dataset_row(db, dataset_id)
    rows = [r for r in (plan_draft(db, dataset_id),) if r] + fix_drafts(db, dataset_id)
    return {
        "drafts": [
            {
                "kind": r["kind"],
                "image_id": r["image_id"] or None,
                "written_by": r["written_by"],
                "updated_at": r["updated_at"],
            }
            for r in sorted(rows, key=lambda r: r["updated_at"], reverse=True)
        ]
    }


CONTENT = ("text", "label_definitions", "references", "leave_out")


def _body(payload):
    return instructions.InstructionInput.model_validate(
        {k: payload[k] for k in instructions.INPUT}
    )


def content_of(payload):
    """What a plan says: its text, labels, what it leaves out, and the result set and revision
    each reference points at (the same revision is the same objects; not who chose them
    when)."""
    return {
        **PlanSays.model_validate(
            {k: payload[k] for k in instructions.INPUT}
        ).model_dump(mode="json"),
        "references": [
            (r["image_id"], r.get("note", ""), r["set_id"], r["revision"])
            for r in payload.get("references") or []
        ],
    }


def same_version(db, dataset_id, payload):
    """The newest version of the dataset saying the same as payload, or None (definition 1 D1:
    the same content is that version; issue #5-12: only the latest was compared, so starting
    from version 2 and running it made a version 4 the same as 2)."""
    content = content_of(payload)
    for row in reversed(instructions.version_rows(db, dataset_id)):
        if content_of(json.loads(row["payload_json"])) == content:
            return row["revision"]
    return None


def version_from_write(db, dataset_id, write_id, actor, decision_id):
    """The version a decision to run makes of a draft write (definition 11.2): the version of
    the same content (same_version), else the next version made from it. The draft goes when
    it is still that write (it became the version); written again since, it stays."""
    with db.transaction():
        write = write_row(db, dataset_id, write_id)
        if write is None:
            raise not_found("Draft write")
        payload = json.loads(write["payload_json"])
        revision = same_version(db, dataset_id, payload)
        if revision is None:
            revision = instructions.save_instruction(
                db,
                dataset_id,
                _body(payload),
                actor,
                decision_id=decision_id,
                references=payload.get("references") or [],
                draft_write_id=write_id,
                origin=origin_of(write),
            )["revision"]
        db.execute(
            "DELETE FROM drafts WHERE dataset_id=? AND kind='instruction' AND write_id=?",
            (dataset_id, write_id),
        )
    return revision


def draft_write_id(db, dataset_id):
    """The write the draft is now, or None without a draft."""
    row = plan_draft(db, dataset_id)
    return row["write_id"] if row else None


def plan_of(db, dataset_id, revision=None, write_id=None, blank=False):
    """A plan as written: a version's, a draft write's, blank (a plan not begun: nothing in it,
    definition 49.1), else the plan now (the draft, else the latest version); {} before any."""
    dataset_row(db, dataset_id)
    if blank:
        if revision is not None or write_id is not None:
            raise invalid("A blank plan is a plan of its own: give it alone")
        return {}
    if revision is not None:
        row = instructions.version_row(db, dataset_id, revision)
        if row is None:
            raise not_found("Instruction version")
        return json.loads(row["payload_json"])
    if write_id is not None:
        row = write_row(db, dataset_id, write_id)
        if row is None:
            raise not_found("Draft write")
        return json.loads(row["payload_json"])
    return plan_now(db, dataset_id) or {}


def plan_basis(db, dataset_id, revision=None, write_id=None, blank=False):
    """(requirement, criteria) of that plan, (None, None) before any and for a blank one: what
    the images' states are judged by when they are looked at with a plan (definition 35.7,
    49.1, 85.4)."""
    return instructions.basis_of(plan_of(db, dataset_id, revision, write_id, blank))


def plan_at(db, dataset_id, write_id=None, revision=None):
    """Where a plan is, to read it as it is later (definition 33.5): {"write": id} or
    {"revision": number}; the write or the version given (one of the dataset's), else the plan
    now: the draft's write, else the latest version; {} before either."""
    if write_id is not None:
        if write_row(db, dataset_id, write_id) is None:
            raise not_found("Draft write")
        return {"write": write_id}
    if revision is not None:
        if instructions.version_row(db, dataset_id, revision) is None:
            raise not_found("Instruction version")
        return {"revision": revision}
    written = draft_write_id(db, dataset_id)
    if written is not None:
        return {"write": written}
    latest = instructions.latest_revision(db, dataset_id)
    return {"revision": latest} if latest is not None else {}


def plan_write_now(db, dataset_id):
    """The write the plan is now (definition 11.10): the draft's, else the one the latest
    version was made from (a run decided on a write makes it a version and the draft goes; what
    was shown with that write still holds). None: neither."""
    written = draft_write_id(db, dataset_id)
    if written is not None:
        return written
    row = instructions.latest_row(db, dataset_id)
    return row["draft_write_id"] if row else None


def from_version(db, dataset_id, revision, actor):
    """The draft written with a version's plan (types design 20.2: back to it), its references
    too."""
    version = instructions.get_instruction(db, dataset_id, revision)
    latest = instructions.get_instruction(db, dataset_id, "latest")
    if version["revision"] == latest["revision"]:
        # Back to the latest version is no draft at all (nothing new to try).
        with db.transaction():
            db.execute(
                "DELETE FROM drafts WHERE dataset_id=? AND kind='instruction'",
                (dataset_id,),
            )
        return {**version, "draft": False}
    return start_plan(
        db, dataset_id, {"kind": "version", "revision": version["revision"]}, actor
    )


BLANK = {
    "text": "",
    "label_definitions": [],
    "references": [],
    "leave_out": [],
}


def start_plan(db, dataset_id, start, actor, from_event_id=None):
    """The draft started again from a place (definition 16.2), as one write that keeps where it
    came from (15.1): blank, a version of this dataset ("version", with its references) or
    another dataset's version ("other": its references are the other dataset's results and are
    not taken, 38.1). The draft there before stays in the record of writes. from_event_id: the
    question it answers (33.3)."""
    if start["kind"] == "blank":
        return write_plan(
            db,
            dataset_id,
            lambda _plan: dict(BLANK),
            actor,
            origin={"kind": "blank"},
            from_event_id=from_event_id,
        )
    source = dataset_id if start["kind"] == "version" else start["dataset_id"]
    if start["kind"] == "other" and source == dataset_id:
        raise ApiError(422, "invalid_input", "Choose another dataset")
    version = instructions.get_instruction(db, source, str(start["revision"]))
    content = {k: version[k] for k in CONTENT}
    if source != dataset_id:
        content["references"] = []
    return write_plan(
        db,
        dataset_id,
        lambda _plan: content,
        actor,
        origin={
            "kind": "version",
            "dataset_id": source,
            "revision": version["revision"],
        },
        from_event_id=from_event_id,
    )


def plan_history(db, dataset_id, limit=20):
    """The plan's record (types design 20.3): its versions with the runs and trials of each,
    and the latest writes of the draft with the request each answered (a worker's write)."""
    versions = instructions.list_instructions(db, dataset_id)["instructions"]
    from .agent_chat import line  # a write answers a line
    from .jobs import job_row

    def asked(write):
        job = job_row(db, write["job_id"])
        return line(db, job["request_event_id"]) if job else None

    return {
        "versions": versions,
        "draft": plan_draft(db, dataset_id) is not None,
        "writes": [
            {
                "written_at": w["written_at"],
                "written_by": w["written_by"],
                "request": ((request := asked(w)) and request["text"] or "")[:80]
                or None,
                "chat_id": request["chat_id"] if request else None,
            }
            for w in list(reversed(writes_of(db, dataset_id)))[:limit]
        ],
    }


def plan_facts(db, dataset_id):
    """The plan as the workers read it (Sol 2026-10-15: asked what changed since the last trial,
    the light answer compared with the first plan, having nothing else): the plan now (a draft
    or the latest version), each version's runs and trials, and what changed from the last
    tried version to the plan now."""
    from .draft_diff import payload_diff

    versions = instructions.list_instructions(db, dataset_id)["instructions"]
    draft = plan_draft(db, dataset_id)
    tried = next((v for v in versions if v["trials"]), None)
    since = None
    if tried:
        old = instructions.version_payload(db, dataset_id, tried["revision"])
        found = payload_diff(old, plan_now(db, dataset_id))
        since = {
            "from_revision": tried["revision"],
            "labels_added": found["added"],
            "labels_removed": found["removed"],
            "labels_renamed": found["renamed"],
            "labels_changed": found["changed"] + found["described"],
            "text_added": found["text"]["added"],
            "text_removed": found["text"]["removed"],
            "references": found["references"],
        }
    return {
        "now": "draft (not tried yet)"
        if draft
        else (f"version {versions[0]['revision']}" if versions else "none"),
        # Where the plan now was started from (definition 15.1): blank, a version of this
        # dataset or another's; None when not recorded.
        "from": origin_of(draft)
        if draft
        else (versions[0]["from"] if versions else None),
        "versions": [
            {k: v[k] for k in ("revision", "created_at", "runs", "trials")}
            for v in versions[:6]
        ],
        "since_last_trial": since,
    }

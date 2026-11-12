"""Each worker's conversation on the work screen (step 24 design 3.5, 3.7): the person's
messages, the worker's answers, questions, offers to hand a request over, and the server's own
lines (a box decided, a run ended), kept apart per worker. Asking puts a light job in the line
of work and returns at once.

A worker's talk is in chats, as in any chat app (user 2026-10-09): a new one, one resumed from
the history, one deleted. Each line is of one chat; the worker goes on with a chat's own lines
and its own CLI session. The server's lines go to the chat the box or the run was made in.

What a worker is told: only its own conversation and, with each message, what changed since
its last answer (the notify check: a worker not told kept proposing what was already decided;
told with the next message, it went on rightly).
"""

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request
from pydantic import Field, StringConstraints

from . import actors
from .agents import AGENTS, AgentName, worker_of
from .datasets import dataset_row
from .db import encoded, now
from .errors import ApiError, Model, not_found
from .jobs import active_jobs, job_chat, job_row, run_job
from .run_queries import SUCCESS, is_trial, record_results, result_counts, run_row

router = APIRouter(prefix="/v1")

# The languages the screen has (ui/src/i18n), by the code it sends as Accept-Language.
LANGUAGES = {"ja": "Japanese", "en": "English"}


def language_of(request: Request):
    """The language of the person's screen: the first tag of the Accept-Language it sends (the
    language chosen on it), when the screen has it."""
    first = (request.headers.get("accept-language") or "").split(",")[0]
    code = first.split(";")[0].split("-")[0].strip().lower()
    return code if code in LANGUAGES else None


def chat_language(db, chat_id):
    """The language a chat is answered in: the screen's of the latest line in it that says one
    (a person's; a turn the server starts, after a run, goes on in it). None when none says."""
    row = db.one(
        "SELECT json_extract(data_json,'$.lang') FROM agent_events WHERE chat_id=?"
        " AND json_extract(data_json,'$.lang') IS NOT NULL ORDER BY id DESC LIMIT 1",
        (chat_id,),
    )
    return LANGUAGES.get(row[0]) if row else None


class Showing(Model):
    """The set of a type shown on the right (types design 3.4: what the person filtered there
    goes with the words)."""

    type: Annotated[str, StringConstraints(max_length=20)]
    where: Annotated[dict[str, Any], Field(default_factory=dict, max_length=12)]
    title: Annotated[str, StringConstraints(max_length=200)] = ""


class LookingAt(Model):
    """What the person was looking at when they wrote (sent with the words, so "this box"
    and "this image" are understood; agent app design 4.2)."""

    # The dataset the right shows, for a worker of the library (a dataset's worker is in it).
    dataset_id: Annotated[str, StringConstraints(max_length=100)] | None = None
    stage: Literal["instruction", "production"] | None = None
    # Apply's screen on the right (definition 34.1, 35.3, 37): annotating with AI or using for
    # training.
    screen: Literal["annotate", "use"] | None = None
    step: Annotated[str, StringConstraints(max_length=40)] | None = None
    image_id: Annotated[str, StringConstraints(max_length=100)] | None = None
    image_name: Annotated[str, StringConstraints(max_length=300)] | None = None
    # The loupe's images before and after it, as its ← → go (the person's order and filter):
    # "next" is understood as the loupe's (definition 59.3).
    previous_image: Annotated[str, StringConstraints(max_length=300)] | None = None
    next_image: Annotated[str, StringConstraints(max_length=300)] | None = None
    # Came to this worker from another's talk (a box's author): kept on the line.
    came_from: AgentName | None = None
    picked: (
        Annotated[
            list[Annotated[str, StringConstraints(max_length=300)]],
            Field(max_length=500),
        ]
        | None
    ) = None
    # The images ticked on the cards (by name): "run these" is understood.
    showing: Showing | None = None
    # The record chosen on the right and the plan its images are judged by (definition 36.6:
    # the left goes to the right with its record and plan, the right comes with them too).
    record_id: Annotated[str, StringConstraints(max_length=100)] | None = None
    record_number: Annotated[int, Field(ge=1)] | None = None
    write: Annotated[int, Field(ge=1)] | None = None
    revision: Annotated[int, Field(ge=1)] | None = None


class MessageInput(Model):
    text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    looking_at: LookingAt | None = None
    # The chat it goes on; none: the worker's latest.
    chat_id: int | None = None


def place_of(request: Request):
    """The place of a talk's route (definition 48.4): its dataset, or the library (None)."""
    dataset_id = request.path_params.get("dataset_id")
    if dataset_id:
        dataset_row(request.app.state.db, dataset_id)
    return dataset_id


def new_chat(db, dataset_id, agent):
    with db.transaction():
        db.execute(
            "INSERT INTO agent_chats(dataset_id, agent, created_at, updated_at)"
            " VALUES(?,?,?,?)",
            (dataset_id, agent, now(), now()),
        )
        return db.one("SELECT last_insert_rowid()")[0]


def current_chat(db, dataset_id, agent):
    """The worker's latest chat not deleted (a new one when it has none)."""
    row = db.one(
        "SELECT id FROM agent_chats WHERE dataset_id IS ? AND agent=?"
        " AND deleted_at IS NULL ORDER BY updated_at DESC, id DESC LIMIT 1",
        (dataset_id, agent),
    )
    return row["id"] if row else new_chat(db, dataset_id, agent)


def chat_of(db, dataset_id, agent, chat_id):
    """The chat asked for, if it is the worker's; else its latest."""
    if chat_id and db.one(
        "SELECT 1 FROM agent_chats WHERE id=? AND dataset_id IS ? AND agent=?"
        " AND deleted_at IS NULL",
        (chat_id, dataset_id, agent),
    ):
        return chat_id
    return current_chat(db, dataset_id, agent)


# The lines a worker's answer makes (an answer that failed makes a "failed" line).
ANSWERED = ("ai", "question", "handoff_offer", "open")
# The lines waiting for the person: a question not answered, a failed answer not seen.
WAITING = ("question", "failed")


def line(db, event_id):
    """A line of a talk as stored, None when there is none: the one place a line is read by its
    id (fact inventory 8)."""
    return (
        db.one("SELECT * FROM agent_events WHERE id=?", (event_id,))
        if event_id
        else None
    )


def line_at(db, event_id, dataset_id, agent):
    """The line, when it is that worker's at that place (a dataset, the library: None); else
    None."""
    row = line(db, event_id)
    if row is None or row["dataset_id"] != dataset_id or row["agent"] != agent:
        return None
    return row


def event_chat(db, event_id):
    row = line(db, event_id)
    return row["chat_id"] if row else None


def close_event(db, event_id, data=None):
    """A line closed now (a question answered, set aside or stale; an offer handed over), its
    data rewritten when given; whether it was open."""
    with db.transaction():
        db.execute(
            "UPDATE agent_events SET closed_at=?, data_json=coalesce(?, data_json)"
            " WHERE id=? AND closed_at IS NULL",
            (now(), encoded(data) if data is not None else None, event_id),
        )
        return db.one("SELECT changes()")[0] > 0


def renote(db, event_id, data):
    """A note said again as now, with what it says now (one line while nothing else is said)."""
    db.execute(
        "UPDATE agent_events SET data_json=?, created_at=? WHERE id=?",
        (encoded(data), now(), event_id),
    )


def unsay(db, event_id):
    """A note taken back: what it said is no more (nothing changed after all)."""
    db.execute("DELETE FROM agent_events WHERE id=?", (event_id,))


def job_last_line(db, job_id):
    """The newest line a job wrote, None for one of none."""
    return db.one(
        "SELECT * FROM agent_events WHERE job_id=? ORDER BY id DESC LIMIT 1", (job_id,)
    )


def last_line(db, chat_id):
    """A chat's newest line, None for a chat of none."""
    return db.one(
        "SELECT * FROM agent_events WHERE chat_id=? ORDER BY id DESC LIMIT 1",
        (chat_id,),
    )


def waiting_lines(db, dataset_id):
    """The lines of a place (a dataset, the library: None) waiting for the person (WAITING),
    the oldest first."""
    return db.execute(
        "SELECT * FROM agent_events WHERE dataset_id IS ? AND closed_at IS NULL"
        f" AND kind IN ({','.join('?' * len(WAITING))}) ORDER BY id",
        (dataset_id, *WAITING),
    )


def question_lines(db, dataset_id):
    """Every question of a place, answered or not, the oldest first."""
    return db.execute(
        "SELECT * FROM agent_events WHERE dataset_id IS ? AND kind='question' ORDER BY id",
        (dataset_id,),
    )


def last_lines(db, dataset_id):
    """Each worker's newest line at a place not the person's own: agent -> the line."""
    return {
        r["agent"]: r
        for r in db.execute(
            "SELECT * FROM agent_events e WHERE e.dataset_id IS ? AND e.id = (SELECT"
            " max(id) FROM agent_events x WHERE x.dataset_id IS e.dataset_id"
            " AND x.agent=e.agent AND x.kind != 'human')",
            (dataset_id,),
        )
    }


def last_answer(db, dataset_id, agent, chat_id):
    """The worker's newest answer in a chat that went on in a CLI session (its model, session and
    rules), None before one."""
    return db.one(
        "SELECT * FROM agent_events WHERE dataset_id IS ? AND agent=?"
        f" AND kind IN ({','.join('?' * len(ANSWERED))})"
        " AND session_id IS NOT NULL AND chat_id IS ? ORDER BY id DESC LIMIT 1",
        (dataset_id, agent, *ANSWERED, chat_id),
    )


def asked_between(db, chat_id, after, until):
    """The person's lines of a chat after one line up to another."""
    return db.execute(
        "SELECT * FROM agent_events WHERE chat_id=? AND kind='human' AND id > ?"
        " AND id <= ? ORDER BY id",
        (chat_id, after, until),
    )


def chat_row(db, chat_id):
    """A chat as stored (its place, worker, whether it was deleted), None when there is none."""
    return (
        db.one("SELECT * FROM agent_chats WHERE id=?", (chat_id,)) if chat_id else None
    )


def add(db, dataset_id, agent, kind, text, by_actor=None, chat_id=None, **extra):
    """One line of a worker's chat; by_actor is who wrote it (definition 21.2): the worker
    itself, the server for its notes, else as given (the person, a worker handing over). A
    chat given (or a job's) is the line's place and worker (the reception's box of a dataset
    is told in the library's talk, 48.2); a deleted one gives way to the worker's latest."""
    with db.transaction():
        given = chat_id or (
            extra.get("job_id") and job_chat(db, job_row(db, extra["job_id"]))
        )
        chat = chat_row(db, given)
        if chat:
            dataset_id, agent = chat["dataset_id"], chat["agent"]
        chat_id = given if chat and not chat["deleted_at"] else None
        chat_id = chat_id or current_chat(db, dataset_id, agent)
        if by_actor is None:
            by_actor = (
                actors.SERVER if kind in ("note", "failed") else actors.agent(agent)
            )
        if kind == "question":
            close_questions(db, chat_id)
        db.execute("UPDATE agent_chats SET updated_at=? WHERE id=?", (now(), chat_id))
        db.execute(
            "INSERT INTO agent_events(dataset_id,agent,kind,text,by_actor,created_at,"
            "model,elapsed_ms,cost_json,tools_json,session_id,prompt_sha,job_id,data_json,"
            "chat_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                dataset_id,
                agent,
                kind,
                text,
                by_actor,
                now(),
                extra.get("model"),
                extra.get("elapsed_ms"),
                encoded(extra["cost"]) if extra.get("cost") else None,
                encoded(extra.get("tools") or []),
                extra.get("session_id"),
                extra.get("prompt_sha"),
                extra.get("job_id"),
                encoded(extra["data"]) if extra.get("data") else None,
                chat_id,
            ),
        )
        return db.one("SELECT last_insert_rowid()")[0]


def event_out(row):
    return {
        "id": row["id"],
        "agent": row["agent"],
        "kind": row["kind"],
        "text": row["text"],
        "by": row["by_actor"],
        "created_at": row["created_at"],
        "model": row["model"],
        "elapsed_ms": row["elapsed_ms"],
        "cost": json.loads(row["cost_json"]) if row["cost_json"] else None,
        "tools": json.loads(row["tools_json"]) if row["tools_json"] else [],
        "job_id": row["job_id"],
        "data": json.loads(row["data_json"]) if row["data_json"] else None,
        "closed_at": row["closed_at"],
        "chat_id": row["chat_id"],
    }


def conversation(db, dataset_id, agent, limit=100, chat_id=None):
    """A chat's lines, oldest first (the worker's latest chat when none is given)."""
    chat_id = chat_id or current_chat(db, dataset_id, agent)
    rows = db.execute(
        "SELECT * FROM agent_events WHERE dataset_id IS ? AND agent=? AND chat_id=?"
        " ORDER BY id DESC LIMIT ?",
        (dataset_id, agent, chat_id, limit),
    )
    return list(reversed(rows))


# The earlier lines of its chat a worker reads when its conversation starts (definition 68.1).
EARLIER = 8
# How a worker reads them, the same for every worker (said in each one's rules).
LINES_WORDS = (
    "context.earlier (a conversation starting) or context.since (going on: the lines after"
    " your last answer) are the chat's lines as the person sees them, oldest first: by is who"
    " said it (person, you, server, or another worker), a question has its options and the"
    " one chosen, a note is what the server told (its kind). context.request.by is who wrote"
    " the message: another worker handed it to you (its words are that worker's summary);"
    " handed_from is the chat it came from, where the person's own words (by person) are what"
    " they asked, and what that worker added is its own idea, not the person's."
)


def _line(row, agent):
    """One line of a chat as a worker reads it (definition 68.1): who, its kind and words, and
    what the screen shows with it."""
    data = json.loads(row["data_json"] or "{}")
    line = {
        "by": actors.as_read_by(row["by_actor"], agent),
        "kind": row["kind"],
        "text": row["text"],
    }
    if row["kind"] == "question":
        options = data.get("options") or []
        line["options"] = [o["label"] for o in options]
        chosen = (data.get("answered") or {}).get("option")
        if chosen is not None and chosen < len(options):
            line["chosen"] = options[chosen]["label"]
    elif row["kind"] == "handoff_offer":
        line |= {"to": data.get("agent"), "summary": data.get("summary")}
    elif row["kind"] == "open":
        line |= {"dataset_id": data.get("dataset_id"), "stage": data.get("stage")}
    elif row["kind"] == "note":
        line["text"] = data.get("note") or row["text"]
        if data.get("title"):
            line["title"] = data["title"]
    return line


def worker_lines(db, request_id, agent):
    """What a worker reads of its chat with a message (definition 68.1): earlier, the lines
    before it (a conversation starting); since, those after its last answer it did not say
    (going on); and who wrote the message, with the chat it was handed from."""
    row = line(db, request_id)
    before = list(
        reversed(
            db.execute(
                "SELECT * FROM agent_events WHERE chat_id=? AND id<? ORDER BY id DESC"
                " LIMIT ?",
                (row["chat_id"], request_id, EARLIER),
            )
        )
    )
    mine = actors.agent(agent)
    last = max((i for i, r in enumerate(before) if r["by_actor"] == mine), default=None)
    since = before[last + 1 :] if last is not None else before
    request = {"by": actors.as_read_by(row["by_actor"], agent)}
    origin = json.loads(row["data_json"] or "{}").get("from_event_id")
    offer = line(db, origin)
    if offer:
        request["handed_from"] = [
            _line(r, agent)
            for r in reversed(
                db.execute(
                    "SELECT * FROM agent_events WHERE chat_id=? AND id<=? ORDER BY id DESC"
                    " LIMIT ?",
                    (offer["chat_id"], origin, EARLIER),
                )
            )
        ]
    return {
        "earlier": [_line(r, agent) for r in before],
        "since": [_line(r, agent) for r in since],
        "request": request,
    }


def chats(db, dataset_id, agent):
    """The worker's chats, the latest first: when, how many lines, its first words."""
    return [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "lines": r["lines"],
            "title": r["title"],
        }
        for r in db.execute(
            "SELECT c.id, c.created_at, c.updated_at, (SELECT count(*) FROM agent_events e"
            " WHERE e.chat_id=c.id) AS lines, (SELECT text FROM agent_events e WHERE"
            " e.chat_id=c.id AND e.kind='human' ORDER BY e.id LIMIT 1) AS title"
            " FROM agent_chats c WHERE c.dataset_id IS ? AND c.agent=?"
            " AND c.deleted_at IS NULL ORDER BY c.updated_at DESC, c.id DESC",
            (dataset_id, agent),
        )
    ]


def has_values(data):
    """Whether a question's options carry values (a plan, a place to start again from, a word
    for a label; definitions 26.4, 33.3): its words alone do not answer it."""
    return any(
        o.get("plan") or o.get("start") or o.get("alias")
        for o in (data or {}).get("options") or []
        if isinstance(o, dict)
    )


def close_questions(db, chat_id, only_plain=False):
    """The chat's open questions closed: by a newer question (it replaces them), or, only_plain,
    by the person's words (they answer a question of words; one with values stays open until
    it is answered, replaced or its plan changes). The ids closed, oldest first."""
    closed = []
    with db.transaction():
        for row in db.execute(
            "SELECT id, data_json FROM agent_events WHERE chat_id=? AND kind='question'"
            " AND closed_at IS NULL ORDER BY id",
            (chat_id,),
        ):
            if not (only_plain and has_values(json.loads(row["data_json"] or "{}"))):
                close_event(db, row["id"])
                closed.append(row["id"])
    return closed


def reopened(data):
    """A question's data opened again after the answer to it was stopped before it reached the
    worker (definition 41.3), or None when it stays: choosing its option already did something
    (wrote the plan, started it again, kept a word for a label), or its plan moved on."""
    chosen = data.get("answered")
    if data.get("stale") or (
        chosen
        and any(
            (data.get("options") or [])[chosen["option"]].get(k)
            for k in ("plan", "start", "alias")
        )
    ):
        return None
    return {k: v for k, v in data.items() if k != "answered"}


def reopen_question(db, line_id):
    """The question the stopped answer's line answered, open again to be answered with one
    press (reopened says when)."""
    said = line(db, line_id)
    answered = json.loads((said and said["data_json"]) or "{}").get("answer_to")
    row = line(db, answered)
    row = row if row and row["kind"] == "question" else None
    data = row and reopened(json.loads(row["data_json"] or "{}"))
    # A newer question of its chat replaced it.
    newer = row and db.one(
        "SELECT 1 FROM agent_events WHERE kind='question' AND id>? AND chat_id IS ?",
        (answered, row["chat_id"]),
    )
    if not row or data is None or newer:
        return
    with db.transaction():
        db.execute(
            "UPDATE agent_events SET data_json=?, closed_at=NULL WHERE id=?",
            (encoded(data), answered),
        )


def ask(jobs, dataset_id, agent, text, by_actor, data=None, chat_id=None, lang=None):
    """A message to a worker in one of its chats: kept with the language of the person's screen,
    the chat's open question answered by it, and the job of the worker's answer (its CLI kept
    for the chat; definition 28: no quick answer of a fast model before it)."""
    db = jobs.db
    if lang:
        data = {**(data or {}), "lang": lang}
    if dataset_id:
        dataset_row(db, dataset_id)
    worker_of(agent, dataset_id)
    chat_id = chat_of(db, dataset_id, agent, chat_id)
    closed = close_questions(db, chat_id, only_plain=True)
    # Words that close a question answer it, as a pressed option does.
    if closed and "answer_to" not in (data or {}):
        data = {**(data or {}), "answer_to": closed[-1]}
    event_id = add(
        db,
        dataset_id,
        agent,
        "human",
        text,
        by_actor=by_actor,
        data=data,
        chat_id=chat_id,
    )
    # Bound to its place's dataset, or, a library's worker, to the one the request reads.
    reads = ((data or {}).get("looking_at") or {}).get("dataset_id")
    queued = jobs.enqueue(
        dataset_id, agent, "answer_heavy", text[:60], event_id, bound=reads
    )
    return {
        "event_id": event_id,
        "job_id": queued["id"],
        "position": queued["position"],
    }


def _origin(db, event_id):
    """The worker a request was handed from and the chat of its offer (else None, None)."""
    if not event_id:
        return None, None
    row = line(db, event_id)
    data = json.loads(row["data_json"]) if row and row["data_json"] else {}
    return data.get("from_agent"), event_chat(db, data.get("from_event_id"))


def note_decided(db, proposal, chat_id=None):
    """A box was decided (applied, declined, outdated, failed): a line in its worker's
    conversation (chat_id: the chat it was decided in, else the one it was made in), and in the
    conversation it was handed from."""
    data = {
        "note": f"box_{proposal['state']}",
        "proposal_id": proposal["id"],
        "title": proposal["title"],
        "changed": proposal.get("changed"),
        "outcome": proposal.get("outcome"),
    }
    agent = proposal.get("agent")
    if agent in AGENTS:
        add(
            db,
            proposal["dataset_id"],
            agent,
            "note",
            data["note"],
            data=data,
            chat_id=chat_id or proposal.get("chat_id"),
        )
    origin, chat = _origin(db, proposal.get("from_event_id"))
    if origin in AGENTS and origin != agent:
        add(
            db,
            proposal["dataset_id"],
            origin,
            "note",
            data["note"],
            data=data,
            chat_id=chat,
        )


def note_own_decision(db, dataset_id, decision, agent, chat_id):
    """A person's own decision (no box, definition 21.3): a line in the steward's
    conversation of the dataset it was decided in (a library's decision too), as a box decided
    there has (what it was, what came of it)."""
    add(
        db,
        dataset_id,
        agent,
        "note",
        "decided",
        chat_id=chat_id,
        data={
            "note": "decided",
            "decision_id": decision["id"],
            "kind": decision["kind"],
            "title": decision["title"],
            "outcome": decision["outcome"],
        },
    )


def note_made(db, proposal):
    """A box was made from a handed request: the conversation it came from hears it."""
    origin, chat = _origin(db, proposal.get("from_event_id"))
    if origin in AGENTS and origin != proposal.get("agent"):
        add(
            db,
            proposal["dataset_id"],
            origin,
            "note",
            "box_made",
            chat_id=chat,
            data={
                "note": "box_made",
                "proposal_id": proposal["id"],
                "title": proposal["title"],
                "by_agent": proposal.get("agent"),
            },
        )


def note_run_end(db, run_id, jobs=None):
    """A run ended, however it ended: its worker's conversation always gets a line (never a
    silent end; Grok Bot's routine worker said a failure might reach nobody). A trial a worker
    proposed wakes it in that chat: it asks the person whether the results are right (26.8)."""
    job = run_job(db, run_id)
    if job is None or job["agent"] not in AGENTS:
        return
    from .images import image_names
    from .proposals import box_of_decision  # a box tells its chat

    row = run_row(db, run_id)
    # The worker that proposed it (a person's own run has none).
    proposed = box_of_decision(db, row["decision_id"])
    results = record_results(db, run_id)
    found = result_counts(r["status"] for r in results)
    run = {
        **{k: row[k] for k in ("status", "error_code", "budget_per_image_usd")},
        "instruction_revision": row["instruction_revision"],
        "trial": is_trial(json.loads(row["settings_json"])),
        "proposed_by": proposed["agent"] if proposed else None,
        "total": found["total"],
        "succeeded": found["succeeded"],
    }
    # Which images, by name (Sol 2026-10-08: "1/1 done" did not tell one run from another):
    # those not done when some were not (10-29: after "ended with failures" the first ten
    # images of 47 read as the failed ones).
    not_done = run["succeeded"] < run["total"]
    ids = [
        r["image_id"] for r in results if not not_done or r["status"] not in SUCCESS
    ][:10]
    names = image_names(db, ids)
    event_id = add(
        db,
        job["dataset_id"],
        job["agent"],
        "note",
        "run_ended",
        job_id=job["id"],
        data={
            "note": "run_ended",
            "run_id": run_id,
            # A trial's end is shown in the plan, a run's in its progress (definition 35.4),
            # judged by the version it ran (36.1).
            "trial": bool(run["trial"]),
            "revision": run["instruction_revision"],
            "status": run["status"],
            "error_code": run["error_code"],
            # The cost limit it was stopped at, said with it (definition 50.3).
            "budget_per_image_usd": run["budget_per_image_usd"],
            "succeeded": run["succeeded"],
            "total": run["total"],
            "images": [names.get(i, i) for i in ids],
            "not_done": not_done,
        },
    )
    if jobs is not None and run["trial"] and run["proposed_by"] == job["agent"]:
        # At the place of the chat told (the line's, as every answer is its request's), bound
        # to the run's dataset (definition 48.10, 48.12).
        told = line(db, event_id)
        jobs.enqueue(
            told["dataset_id"],
            job["agent"],
            "answer_heavy",
            "trial",
            event_id,
            bound=job["dataset_id"],
        )


def changes_since(db, dataset_id, agent):
    """What happened since the worker's last answer: the server's lines after it."""
    last = db.one(
        "SELECT max(id) FROM agent_events WHERE dataset_id IS ? AND agent=?"
        f" AND kind IN ({','.join('?' * (len(ANSWERED) + 1))})",
        (dataset_id, agent, *ANSWERED, "failed"),
    )[0]
    rows = db.execute(
        "SELECT data_json FROM agent_events WHERE dataset_id IS ? AND agent=?"
        " AND kind='note' AND id>?",
        (dataset_id, agent, last or 0),
    )
    return [json.loads(r["data_json"]) for r in rows if r["data_json"]]


def answering(db, dataset_id, agent, chat_id=None):
    """The worker answers (in that chat, when one is given)."""
    return any(
        j["agent"] == agent
        and j["kind"] == "answer_heavy"
        and (chat_id is None or job_chat(db, j) == chat_id)
        for j in active_jobs(db, dataset_id)
    )


def jobs_of(request: Request):
    return request.app.state.jobs


# The talk's routes, one set for every place (definition 48.4): a dataset's worker under
# /datasets/{dataset_id}, the library's under /library.
DATASET = "/datasets/{dataset_id}/agents/{agent}"
LIBRARY = "/library/agents/{agent}"


@router.get(DATASET + "/events")
@router.get(LIBRARY + "/events")
def events_route(request: Request, agent: str, chat: int | None = None):
    db = request.app.state.db
    place = place_of(request)
    worker_of(agent, place)
    chat_id = chat_of(db, place, agent, chat)
    return {
        "chat_id": chat_id,
        "events": [
            event_out(r) for r in conversation(db, place, agent, chat_id=chat_id)
        ],
        "answering": answering(db, place, agent, chat_id),
    }


@router.get(DATASET + "/chats")
@router.get(LIBRARY + "/chats")
def chats_route(request: Request, agent: str):
    place = place_of(request)
    worker_of(agent, place)
    return {"chats": chats(request.app.state.db, place, agent)}


@router.post(DATASET + "/chats", status_code=201)
@router.post(LIBRARY + "/chats", status_code=201)
def new_chat_route(request: Request, agent: str):
    if request.headers.get("x-annotation-agent"):
        raise ApiError(403, "agent_scope", "Only a person starts a chat")
    place = place_of(request)
    worker_of(agent, place)
    return {"id": new_chat(request.app.state.db, place, agent)}


@router.delete(DATASET + "/chats/{chat_id}")
@router.delete(LIBRARY + "/chats/{chat_id}")
def delete_chat_route(request: Request, agent: str, chat_id: int):
    """A chat and its lines go; boxes, notes and data stay. Not while it is answered."""
    if request.headers.get("x-annotation-agent"):
        raise ApiError(403, "agent_scope", "Only a person deletes a chat")
    db = request.app.state.db
    place = place_of(request)
    worker_of(agent, place)
    if not db.one(
        "SELECT 1 FROM agent_chats WHERE id=? AND dataset_id IS ? AND agent=?",
        (chat_id, place, agent),
    ):
        raise not_found("Chat")
    if answering(db, place, agent, chat_id):
        raise ApiError(
            409, "agent_answering", "The worker is answering in it; delete after"
        )
    with db.transaction():
        # Hidden, not gone: a box or a write made from its lines still says which (#4 F-09).
        db.execute(
            "UPDATE agent_chats SET deleted_at=?, deleted_by=? WHERE id=?",
            (now(), actors.who_of(request), chat_id),
        )
    jobs_of(request).forget_chat(agent, chat_id)
    return {"deleted": chat_id}


@router.post(DATASET + "/messages", status_code=202)
@router.post(LIBRARY + "/messages", status_code=202)
def message_route(request: Request, agent: str, body: MessageInput):
    if request.headers.get("x-annotation-agent"):
        raise ApiError(403, "agent_scope", "Workers do not write to workers")
    place = place_of(request)
    looking = body.looking_at.model_dump(exclude_none=True) if body.looking_at else None
    if looking and looking.get("dataset_id"):
        # The dataset the right shows, for the library's worker (else 404 before the line).
        dataset_row(request.app.state.db, looking["dataset_id"])
    data = {"looking_at": looking} if looking else None
    return ask(
        jobs_of(request),
        place,
        agent,
        body.text,
        actors.who_of(request),
        data=data,
        chat_id=body.chat_id,
        lang=language_of(request),
    )


def close_line(db, row, actor):
    """A person saw a failed answer (［確かめた］) or does not answer a question (［答えない］):
    it no longer counts. A question not answered says so, and its worker hears it in its next
    answer (a note; definition 44.2)."""
    data = json.loads(row["data_json"] or "{}")
    if row["kind"] == "question":
        data["unanswered"] = {"by": actor, "at": now()}
    closed = close_event(db, row["id"], data if row["kind"] == "question" else None)
    if closed and row["kind"] == "question":
        note = {"note": "question_unanswered", "title": row["text"]}
        add(
            db,
            row["dataset_id"],
            row["agent"],
            "note",
            note["note"],
            data=note,
            chat_id=row["chat_id"],
        )


@router.post(DATASET + "/events/{event_id}/close")
@router.post(LIBRARY + "/events/{event_id}/close")
def close_route(request: Request, agent: str, event_id: int):
    db = request.app.state.db
    row = line_at(db, event_id, place_of(request), agent)
    if row is None:
        raise not_found("Event")
    close_line(db, row, actors.who_of(request))
    return event_out(line(db, event_id))

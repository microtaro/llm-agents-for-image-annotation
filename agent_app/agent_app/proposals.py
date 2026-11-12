"""Proposals of the work room (step 22, trial C) and the boxes of the work screen (step 24).
Palantir's way: a worker makes a decision ready (the tool, its arguments, why) and a person
applies or declines it. Applying runs the same tool with the same arguments through the HTTP
API, so the tool's own input rules and the server's checks hold as they do when the AI calls
it; what came of it is kept.

Step 24: a box keeps which worker it is of, what it showed (preview) and what it stood on
(premise). Applying first compares the premise with the data now and withdraws a box whose
premise another decision changed first, saying what changed (definition 18.13); a person may
change the values, which are applied once and recorded (design D3); a refusal of the API leaves
the box failed with the reason. A box is also withdrawn when a write moves its ground (settle,
after every write; definition 19.7), so the screen and the worker never show it waiting (Sol
2026-10-08: a box showed the state it was made on after a person had changed the image by
hand). Reading a box writes nothing (issue #5-4).
"""

import json
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Request
from pydantic import StringConstraints, ValidationError

from . import actors, config, decisions, shared_notes
from .actions import DECISION_TOOLS, DECISIONS, place
from .actors import who_of
from .agent_chat import chat_of, chat_row, current_chat, event_chat
from .agents import AGENTS, AgentName, counts, worker_at
from .box_facts import facts, plan_now_of, what_changed
from .codex_execution import catalog_models, check_choice, effort_for, model_option
from .datasets import dataset_row
from .db import encoded, new_id, now
from .drafts import plan_basis
from .errors import ApiError, Model, invalid, not_found, problems_of
from .images import image_names
from .jobs import job_row, tell_run_in
from .mcp_general import GENERAL, kept_in_place, run_tool
from .run_inputs import (
    default_choice,
    named_references,
    plan_to_run,
    refuse_writing,
    run_limit,
    start_targets,
)

router = APIRouter(prefix="/v1")

Bot = Literal["secretary", "instruction", "production"]
# The decisions a proposal may hold: the decisions of the one list (definition 22.2).
Tool = Literal[DECISION_TOOLS]
Text = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]


class ProposalInput(Model):
    # Not used: the work area comes from the tool and its arguments (place, step 23).
    bot: Bot | None = None
    # The worker it is of (a rule's box made on the work screen); an AI's comes from the
    # headers the server gave its CLI.
    agent: AgentName | None = None
    tool: Tool
    args: dict[str, Any]
    title: Text
    reason: Text


class ApplyInput(Model):
    args: dict[str, Any] | None = None


def _parsed(value):
    return json.loads(value) if value else None


def is_waiting(row):
    """A box waits for the person: to be decided (definition 16)."""
    return row["state"] == "open"


def is_trouble(row):
    """A box that failed and the person has not seen: trouble (the person's turn)."""
    return row["state"] == "failed" and row["seen_at"] is None


def is_decided(row):
    """A box decided: applied, or failed when it was carried out (declined and withdrawn ones were
    not decided on)."""
    return row["state"] in ("applied", "failed")


def _box_out(row):
    return {
        "id": row["id"],
        "dataset_id": row["dataset_id"],
        "bot": row["bot"],
        "agent": row["agent"],
        "tool": row["tool"],
        "args": json.loads(row["args_json"]),
        "title": row["title"],
        "reason": row["reason"],
        "made_by": row["made_by"],
        "state": row["state"],
        # What the state says, as the server counts it (the screen does not make it again).
        "waiting": is_waiting(row),
        "trouble": is_trouble(row),
        "decided": is_decided(row),
        "created_at": row["created_at"],
        "decided_at": row["decided_at"],
        "decided_by": row["decided_by"],
        "outcome": _parsed(row["outcome_json"]),
        "preview": _parsed(row["preview_json"]),
        "changed": _parsed(row["changed_json"]),
        "from_event_id": row["from_event_id"],
        "seen_at": row["seen_at"],
        "chat_id": row["chat_id"],
        # The map's place of the box, from what it changes (place, step); its author is agent.
        "stage": row["bot"],
        "step": row["step"],
    }


def box_row(db, proposal_id):
    """A box as stored: the one place a box is read by its id (fact inventory 7)."""
    row = db.one("SELECT * FROM proposals WHERE id=?", (proposal_id,))
    if row is None:
        raise not_found("Proposal")
    return row


def _place_boxes(db, dataset_id):
    return db.execute(
        "SELECT * FROM proposals WHERE dataset_id IS ? ORDER BY created_at",
        (dataset_id,),
    )


def waiting_boxes(db, dataset_id):
    """The boxes waiting at a place (a dataset, the library: None) for a person, the oldest
    first."""
    return [r for r in _place_boxes(db, dataset_id) if is_waiting(r)]


def every_waiting_box(db):
    """The boxes waiting at every place."""
    return [r for r in db.execute("SELECT * FROM proposals") if is_waiting(r)]


def unseen_trouble(db, dataset_id):
    """The boxes of a place that failed and the person has not seen: its trouble."""
    return [r for r in _place_boxes(db, dataset_id) if is_trouble(r)]


def see_trouble(db, dataset_id):
    """The place's trouble seen now; how many."""
    found = unseen_trouble(db, dataset_id)
    with db.transaction():
        for r in found:
            db.execute("UPDATE proposals SET seen_at=? WHERE id=?", (now(), r["id"]))
    return len(found)


def box_of_decision(db, decision_id):
    """The box a decision came from (a worker's, a person applied it), None for a person's own
    press."""
    decision = decisions.get_decision(db, decision_id) if decision_id else None
    if decision is None or decision["proposal_id"] is None:
        return None
    return box_row(db, decision["proposal_id"])


def made_boxes(db, job, agent):
    """The boxes an answer made (its request's, since the answer began), with their state and
    why one was withdrawn."""
    return db.execute(
        "SELECT * FROM proposals WHERE from_event_id=? AND created_at>=? AND agent=?"
        " ORDER BY created_at",
        (job["request_event_id"], job["started_at"], agent),
    )


def with_dataset(tool, args, dataset_id):
    """A decision's arguments with its dataset: a decision of a dataset names the proposal's
    (a worker or the screen may leave it out; another one is refused); one of the library is
    of no dataset and names its own in its arguments (definition 22.2)."""
    library = DECISIONS[tool].scope == "library"
    if library != (dataset_id is None):
        raise invalid(
            f"{tool} is a decision of the library: it has no dataset"
            if library
            else f"{tool} is a decision of a dataset: give its dataset"
        )
    if library or "dataset_id" not in GENERAL[tool].input.model_fields:
        return dict(args)
    if args.get("dataset_id") not in (None, dataset_id):
        raise invalid("The proposal's arguments are of another dataset")
    return {**args, "dataset_id": dataset_id}


def _checked(db, dataset_id, body: ProposalInput):
    """The decision's arguments by the tool's own input rules, now, not when applied."""
    if dataset_id is not None:
        dataset_row(db, dataset_id)
    given = with_dataset(body.tool, body.args, dataset_id)
    if body.tool == "run_start":
        given = _run_values(db, dataset_id, given)
    return _valid_args(body.tool, given).model_dump(mode="json", by_alias=True)


def _valid_args(tool, given):
    """A decision's arguments by its tool's input rules; wrong ones are refused as input, nothing
    written (issue #3 U-01: they went out as a broken write, "never blindly resend")."""
    try:
        return GENERAL[tool].input.model_validate(given)
    except ValidationError as exc:
        raise invalid(
            f"The arguments of {tool} are not valid; fix them and send again",
            problems=problems_of(exc.errors(), ("args",)),
        ) from exc


# What a run's box holds by value and a person may not change when applying a worker's box
# (definition 40.1; 11.4 fixed the model and the effort too): the plan it points at and the
# shared notes' version. The images, the model, the effort and the limit are the person's to
# change, kept as what was changed.
FIXED = ("draft_write_id", "revision", "shared_revision")


def _run_values(db, dataset_id, given):
    """A run's box by value (definition 11.4): the plan it points at (the plan now when none
    is given: the draft's write, else the latest version), the model (the settings' default
    for runs), the effort (as the run takes it) and the cost limit per image (the settings',
    definition 65). Applied later, it runs this, whatever was written since."""
    plan = plan_to_run(
        db, dataset_id, given.get("draft_write_id"), given.get("revision")
    )
    chosen = default_choice(db)
    model = given.get("model") or chosen[0]
    effort = effort_for(
        model, given.get("effort") or (chosen[1] if model == chosen[0] else None)
    )
    # As the run will check them, now and not once decided (review 2026-10-28 C#9).
    check_choice(
        model_option(model),
        effort,
        given.get("tier"),
        [m["model"] for m in catalog_models()],
    )
    notes = shared_notes.latest(db)
    return {
        **given,
        "draft_write_id": plan.get("write"),
        "revision": plan.get("revision"),
        "model": model,
        "effort": effort,
        "budget_per_image_usd": run_limit(
            db,
            dataset_id,
            plan_basis(db, dataset_id, plan.get("revision"), plan.get("write"))[0],
            (model, effort),
            given.get("budget_per_image_usd"),
        ),
        # The shared notes for every worker AI, the version now (definition 18.15).
        "shared_revision": given.get("shared_revision")
        or (notes["revision"] if notes else None),
    }


def make(
    db,
    dataset_id,
    body: ProposalInput,
    actor,
    agent=None,
    from_event_id=None,
):
    kept = _checked(db, dataset_id, body)
    _no_references_named(db, dataset_id, body.tool, kept)
    stage, step = place(body.tool, kept)
    # The library's decisions are the library's worker's (definition 22.5), a dataset's its
    # worker's (35.1): by the place (48.11).
    agent = (
        agent
        or body.agent
        or worker_at(None if DECISIONS[body.tool].scope == "library" else dataset_id)
    )
    if agent not in AGENTS:
        raise invalid("No such worker")
    # The same decision of the same worker waiting already: that one (an AI asked twice; a box
    # whose ground moved was withdrawn by that write). A person's own decision makes no box
    # (decide_route), so a worker's same box is withdrawn when it runs (user 2026-10-17).
    for row in waiting_boxes(db, dataset_id):
        if (row["tool"], row["agent"]) == (body.tool, agent) and json.loads(
            row["args_json"]
        ) == kept:
            return _box_out(row)
    preview, premise = facts(db, dataset_id, body.tool, kept)
    proposal_id = new_id("prp-")
    with db.transaction():
        db.execute(
            "INSERT INTO proposals(id, dataset_id, bot, tool, args_json, title, reason,"
            " made_by, state, created_at, agent, premise_json, preview_json,"
            " from_event_id, step, chat_id) VALUES(?,?,?,?,?,?,?,?,'open',?,?,?,?,?,?,?)",
            (
                proposal_id,
                dataset_id,
                stage,
                body.tool,
                encoded(kept),
                body.title,
                body.reason,
                actor,
                now(),
                agent,
                encoded(premise),
                encoded(preview),
                from_event_id,
                step,
                _chat(db, dataset_id, agent, from_event_id),
            ),
        )
    made = _box_out(box_row(db, proposal_id))
    from .agent_chat import note_made

    note_made(db, made)
    if body.tool == "run_start":
        # Said with what was made (2026-10-29: the worker said the one replaced still waited).
        made["replaced"] = _replace_older_runs(db, made, actor)
    return made


def _replace_older_runs(db, made, actor):
    """One waiting run of a kind (samples or a run) per dataset (definition 40.1): a worker's new
    one withdraws the one before it, whose images the cards no longer show. The ones withdrawn
    (id, title)."""
    trial = bool(made["args"].get("trial"))
    replaced = []
    for row in waiting_boxes(db, made["dataset_id"]):
        if row["tool"] != "run_start" or row["id"] == made["id"]:
            continue
        if bool(json.loads(row["args_json"]).get("trial")) == trial:
            _withdraw(db, row, {"kind": "replaced", "by": made["id"]}, actor)
            replaced.append({"id": row["id"], "title": row["title"]})
    return replaced


def _chat(db, dataset_id, agent, from_event_id):
    """The chat a box's lines go to: the one it was asked in, else the worker's latest at its
    place (the reception's in the library's talk, definition 22.5, 48.2)."""
    place = dataset_id if AGENTS[agent].place == "dataset" else None
    return event_chat(db, from_event_id) or current_chat(db, place, agent)


def _outdated(db, row):
    """The decision's (preview, premise) now when what it stood on changed, else None. What it
    names gone (a dataset deleted, an image taken out) is a change too: (None, None). One that
    stands on nothing (making a dataset, adding images) never goes out of date."""
    if not row["premise_json"] or json.loads(row["premise_json"]) == {}:
        return None
    try:
        preview, premise = facts(
            db, row["dataset_id"], row["tool"], json.loads(row["args_json"])
        )
    except ApiError:
        return None, None
    return None if premise == json.loads(row["premise_json"]) else (preview, premise)


def _withdraw(db, row, cause, actor, now_shown=None):
    """A waiting box whose ground moved on is withdrawn, saying what moved by name: the plan
    written again (definition 11.10) or what another decision changed first (18.13). One way
    for both; it used to stop as outdated and ask the worker for a remake."""
    outcome = {"withdrawn": "changed", "cause": cause}
    if now_shown is not None:
        outcome["now"] = now_shown
    return _decide(db, row, "withdrawn", actor, outcome)


def _withdraw_changed(db, row, found, actor):
    """What the box stood on changed: what changed, as its type says (box_facts)."""
    preview, premise = found
    if premise is None:
        return _withdraw(db, row, {"kind": "gone"}, actor)
    cause = what_changed(
        db,
        row["dataset_id"],
        row["tool"],
        json.loads(row["args_json"]),
        json.loads(row["premise_json"]),
        premise,
    )
    return _withdraw(db, row, cause, actor, preview)


def workers_answering(db, dataset_id):
    """Whether a worker bound to the dataset is answering or waits to, whichever its role (its
    answer may write the plan): no run is decided meanwhile (definition 11.10, 48.10)."""
    return any(c["bound"] for c in counts(db, dataset_id).values())


def _no_references_named(db, dataset_id, tool, args):
    """A worker's run naming images its plan takes as references is refused, so its box says the
    images that will run (2026-10-29: titled "all 4 images", 3 would run; a person's own decision
    leaves them out unsaid, definition 38.1)."""
    if tool != "run_start":
        return
    named = named_references(
        db,
        dataset_id,
        args.get("image_ids"),
        args.get("revision"),
        args.get("draft_write_id"),
    )
    if named:
        names = image_names(db, named)
        raise invalid(
            "These images are references of the plan, and a run does not annotate them"
            " again: leave them out",
            images=[names.get(i, i) for i in named],
        )


def _no_run_on_held_images(db, dataset_id, tool, args):
    """A run of images another decided run holds is refused before it is decided, so a box
    stays as it was (not failed) and a person's own decision is not kept (definition 18.13)."""
    if tool == "run_start":
        refuse_writing(
            db,
            dataset_id,
            start_targets(
                db,
                dataset_id,
                args.get("image_ids"),
                bool(args.get("trial")),
                args.get("revision"),
                args.get("draft_write_id"),
            ),
        )


def _no_run_while_answering(db, dataset_id, tool):
    if tool == "run_start" and workers_answering(db, dataset_id):
        raise ApiError(
            409,
            "workers_answering",
            "A worker is answering and may write the plan; decide after it answers",
        )


def _plan_still(db, dataset_id, args):
    """A person's own run of a draft write decides the plan as it is: a write the draft has
    moved on from is refused (definition 11.10), the window shows the plan again."""
    from .drafts import draft_write_id

    written = args.get("draft_write_id")
    if written is not None and written != draft_write_id(db, dataset_id):
        raise ApiError(
            409,
            "plan_rewritten",
            "The plan was written again after it was shown; look at it again",
        )


def settle(db):
    """After a write (app.py, definition 19.7): every waiting box whose ground the write moved is
    withdrawn then, saying what moved: the plan written again after a run's box of an older
    write (11.10; a box of a version stays, it points at what does not change), or what the box
    stood on (18.13). The one place boxes are withdrawn when nobody decides them."""
    from .drafts import plan_write_now

    for row in every_waiting_box(db):
        written = json.loads(row["args_json"]).get("draft_write_id")
        if row["tool"] == "run_start" and written is not None:
            now_written = plan_write_now(db, row["dataset_id"])
            if written != now_written:
                _withdraw(
                    db, row, {"kind": "plan", "write_id": now_written}, actors.SERVER
                )
                continue
        found = _outdated(db, row)
        if found is not None:
            _withdraw_changed(db, row, found, actors.SERVER)


def list_proposals(db, dataset_id, agent=None):
    """The open ones, oldest first (the longest waiting is not buried, the kanban research),
    then the last 20 decided, newest first (the decisions' record). No dataset: the library's."""
    if dataset_id is not None:
        dataset_row(db, dataset_id)
    where, params = "dataset_id IS ?", [dataset_id]
    if agent:
        where += " AND agent=?"
        params.append(agent)
    return _listed(db, where, params)


def library_worker_boxes(db):
    """The library's worker's boxes, the library's and those of a dataset it made there: its
    talk shows them in its lines (definition 22.5)."""
    return _listed(db, "agent=?", [worker_at(None)])


def _listed(db, where, params):
    rows = db.execute(
        f"SELECT * FROM proposals WHERE {where} ORDER BY coalesce(decided_at, created_at)"
        " DESC LIMIT 200",
        tuple(params),
    )
    open_ones = sorted(
        (r for r in rows if r["state"] == "open"), key=lambda r: r["created_at"]
    )
    decided = [r for r in rows if r["state"] != "open"][:20]
    return {"proposals": [_shown(db, r) for r in [*open_ones, *decided]]}


def _shown(db, row):
    """A box as read: a waiting run's plan computed now (box_facts.plan_now_of)."""
    out = _box_out(row)
    out["preview"] = plan_now_of(db, out)
    return out


def _decide(db, row, state, actor, outcome=None, changed=None, chat_id=None):
    with db.transaction():
        db.execute(
            "UPDATE proposals SET state=?, decided_at=?, decided_by=?, outcome_json=?,"
            " changed_json=? WHERE id=? AND state IN ('open', 'applying')",
            (
                state,
                now(),
                actor,
                encoded(outcome) if outcome else None,
                encoded(changed) if changed else None,
                row["id"],
            ),
        )
        # Readers may stop the same box at once (found 2026-10-08: two lines "stopped"):
        # only the one that changed it tells.
        won = db.one("SELECT changes()")[0]
    decided = _box_out(box_row(db, row["id"]))
    if won:
        _told(db, decided, chat_id)
    return decided


def _told(db, proposal, chat_id=None):
    """The worker's conversation hears what became of its box (step 24 design 3.7), in the chat
    it was decided in (_told_chat), else the one it was made in."""
    from .agent_chat import note_decided

    note_decided(db, proposal, chat_id)


def _told_chat(db, row, chat_id):
    """The chat a box's end is told in (definition 81; user 2026-10-29: a box made in an earlier
    chat was decided in a later one, and what came of it went to the earlier one): the chat the
    person decided it in when it is its worker's, else the chat its talk shows (its latest)."""
    made = chat_row(db, row["chat_id"])
    if not made:
        return row["chat_id"]
    return chat_of(db, made["dataset_id"], row["agent"], chat_id)


def changes(before, after):
    """The values a person changed: {key: [before, after]} of the keys either sets."""
    return {
        k: [before.get(k), after.get(k)]
        for k in sorted(set(before) | set(after))
        if before.get(k) != after.get(k)
    }


def settle_applying(db):
    """When the server starts: boxes left being applied when it stopped (review 2026-10-28
    B#18: one stayed "applying" for ever, never to be decided). A tool records its decision with
    what it changed, in one transaction: a box whose decision is recorded was carried out and is
    applied as it was decided; any other changed nothing and waits again, as one refused."""
    for row in list(db.execute("SELECT * FROM proposals WHERE state='applying'")):
        done = decisions.of_box(db, row["id"])
        if done is None:
            with db.transaction():
                db.execute(
                    "UPDATE proposals SET state='open' WHERE id=? AND state='applying'",
                    (row["id"],),
                )
            continue
        outcome = json.loads(done["outcome_json"]) if done["outcome_json"] else None
        _decide(db, row, "applied", done["decided_by"], outcome or {"done": True})


def _take(db, proposal_id):
    """The box taken to be applied, by one press only (issue #5-1: two presses at once, the
    band and a "1" in the talk, both ran it): whether this one took it."""
    with db.transaction():
        db.execute(
            "UPDATE proposals SET state='applying' WHERE id=? AND state='open'",
            (proposal_id,),
        )
        return db.one("SELECT changes()")[0] == 1


async def apply_box(request: Request, proposal_id, actor, override=None, chat_id=None):
    db = request.app.state.db
    if not _take(db, proposal_id):
        raise ApiError(409, "proposal_decided", "The proposal is decided already")
    try:
        return await _apply_taken(
            request, box_row(db, proposal_id), actor, override, chat_id
        )
    except BaseException:
        # Refused before it was decided (a worker answering, its images held, wrong values):
        # the box waits again as it was.
        with db.transaction():
            db.execute(
                "UPDATE proposals SET state='open' WHERE id=? AND state='applying'",
                (proposal_id,),
            )
        raise


async def _apply_taken(request, row, actor, override, chat_id=None):
    db = request.app.state.db
    told = _told_chat(db, row, chat_id)
    proposed = json.loads(row["args_json"])
    _no_run_while_answering(db, row["dataset_id"], row["tool"])
    found = _outdated(db, row)
    if found is not None:
        _withdraw_changed(db, row, found, actor)
        raise ApiError(
            409,
            "proposal_withdrawn",
            "What the proposal was based on changed after it was made; it was withdrawn",
        )
    fixed = [
        k for k in FIXED if k in (override or {}) and override[k] != proposed.get(k)
    ]
    if row["tool"] == "run_start" and fixed:
        # A worker's box is its plan: another plan is another box.
        raise ApiError(
            422,
            "box_fixed",
            "The plan of a worker's box is fixed; ask the worker for a new box",
            {"fields": fixed},
        )
    used = with_dataset(
        row["tool"], {**proposed, **(override or {})}, row["dataset_id"]
    )
    args = _valid_args(row["tool"], used)
    taken = args.model_dump(mode="json", by_alias=True)
    _no_run_on_held_images(db, row["dataset_id"], row["tool"], taken)
    changed = changes(proposed, taken) if override else None
    headers = {**actors.headers_of(actor), "X-Annotation-Proposal": row["id"]}
    try:
        kept = await _carry_out(request, row["tool"], args, headers)
    except httpx.HTTPStatusError as exc:
        # The API's own refusal, as it said it (a run going, nothing to save…).
        error = exc.response.json().get("error", {})
        _decide(
            db,
            row,
            "failed",
            actor,
            {"error": error.get("code"), "message": error.get("message")},
            changed,
            told,
        )
        raise _refused(exc) from exc
    if row["tool"] == "run_start" and kept.get("id"):
        # The run is of the worker that made the box: its end is told where it was decided.
        tell_run_in(db, kept["id"], row["agent"], told)
    return _decide(db, row, "applied", actor, kept or {"done": True}, changed, told)


async def _carry_out(request, tool, args, headers):
    """A decision carried out by its tool through the HTTP API, with the headers of who decides
    (and of the box applied), so the tool's input rules and the server's checks hold as when the
    AI calls it (step 22). What came of it, as the screen shows it."""
    transport = httpx.ASGITransport(app=request.app)
    async with httpx.AsyncClient(
        transport=transport, base_url=config.INSIDE, timeout=None
    ) as http:

        async def ask_api(method, path, allow=(), **kwargs):
            response = await http.request(
                method, kept_in_place(path), headers=headers, **kwargs
            )
            if response.status_code not in allow:
                response.raise_for_status()
            return response

        async def view(*_):
            raise ApiError(422, "invalid_input", "A decision does not make views")

        data, _ = await run_tool(tool, args, ask_api, ask_api, view, view)
    kept = {
        k: data[k] for k in ("id", "name", "status", "count", "revision") if k in data
    }
    if tool == "run_start" and data.get("instruction_revision"):
        # The version it ran (a box's preview only foresaw it).
        kept["revision"] = data["instruction_revision"]
    if tool == "run_start" and data.get("number"):
        kept["number"] = data["number"]
    if data.get("skipped"):
        # The files a dataset was made without, and why (definition 76; 2026-10-29: 11 files
        # made 9 images, and the talk could not say why).
        kept["skipped"] = [
            {
                "name": Path(s["path"]).name,
                "reason": s["reason"],
                **({"as": s["as"]} if s.get("as") else {}),
            }
            for s in data["skipped"][:50]
        ]
    if data.get("image_ids"):
        # Which images it was of, by name (Sol 2026-10-08: the worker asked the person
        # which one it had just taken).
        names = image_names(request.app.state.db, data["image_ids"])
        kept["images"] = [names.get(i, i) for i in data["image_ids"]]
    return kept


def _refused(exc):
    error = exc.response.json().get("error", {})
    return ApiError(
        exc.response.status_code,
        error.get("code", "apply_failed"),
        error.get("message", "The decision could not be carried out"),
        error.get("details"),
    )


def _made_by_request(request, dataset_id, body):
    """An AI worker's proposal (through its MCP tool): the worker and the message it answers
    come from the headers the server gave its CLI, not from what it wrote."""
    agent = request.headers.get("x-annotation-agent")
    job = request.headers.get("x-annotation-job")
    db = request.app.state.db
    asked = None
    if job:
        found = job_row(db, job)
        asked = found["request_event_id"] if found else None
    return make(db, dataset_id, body, who_of(request), agent=agent, from_event_id=asked)


@router.post("/datasets/{dataset_id}/proposals", status_code=201)
def make_route(request: Request, dataset_id: str, body: ProposalInput):
    return _made_by_request(request, dataset_id, body)


@router.post("/library/proposals", status_code=201)
def make_library_route(request: Request, body: ProposalInput):
    """A decision of the library made ready (making, deleting a dataset; definition 22.5)."""
    return _made_by_request(request, None, body)


@router.get("/library/proposals")
def list_library_route(request: Request):
    return library_worker_boxes(request.app.state.db)


@router.post("/datasets/{dataset_id}/proposals/preview")
def preview_route(request: Request, dataset_id: str, body: ProposalInput):
    """What a person's own decision would do, before it is done (nothing is kept): the same
    facts a box shows (user 2026-10-13: a person's press is not put in the line to decide
    again; it is checked once where it was pressed)."""
    db = request.app.state.db
    kept = _checked(db, dataset_id, body)
    preview, _ = facts(db, dataset_id, body.tool, kept)
    return {"tool": body.tool, "args": kept, "preview": preview, "title": body.title}


@router.post("/datasets/{dataset_id}/decisions", status_code=201)
async def decide_route(
    request: Request, dataset_id: str, body: ProposalInput, chat: int | None = None
):
    """A person's own decision (user 2026-10-13: never left waiting): checked as a box is, done
    by its tool as the person, recorded as a decision with no proposal (definition 21.3: only a
    worker's box waits for a person), and told in the conversation of the place's worker, a
    run's end too, as a box's is."""
    if request.headers.get("x-annotation-agent"):
        raise ApiError(403, "agent_scope", "A worker proposes; only a person decides")
    db = request.app.state.db
    who = who_of(request)
    _no_run_while_answering(db, dataset_id, body.tool)
    if body.tool == "run_start":
        _plan_still(db, dataset_id, body.args)
    _no_run_on_held_images(db, dataset_id, body.tool, body.args)
    kept = _checked(db, dataset_id, body)
    decision_id = new_id("dec-")
    headers = {**actors.headers_of(who), "X-Annotation-Decision": decision_id}
    try:
        outcome = await _carry_out(
            request, body.tool, _valid_args(body.tool, kept), headers
        )
    except httpx.HTTPStatusError as exc:
        raise _refused(exc) from exc
    # The dataset's worker's talk hears it (definition 35.1), as of a box decided there: the
    # chat it was decided in (chat), else its latest.
    agent = worker_at(dataset_id)
    chat_id = chat_of(db, dataset_id, agent, chat)
    if body.tool == "run_start" and outcome.get("id"):
        tell_run_in(db, outcome["id"], agent, chat_id)
    decision = {
        **decisions.get_decision(db, decision_id),
        "title": body.title,
        "outcome": outcome,
    }
    from .agent_chat import note_own_decision

    note_own_decision(db, dataset_id, decision, agent, chat_id)
    return decision


@router.get("/datasets/{dataset_id}/proposals")
def list_proposals_route(request: Request, dataset_id: str, agent: str | None = None):
    return list_proposals(request.app.state.db, dataset_id, agent)


@router.get("/proposals/{proposal_id}")
def get_proposal_route(request: Request, proposal_id: str):
    db = request.app.state.db
    return _shown(db, box_row(db, proposal_id))


@router.post("/proposals/{proposal_id}/apply")
async def apply_route(
    request: Request,
    proposal_id: str,
    body: ApplyInput | None = None,
    chat: int | None = None,
):
    """chat: the chat it is decided in (definition 81), told what came of it."""
    if request.headers.get("x-annotation-agent"):
        raise ApiError(403, "agent_scope", "Only a person applies a proposal")
    override = body.args if body else None
    return await apply_box(request, proposal_id, who_of(request), override, chat)


def decline(db, proposal_id, actor, chat_id=None):
    """A person does not do it (［しない］, and closing the person's turns, definition 44.2):
    the box closed, nothing changed, its worker told (in the chat it was declined in)."""
    row = box_row(db, proposal_id)
    if row["state"] != "open":
        raise ApiError(409, "proposal_decided", "The proposal is decided already")
    return _decide(db, row, "declined", actor, chat_id=_told_chat(db, row, chat_id))


@router.post("/proposals/{proposal_id}/decline")
def decline_route(request: Request, proposal_id: str, chat: int | None = None):
    if request.headers.get("x-annotation-agent"):
        raise ApiError(403, "agent_scope", "Only a person declines a proposal")
    return decline(request.app.state.db, proposal_id, who_of(request), chat)


@router.post("/proposals/{proposal_id}/seen")
def seen_route(request: Request, proposal_id: str):
    """A person saw a failed or outdated box: it no longer counts as trouble."""
    db = request.app.state.db
    row = box_row(db, proposal_id)
    with db.transaction():
        db.execute(
            "UPDATE proposals SET seen_at=? WHERE id=? AND seen_at IS NULL",
            (now(), row["id"]),
        )
    return _box_out(box_row(db, row["id"]))

"""Questions with values (definition 26.4): a worker asks about an item of the plan with up to
four options, each with the plan as it would be once chosen or the place it starts again from
(33.3); the server checks each option when the question is made and keeps what it stood on, and a
person's answer writes that plan as the person's own write, starts the draft again from that
place, or adds the word they said to a label of the library. What a person changes on the right is
told in the steward's chat. The interview starts by itself when the plan has nothing yet:
with a plan of these images in other datasets or a draft, the server asks how the plan is made
(34.2: which existing plan, as it is or changed; options whose next is the server's own question
wake no worker), else the worker asks what is wanted. A question has up to three options; the
screen adds "other" (34.3).
"""

import json

from fastapi import APIRouter, Request
from pydantic import Field, ValidationError

from . import actors
from .agent_chat import (
    add,
    ask,
    close_event,
    current_chat,
    jobs_of,
    language_of,
    last_line,
    line_at,
    place_of,
    question_lines,
    renote,
    unsay,
)
from .agents import worker_at
from .datasets import dataset_row, image_count
from .db import now
from .draft_diff import plan_changes
from .drafts import BLANK, draft_write_id, plan_of, start_plan, write_plan
from .errors import ApiError, Model, not_found
from .instructions import (
    INPUT,
    InstructionInput,
    check_definitions,
    get_instruction,
    latest_revision,
    requirement_key,
)
from .label_library import add_alias, with_library
from .past_requirements import past_requirements
from .plan_state import ITEMS, plan_state

router = APIRouter(prefix="/v1")
# A question's options; the screen adds "other" after them (user 2026-10-21: "選択肢は最大でも
# ４つ、できれば、２－３個", definition 34.3).
OPTIONS = 3


def question_schema():
    """A worker's question in its answer: the item it decides and its options."""
    nullable = lambda body: {"anyOf": [body, {"type": "null"}]}
    return {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "item": nullable({"type": "string", "enum": list(ITEMS)}),
            "options": {
                "type": "array",
                "maxItems": OPTIONS,
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "recommend": {"type": "boolean"},
                        # The parts of the plan it sets, as a JSON object (text,
                        # label_definitions, leave_out); the rest stays. References are
                        # results chosen with reference_set (definition 38.1).
                        "plan": nullable({"type": "string"}),
                        "alias": nullable(
                            {
                                "type": "object",
                                "properties": {
                                    "label_id": {"type": "string"},
                                    "word": {"type": "string"},
                                },
                                "required": ["label_id", "word"],
                                "additionalProperties": False,
                            }
                        ),
                        # Where the draft starts again from instead (33.3): blank, a version
                        # of this dataset, another dataset's version.
                        "start": nullable(
                            {
                                "type": "object",
                                "properties": {
                                    "kind": {
                                        "type": "string",
                                        "enum": ["blank", "version", "other"],
                                    },
                                    "dataset_id": nullable({"type": "string"}),
                                    "revision": nullable({"type": "integer"}),
                                },
                                "required": ["kind", "dataset_id", "revision"],
                                "additionalProperties": False,
                            }
                        ),
                    },
                    "required": ["label", "recommend", "plan", "alias", "start"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["text", "item", "options"],
        "additionalProperties": False,
    }


def valued(db, dataset_id, question):
    """(the question's data, the options dropped with why): each option's plan made whole from
    the plan now and checked as a draft write is, or the place it starts again from checked to
    be there; what the question stands on. The library has no plan: its options carry words
    only (definition 48.5)."""
    if dataset_id is None:
        kept, dropped = [], []
        for option in question["options"][:OPTIONS]:
            if option.get("plan") or option.get("start"):
                dropped.append(
                    {"label": option["label"], "reason": "the library has no plan"}
                )
            else:
                kept.append(option)
        return {"item": None, "options": kept, "premise": None}, dropped
    state = plan_state(db, dataset_id)
    base = state["plan"] or BLANK
    kept, dropped = [], []
    for option in question["options"][:OPTIONS]:
        plan = None
        if option.get("plan"):
            try:
                parts = json.loads(option["plan"])
                if "references" in parts:
                    raise ValueError(
                        "an option does not set references: choose them with reference_set"
                    )
                body = InstructionInput.model_validate(
                    {k: parts.get(k, base[k]) for k in INPUT}
                )
                plan = body.model_dump(mode="json")
                check_definitions(plan["label_definitions"])
                plan = with_library(db, plan, base["label_definitions"])
                # The requirement it sets: the right's card of it takes its number (34.3).
                option = {**option, "key": requirement_key(plan["label_definitions"])}
            except (ValueError, AttributeError, ValidationError, ApiError) as exc:
                dropped.append({"label": option["label"], "reason": str(exc)[:300]})
                continue
        start = option.get("start")
        if start is not None:
            try:
                if plan is not None:
                    raise ValueError("an option sets a plan or a start, not both")
                start = _start_of(db, dataset_id, start)
            except (ValueError, ApiError) as exc:
                reason = exc.message if isinstance(exc, ApiError) else str(exc)
                dropped.append({"label": option["label"], "reason": reason[:300]})
                continue
        kept.append({**option, "plan": plan, "start": start})
    data = {
        "item": question.get("item"),
        "options": kept,
        "premise": {"write_id": state["write_id"], "revision": state["revision"]},
    }
    return data, dropped


def _start_of(db, dataset_id, start):
    """A place to start the draft again from, checked to be there (drafts.start_plan's form):
    blank, a version of this dataset, or another dataset's version."""
    kind = start["kind"]
    if kind == "blank":
        return {"kind": "blank"}
    source = dataset_id if kind == "version" else start.get("dataset_id")
    if kind == "other" and (not source or source == dataset_id):
        raise ValueError(
            "other starts from another dataset's plan: give its dataset_id"
        )
    if start.get("revision") is None:
        raise ValueError("give the version (revision) to start from")
    version = get_instruction(db, source, str(start["revision"]))
    found = {"kind": kind, "revision": version["revision"]}
    return {**found, "dataset_id": source} if kind == "other" else found


def _option(label, say, values=None, recommend=False, start=None, ask=None, key=None):
    """An option of the server's own question: label in words for the worker that reads the
    talk, say and values for the screen's words (its language), and what choosing it does."""
    return {
        "label": label,
        "say": say,
        "values": values or {},
        "recommend": recommend,
        "plan": None,
        "alias": None,
        "start": start,
        "ask": ask,
        "key": key,
    }


def _entry(db, dataset_id, step, key=None):
    """The server's question of the plan's entry (34.2): (text, options, what the right shows),
    or None when there is nothing to choose. how: an existing plan of these images, a new one,
    or the draft; which: the existing plans, the most annotated first; keep: that plan as it
    is or changed, both starting the draft from it."""
    existing = past_requirements(db, dataset_id, with_objects=False)["requirements"]
    if step == "how":
        # The one recommended first: the draft being made, else an existing plan, else new.
        draft = draft_write_id(db, dataset_id) is not None
        options = []
        if draft:
            options.append(_option("Go on from the draft", "draft", recommend=True))
        if existing:
            options.append(
                _option(
                    "Use an existing plan of these images",
                    "use",
                    {"count": len(existing)},
                    recommend=not draft,
                    ask={"step": "which"},
                )
            )
        options.append(
            _option("Make a new plan", "new", recommend=not (draft or existing))
        )
        if len(options) == 1:
            return None
        return "How is this plan made?", options, {"count": len(existing)}
    total = image_count(db, dataset_id)
    if step == "which":
        options = [
            _option(
                f"Existing plan {n}: {', '.join(l['name'] for l in r['labels'])}"
                f" ({r['images']}/{total} images annotated)",
                "plan",
                {"n": n, "done": r["images"], "total": total, "labels": r["labels"]},
                recommend=n == 1,
                ask={"step": "keep", "key": r["requirement_key"]},
                key=r["requirement_key"],
            )
            for n, r in enumerate(existing[:OPTIONS], 1)
        ]
        # More plans than options: the rest are said to be on the right (the workers' tests
        # 2026-10-29: "4 existing plans" with three to choose).
        return (
            "Which existing plan is used?",
            options,
            {"count": len(existing), "shown": len(options)},
        )
    found = [(n, r) for n, r in enumerate(existing, 1) if r["requirement_key"] == key]
    if not found:
        raise ApiError(409, "plan_gone", "That existing plan is no longer there")
    n, r = found[0]
    start = _start_of(
        db,
        dataset_id,
        {
            "kind": "other",
            "dataset_id": r["plan"]["dataset_id"],
            "revision": r["plan"]["revision"],
        },
    )
    return (
        f"How is existing plan {n} used?",
        [
            _option(
                f"Use existing plan {n} as it is",
                "as_is",
                {"n": n},
                recommend=True,
                start=start,
                key=key,
            ),
            _option(
                f"Use existing plan {n} with changes",
                "change",
                {"n": n},
                start=start,
                key=key,
            ),
        ],
        {"n": n, "key": key},
    )


def ask_entry(db, dataset_id, step, chat_id, key=None):
    """The server asks a question of the plan's entry in the steward's chat (no worker
    waited for); False when there is nothing to choose."""
    found = _entry(db, dataset_id, step, key)
    if found is None:
        return False
    text, options, entry = found
    state = plan_state(db, dataset_id)
    add(
        db,
        dataset_id,
        worker_at(dataset_id),
        "question",
        text,
        by_actor=actors.SERVER,
        chat_id=chat_id,
        data={
            "item": None,
            "entry": {"step": step, **entry},
            "options": options,
            "premise": {"write_id": state["write_id"], "revision": state["revision"]},
        },
    )
    return True


class AnswerInput(Model):
    option: int
    # The option's words as the screen showed them (the server's own questions are worded by
    # the screen, in the person's language): the person's line.
    words: str | None = Field(None, max_length=500)


def answer(jobs, dataset_id, agent, event_id, index, by, words=None, lang=None):
    """A person chose an option of a question: its plan written as theirs (or the draft started
    again from its place), its word added to its label, the question closed, and the option's
    words (as the screen showed them) sent on to the worker, or, when the option's next is the
    server's own question, said in the talk with that question after it (34.2). Writing the
    plan is refused when the plan changed since it was asked."""
    db = jobs.db
    if dataset_id:
        dataset_row(db, dataset_id)
    row = line_at(db, event_id, dataset_id, agent)
    if row is None or row["kind"] != "question":
        raise not_found("Question")
    data = json.loads(row["data_json"] or "{}")
    if row["closed_at"]:
        if data.get("stale"):
            raise ApiError(409, "question_stale", "The plan changed since it was asked")
        raise ApiError(409, "question_closed", "The question is answered or set aside")
    options = data.get("options") or []
    if not 0 <= index < len(options):
        raise ApiError(
            422, "invalid_input", "No such option", {"options": len(options)}
        )
    option = options[index]
    # An option that writes the plan is refused when the plan changed since it was asked.
    if option["plan"] or option.get("start"):
        state = plan_state(db, dataset_id)
        if data["premise"] != {
            "write_id": state["write_id"],
            "revision": state["revision"],
        }:
            data["stale"] = True
            close_event(db, event_id, data)
            raise ApiError(409, "question_stale", "The plan changed since it was asked")
    with db.transaction():
        if option["plan"]:
            write_plan(
                db,
                dataset_id,
                lambda plan: {
                    **option["plan"],
                    # Chosen by their own entries (definition 38.1): the plan's stay.
                    "references": plan["references"] if plan else [],
                },
                by,
                from_event_id=event_id,
            )
        if option.get("start"):
            start_plan(db, dataset_id, option["start"], by, from_event_id=event_id)
        if option["alias"]:
            add_alias(db, option["alias"]["label_id"], option["alias"]["word"], by)
        data["answered"] = {"option": index, "by": by, "at": now()}
        close_event(db, event_id, data)
    said = (words or "").strip() or option["label"]
    if option.get("ask"):
        add(
            db,
            dataset_id,
            agent,
            "human",
            said,
            by_actor=by,
            data={"answer_to": event_id, **({"lang": lang} if lang else {})},
            chat_id=row["chat_id"],
        )
        ask_entry(
            db,
            dataset_id,
            option["ask"]["step"],
            row["chat_id"],
            option["ask"].get("key"),
        )
        return {"asked": option["ask"]["step"]}
    return ask(
        jobs,
        dataset_id,
        agent,
        said,
        by,
        data={"answer_to": event_id},
        chat_id=row["chat_id"],
        lang=lang,
    )


def outdate_questions(db, dataset_id, answered=None):
    """The plan was written: the open questions whose options write the plan stood on the plan
    before, so they close as stale (as a box whose premise changed is withdrawn;
    the person sees why under the question). answered: the question the write answers."""
    for row in question_lines(db, dataset_id):
        data = json.loads(row["data_json"] or "{}")
        if (
            row["closed_at"]
            or row["id"] == answered
            or not any(
                o.get("plan") or o.get("start") for o in data.get("options") or []
            )
        ):
            continue
        data["stale"] = True
        close_event(db, row["id"], data)


def tell_right(db, dataset_id, before_at, after):
    """A person changed the plan on the right (not by an answer): one line in the steward's
    chat with what changed since before (before_at: where the plan was, drafts.plan_at); while
    nothing else is said there, the same line."""
    chat_id = current_chat(db, dataset_id, worker_at(dataset_id))
    last = last_line(db, chat_id)
    data = json.loads(last["data_json"] or "{}") if last else {}
    if last and last["kind"] == "note" and data.get("note") == "right":
        base = data["base"]
    else:
        last = None
        base = before_at or None
    changes = plan_changes(
        plan_of(db, dataset_id, base.get("revision"), base.get("write"))
        if base
        else None,
        after,
    )
    if last is not None:
        if changes is None:
            unsay(db, last["id"])
        else:
            renote(db, last["id"], {**data, "changes": changes})
    elif changes is not None:
        add(
            db,
            dataset_id,
            worker_at(dataset_id),
            "note",
            "right",
            by_actor=actors.PERSON,
            data={"note": "right", "base": base, "changes": changes},
            chat_id=chat_id,
        )


def start_interview(jobs, dataset_id, lang=None):
    """The plan's entry, when the dataset has no version and the steward's chat no line:
    the server asks how the plan is made (34.2), or, with nothing to choose from (no existing
    plan, no draft), the steward asks first. Else nothing. Called whenever the plan's
    screen opens."""
    db = jobs.db
    dataset_row(db, dataset_id)
    if latest_revision(db, dataset_id) is not None:
        return {"started": False}
    chat_id = current_chat(db, dataset_id, worker_at(dataset_id))
    if last_line(db, chat_id) is not None:
        return {"started": False}
    if ask_entry(db, dataset_id, "how", chat_id):
        return {"started": True, "asked": "how"}
    event_id = add(
        db,
        dataset_id,
        worker_at(dataset_id),
        "note",
        "Start the interview: the plan has nothing yet.",
        data={"note": "interview", **({"lang": lang} if lang else {})},
        chat_id=chat_id,
    )
    job = jobs.enqueue(
        dataset_id, worker_at(dataset_id), "answer_heavy", "interview", event_id
    )
    return {"started": True, "job_id": job["id"]}


@router.post(
    "/datasets/{dataset_id}/agents/{agent}/events/{event_id}/answer", status_code=202
)
@router.post("/library/agents/{agent}/events/{event_id}/answer", status_code=202)
def answer_route(request: Request, agent: str, event_id: int, body: AnswerInput):
    if request.headers.get("x-annotation-agent"):
        raise ApiError(403, "agent_scope", "Only a person answers a question")
    return answer(
        jobs_of(request),
        place_of(request),
        agent,
        event_id,
        body.option,
        actors.who_of(request),
        body.words,
        language_of(request),
    )


@router.post("/datasets/{dataset_id}/plan/interview")
def interview_route(request: Request, dataset_id: str):
    if request.headers.get("x-annotation-agent"):
        raise ApiError(403, "agent_scope", "The plan's screen starts the interview")
    return start_interview(jobs_of(request), dataset_id, language_of(request))

"""A worker's answers (step 24 design 3.5), each a job of the line of work.

Each chat has the worker's own CLI kept running (residents.py, definition 27) with only its
tools, bound to the dataset and the chat by the MCP connection's headers (authority.py); it
proposes through proposal_make and never changes anything itself (logs/scope-check, the second
level). Every line of the person goes to it (definition 28; a quick answer of a fast model
before it was let go, user 2026-10-20: it passed 7 lines of 10 on and took their time, and
answered some it was asked to look at).
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import library_here
from .agent_chat import (
    LINES_WORDS,
    add,
    changes_since,
    chat_language,
    last_answer,
    line,
    reopen_question,
    worker_lines,
)
from .agents import AGENTS, NOT_HERE_WORDS, workers
from .codex_execution import selected_execution_settings
from .costs import api_cost
from .datasets import dataset_row, dataset_rows
from .drafts import plan_at, plan_facts, plan_of
from .errors import ApiError
from .gallery import gallery
from .handoff import handoff
from .jobs import keep_said
from .notes import latest_notes
from .object_types import check_show, show_schema, show_words
from .past_requirements import past_requirements
from .plan_questions import question_schema, valued
from .progress import progress
from .proposals import list_proposals, made_boxes, waiting_boxes
from .run_inputs import last_choice
from .screen_words import LANGUAGE, words
from .settings import read_settings
from .shared_notes import worker_gets

logger = logging.getLogger("agent_app.agent_answer")
# The screen's words and what a show may say, from their one places (issue #3 U-14).
RULES = (
    (Path(__file__).parent / "agent_prompt.yaml")
    .read_text(encoding="utf-8")
    .replace("{words}", words())
    .replace("{show}", show_words())
    .replace("{lines}", LINES_WORDS)
    .replace("{language}", LANGUAGE)
    .replace("{not_here}", NOT_HERE_WORDS)
)
MAX_IMAGES = 200


def shown(db, dataset_id, show):
    """A worker's show for its line, checked and counted (types design 3.2); ApiError when
    refused."""
    found = check_show(db, dataset_id, show)
    # The images judged by the plan of when it is said (35.7), so the line shows them so later;
    # a plan named (a write, a version, a blank one, 49.1) is kept.
    where = found["where"]
    if found["type"] == "image" and not (
        {"write", "revision"} & where.keys() or where.get("blank")
    ):
        found["where"] = {**found["where"], **plan_at(db, dataset_id)}
    return found


def _nullable(body):
    return {"anyOf": [body, {"type": "null"}]}


def answer_schema(agent):
    """A worker's answer (definition 48.3): one form, its kinds the worker's. A dataset's worker
    shows a set of things on the right; the library's opens a place."""
    worker = AGENTS[agent]
    text = {"type": "string"}
    properties = {
        "kind": {"type": "string", "enum": list(worker.kinds)},
        "message": text,
        "question": _nullable(question_schema()),
        # A request for another worker (definition 36.7): a dataset's names its dataset.
        "handoff": _nullable(
            {
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "enum": [k for k in AGENTS if k != agent],
                    },
                    "dataset_id": _nullable(text),
                    "summary": text,
                    # The person asked for it already: handed at once.
                    "now": {"type": "boolean"},
                },
                "required": ["agent", "dataset_id", "summary", "now"],
                "additionalProperties": False,
            }
        ),
        # Waiting proposals made before that the answer is about (their links on the line;
        # 10-09: "the save proposal waits" had no way to it).
        "boxes": {"type": "array", "items": text},
    }
    if worker.place == "dataset":
        # A set of things to show on the right (types design 3.1).
        properties["show"] = _nullable(show_schema())
    if "open" in worker.kinds:
        properties["open"] = _nullable(
            {
                "type": "object",
                "properties": {
                    "dataset_id": text,
                    "stage": _nullable(
                        {"type": "string", "enum": list(library_here.STAGES)}
                    ),
                    "image": _nullable(text),
                    "now": {"type": "boolean"},
                },
                "required": ["dataset_id", "stage", "image", "now"],
                "additionalProperties": False,
            }
        )
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


IMAGE_STATES = {
    "result": "annotated and used for training (アノテーション済み・学習に使う)",
    "detected": "annotated (アノテーション済み)",
    "not_detected": "annotated, nothing found (アノテーション済み・物なし)",
    "excluded": "left out of training (学習に使わない); it may still have annotations",
    "stale": "has annotations only of an earlier requirement (the labels changed since); the"
    " screen says ラベルが今と違う版の結果だけ (the card names the version of its result: 第2版の結果だけ for version 2; 2026-10-29: 「第n版」 was said as written); for the plan now it is not annotated yet, and it is"
    " in the set アノテーションの無い to annotate",
    "no_result": "never annotated (アノテーションの無い)",
    "failed": "the last annotation failed (失敗した)",
    "interrupted": "the last annotation was stopped before it ended, by its cost cap or a person"
    " (中断; not a failure)",
    "running": "being annotated now (アノテーション中)",
    "pending": "waiting to be annotated",
}


def _training(db, dataset_id):
    """What training uses now (Sol 2026-10-13: the worker could not say how many images it
    held, while the screen showed it)."""
    from .training import training_state

    found = training_state(db, dataset_id)
    return {
        "used_now": found["used"],
        "images": found["images"],
        # No fixing (user 2026-10-15): what is chosen is what training uses, recorded when
        # training or an export starts.
        "words": "used_now is 学習に使う, what training uses as it is; nothing to fix",
    }


def _objects_held(annotations):
    """Objects per label and how many attribute values are filled, for one image."""
    if not annotations:
        return {}
    labels = {}
    for a in annotations:
        labels[a["label"]] = labels.get(a["label"], 0) + 1
    values = sum(
        1
        for a in annotations
        for v in (a.get("attributes") or {}).values()
        if v not in (None, "")
    )
    return {"objects": labels, "values_read": values}


def dataset_context(db, dataset_id, agent):
    """What the worker's screen shows, and nothing else (need-only context). The chat's lines
    are the answer path's (worker_lines)."""
    found = {
        "dataset_id": dataset_id,
        # Its name too (Sol 2026-10-12: a request handed over from the library named the dataset,
        # and the worker said it could not tell whether it was this one).
        "dataset": dataset_row(db, dataset_id)["name"],
        # Its number, as #number names it (definition 61; 75: #29 was read as an image's name).
        "number": dataset_row(db, dataset_id)["number"],
        "map": progress(db, dataset_id),
        "workers": workers(),
        "changes": changes_since(db, dataset_id, agent),
        "notes": [
            {"by": n["agent"], "text": n["text"]} for n in latest_notes(db, dataset_id)
        ],
    }
    # Judged by the plan now (the draft, else the latest version): the plan worked on (36.1).
    items = gallery(db, dataset_id, "production", plan_of(db, dataset_id))["items"][
        :MAX_IMAGES
    ]
    names = {i["image"]["id"]: i["image"]["name"] for i in items}
    model, effort, _ = last_choice(db, dataset_id)
    # Every waiting box of the dataset, with the worker that made it (loose roles: any worker
    # may answer about any box).
    boxes = [
        p for p in list_proposals(db, dataset_id)["proposals"] if p["state"] == "open"
    ]
    return {
        **found,
        "images": [
            {
                "name": i["image"]["name"],
                "state": i["badge"].get("inspect") or i["badge"].get("kind"),
                # What its annotation holds (Astra 2026-10-15: asked how many boxes and values,
                # the worker said it was not in what it had): objects per label, values read.
                **_objects_held(i.get("annotations") or []),
                **({"left_out": True} if i["image"].get("excluded") else {}),
            }
            for i in items
        ],
        # What each image state means, in the screen's words (Sol 2026-10-13: the worker said
        # the images marked "前の要求の結果だけ" had no results, and named other images).
        "image_states": IMAGE_STATES,
        "training": _training(db, dataset_id),
        # The plan's record (types design 20.3): versions, trials, and what changed since the
        # last trial, so "what is different from when we tried" is answered from it.
        "plan": plan_facts(db, dataset_id),
        # What other datasets annotated these images for (definition 26.5; Astra 2026-10-20:
        # asked to see them, the quick answer said there were none).
        "earlier_requirements": {
            "count": len(past_requirements(db, dataset_id)["requirements"]),
            "words": "the existing plans of these images (既存計画: what other datasets"
            " annotated or planned them for); show type requirement shows them on the right",
        },
        "last_run": {"model": model, "effort": effort} if model else None,
        "open_boxes": [
            {
                "id": p["id"],
                "title": p["title"],
                "tool": p["tool"],
                "made_by": p["agent"],
                "stage": p["stage"],
                "images": [names.get(i, i) for i in p["args"].get("image_ids") or []],
            }
            for p in boxes
        ],
    }


# Said to the worker when the server cannot use parts of its answer (definition 68.2).
ANSWER_AGAIN = (
    "The server could not use these parts of your answer: {problems}. Give the same answer"
    " again (make no box and write nothing again) with those parts mended as said, or left"
    " out."
)


# A dataset named as the screen names it (definition 61): #number「name」.
NAMED = re.compile(r"#(\d+)\s*[「『]([^」』]+)[」』]")


def _words(said):
    """Every text of an answer the person reads: its message, its question and options, what
    it hands over."""
    question = said.get("question") or {}
    return [
        said.get("message") or "",
        question.get("text") or "",
        *(o.get("label") or "" for o in question.get("options") or []),
        (said.get("handoff") or {}).get("summary") or "",
    ]


def misnamed(db, said):
    """The datasets an answer names by a number and a name that do not go together (2026-10-29:
    "#34「確かめ 段ボール」", #34 being 確かめ 順番): [{number, said, name}]."""
    names = {r["number"]: r["name"] for r in dataset_rows(db)}
    found = {}
    for text in _words(said):
        for number, name in NAMED.findall(text):
            right = names.get(int(number))
            if right is not None and name != right:
                found[(int(number), name)] = right
    return [{"number": n, "said": s, "name": right} for (n, s), right in found.items()]


def usable(db, place, agent, said, job=None):
    """What of a worker's answer the server can use, made ready for its lines, and the parts it
    cannot with why (definition 68.2): (ready, problems)."""
    worker = AGENTS[agent]
    kind = said.get("kind")
    ready, problems = {}, []

    def cannot(part, why, **more):
        problems.append({"part": part, **more, "why": why})

    if worker.place == "dataset" and said.get("show"):
        try:
            ready["show"] = shown(db, place, said["show"])
        except ApiError as exc:
            cannot(
                "show",
                f"{exc.message} {json.dumps(exc.details, ensure_ascii=False)}".strip(),
            )
    for part in ("question", "handoff", "open"):
        if said.get(part) and kind != part:
            cannot(
                part, f"given with kind={kind}: give kind={part} for it, or {part} null"
            )
        elif kind == part and not said.get(part):
            cannot(part, f"kind={part} needs {part}")
    known = {r["id"] for r in dataset_rows(db)}
    if kind == "question" and said.get("question"):
        ready["question"], dropped = valued(db, place, said["question"])
        for d in dropped:
            cannot("option", d["reason"], label=d["label"])
    elif kind == "handoff" and said.get("handoff"):
        offer = said["handoff"]
        to = AGENTS.get(offer.get("agent"))
        if to is None or to.key == agent:
            cannot(
                "handoff",
                "hand it to another worker: agents are "
                + ", ".join(k for k in AGENTS if k != agent),
            )
        elif to.place == "dataset" and offer.get("dataset_id") not in known:
            cannot("handoff", "dataset_id is not a dataset of the library")
        else:
            ready["handoff"] = offer
    elif kind == "open" and said.get("open"):
        try:
            ready["open"] = library_here.where_to(db, said["open"], known)
        except (ValueError, ApiError) as exc:
            cannot("open", exc.message if isinstance(exc, ApiError) else str(exc))
    # A box it made withdrawn within the answer (a later write of its own moved the plan it held,
    # or what it stood on changed): it says the box is ready, and none waits (definition 76;
    # 2026-10-29: the samples' box was withdrawn by the plan it wrote after it). One made again
    # after it (its own remaking, or asked again) is no problem: the new one waits.
    if job is not None:
        boxes = made_boxes(db, job, agent)
        for box in boxes:
            # Made again after it (the same decision waits): no problem.
            again = any(
                b["tool"] == box["tool"]
                and b["state"] == "open"
                and b["created_at"] > box["created_at"]
                for b in boxes
            )
            cause = json.loads(box["outcome_json"] or "{}").get("cause") or {}
            if box["state"] == "withdrawn" and not again:
                cannot(
                    "box",
                    f"your decision 「{box['title']}」 was withdrawn ({json.dumps(cause)}):"
                    " make it again of what is now, after your writes of the plan",
                    title=box["title"],
                )
    # A dataset named by a number and another's name: the words go to the person as they are,
    # so the worker says them again (definition 73).
    for wrong in misnamed(db, said):
        cannot(
            "name",
            f"#{wrong['number']} is 「{wrong['name']}」, not 「{wrong['said']}」",
            **wrong,
        )
    return ready, problems


def added(first, second):
    """Two turns' token counts as one answer's, the counts inside too (2026-10-29: an answer
    given again lost its cost: its cache writes were added, their breakdown by retention was
    the second turn's alone, and the two no longer agreed)."""
    if not first or not second:
        return second or first
    return {
        k: added(first.get(k), v)
        if isinstance(v, dict)
        else first.get(k, 0) + v
        if isinstance(v, (int, float)) and isinstance(first.get(k, 0), (int, float))
        else v
        for k, v in second.items()
    }


def _costs(settings, usage, began, tools=()):
    return {
        "model": settings and settings.get("model"),
        "elapsed_ms": (time.monotonic() - began) * 1000,
        "cost": api_cost(usage, settings, reason=None if usage else "No usage")
        if settings
        else None,
        "tools": list(tools),
    }


def call_name(item):
    """A tool call's name as kept and shown: a call of a type its tool and type, read:version
    (definition 51.6), else its tool."""
    kind = (item.get("arguments") or {}).get("type")
    tool = item.get("tool")
    return f"{tool}:{kind}" if isinstance(kind, str) and kind else tool


def tool_recorder(tools, began, doing=None):
    """A CLI event recorder that keeps a turn's MCP tool calls in tools: each one's tool,
    whether it went, when it started (at: ms after the answer began, the time.monotonic of
    began) and how long it took (ms), from the CLI's start and end of the call (definition
    47). Calls at once overlap; a call whose start was not seen has no times. doing hears the
    calls going now and the tools of those done, for what the worker is doing (definition
    48.7)."""
    started, going = {}, {}

    async def note_event(event):
        item = event.get("item", {})
        if item.get("type") != "mcp_tool_call":
            return
        now = (time.monotonic() - began) * 1000
        if event.get("type") == "item.started":
            started[item.get("id")] = now
            going[item.get("id")] = {
                "tool": call_name(item),
                "args": item.get("arguments") or {},
            }
        elif event.get("type") == "item.completed":
            at = started.pop(item.get("id"), None)
            going.pop(item.get("id"), None)
            tools.append(
                {
                    "tool": call_name(item),
                    "ok": item.get("status") == "completed",
                    "at": None if at is None else round(at),
                    "ms": None if at is None else round(now - at),
                }
            )
        else:
            return
        if doing is not None:
            doing({"going": list(going.values()), "done": [t["tool"] for t in tools]})

    return note_event


async def worker_settings(db):
    """The workers' own model for a turn with tools, not the last run's (user 2026-10-08: a run
    on Haiku made the answers with tools Haiku's too, and Haiku cannot do them)."""
    chosen = read_settings(db)
    try:
        selected = await asyncio.to_thread(
            selected_execution_settings, chosen["agent_model"], chosen["agent_effort"]
        )
    except ApiError as error:
        if error.code != "invalid_model":
            raise
        # The settings' model is not of a CLI this machine has (2026-10-29: a zip given to
        # someone with Codex only): said as the setting to change.
        raise ApiError(
            422,
            "agent_model_unavailable",
            "The workers' model in the settings is not usable here; choose another",
            {"model": chosen["agent_model"]},
        ) from error
    return {**selected, **chosen}


@dataclass(frozen=True)
class Role:
    """A worker's role data for the one answer path (definition 48.1): its rules and what it
    reads (made by found(db, place, agent, looking); the chat's lines are worker_lines)."""

    rules: str
    found: Callable

    @property
    def sha(self):
        return hashlib.sha256(self.rules.encode()).hexdigest()


def _steward_found(db, place, agent, looking):
    found = dataset_context(db, place, agent)
    if looking:
        found["looking_at"] = looking  # what the person was looking at
    # What a worker AI gets besides the plan, for the answers that write it (18.15).
    found["worker_gets"] = worker_gets(db)
    return found


def _reception_found(db, place, agent, looking):
    return library_here.library_context(db, looking)


ROLES = {
    "steward": Role(RULES, _steward_found),
    "reception": Role(library_here.RULES, _reception_found),
}
assert set(ROLES) == set(AGENTS), "Every worker has its role's data"


class Answers:
    """The runner of every worker's answer jobs (jobs.JobQueue), one way for every place
    (definition 48.3)."""

    def __init__(self, db, jobs):
        self.db = db
        self.jobs = jobs

    async def heavy(self, job):
        db, place, agent = self.db, job["dataset_id"], job["agent"]
        if place:
            dataset_row(db, place)
        began = time.monotonic()
        tools, settings, usage = [], None, None
        record = tool_recorder(
            tools, began, lambda doing: self.jobs.now_doing(job["id"], doing)
        )
        asked = line(db, job["request_event_id"])
        looking = json.loads(asked["data_json"] or "{}").get("looking_at") or {}
        try:
            settings = await worker_settings(db)
            session = self._session(place, agent, settings["model"], asked["chat_id"])
            try:
                said, usage, evidence = await self._turn(
                    job, asked["text"], looking, settings, session, record
                )
            except (RuntimeError, ValueError) as exc:
                if session is None:
                    raise
                logger.warning("A worker could not resume its session: %s", exc)
                said, usage, evidence = await self._turn(
                    job, asked["text"], looking, settings, None, record
                )
            ready, problems = usable(db, place, agent, said, job)
            turns = [{"said": said, "problems": problems}]
            if problems:
                # Parts the server cannot use (a show finding nothing, an option it cannot make
                # a plan of, a part its kind does not use): the worker is told why and answers
                # again in the same conversation, once (68.2).
                said, again, evidence = await self._turn(
                    job,
                    ANSWER_AGAIN.format(
                        problems=json.dumps(problems, ensure_ascii=False)
                    ),
                    looking,
                    settings,
                    (evidence or {}).get("session_id"),
                    record,
                    again=True,
                )
                usage = added(usage, again)
                ready, problems = usable(db, place, agent, said, job)
                turns.append({"said": said, "problems": problems})
            # The answer as the worker gave it, kept to check what reached the person (74).
            keep_said(db, job["id"], turns)
            extra = {
                "job_id": job["id"],
                "session_id": (evidence or {}).get("session_id"),
                "prompt_sha": ROLES[agent].sha,
                **_costs(settings, usage, began, tools),
            }
            self._record(job, said, ready, problems, extra)
        except asyncio.CancelledError:
            if self.jobs.closing:
                # The app closing stopped it: said as when it stopped by a crash (72).
                self.cut_off(job)
                raise
            # A person stopped it: said as what happened, not as a failure to see to (user
            # 2026-10-23: a stop showed "could not answer" with a button to press again); the
            # question it answered is open again (41.3).
            reopen_question(db, job["request_event_id"])
            add(
                db,
                place,
                agent,
                "note",
                "answer_cancelled",
                job_id=job["id"],
                data={"note": "answer_cancelled"},
                **_costs(settings, usage, began, tools),
            )
            raise
        except Exception as exc:
            logger.exception("A worker's answer failed")
            add(
                db,
                place,
                agent,
                "failed",
                str(exc) or type(exc).__name__,
                job_id=job["id"],
                # Its kind, so the screen says it in the person's words (2026-10-29).
                data={"code": exc.code} if isinstance(exc, ApiError) else None,
                **_costs(settings, getattr(exc, "usage", usage), began, tools),
            )
        finally:
            self.jobs.now_doing(job["id"], None)

    def cut_off(self, job):
        """An answer the app stopped in the middle (it closed, or it ended without closing and
        started again): its question open again, as when a person stops it (41.3), and a line
        saying the app stopped, to ask again (definition 72)."""
        reopen_question(self.db, job["request_event_id"])
        add(
            self.db,
            job["dataset_id"],
            job["agent"],
            "failed",
            "The app stopped while answering; ask again.",
            job_id=job["id"],
            data={"code": "app_stopped"},
        )

    def _record(self, job, said, ready, problems, extra):
        """The answer as its lines, by what of it the server can use (definition 48.3, 68.2),
        with the boxes it made and the waiting ones it points at; then, when parts of it could
        not be used, a note saying which."""
        db, place, agent = self.db, job["dataset_id"], job["agent"]
        # The boxes this answer made that wait: none withdrawn within it, by its own remaking or
        # otherwise (definition 74, 76; 2026-10-29: the line showed one withdrawn under the
        # title of the one that waited).
        made = [b["id"] for b in made_boxes(db, job, agent) if b["state"] == "open"]
        waiting = {r["id"] for r in waiting_boxes(db, place)}
        pointed = [b for b in said.get("boxes") or [] if b in waiting and b not in made]
        data = {
            **({"show": ready["show"]} if "show" in ready else {}),
            "proposal_ids": [*made, *dict.fromkeys(pointed)],
        }
        message = (said.get("message") or "").strip()
        if "question" in ready:
            # What the worker says before its question, a line of its own above it (user
            # 2026-10-29: 「8つの値ってなに？」 twice; the worker named the eight values in its
            # message each time, and only the question's line was written). Its cost is the
            # question's.
            if message and message != said["question"]["text"].strip():
                add(db, place, agent, "ai", message, job_id=extra.get("job_id"))
            add(
                db,
                place,
                agent,
                "question",
                said["question"]["text"],
                data={**ready["question"], **data},
                **extra,
            )
        elif "handoff" in ready:
            line = add(
                db,
                place,
                agent,
                "handoff_offer",
                said["message"],
                data={**ready["handoff"], **data},
                **extra,
            )
            # Asked for already: the request goes to that worker at once (definition 33.2).
            if ready["handoff"].get("now"):
                handoff(self.jobs, line)
        elif "open" in ready:
            add(
                db,
                place,
                agent,
                "open",
                said["message"],
                data={**ready["open"], **data},
                **extra,
            )
        else:
            add(db, place, agent, "ai", said["message"], data=data, **extra)
        # Still not right after the worker answered again: said to the person (68.2), the
        # parts not used apart from the names its words have wrong (they are shown; 73).
        unused = [p for p in problems if p["part"] != "name"]
        names = [p for p in problems if p["part"] == "name"]
        for note, parts in (("answer_unused", unused), ("answer_names", names)):
            if parts:
                add(
                    db,
                    place,
                    agent,
                    "note",
                    note,
                    data={"note": note, "parts": parts},
                    job_id=extra.get("job_id"),
                )

    def _session(self, place, agent, model, chat_id=None):
        """The chat's CLI session to go on with: its latest answer's, made by the same model
        under the same rules (each chat its own, user 2026-10-09)."""
        row = last_answer(self.db, place, agent, chat_id)
        if row and row["model"] == model and row["prompt_sha"] == ROLES[agent].sha:
            return row["session_id"]
        return None

    async def _turn(self, job, text, looking, settings, session, record, again=False):
        """One turn of the chat's CLI with the worker's tools, bound to the job's dataset (its
        place's, or the one its request reads; definition 48.10), with the chat's lines it
        reads (68.1; an answer asked again has none new)."""
        db, place, agent = self.db, job["dataset_id"], job["agent"]
        asked = line(db, job["request_event_id"])
        role = ROLES[agent]
        found = role.found(db, place, agent, looking)
        lines = worker_lines(db, job["request_event_id"], agent)
        found |= {"request": lines["request"]} if again else lines
        # The person's time now (the app runs on their machine; definition 74).
        found["now"] = datetime.now().astimezone().isoformat(timespec="minutes")
        language = chat_language(db, asked["chat_id"])
        talk = self.jobs.talk(job)
        return await self.jobs.residents.turn(
            talk,
            settings=settings,
            schema=answer_schema(agent),
            tools=AGENTS[agent].tools,
            headers={
                "X-Actor": "ai",
                "X-Annotation-Agent": agent,
                "X-Annotation-Dataset": job["bound_dataset_id"] or "",
                "X-Annotation-Chat": str(talk[2]),
            },
            rules=role.rules.replace("{agent}", agent),
            context={**found, "language": language} if language else found,
            message=text,
            session=session,
            record=record,
        )

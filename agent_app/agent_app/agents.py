"""The workers (step 24 design 3.1): each a setting, not a process (its icon, tools and rules);
their states are computed from jobs, proposals and questions, never stored (2026-10-08 states
research: a worker's "done" belongs to the job's result).

Two workers (definition 35.1, user 2026-10-22): the library's reception, and in a dataset its
steward, who makes the plan and carries it out in one talk (the plan's and Apply's workers had
the same tools and differed only in the talk and the right they went with). The map's places
(Plan, Apply) stay: a box's place and the right's screen. What guards the data is the same for
both: the dataset bound in the headers, every change a box a person decides, no shell.
"""

from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Request

from .datasets import dataset_row
from .errors import not_found
from .jobs import active_jobs, bound_answers
from .mcp_general import GENERAL

router = APIRouter(prefix="/v1")

# What every worker does with a request that is not this app's work, the same for every worker
# (definition 69; 2026-10-29: asked about the weather, code, a ramen shop and minutes, the
# steward wrote code and the reception declined as "the reception": no rule said).
NOT_HERE_WORDS = (
    "A request that is not about this app's work (its datasets, images, labels, plans,"
    " annotations, training, its settings, or how to use it), such as general knowledge, the"
    " weather, writing"
    " code, recommendations or other services: kind=answer, one short sentence that you are this"
    " app's worker and do not take it here, then one or two requests the person can make of you"
    " here, as they would write them. Do not answer it, even when you could."
)


# What every worker may call (definition 22.5, AGENTS.md: the left is what the right does and
# more): every tool that reads, writes a draft or a note, chooses a reference (no data a person relies on
# changes) or proposes a decision; never a decision itself (a person decides it). The same for
# every worker (definition 51.1): what each reads is its place's (authority).
TOOLS = tuple(
    name for name, tool in GENERAL.items() if tool.kind in ("read", "write", "propose")
)


@dataclass(frozen=True)
class Agent:
    """A worker: a role in a place (definition 48.1). Its place is the library (its chats and
    lines have no dataset) or a dataset; kinds are the answers it gives (open: a place opened
    on the right, the library's; a dataset's worker shows a set of things instead)."""

    key: str
    icon: str
    tools: tuple
    place: str
    kinds: tuple
    # What it is for, and so whom a request goes to (definition 35.1, 36.7), in one line.
    does: str


AGENTS = {
    # The library's: it makes, combines and deletes datasets (definition 22.5, 35.2).
    "reception": Agent(
        "reception",
        "受",
        TOOLS,
        "library",
        ("answer", "question", "handoff", "open"),
        "the library's: makes, combines and deletes datasets",
    ),
    # A dataset's: its plan and its carrying out (definition 35.1).
    "steward": Agent(
        "steward",
        "担",
        TOOLS,
        "dataset",
        ("answer", "question", "handoff"),
        "the dataset's: its plan (the instruction draft: labels, text, references chosen from"
        " results; its samples, a trial annotating a few images by it, a run keeps the draft"
        " as a version; renaming a label of it, which renames it in every dataset using it, a"
        " label being one for every dataset) and carrying it out (runs of the images, fixing results by hand,"
        " marking images in or out of training)",
    ),
}
ORDER = list(AGENTS)
# A worker named in an input (the keys of AGENTS).
AgentName = Literal["reception", "steward"]


def workers():
    """Every worker and what it is for, as a worker reads them."""
    return [{"agent": key, "does": AGENTS[key].does} for key in ORDER]


def place_kind(dataset_id):
    """A place's kind: a dataset (its id), or the library (None)."""
    return "dataset" if dataset_id else "library"


def worker_at(dataset_id):
    """The worker of a place, one each (definition 48.1, 48.11): a dataset's, or the library's
    (None). What is a place's worker's is found by its place, never by a worker's name."""
    return next(key for key in ORDER if AGENTS[key].place == place_kind(dataset_id))


def worker_of(agent, dataset_id):
    """The worker of a place (a dataset, or the library: None), or not found: a worker talks
    in its own place only (definition 48.4)."""
    found = AGENTS.get(agent)
    if found is None or found.place != place_kind(dataset_id):
        raise not_found("Worker")
    return found


def counts(db, dataset_id):
    """Per worker: jobs going and waiting, the person's turn (open proposals and questions,
    apart and together) and trouble (failed proposals and failed answers not yet
    seen). dataset_id None: the library's (its boxes; definition 44.1)."""
    found = {
        a: {
            "running": 0,
            "queued": 0,
            "answering": 0,
            "boxes": 0,
            "questions": 0,
            "trouble": 0,
            # Answers going or waiting bound to this place's dataset, of any worker (one of the
            # library reading it too): they may write its plan (definition 11.10, 48.10).
            "bound": 0,
        }
        for a in AGENTS
    }
    from .agent_chat import last_lines, waiting_lines  # a line is a worker's
    from .proposals import unseen_trouble, waiting_boxes  # a box is a worker's

    for r in active_jobs(db, dataset_id):
        if r["agent"] in found:
            found[r["agent"]][r["state"]] += 1
            # Answers going or waiting at this place (not runs).
            if r["kind"] != "run":
                found[r["agent"]]["answering"] += 1
    for r in bound_answers(db, dataset_id):
        if r["agent"] in found:
            found[r["agent"]]["bound"] += 1
    for key, boxes in (
        ("boxes", waiting_boxes(db, dataset_id)),
        ("trouble", unseen_trouble(db, dataset_id)),
    ):
        for r in boxes:
            if r["agent"] in found:
                found[r["agent"]][key] += 1
    for r in waiting_lines(db, dataset_id):
        if r["agent"] in found:
            key = "questions" if r["kind"] == "question" else "trouble"
            found[r["agent"]][key] += 1
    for count in found.values():
        count["waiting"] = count["boxes"] + count["questions"]
        count["last_event"] = None
        count["last_event_chat"] = None
    # The newest line not the person's own, for the "new" mark on the worker's button.
    # And its chat: unread lines in another chat open that chat (user 2026-10-15).
    for agent, r in last_lines(db, dataset_id).items():
        if agent in found:
            found[agent]["last_event"] = r["id"]
            found[agent]["last_event_chat"] = r["chat_id"]
    return found


def state_of(count):
    if count["trouble"]:
        return "trouble"
    if count["waiting"]:
        return "you"
    if count["running"] or count["queued"]:
        return "working"
    return "idle"


def agent_list(db, dataset_id):
    """Every worker's counts in a place (a dataset, or the library: None)."""
    if dataset_id:
        dataset_row(db, dataset_id)
    found = counts(db, dataset_id)
    return {
        "agents": [
            {
                "agent": key,
                "icon": AGENTS[key].icon,
                # Its place (the screen reads each worker's counts from its own, 48.6).
                "place": AGENTS[key].place,
                "state": state_of(found[key]),
                **found[key],
            }
            for key in ORDER
        ]
    }


@router.get("/datasets/{dataset_id}/agents")
@router.get("/library/agents")
def list_agents_route(request: Request):
    return agent_list(request.app.state.db, request.path_params.get("dataset_id"))

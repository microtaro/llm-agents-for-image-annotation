"""A request handed from one worker's talk to another's (definition 36.7, 48.5): from the
library's reception to a dataset's steward (a dataset's work), and from a dataset's steward to
the reception (the library's: making, combining or deleting a dataset, a label's name). The
worker it is not for offers it with the request in a line; the person presses, or it goes at
once when the person asked for it already (now). The offer closes, the request goes into a new
chat of the worker it is for as the handing worker's words with where it came from, and a line
in the offer's chat says it went. One way for both: the offer's line says whose it is and the
worker it is for."""

import json

from fastapi import APIRouter, Request

from . import actors, agent_chat
from .agents import AGENTS
from .errors import ApiError, Model, invalid, not_found

router = APIRouter(prefix="/v1")


class HandoffInput(Model):
    event_id: int


def handoff(jobs, event_id, lang=None):
    """The offer of a worker's line handed to the worker it names: into a new chat of that
    worker, at its place (a dataset's worker: the offer's dataset; the library's: the library,
    reading the offer's dataset as open on the right)."""
    db = jobs.db
    row = agent_chat.line(db, event_id)
    if row is None or row["kind"] != "handoff_offer":
        raise not_found("Offer to hand over")
    if row["closed_at"]:
        raise ApiError(409, "handoff_done", "The request was handed over already")
    offer = json.loads(row["data_json"])
    to = AGENTS.get(offer.get("agent"))
    if to is None or to.key == row["agent"]:
        raise invalid("No such worker")
    if to.place == "dataset":
        place, looking = offer.get("dataset_id"), None
        if not place:
            raise invalid("A dataset's worker is handed a request of a dataset")
    else:
        place, looking = None, row["dataset_id"]
    agent_chat.close_event(db, event_id)
    asked = agent_chat.ask(
        jobs,
        place,
        to.key,
        offer["summary"],
        by_actor=actors.agent(row["agent"]),
        data={
            **({"looking_at": {"dataset_id": looking}} if looking else {}),
            "from_agent": row["agent"],
            "from_event_id": event_id,
        },
        chat_id=agent_chat.new_chat(db, place, to.key),
        lang=lang,
    )
    agent_chat.add(
        db,
        row["dataset_id"],
        row["agent"],
        "note",
        "handed",
        data={
            "note": "handed",
            "to_agent": to.key,
            "dataset_id": place,
            "job_id": asked["job_id"],
        },
        chat_id=row["chat_id"],
    )
    return {**asked, "dataset_id": place, "agent": to.key}


@router.post("/datasets/{dataset_id}/agents/{agent}/handoffs", status_code=202)
@router.post("/library/agents/{agent}/handoffs", status_code=202)
def handoff_route(request: Request, agent: str, body: HandoffInput):
    if request.headers.get("x-annotation-agent"):
        raise ApiError(403, "agent_scope", "Only a person hands a request over")
    db = request.app.state.db
    if not agent_chat.line_at(db, body.event_id, agent_chat.place_of(request), agent):
        raise not_found("Offer to hand over")
    return handoff(
        request.app.state.jobs, body.event_id, agent_chat.language_of(request)
    )

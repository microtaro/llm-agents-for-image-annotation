"""The person's turns (definition 44): what waits for a person in each place (the library and
every dataset), counted where the workers' counts are (agents.counts), and cleared at once:
boxes not done, questions not answered, trouble seen. Clearing changes no data.
"""

from fastapi import APIRouter, Request
from pydantic import Field

from .actors import who_of
from .agent_chat import close_line, waiting_lines
from .agents import counts
from .datasets import dataset_row, dataset_rows
from .errors import ApiError, Model
from .proposals import decline, see_trouble, waiting_boxes

router = APIRouter(prefix="/v1")


def _place(db, dataset_id, name):
    found = counts(db, dataset_id).values()
    place = {
        "dataset_id": dataset_id,
        "name": name,
        **{k: sum(c[k] for c in found) for k in ("boxes", "questions", "trouble")},
    }
    return {**place, "count": place["boxes"] + place["questions"] + place["trouble"]}


def turns(db):
    """Every place with something waiting for the person, the library first, and the sum."""
    places = [_place(db, None, None)] + [
        _place(db, r["id"], r["name"]) for r in dataset_rows(db)
    ]
    places = [p for p in places if p["count"]]
    return {"count": sum(p["count"] for p in places), "places": places}


def _clear_place(db, dataset_id, actor, cleared):
    for row in waiting_boxes(db, dataset_id):
        decline(db, row["id"], actor)
        cleared["boxes"] += 1
    cleared["trouble"] += see_trouble(db, dataset_id)
    for row in waiting_lines(db, dataset_id):
        close_line(db, row, actor)
        cleared["questions" if row["kind"] == "question" else "trouble"] += 1


def clear(db, dataset_id, actor):
    """Clear what waits for the person in one dataset, or everywhere (None)."""
    cleared = {"boxes": 0, "questions": 0, "trouble": 0}
    if dataset_id:
        dataset_row(db, dataset_id)
    places = (
        [dataset_id] if dataset_id else [None] + [r["id"] for r in dataset_rows(db)]
    )
    for place in places:
        _clear_place(db, place, actor, cleared)
    return cleared


class ClearInput(Model):
    dataset_id: str | None = Field(
        None, description="The dataset whose turns are cleared; null: every place."
    )


@router.get("/turns")
def get_turns(request: Request):
    return turns(request.app.state.db)


@router.post("/turns/clear")
def clear_turns(request: Request, body: ClearInput):
    if request.headers.get("x-annotation-agent"):
        raise ApiError(403, "agent_scope", "Only a person clears the person's turns")
    return clear(request.app.state.db, body.dataset_id, who_of(request))

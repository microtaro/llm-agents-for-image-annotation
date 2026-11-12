"""The plan's state by its items (definition 26.3), from the facts in one place: who last decided
each item (a worker's write; a person's write, answer or trial of it), what is still open, and the
item to ask next. The workers, the plan's screen and the map read it. Read only.
"""

import json

from fastapi import APIRouter, Request

from .actors import is_agent
from .agent_chat import question_lines
from .datasets import dataset_row
from .drafts import plan_draft, same_version, write_row, writes_of
from .instructions import latest_row, requirement_key, version_rows
from .references import resolved
from .usage import empty, version_usage

router = APIRouter(prefix="/v1")
# In the order they are asked; the text is the worker's. The trial is the plan's samples
# (definition 38.1).
ITEMS = ("requirement", "leave_out", "references", "trial", "text")
ASKED = ("requirement", "leave_out", "references", "trial")
# Each item's value when nothing is decided (what the first write is compared with).
NOTHING = {"requirement": None, "text": ""}


def _value(item, plan):
    if item == "requirement":
        definitions = plan["label_definitions"]
        return requirement_key(definitions) if definitions else None
    return plan[item]


def _item_summary(item, plan, tried):
    if item == "requirement":
        return [
            {
                "label": d["name"],
                "shape": d["shape"],
                "parent": d.get("parent"),
                "attributes": [a["name"] for a in d.get("attributes") or []],
            }
            for d in plan["label_definitions"]
        ]
    if item == "references":
        return [
            {"image_id": x["image_id"], "objects": len(x["annotations"])}
            for x in plan["references"]
        ]
    if item == "trial":
        return tried
    return plan[item]


def _changes(db, dataset_id, until):
    """The plan's contents in the order they were made, up to the one it is now: (who, when,
    content) of each write of the draft and each version saved without one (a rename, the
    outside; a version made from a write says what the write says)."""
    made = [
        (r["written_at"], r["written_by"], r["payload_json"])
        for r in writes_of(db, dataset_id)
        if r["written_at"] <= until
    ] + [
        (r["created_at"], r["created_by"], r["payload_json"])
        for r in version_rows(db, dataset_id)
        if r["draft_write_id"] is None and r["created_at"] <= until
    ]
    return [(who, at, json.loads(content)) for at, who, content in sorted(made)]


def _answered_items(db, dataset_id):
    """item -> when a person last answered a question about it."""
    found = {}
    for r in question_lines(db, dataset_id):
        data = json.loads(r["data_json"] or "{}")
        if data.get("item") and data.get("answered"):
            found[data["item"]] = max(
                found.get(data["item"], ""), data["answered"]["at"]
            )
    return found


def _status(who):
    return "agent" if is_agent(who) else "person"


def plan_state(db, dataset_id):
    """{plan, write_id, revision, items: [{item, status, summary}], next}: status open (not yet,
    or made empty since it was answered about), agent (a worker decided it) or person (a person
    did: wrote it, answered about it after its last change, or ran the plan as it is). write_id
    and revision are what a question stands on: the draft's write, else the latest version."""
    dataset_row(db, dataset_id)
    draft = plan_draft(db, dataset_id)
    latest = latest_row(db, dataset_id)
    now_ = draft or latest
    plan = json.loads(now_["payload_json"]) if now_ else None
    # When the plan now was written: the draft's write, else the version's making.
    at = (
        write_row(db, dataset_id, draft["write_id"])["written_at"]
        if draft
        else latest["created_at"]
        if latest
        else None
    )
    entries = _changes(db, dataset_id, at) if now_ else []
    # The plan as it is, run (definition 26.3 (3); a trial or all the images): a person decided
    # every item by running it.
    revision = same_version(db, dataset_id, plan) if plan else None
    use = version_usage(db, dataset_id).get(revision, empty()) if revision else empty()
    tried = (
        {"revision": revision, "runs": use["runs"], "trials": use["trials"]}
        if use["runs"]
        else None
    )
    answered = _answered_items(db, dataset_id)
    # The objects of its references, for the summaries and the screen.
    plan = resolved(db, plan)
    items = []
    for item in ITEMS:
        if item == "trial":
            status = "person" if tried else "open"
        else:
            nothing = NOTHING.get(item, [])
            changed, before = None, nothing
            for who, at, content in entries:
                value = _value(item, content)
                if value != before:
                    changed = (who, at)
                before = value
            if tried:
                status = "person"
            elif changed and answered.get(item, "") <= changed[1]:
                # Made empty (the plan started again blank) is not decided (copy 2026-10-22:
                # every item was the person's and the next was the trial).
                status = "open" if before == nothing else _status(changed[0])
            elif item in answered:
                status = "person"
            else:
                status = "open"
        items.append(
            {
                "item": item,
                "status": status,
                "summary": _item_summary(item, plan, tried) if plan else None,
            }
        )
    state = {i["item"]: i["status"] for i in items}
    return {
        "plan": plan,
        "write_id": draft["write_id"] if draft else None,
        "revision": latest["revision"] if latest else None,
        "items": items,
        "next": next((i for i in ASKED if state[i] == "open"), None),
    }


@router.get("/datasets/{dataset_id}/plan/state")
def get_plan_state(request: Request, dataset_id: str):
    return plan_state(request.app.state.db, dataset_id)

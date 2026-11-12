"""What a caller of the AI tools may do (step 24 design 3.2): one pure function, reading neither
the database nor the request (agent_kanban's task-authority; the scope check of 2026-10-08
found the progress panel's AI starting a run and deleting a dataset when told to, its only
guard the words of its prompt).

A worker of the work screen (an agent) is bound by the server, in the MCP connection's headers
it cannot change, to one dataset and one chat (its CLI is kept for the chat, definition 27.4): it sees and calls only its own tools, and every
dataset it names is that one. The reception is the library's (definition 22.5): bound to the
dataset the person has open on the right, or to none; it reads the library and proposes the
library's decisions (making, deleting a dataset), and works in the dataset it is bound to, or
else in the dataset a call names (definition 63: a decision names its dataset, the screen is
only a way of seeing), as a dataset's worker does. The progress panel's AI and the API (no agent headers) keep everything,
as before (the manual app's users).
"""

from dataclasses import dataclass

from .actions import DECISIONS
from .agents import AGENTS
from .mcp_general import GENERAL
from .object_types import LIBRARY_TYPES


def library_read(tool, args):
    """What the library's worker reads with no dataset open (definition 51.5), by its type:
    the library's types read, a dataset's images (any dataset's) or a label seen."""
    kind = args.get("type")
    if tool == "read":
        return kind in LIBRARY_TYPES
    return tool == "look" and kind in ("dataset", "label")


# The arguments that name what a tool touches, besides dataset_id (checked against the
# dataset's own images, runs and results by the caller, which has the database).
REFERENCES = ("image_id", "image_ids", "run_id", "result_id")


@dataclass(frozen=True)
class Caller:
    kind: str  # "agent" or "person"
    agent: str | None = None
    dataset_id: str | None = None
    chat_id: int | None = None


@dataclass(frozen=True)
class Allowed:
    args: dict
    # The dataset the call is of, for the caller's check of the images, runs and results it
    # names: the worker's own, or the one it named (definition 63); None for none.
    dataset_id: str | None = None


@dataclass(frozen=True)
class Denied:
    code: str
    message: str


def caller_of(headers):
    """The caller as the server bound it; an agent header without a dataset is refused."""
    agent = headers.get("x-annotation-agent")
    if agent is None:
        return Caller("person")
    return Caller(
        "agent",
        agent=agent,
        dataset_id=headers.get("x-annotation-dataset") or None,
        chat_id=int(headers["x-annotation-chat"])
        if (headers.get("x-annotation-chat") or "").isdigit()
        else None,
    )


def tools_of(caller, general):
    """The tools a caller sees in tools/list."""
    if caller.kind != "agent":
        return dict(general)
    allowed = AGENTS[caller.agent].tools if caller.agent in AGENTS else ()
    return {name: spec for name, spec in general.items() if name in allowed}


def permit(caller, tool, args):
    """Allowed (with the arguments to use) or Denied. args is the tool's raw input."""
    if caller.kind != "agent":
        return Allowed(dict(args))
    if caller.agent not in AGENTS:
        return Denied("agent_scope", "No such worker")
    if tool not in AGENTS[caller.agent].tools:
        return Denied("agent_tool", f"{tool} is not one of this worker's tools")
    proposed = DECISIONS.get(args.get("tool")) if tool == "proposal_make" else None
    # What a worker may do by its place (definition 48.11): the library's worker the
    # library's decisions and reads, a dataset's worker its dataset's.
    library = AGENTS[caller.agent].place == "library"
    if proposed is not None and proposed.scope == "library":
        if not library:
            return Denied(
                "library_decision",
                f"{args.get('tool')} is a decision of the library: the library's worker's",
            )
        return Allowed(
            {k: v for k, v in args.items() if k != "dataset_id"}, caller.dataset_id
        )
    if tool == "datasets_export":
        # Writing out changes no data (definition 60.6): the library's worker writes any
        # datasets out, a dataset's worker its own.
        if library or set(args.get("dataset_ids") or []) <= {caller.dataset_id}:
            return Allowed(dict(args), caller.dataset_id)
        return Denied("agent_scope", "Another dataset is another worker's to write out")
    given = _named_dataset(tool, args)
    bound = caller.dataset_id
    if not bound:
        if library and library_read(tool, args):
            return Allowed(dict(args))
        # The library's worker works in the dataset a call names, as a dataset's worker in
        # its own (definition 63; user 2026-10-28: as the ontology goes).
        bound = given if library else None
        if not bound:
            return Denied(
                "agent_scope",
                "This is of one dataset: name it (dataset_id)"
                if library
                else "This worker is not bound to a dataset",
            )
    if given not in (None, bound):
        return Denied(
            "agent_scope",
            f"This work is bound to dataset {bound}; another dataset is another worker's",
        )
    fixed = dict(args)
    # A tool that names a dataset names this one; the others (a run, a result, an image) are
    # checked by the caller against it (references).
    if "dataset_id" in GENERAL[tool].input.model_fields:
        fixed["dataset_id"] = bound
    if tool == "proposal_make":
        inner = dict(fixed.get("args") or {})
        if inner.get("dataset_id") not in (None, bound):
            return Denied("agent_scope", "A proposal of another dataset")
    return Allowed(fixed, bound)


def _named_dataset(tool, args):
    """The dataset a call names: its dataset_id, or the dataset read or seen (definition
    51.5)."""
    if tool in ("read", "look") and args.get("type") == "dataset":
        return args.get("id") or args.get("dataset_id")
    if tool == "proposal_make":
        return args.get("dataset_id") or (args.get("args") or {}).get("dataset_id")
    return args.get("dataset_id")


def _named_part(tool, args):
    """Where a tool's arguments name things: what a look sees (an image, a result), a
    proposal's own arguments, else the arguments themselves."""
    if tool == "proposal_make":
        return dict(args.get("args") or {})
    if tool == "look":
        named = {"image": "image_id", "result": "result_id"}.get(args.get("type"))
        return {named: args.get("id")} if named else {}
    return dict(args)


def with_image_ids(tool, args, to_id):
    """args with every image they name given by its id, through to_id (a worker names images by
    name, as its prompt says; issue #3 U-06 refused a name as "not of this dataset")."""
    part = _named_part(tool, args)
    if part.get("image_id") is not None:
        part["image_id"] = to_id(part["image_id"])
    if isinstance(part.get("image_ids"), list):
        part["image_ids"] = [to_id(v) for v in part["image_ids"]]
    if tool == "proposal_make":
        return {**args, "args": part}
    if tool == "look":
        return {**args, "id": part.get("image_id", args.get("id"))}
    return part


def references(tool, args):
    """What a tool's arguments name, for the caller to check against the bound dataset:
    {"image": [...], "run": [...], "result": [...]}."""
    named = {"image": [], "run": [], "result": []}
    found = _named_part(tool, args)
    for key in REFERENCES:
        value = found.get(key)
        if value is None:
            continue
        kind = key.removesuffix("_ids").removesuffix("_id")
        named[kind] += value if isinstance(value, list) else [value]
    return named

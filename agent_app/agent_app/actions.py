"""The decisions and what can be done with each type (types design 8, definition 22.2): one list,
from which the screen's buttons, a worker's proposals, the tools' kinds and a decision's place
on the map all come (memory bidirectional-or-one-way: what a person can do and what a worker can
propose are said in one place; issue #5-8: the list was in two).

A decision's tool is the MCP tool the server runs when it is decided. A worker's proposal of it
is decided by a person (in the talk or the band); a person's own press of it is done at once (it
is the person's decision); the outside calls the tool itself. Each is recorded as a decision of
its kind (decisions.record).
"""

from dataclasses import dataclass


def _production(_args):
    return "production"


def _library_place(_args):
    return "library"


def _none(_args):
    return None


@dataclass(frozen=True)
class Decision:
    kind: str  # decisions.kind
    scope: str  # "dataset": of one dataset; "library": of none (making, deleting one)
    stage: object  # args -> the place of the map it is at (proposals.bot)
    step: object  # args -> the step of the place (proposals.step), or None
    # What it does is not only added: it removes, stops or overwrites (the MCP hint, U-12).
    destructive: bool = False


DECISIONS = {
    # A trial is the plan's (①), a run the carrying out's (definition 1).
    "run_start": Decision(
        "run",
        "dataset",
        lambda args: "instruction" if args.get("trial") else "production",
        lambda args: "trial" if args.get("trial") else "run",
    ),
    "run_stop": Decision("stop", "dataset", _production, lambda _args: "run", True),
    "mark": Decision("use", "dataset", _production, lambda _args: "drop"),
    "pick": Decision("use", "dataset", _production, lambda _args: "drop"),
    # A person checked images' annotations by a version's criteria (definition 85.5).
    "confirm": Decision("confirm", "dataset", _production, _none),
    # Results of another version or dataset copied as the plan's (definition 85.15).
    "carry": Decision("carry", "dataset", _production, _none),
    "dataset_add_images": Decision("images", "dataset", _production, _none),
    "dataset_remove_images": Decision("images", "dataset", _production, _none, True),
    # Decided in the dataset whose plan names the label, at its plan (user 2026-10-28: a label is
    # named in the plan, so it is renamed there, by its steward); the label is the library's
    # (definition 26.1), so its name changes in every dataset using it, as the box says.
    "label_rename": Decision("label", "dataset", lambda _args: "instruction", _none),
    # A label of this dataset only (definition 79): the library's label stays; the dataset's next
    # version and its annotations now take the other label.
    "label_change": Decision("label", "dataset", lambda _args: "instruction", _none),
    "dataset_rename": Decision("dataset", "dataset", _production, _none, True),
    "dataset_create": Decision("dataset", "library", _library_place, _none),
    "dataset_from": Decision("dataset", "library", _library_place, _none),
    "dataset_import": Decision("dataset", "library", _library_place, _none),
    "dataset_delete": Decision("dataset", "library", _library_place, _none, True),
}
DECISION_TOOLS = tuple(DECISIONS)

# type -> [(name, decision tool or None, method, path for a person's press or None)]
ACTIONS = {
    "image": [
        ("run", "run_start", None, None),
        ("exclude", "mark", "POST", "/v1/datasets/{dataset_id}/images/{id}/exclude"),
        ("include", "mark", "POST", "/v1/datasets/{dataset_id}/images/{id}/include"),
        ("latest", "pick", "DELETE", "/v1/datasets/{dataset_id}/images/{id}/adoption"),
    ],
    "run": [
        ("stop", "run_stop", "POST", "/v1/runs/{id}/stop"),
        # Its images use its results (definition 19.5; going back to "the ones before" is gone,
        # definition 54: another record is chosen by name instead).
        ("use", "mark", "POST", "/v1/runs/{id}/use"),
    ],
    # The plan's draft is saved when a run starts, never by a decision (types design 20.1).
}


def place(tool, args):
    """(stage, step) of a decision on the map, from the tool and its arguments by the map's
    rules, not as the AI says (step 23: they could disagree)."""
    decision = DECISIONS[tool]
    return decision.stage(args), decision.step(args)


def action_listing():
    """The list for the screen: per type, each action's name, whether a worker's proposal of it
    is a decision, and how a person's press is done."""
    return {
        kind: [
            {"name": name, "decision_tool": tool, "method": method, "path": path}
            for name, tool, method, path in actions
        ]
        for kind, actions in ACTIONS.items()
    }

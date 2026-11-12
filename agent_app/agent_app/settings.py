"""App-wide settings a person can see and change: run limits, what the worker prompt states
and the yen rate. Copied from annotation_server/app_settings.py (step 2 design 2).

A run copies the run settings into its own settings when it starts, so changing them never
affects a running run.
"""

import json
from dataclasses import dataclass

from pydantic import Field, StrictFloat, StrictInt

from .db import now
from .errors import ApiError, Model
from .screen_words import screen


@dataclass(frozen=True)
class Item:
    """One setting: its default and range (none for a text). What it does (what it changes,
    when it applies, what raising or lowering it gains and costs) is the screen's dictionary's
    settings.<key>.tip, the one place the screen and the workers read (definition 71, 72)."""

    default: object
    low: object
    high: object


# A run copies every setting into its own when it starts (runs.py), so what a run uses never
# changes while it goes.
ITEMS = {
    "target_timeout_seconds": Item(600, 60, 3600),
    "max_mcp_calls": Item(40, 5, 200),
    # Every model gets the same size, one no receiver scales down (user 2026-10-07: the size is
    # ours so the coordinates that come back need no reading). Claude takes about 1.15 MP as
    # it is: 1024 x 1024 fits it, 1536 did not (model_catalog.WORKER_VIEW_MAX_PIXELS).
    "worker_view_max_side": Item(1024, 256, 1024),
    "mcp_tool_timeout_seconds": Item(40, 10, 600),
    "usd_to_jpy": Item(160, 1, 1000),
    # A run's cost limit per image, when a run's decision gives none (user 2026-10-28: the
    # cards say each image's cost, so a limit of the whole read as one image's). 2026-11-05: from
    # $0.50 to $2, as outlines by Claude Opus 5.5 medium cost $0.80 to $1.69 an image and a first
    # run stopped at the limit; boxes cost about $0.20, and a later run goes by its own cost.
    "run_budget_per_image_usd": Item(2, 0.01, 100),
    # A failure the provider says is passing (busy, rate limit, connection) is tried again
    # this many times, waiting between tries, only while nothing was saved yet (step 12).
    "retry_count": Item(2, 0, 5),
    "retry_wait_seconds": Item(30, 5, 600),
    # The line of work (step 24): at most this many runs and workers' answers (each chat's CLI
    # kept running, so as many kept; apart from the runs, user 2026-10-20: "６本でいい") at
    # once; free memory decides too. A CLI that writes nothing for stall_seconds is stopped
    # (only the per-image limit was seen before).
    "run_slots": Item(2, 1, 8),
    # A run's images at once (definition 50.2: they went one at a time, a 3-image run took
    # the three's sum); so at most run_slots x image_slots worker CLIs annotate at once.
    "image_slots": Item(3, 1, 8),
    "chat_slots": Item(6, 1, 8),
    "stall_seconds": Item(180, 30, 600),
    # The model of the workers, every answer of their chats (definition 28; user 2026-10-08:
    # "Haiku cannot do the heavy ones"): chosen apart from the runs' model. Opus 5.5 at first, as
    # the runs': the people it is given to use Claude (user 2026-10-20), and a clone starts from
    # these (2026-11-06: it would have asked for Codex's model).
    "agent_model": Item("claude-opus-5-5", None, None),
    "agent_effort": Item("medium", None, None),
    # The model a run takes when none is chosen, the same for every dataset (user 2026-10-27:
    # set here; it was the dataset's last run's). Haiku 5.5 is chosen for a run, never the
    # default.
    "run_model": Item("claude-opus-5-5", None, None),
    "run_effort": Item("medium", None, None),
    # The shared notes for every worker AI are versions of their own (shared_notes.py).
}


# A model's effort, shown and read with its model (the screen's groups name the model only).
EFFORTS = {"agent_model": "agent_effort", "run_model": "run_effort"}

# The settings screen's groups, in order, and each group's settings in order (user 2026-10-29:
# "not in a fit order, nor in groups"): what is changed most first. A model stands for its
# effort too. Every setting is in one group (test_settings.py).
GROUPS = [
    ["models", ["agent_model", "run_model"]],
    ["cost", ["run_budget_per_image_usd", "usd_to_jpy"]],
    [
        "image",
        [
            "worker_view_max_side",
            "target_timeout_seconds",
            "max_mcp_calls",
            "mcp_tool_timeout_seconds",
        ],
    ],
    ["slots", ["run_slots", "image_slots", "chat_slots"]],
    ["stop", ["stall_seconds", "retry_count", "retry_wait_seconds"]],
]


def _says(key):
    """A setting's description for the API: what it does (the dictionary's, in English), and
    its range."""
    item = ITEMS[key]
    does = screen(f"settings.{key}.tip")["en"]
    span = f" ({item.low}-{item.high})" if item.low is not None else ""
    return (does + span) if does else None


class SettingsInput(Model):
    target_timeout_seconds: StrictInt | None = Field(
        None, description=_says("target_timeout_seconds")
    )
    max_mcp_calls: StrictInt | None = Field(None, description=_says("max_mcp_calls"))
    worker_view_max_side: StrictInt | None = Field(
        None, description=_says("worker_view_max_side")
    )
    mcp_tool_timeout_seconds: StrictInt | None = Field(
        None, description=_says("mcp_tool_timeout_seconds")
    )
    usd_to_jpy: StrictInt | StrictFloat | None = Field(
        None, description=_says("usd_to_jpy")
    )
    run_budget_per_image_usd: StrictInt | StrictFloat | None = Field(
        None, description=_says("run_budget_per_image_usd")
    )
    retry_count: StrictInt | None = Field(None, description=_says("retry_count"))
    retry_wait_seconds: StrictInt | None = Field(
        None, description=_says("retry_wait_seconds")
    )
    run_slots: StrictInt | None = Field(None, description=_says("run_slots"))
    image_slots: StrictInt | None = Field(None, description=_says("image_slots"))
    chat_slots: StrictInt | None = Field(None, description=_says("chat_slots"))
    stall_seconds: StrictInt | None = Field(None, description=_says("stall_seconds"))
    agent_model: str | None = Field(
        None, min_length=1, max_length=80, description=_says("agent_model")
    )
    agent_effort: str | None = Field(
        None, min_length=1, max_length=20, description=_says("agent_effort")
    )
    run_model: str | None = Field(
        None, min_length=1, max_length=80, description=_says("run_model")
    )
    run_effort: str | None = Field(
        None, min_length=1, max_length=20, description=_says("run_effort")
    )


def read_settings(db):
    stored = {
        r["key"]: json.loads(r["value_json"])
        for r in db.execute("SELECT key, value_json FROM app_settings")
    }
    values = {key: stored.get(key, item.default) for key, item in ITEMS.items()}
    # A value saved before its range narrowed reads inside it (1536 from before 2026-10-07).
    for key, item in ITEMS.items():
        if item.low is not None and isinstance(values[key], int | float):
            values[key] = min(max(values[key], item.low), item.high)
    return values


def ranges():
    """The allowed range of each number, for the settings screen."""
    return {k: [i.low, i.high] for k, i in ITEMS.items() if i.low is not None}


def tool_time_limit(settings):
    """Seconds one MCP tool call may take, from app or run settings."""
    return (
        settings.get("mcp_tool_timeout_seconds")
        or ITEMS["mcp_tool_timeout_seconds"].default
    )


# Models that only judge (one quick call): never the workers' answers with tools, nor the
# runs' default.
LIGHT_ONLY = ("claude-haiku-5-5",)


def write_settings(db, body: SettingsInput):
    changes = body.model_dump(exclude_none=True)
    for key in ("agent_model", "run_model"):
        if changes.get(key) in LIGHT_ONLY:
            raise ApiError(
                422,
                "light_model",
                "This model only judges quickly; choose another here",
                {"key": key},
            )
    for key, value in changes.items():
        low, high = ITEMS[key].low, ITEMS[key].high
        if low is not None and not low <= value <= high:
            raise ApiError(
                422,
                "invalid_setting",
                f"{key} must be between {low} and {high}",
                {"key": key, "minimum": low, "maximum": high},
            )
    with db.transaction():
        for key, value in changes.items():
            db.execute(
                "INSERT INTO app_settings(key,value_json,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,"
                " updated_at=excluded.updated_at",
                (key, json.dumps(value), now()),
            )
    return read_settings(db)


def explained(db, group=None):
    """The settings as a worker reads and the right shows them, read only (definition 71; user
    2026-10-29: changed only on the settings screen): each one's group, its words on the screen,
    value (a model with its effort), default, range and what it does; then this machine's
    facts (group machine). What each does is the screen's dictionary's (definition 72)."""
    values = read_settings(db)
    rows = []
    for name, keys in GROUPS:
        for key in keys:
            item = ITEMS[key]
            effort = EFFORTS.get(key)
            rows.append(
                {
                    "key": key,
                    "group": name,
                    "screen": screen(f"settings.{key}"),
                    "group_screen": screen(f"settings.group.{name}"),
                    "value": values[key],
                    **({"effort": values[effort]} if effort else {}),
                    "default": item.default,
                    **(
                        {"range": [item.low, item.high]} if item.low is not None else {}
                    ),
                    "does": _does(f"settings.{key}"),
                }
            )
    rows += [
        {
            "key": key,
            "group": "machine",
            "value": value,
            "does": _does(f"objects.settings.{key}"),
        }
        for key, value in {**machine(), "storage": db.storage()}.items()
    ]
    return [r for r in rows if group is None or r["group"] == group]


def machine():
    """This machine's facts the settings screen and the workers read (definition 71): the
    software's version and the memory free now, what the jobs' line holds work back by
    (jobs.memory_needed; 2026-10-30: the free memory was on no screen a person opens)."""
    from .config import VERSION
    from .system import free_mb

    return {"version": VERSION, "free_memory_mb": free_mb()}


def _does(key):
    """What a setting does, in the screen's words in each language: its tip, with its note when
    it has one (the dictionary, the one place; definition 72)."""
    tip, note = screen(f"{key}.tip"), screen(f"{key}.note")
    return {
        lang: " ".join(part for part in (tip[lang], note[lang]) if part) for lang in tip
    }

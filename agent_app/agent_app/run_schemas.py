"""Run settings and models as the API returns them; the run request.

Copied from annotation_server/run_schemas.py (RunSettings, RunModel, RunModels).
"""

from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, model_validator

from .errors import Model
from .settings import ITEMS
from .shapes import ExecutionSelection


class RunSettings(Model):
    api_price_version: str | None = Field(
        None,
        description="Versioned API-equivalent price table, not subscription billing.",
    )
    model: str | None = Field(None, description="Model passed to the child CLI.")
    effort: str | None = Field(
        None, description="Reasoning effort passed to the child CLI."
    )
    tier: str | None = Field(None, description="Requested service tier.")
    cli_version: str | None = Field(None, description="Installed CLI version.")
    method: str = Field(
        "codex_exec_annotation_mcp", description="Codex or Claude Code over MCP."
    )
    target_timeout_seconds: int = Field(
        ITEMS["target_timeout_seconds"].default, description="Time limit per image."
    )
    max_mcp_calls: int = Field(
        ITEMS["max_mcp_calls"].default, description="Maximum MCP calls per image."
    )
    worker_view_max_side: int | None = Field(
        None, description="Longer side, in pixels, of the images given to the worker."
    )
    mcp_tool_timeout_seconds: int | None = Field(
        None,
        description="Time limit of one MCP tool call; null for runs started before it was a setting.",
    )
    usd_to_jpy: float | None = Field(
        None, description="Yen per US dollar for this run's yen costs."
    )
    label_colors: dict[str, str] | None = Field(
        None,
        description="The label colors when the run started; the worker sees these.",
    )
    worker_extra_instructions: str | None = Field(
        None,
        description="The shared notes this run added to the worker prompt.",
    )
    shared_revision: int | None = Field(
        None, description="The version of the shared notes this run added."
    )
    missing_reasons: dict[str, str] = Field(
        default_factory=dict, description="Why a setting is unknown."
    )


class RunModel(Model):
    model: str = Field(description="Image-capable model identifier.")
    display_name: str = Field(description="Human-readable model name.")
    efforts: list[str] = Field(description="Supported reasoning efforts.")
    default_effort: str | None = Field(
        None, description="Model-specific default effort."
    )
    speeds: list[dict] = Field(
        default_factory=list,
        description="Faster tiers to choose instead of the standard one: {id, name, description}.",
    )


class RunModels(Model):
    defaults: RunSettings = Field(description="Server defaults.")
    models: list[RunModel] = Field(
        description="Models of the usable CLIs; the first is the default (defaults.model)."
    )
    clis: dict[str, Literal["ok", "missing", "signed_out"]] = Field(
        default_factory=dict,
        description="codex / claude: ok, missing (not installed) or signed_out.",
    )
    unavailable_reason: str | None = Field(
        None, description="Why no model can run, or null."
    )


def _positive_amount(value):
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("budget_per_image_usd must be a decimal number") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("budget_per_image_usd must be positive")
    return value


# A run's cost limit per image, in US dollars as text: checked the same when a run starts and
# when a decision to run is made (review 2026-10-28: "0" was taken by a decision and refused
# only once decided).
BudgetPerImage = Annotated[str, AfterValidator(_positive_amount)]


class RunInput(ExecutionSelection):
    image_ids: (
        Annotated[
            list[Annotated[str, Field(min_length=1, max_length=80)]],
            Field(min_length=1, max_length=10000),
        ]
        | None
    ) = Field(
        None,
        description="Images of the dataset to run, in this order; null runs every image of the dataset.",
    )
    trial: bool = Field(
        False,
        description="A trial from the plan (a few images); null image_ids runs 3 images spread over the dataset (the first of its sheets' order).",
    )
    # The plan it runs, held by value (definition 11.3): a draft write (the version is made
    # from it), or a version. Neither: the plan now (the draft's write, else the latest version).
    draft_write_id: int | None = Field(
        None,
        description="The draft write to run (the write_id a draft read returns): the version is made from it.",
    )
    revision: int | None = Field(
        None, description="The instruction version to run, instead of a draft write."
    )
    # The shared notes for every worker AI, held by value as the model is (definition 18.15).
    shared_revision: int | None = Field(
        None,
        description="The version of the shared notes to add to the worker prompt; null: the version now.",
    )
    budget_per_image_usd: BudgetPerImage | None = Field(
        None,
        description="The cost limit per image in US dollars: the run stops before the next image once its known costs (unknown ones at the average) would pass it times the run's images. Left out: twice what one image cost by the run's way (model and effort) before, else the settings' run_budget_per_image_usd.",
    )

    @model_validator(mode="after")
    def one_plan(self):
        if self.draft_write_id is not None and self.revision is not None:
            raise ValueError("Give draft_write_id or revision, not both")
        return self

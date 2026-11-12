"""The AI's MCP tools (callers that are not a run's worker), each a few calls of the HTTP API
(docs/2026-10-05-app-step4-design.md 5). Results change only through the same API the screen
uses; reading is free (read-only SQL). Things are read by their type and conditions, the same
as a worker shows them (read), and seen as pictures of their type (look; definition 51).

Each tool is of a kind (definition 22.6): read, write (a draft, a reference chosen, a note:
nothing a person relies on changes), propose (a decision made ready for a person) or decision (one of
actions.DECISIONS: the outside calls it, a worker proposes it).
"""

import functools
import operator
import uuid
from dataclasses import dataclass
from typing import Annotated, Literal
from urllib.parse import quote

from pydantic import (
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from .actions import DECISION_TOOLS, DECISIONS
from .carry import CarryInput
from .confirmations import ConfirmInput
from .dataset_export import ExportInput
from .dataset_import import DatasetImportInput
from .errors import Model, invalid
from .label_change import LabelChangeInput
from .label_rename import RenameInput
from .mcp_schemas import measured
from .object_types import TYPES, types_words
from .run_schemas import BudgetPerImage
from .shapes import ViewRequest
from .system import FOLDER_EXAMPLE, THIS_COMPUTER, usual_folders

# The image paths a tool takes: files or folders of this computer, as it writes them
# (2026-11-02: "server-local" made the workers say "サーバー上").
IMAGE_PATHS = (
    f"Image files or folders {THIS_COMPUTER} (images directly inside), as it writes them"
    f" (e.g. {FOLDER_EXAMPLE})."
)
# Where to write out, asked: the person's usual folders there are, and that they may write
# another (2026-11-02: the steward asked for a folder "on the server", "/home/…/export").
_USUAL = usual_folders()
WHERE_TO = (
    f"offer as options the person's folders {', '.join(_USUAL)} (written as they are), and"
    f" that they may write another (e.g. {FOLDER_EXAMPLE})"
    if _USUAL
    else f"they write a folder that is there already (e.g. {FOLDER_EXAMPLE})"
)


class DatasetIn(Model):
    dataset_id: str


class DatasetCreateIn(Model):
    name: str = Field(min_length=1, max_length=100)
    purpose: str = Field(
        min_length=1, max_length=200, description="One line; fixed after creation."
    )
    paths: Annotated[list[str], Field(min_length=1, max_length=1000)] = Field(
        description=IMAGE_PATHS
    )
    generated_how: dict | None = Field(
        None,
        description="For generated images: how they were made. Null for photographs."
        " Images imported before keep their own.",
    )


class DraftWriteIn(Model):
    dataset_id: str
    # The instruction's draft only (the master and value drafts were taken out, types
    # design 6).
    kind: Literal["instruction"] = "instruction"
    content: dict = Field(
        description="{text, label_definitions, leave_out:[what not to annotate, one short rule each: what to leave out goes here, not in the text]}; the references stay (reference_set chooses them). Keep each label's id (a label of the library; its name is the library's); a label not in the plan yet has none (a name the library has is that label). Plus if_updated_at to refuse a write over a newer draft."
    )

    @model_validator(mode="after")
    def no_references(self):
        # References are results chosen as examples (definition 38.1).
        if "references" in self.content:
            raise ValueError(
                "content.references: choose each reference with reference_set (a result of"
                " the image)"
            )
        return self


class RunStartIn(Model):
    dataset_id: str
    budget_per_image_usd: BudgetPerImage | None = Field(
        None,
        description="The cost limit per image in US dollars (the run stops before the next image once its costs would pass it times its images). Give it only when the person gave one. Else leave it out: a run gets twice what one image cost by its way (model and effort) before, as the box's estimate says, else the settings' limit; never work it out from other costs (user 2026-10-29: a limit from Sonnet's costs stopped Astra's samples).",
    )
    image_ids: list[str] | None = Field(
        None, description="Null runs every image of the dataset."
    )
    model: str | None = None
    effort: str | None = None
    tier: str | None = Field(
        None, description="A faster tier of the model (fast mode)."
    )
    trial: bool = Field(
        False,
        description="The plan's samples (people call them 見本, samples): a trial of the plan on a few images, none of them a reference. Its results are the version's like any run's.",
    )
    draft_write_id: int | None = Field(
        None,
        description="The draft write to run (draft_write returns its write_id): the version is made from it when the run starts. With neither this nor revision: the plan now.",
    )
    revision: int | None = Field(
        None,
        description="An instruction version to run as it is (e.g. the one a trial ran), instead of a draft write.",
    )
    shared_revision: int | None = Field(
        None,
        description="The version of the shared notes for every worker AI to add; null: the version now.",
    )


class FromIn(DatasetIn):
    from_dataset_id: str = Field(description="The dataset whose instruction to copy.")
    revision: int | None = None


class ReferenceSetIn(Model):
    dataset_id: str
    image_id: str
    result_id: str | None = Field(
        description="The result taken as the image's example: an AI's (a sample's among them)"
        " or a person's fix of this image, of the plan's labels now. Null takes the image's"
        " reference out."
    )
    note: str = Field("", max_length=1000, description="What this example shows.")


class NoteIn(DatasetIn):
    text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]


class RunIn(Model):
    run_id: str


class RunWaitIn(RunIn):
    after_version: int | None = None
    timeout: Annotated[int, Field(ge=0, le=25)] = 20


class ImagesIn(DatasetIn):
    image_ids: Annotated[list[str], Field(min_length=1, max_length=10000)]


class RenameIn(DatasetIn, RenameInput):
    """The dataset and the rename's own input (from, to), as the API takes it."""


class ChangeIn(DatasetIn, LabelChangeInput):
    """The dataset and the change's own input (from, to), as the API takes it."""


class MarkIn(Model):
    target: Literal["image", "run"]
    excluded: bool
    dataset_id: str | None = None
    image_id: str | None = None
    run_id: str | None = None

    @model_validator(mode="after")
    def _a_record_is_used(self):
        # A record's images use its results; "not used" went back to a result before it that
        # differed per image and was not seen (definition 54): another record is chosen by
        # name, or images are left out.
        if self.target == "run" and self.excluded:
            raise ValueError(
                "A record is only used (excluded=false); to stop using one, use another"
                " record, pick an image's result, or leave images out"
            )
        return self


class PickIn(DatasetIn):
    image_id: str
    result_id: str | None = Field(
        None,
        description="A result of the image (its id) for training to use; null goes back to the"
        " rule (the newest success).",
    )


class ConfirmIn(DatasetIn, ConfirmInput):
    """The dataset and the check's own input (image_ids, revision), as the API takes it."""


class CarryIn(DatasetIn, CarryInput):
    """The dataset and the carrying's own input (from_dataset_id, from_revision, image_ids)."""


class AddImagesIn(DatasetIn):
    paths: Annotated[list[str], Field(min_length=1, max_length=1000)] = Field(
        description=IMAGE_PATHS
    )
    generated_how: dict | None = Field(
        None,
        description="For generated images: how they were made. Null for photographs."
        " Images imported before keep their own.",
    )


class DatasetRenameIn(DatasetIn):
    name: str = Field(min_length=1, max_length=100, description="Its new name.")


class DatasetFromIn(Model):
    name: str = Field(min_length=1, max_length=100)
    purpose: str = Field(
        min_length=1, max_length=200, description="One line; fixed after creation."
    )
    dataset_ids: Annotated[list[str], Field(min_length=1, max_length=200)] = Field(
        description="The datasets whose images it holds (each image once). One dataset is a"
        " copy of it."
    )
    instruction: bool = Field(
        False,
        description="Start its plan from the latest version (one dataset only).",
    )


class ReadIn(Model):
    """Things of one type by an id or conditions (definition 51.1)."""

    type: Literal[tuple(TYPES)]
    id: str | None = Field(
        None,
        max_length=200,
        description="One thing: an image's id or name, a version's number, a run's or a"
        " result's id, a label's id; a dataset's id to read that dataset.",
    )
    where: dict[str, str | int | bool | list[str]] | None = Field(
        None, description="Conditions {field: value}, only the type's fields."
    )
    dataset_id: str | None = Field(
        None,
        description="The dataset; none at the library (dataset, label, version, settings only).",
    )


# What look shows of a type (definition 51.1): an image or a result as a view, a dataset's
# images 16 a page, a library label's objects.
LOOK_TYPES = ("image", "result", "dataset", "label")


class LookIn(Model):
    type: Literal[LOOK_TYPES]
    id: str | None = Field(
        None,
        max_length=200,
        description="image: its id or name; result: its id (a reference is one); dataset: none"
        " for this one (at the library, a dataset's id); label: the library label's id.",
    )
    page: int = Field(1, ge=1, description="dataset: 1 to pages; 16 images a page.")
    view: ViewRequest = Field(default_factory=ViewRequest)
    dataset_id: str | None = None

    @model_validator(mode="after")
    def one_thing(self):
        if self.type in ("image", "result", "label") and not self.id:
            raise ValueError(f"id: give the {self.type}")
        measured(self.view.coordinate_view_id, [self.view.crop_xywh], "view.crop_xywh")
        return self


# Each decision's input (actions.DECISIONS): the tool's own, called or proposed (issue #3 U-02:
# a worker saw only "a dict" and guessed budget_usd and the rest).
DECISION_INPUTS = {
    "run_start": RunStartIn,
    "run_stop": RunIn,
    "mark": MarkIn,
    "pick": PickIn,
    "confirm": ConfirmIn,
    "carry": CarryIn,
    "dataset_add_images": AddImagesIn,
    "dataset_remove_images": ImagesIn,
    "label_rename": RenameIn,
    "label_change": ChangeIn,
    "dataset_rename": DatasetRenameIn,
    "dataset_create": DatasetCreateIn,
    "dataset_from": DatasetFromIn,
    "dataset_import": DatasetImportInput,
    "dataset_delete": DatasetIn,
}
assert set(DECISION_INPUTS) == set(DECISIONS), "Every decision has its tool's input"
# The union of the inputs, made from the list (Union[...] of it was rewritten by the linter).
DecisionArgs = functools.reduce(operator.or_, DECISION_INPUTS.values())


def _of_the_tool(data):
    """args by the tool's own input type (a smart union could pick a near one), with the
    proposal's dataset in them for a decision of a dataset; wrong ones say where (args.…)."""
    tool = data.get("tool")
    if tool not in DECISION_INPUTS or not isinstance(data.get("args"), dict):
        return data
    args, model = dict(data["args"]), DECISION_INPUTS[tool]
    names_dataset = "dataset_id" in model.model_fields
    if DECISIONS[tool].scope == "dataset" and names_dataset and data.get("dataset_id"):
        args.setdefault("dataset_id", data["dataset_id"])
    try:
        return {**data, "args": model.model_validate(args)}
    except ValidationError as exc:
        raise ValidationError.from_exception_data(
            exc.title,
            [
                {
                    "type": e["type"],
                    "loc": ("args", *e["loc"]),
                    "input": e["input"],
                    **({"ctx": e["ctx"]} if "ctx" in e else {}),
                }
                for e in exc.errors()
            ],
        ) from exc


class ProposalIn(Model):
    """A decision made ready for the person (the work room's trial C)."""

    dataset_id: str | None = Field(
        None,
        description="The dataset of a decision of a dataset; none for one of the library"
        " (dataset_create, dataset_from, dataset_delete, which name their datasets in args).",
    )
    tool: Literal[DECISION_TOOLS] = Field(
        description="The decision: one of the decision tools (tools/list), by name."
    )
    args: DecisionArgs = Field(
        description="The arguments of the tool, as that tool takes them (its input schema)."
        " dataset_id of a dataset's decision is the proposal's."
    )
    title: str = Field(description="One line, in the person's language: what it does.")
    reason: str = Field(description="One line, in the person's language: why now.")

    @model_validator(mode="before")
    @classmethod
    def args_of_the_tool(cls, data):
        return _of_the_tool(data) if isinstance(data, dict) else data

    # Whether the decision is of a dataset or of the library is checked where the proposal is
    # made (proposals.with_dataset), for every way in.
    @model_validator(mode="after")
    def args_are_the_tools(self):
        if type(self.args) is not DECISION_INPUTS[self.tool]:
            raise ValueError(f"args are not those of {self.tool}")
        return self


@dataclass(frozen=True)
class Tool:
    description: str
    input: type
    kind: str  # read, write, propose or decision (definition 22.6)


GENERAL = {
    "read": Tool(
        "Read things of one type, by an id or by conditions: the same types and conditions"
        " a show of yours names (what you can show, you can read). "
        + types_words()
        + " At the library (no dataset open) dataset (every dataset), label, version"
        " (every dataset's latest) and settings; the other types of a dataset you name with"
        " dataset_id. settings: the app's settings, each with its words on the screen, value,"
        " default, range and what it does, and this machine's facts (group machine: the version,"
        " the memory free now, where the data is kept); read only: a person changes them on the"
        " settings screen (設定, top right), never you, but asked to see them or about one of them"
        " (the memory free, a model), read them: a dataset's worker shows them on the right (a"
        " show of type settings), the library's (it shows nothing on the right) says what was"
        " asked in words, and that the settings screen shows them all; either way only what was"
        " asked (2026-10-30: asked to show them, a worker sent the person to the settings"
        " screen, which had no free memory; then the library's listed every setting in the talk"
        " and said it showed them on the right, which it cannot)."
        " dataset, in one: what it holds (images, the latest"
        " version, what training uses, recent runs, the map's line, the person's turns, the"
        " plan now as a draft). draft: the plan now, who decided each item and the next to ask,"
        " its writes with the request each answered. version: this dataset's versions (the"
        " runs and trials of each, what changed from the one before); others true: the other"
        " datasets' latest versions and how each was used (to start from one; query finds"
        " them). requirement: what these images were annotated for in other datasets (each"
        " with cost_per_result: USD for one image once). No coordinates are read: look at a"
        " thing for where it is.",
        ReadIn,
        "read",
    ),
    "look": Tool(
        "See a thing as a picture: an image or a result (crop, shrink and overlay; a crop comes"
        " back with a margin around it, enlarged up to 8x or shrunk to the view size; returns"
        " its view_id and what is drawn on it in its pixels; coordinates you give are in the"
        " pixels of an image you looked at, with its view_id), a dataset's images 16 a page"
        " (each tile numbered in a band under it; tiles gives each number's image name; the"
        " images spread over the folders they came from, page 1 taken from all of them, every"
        " page together every image once; to know what the images hold or to choose images of"
        " every kind, look at every page), or a library label as other datasets annotated it"
        " (up to 16 of its objects cut out into one image, the ones a person fixed first;"
        " before you ask whether what the person means is this label, look at it beside this"
        " dataset's images).",
        LookIn,
        "read",
    ),
    "proposal_make": Tool(
        "Make a decision ready for the person to decide, instead of doing it: the decision's"
        " tool (any decision tool), its arguments as that tool takes them, a title and the"
        " reason. Nothing changes until the person decides it. A decision of a dataset gives"
        " the dataset; one of the library (making, deleting a dataset) gives none. A run_start"
        " proposal holds its plan (the draft write, else the version), model and effort as they"
        " are when made; to change them, make a new one: the waiting one of its kind (samples"
        " or a run) is withdrawn, and replaced lists it. Make it after your writes of the plan:"
        " a later write withdraws it.",
        ProposalIn,
        "propose",
    ),
    "dataset_create": Tool(
        f"Import images (files or folders) {THIS_COMPUTER} and make a dataset with a fixed"
        " purpose. A decision of the library.",
        DatasetCreateIn,
        "decision",
    ),
    "dataset_from": Tool(
        "Make a dataset of the images of other datasets (no files copied; each image once),"
        " optionally starting its plan from the latest version of a single one. A decision of"
        " the library.",
        DatasetFromIn,
        "decision",
    ),
    "dataset_import": Tool(
        "Take in a folder written out in this app's form (a dataset's folder, or a folder"
        " holding several): each dataset becomes a new one with its plan, annotation records"
        " and what training uses, as they were. A decision of the library.",
        DatasetImportInput,
        "decision",
    ),
    "dataset_delete": Tool(
        "Delete a dataset and everything made in it (instruction versions, runs, drafts); its"
        " images no other dataset uses are deleted too (rows and files; the source folders are"
        " not touched). Refused while one of its runs is active. A decision of the library.",
        DatasetIn,
        "decision",
    ),
    "dataset_rename": Tool("Rename a dataset.", DatasetRenameIn, "decision"),
    "dataset_add_images": Tool(
        f"Import images (files or folders) {THIS_COMPUTER} into a dataset.",
        AddImagesIn,
        "decision",
    ),
    "dataset_remove_images": Tool(
        "Take images out of a dataset; the images and their results stay.",
        ImagesIn,
        "decision",
    ),
    "label_rename": Tool(
        "Rename a label of the dataset's plan (its latest version or its draft). A label is"
        " one for every dataset: every dataset using it takes the new name (its latest version"
        " saved as the next one when it has the label, its color and its drafts); results are"
        " shown with the new name.",
        RenameIn,
        "decision",
    ),
    "label_change": Tool(
        "Change a label of this dataset only, when it was the wrong one (another dataset may use"
        " it rightly; label_rename would change it there too). The library's labels stay: the"
        " next version takes the label named to (the plan's, the library's or a new one), and"
        " each image's annotation now is made again with it, as one record; nothing runs again."
        " A label of the plan named to must be taken the same way (shape, attributes).",
        ChangeIn,
        "decision",
    ),
    "instruction_from": Tool(
        "Copy another dataset's instruction (text and labels, not references) into this"
        " dataset's instruction draft; refused over an existing draft.",
        FromIn,
        "write",
    ),
    "reference_set": Tool(
        "Choose the plan's reference of an image (an example the workers see of how to"
        " annotate, where the plan's words leave the way open): a result of the image, an AI's"
        " (a sample's among them) or a person's fix. You never draw one: a worker annotates, a person fixes, you choose. The image is"
        " then left out of samples and runs (its annotation is the reference). Null result_id"
        " takes it out. A write of the draft, no decision.",
        ReferenceSetIn,
        "write",
    ),
    "draft_write": Tool(
        "Write the dataset's instruction draft (text, labels, leave_out) in one call; the"
        " references stay (reference_set chooses them). What not to annotate goes in"
        " leave_out, one rule a line, not in the text (the text is how to draw): leave_out"
        " changed makes the annotations before another criteria's, the text does not"
        " (definition 85.16). People"
        " see it on the screen. Returns its write_id. A version is made from it when a run of"
        " it starts; there is no saving.",
        DraftWriteIn,
        "write",
    ),
    "run_start": Tool(
        "Start a run (one AI worker per image). One run at a time. Then call run_wait.",
        RunStartIn,
        "decision",
    ),
    "run_wait": Tool(
        "Wait until the run's status or an image's result changes; pass the returned version"
        " as after_version next time.",
        RunWaitIn,
        "read",
    ),
    "run_stop": Tool(
        "Stop a run; unfinished images become interrupted.", RunIn, "decision"
    ),
    "mark": Tool(
        "Whether training uses it. An image: not used (excluded=true) or used again. A record"
        " (target run, excluded=false): its images use its results.",
        MarkIn,
        "decision",
    ),
    "pick": Tool(
        "Which result of an image training uses: one of its results, or back to the rule"
        " (result_id null: the newest success).",
        PickIn,
        "decision",
    ),
    "confirm": Tool(
        "A person checked images' annotations now by a version's criteria (definition 85.5):"
        " each image's annotation by that version (its text, what it leaves out, the labels'"
        " descriptions) is right. Propose it only when you saw the images and they are right by"
        " that version; a run by the plan is not a check. It changes no annotation and not what"
        " training uses.",
        ConfirmIn,
        "decision",
    ),
    "carry": Tool(
        "Copy annotations over (definition 85.15): each image's annotation now by a version of"
        " this dataset or of another one (from_dataset_id, from_revision: name both) is copied"
        " as this dataset's plan's result, as one record. For a plan whose labels, shapes or"
        " parents changed (an attribute added needs none: the annotations stay, definition"
        " 85.17) or results made in another dataset with these images. Only images with no annotation by the plan take"
        " one; an object of a label the plan does not have is left out. The results keep the"
        " criteria they were made by: when those differ from the plan's, say so (check them or"
        " annotate again).",
        CarryIn,
        "decision",
    ),
    "datasets_export": Tool(
        f"Write datasets out into a folder {THIS_COMPUTER} (definition 60.4): app (this app's"
        " form, to give to another person using it: images, plan, annotation records) or coco"
        " (COCO's JSON, to open and analyse in other tools). Each dataset gets a new folder"
        " under dest (never written over). dest is the person's: the folder they named; when"
        " they named none, ask where before writing, never choose one yourself (2026-10-29: a"
        f" dataset was written into the home folder unasked): {WHERE_TO}. Nothing in the app"
        " changes: no proposal; say where it was written. The library's worker writes any"
        " datasets, a dataset's its own.",
        ExportInput,
        "write",
    ),
    "note_write": Tool(
        "Leave a note for the other workers of this dataset (what you found that they should"
        " know, e.g. an image Haiku cannot read). Not a change of the data; no proposal.",
        NoteIn,
        "write",
    ),
}
assert {n for n, t in GENERAL.items() if t.kind == "decision"} == set(DECISIONS), (
    "The decision tools are the decisions of actions.DECISIONS"
)
NEXT = {
    "read": ["look", "read", "proposal_make"],
    "dataset_create": ["draft_write"],
    "draft_write": ["proposal_make"],
    "run_start": ["run_wait"],
    "run_wait": ["run_wait", "look", "reference_set", "read"],
}


def result_drawn(request, result_id):
    """What a result's view drew (view's drawn): its annotations the frame names, read at the
    frame's revision."""

    async def read_view(frame):
        path = f"/v1/results/{result_id}"
        params = {"revision": frame["revision"]}
        state = (await request("GET", path, params=params)).json()
        ids = set(frame["annotation_ids"])
        return [a for a in state["annotations"] if a["id"] in ids]

    return read_view


def worker_reads(data):
    """What a worker reads (definition 51.3): no coordinates (it never draws, definition 38;
    it looks at a thing for where it is), and at most 100 of a set (its count says how
    many)."""
    if isinstance(data, list):
        return [worker_reads(v) for v in data]
    if not isinstance(data, dict):
        return data
    out = {k: worker_reads(v) for k, v in data.items() if k != "geometry"}
    if isinstance(out.get("items"), list):
        out["items"] = out["items"][:100]
    return out


def kept_in_place(path):
    """A tool's path, built from the ids it was given, as it is sent: refused when an id would
    move it elsewhere (review 2026-10-28 C#1: look(type="label", id="../datasets/B") read
    another dataset's sheet, the HTTP client resolving ".."). Every tool's call is sent through
    here (the MCP tools' and a decision's)."""
    if any(part in (".", "..") for part in path.split("?", 1)[0].split("/")):
        raise invalid("An id is not a path: no . or .. in it", path=path)
    return path


async def run_tool(name, args, request, write, view, picture):
    """Run one AI tool. request/write call the HTTP API (write marks a save); view returns
    an image as the AI is told it; picture shows an image as it is (a sheet). Returns (data,
    the images shown: none, one, or a crop and the whole image after a write)."""
    match name:
        case "read":
            # Conditions as the screen's query (true/false, ids as a comma list).
            params = {
                k: ",".join(v)
                if isinstance(v, list)
                else str(v).lower()
                if isinstance(v, bool)
                else str(v)
                for k, v in (args.where or {}).items()
            }
            one = f"/{quote(args.id, safe='')}" if args.id else ""
            if args.type == "dataset" and args.id:
                # A dataset's own facts are read in it (its summary).
                path, params = f"/v1/datasets/{args.id}/objects/dataset{one}", {}
            elif args.dataset_id:
                path = f"/v1/datasets/{args.dataset_id}/objects/{args.type}{one}"
            else:
                path = f"/v1/objects/{args.type}{one}"
            return worker_reads((await request("GET", path, params=params)).json()), []
        case "look":
            body = args.view.model_dump(mode="json", exclude_unset=True)
            match args.type:
                case "image":
                    return None, [await view(f"/v1/images/{args.id}/views", body)]
                case "result":
                    path = f"/v1/results/{args.id}/views"
                    return None, [
                        await view(path, body, result_drawn(request, args.id))
                    ]
                case "dataset":
                    path = f"/v1/datasets/{args.id or args.dataset_id}/sheet"
                    data = (
                        await request("GET", path, params={"page": args.page})
                    ).json()
                case _:
                    data = (await request("GET", f"/v1/labels/{args.id}/sheet")).json()
            await picture(data.pop("image"))
            return data, []
        case "dataset_create":
            origin = (
                {"kind": "generated", "how": args.generated_how}
                if args.generated_how
                else None
            )
            body = {
                "name": args.name,
                "purpose": args.purpose,
                "paths": args.paths,
                "origin": origin,
            }
            return (await write("POST", "/v1/datasets", json=body)).json(), []
        case "datasets_export":
            # No data changes (nothing to mark as written).
            body = args.model_dump(mode="json")
            return (await request("POST", "/v1/library/export", json=body)).json(), []
        case "dataset_from":
            body = args.model_dump(mode="json")
            return (await write("POST", "/v1/datasets/from", json=body)).json(), []
        case "dataset_import":
            body = args.model_dump(mode="json")
            return (await write("POST", "/v1/library/import", json=body)).json(), []
        case "dataset_delete":
            path = f"/v1/datasets/{args.dataset_id}"
            return (await write("DELETE", path)).json(), []
        case "dataset_rename":
            path = f"/v1/datasets/{args.dataset_id}"
            body = {"name": args.name}
            return (await write("PATCH", path, json=body)).json(), []
        case "dataset_add_images":
            path = f"/v1/datasets/{args.dataset_id}/images/import"
            origin = (
                {"kind": "generated", "how": args.generated_how}
                if args.generated_how
                else None
            )
            body = {"paths": args.paths, "origin": origin}
            return (await write("POST", path, json=body)).json(), []
        case "dataset_remove_images":
            path = f"/v1/datasets/{args.dataset_id}/images/remove"
            body = {"image_ids": args.image_ids}
            return (await write("POST", path, json=body)).json(), []
        case "label_rename":
            path = f"/v1/datasets/{args.dataset_id}/labels/rename"
            body = {"from": args.old, "to": args.new}
            return (await write("POST", path, json=body)).json(), []
        case "label_change":
            path = f"/v1/datasets/{args.dataset_id}/labels/change"
            body = {"from": args.old, "to": args.new}
            return (await write("POST", path, json=body)).json(), []
        case "instruction_from":
            path = f"/v1/datasets/{args.dataset_id}/instruction-from"
            body = {"dataset_id": args.from_dataset_id, "revision": args.revision}
            return (await write("POST", path, json=body)).json(), []
        case "reference_set":
            path = f"/v1/datasets/{args.dataset_id}/images/{args.image_id}/reference"
            if args.result_id is None:
                return (await write("DELETE", path)).json(), []
            body = {"result_id": args.result_id, "note": args.note}
            return (await write("PUT", path, json=body)).json(), []
        case "draft_write":
            path = f"/v1/datasets/{args.dataset_id}/drafts/instruction"
            return (await write("PUT", path, json=args.content)).json(), []
        case "run_start":
            body = args.model_dump(exclude={"dataset_id"})
            path = f"/v1/datasets/{args.dataset_id}/runs/{uuid.uuid4()}"
            return (await write("PUT", path, json=body)).json(), []
        case "run_wait":
            params = {"timeout": args.timeout}
            if args.after_version is not None:
                params["after_version"] = args.after_version
            run = (
                await request("GET", f"/v1/runs/{args.run_id}/wait", params=params)
            ).json()
            results = (await request("GET", f"/v1/runs/{args.run_id}/results")).json()
            return {**run, "results": results["results"]}, []
        case "run_stop":
            return (await write("POST", f"/v1/runs/{args.run_id}/stop")).json(), []
        case "mark":
            if args.target == "run":
                path = f"/v1/runs/{args.run_id}/use"
            else:
                action = "exclude" if args.excluded else "include"
                path = f"/v1/datasets/{args.dataset_id}/images/{args.image_id}/{action}"
            return (await write("POST", path)).json(), []
        case "pick":
            path = f"/v1/datasets/{args.dataset_id}/images/{args.image_id}/adoption"
            if args.result_id is None:
                return (await write("DELETE", path)).json(), []
            body = {"result_id": args.result_id}
            return (await write("PUT", path, json=body)).json(), []
        case "carry":
            path = f"/v1/datasets/{args.dataset_id}/carry"
            body = args.model_dump(mode="json", exclude={"dataset_id"})
            return (await write("POST", path, json=body)).json(), []
        case "confirm":
            path = f"/v1/datasets/{args.dataset_id}/confirmations"
            body = args.model_dump(mode="json", exclude={"dataset_id"})
            return (await write("POST", path, json=body)).json(), []
        case "note_write":
            path = f"/v1/datasets/{args.dataset_id}/notes"
            return (await write("POST", path, json={"text": args.text})).json(), []
        case "proposal_make":
            path = (
                f"/v1/datasets/{args.dataset_id}/proposals"
                if args.dataset_id
                else "/v1/library/proposals"
            )
            # Its args by the names the tool takes (a label's from and to).
            body = args.model_dump(
                mode="json", exclude={"dataset_id"}, exclude_unset=True, by_alias=True
            )
            return (await write("POST", path, json=body)).json(), []
    raise ValueError("Unknown tool; call tools/list")

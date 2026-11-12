"""Instruction versions and the requirement key computed from them (step 1 design 5-6).

A version holds the instruction text (means: how to work), the label definitions, what is
left out, and the references, each pointing at a result's annotation set and its revision
(definition 38.1; chosen by references). The requirement (what output is expected) is the
structural part of the label definitions; it is computed, never edited by people
(docs/2026-10-05-data-model.md 4.2, D1).
"""

import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from .datasets import dataset_row
from .db import encoded, now
from .errors import ApiError, Model, invalid, not_found
from .label_library import key_of, register, with_library
from .shapes import LABEL_MAX
from .usage import empty, origin_of, version_usage

MAX_LABELS = 100
MAX_DESCRIPTION = 500
MAX_ATTRIBUTES = 20
MAX_CHOICES = 50
MAX_TEXT = 8000

Scope = Literal["image", "group"]


class AttributeDefinition(Model):
    name: str = Field(description="Unique within its label; 1 to 32 characters.")
    type: Literal["text", "number", "choice"]
    choices: (
        Annotated[
            list[Annotated[str, Field(min_length=1, max_length=64)]],
            Field(max_length=MAX_CHOICES),
        ]
        | None
    ) = Field(
        None, description="The values a choice attribute allows; only for choice."
    )
    description: str = Field("", max_length=MAX_DESCRIPTION)
    scope: Scope = Field(
        "image",
        description="image: a master's value checks only its own image; group: also the other images of its subset.",
    )

    @field_validator("name")
    @classmethod
    def name_length(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 32:
            raise ValueError("attribute name must contain 1 to 32 characters")
        return value


class LabelDefinition(Model):
    id: str | None = Field(
        None,
        description="The library label's id (the same label in every dataset); leave it out"
        " for a label not in the plan yet: a name the library has is that label, else the"
        " server gives a new one.",
        max_length=40,
    )
    name: str = Field(description=f"Label, trimmed; 1 to {LABEL_MAX} characters.")
    shape: Literal["bbox", "polygon", "image"] = Field(
        description="bbox, polygon, or image: one answer for the whole image (VQA), its questions as attributes, saved as a box over the whole image."
    )
    parent: str | None = Field(
        None,
        description="The label this one is part of, by name: an object of it is inside an"
        " object of the parent (a band in its box). Not a kind of the parent.",
    )
    description: str = Field("", max_length=MAX_DESCRIPTION)
    attributes: Annotated[
        list[AttributeDefinition], Field(max_length=MAX_ATTRIBUTES)
    ] = Field(default_factory=list)
    scope: Scope = Field(
        "image",
        description="image: a master's position checks only its own image; group: also the other images of its subset.",
    )

    @field_validator("name")
    @classmethod
    def name_length(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= LABEL_MAX:
            raise ValueError(
                f"label must contain 1 to {LABEL_MAX} characters after trimming"
            )
        return value


class InstructionInput(Model):
    text: str = Field(
        "", max_length=MAX_TEXT, description="How to work; not part of the requirement."
    )
    label_definitions: Annotated[
        list[LabelDefinition], Field(min_length=1, max_length=MAX_LABELS)
    ]
    leave_out: Annotated[
        list[
            Annotated[
                str,
                StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
            ]
        ],
        Field(max_length=20),
    ] = Field(
        default_factory=list,
        description="What not to annotate and how a borderline object is taken, one short rule"
        " each (definition 26.2); how to work, not part of the requirement.",
    )


# What a plan's own input holds; its references point at results (references).
INPUT = tuple(InstructionInput.model_fields)


def check_references(db, references, definitions):
    """At a version's save: every object of its references is of a label the version defines,
    drawn in that label's shape (a reference shows how the answer looks, definition 26.2a). A
    draft may hold a label just removed; a reference is checked against the plan's labels when
    chosen (references.reference_set)."""
    from .references import resolved

    shapes = {d["name"]: d["shape"] for d in definitions}
    for reference in resolved(
        db, {"references": references, "label_definitions": definitions}
    )["references"]:
        for item in reference["annotations"]:
            if item["label"] not in shapes:
                raise invalid(
                    "A reference uses a label that is not defined",
                    image_id=reference["image_id"],
                    label=item["label"],
                )
            shape = (
                "bbox" if shapes[item["label"]] == "image" else shapes[item["label"]]
            )
            if item["geometry"]["type"] != shape:
                raise ApiError(
                    422,
                    "reference_shape",
                    "A reference draws a label in its own shape",
                    {
                        "image_id": reference["image_id"],
                        "label": item["label"],
                        "shape": shapes[item["label"]],
                    },
                )


def _wrong(reason, message, **details):
    """A wrong label definition, with its reason for the screen's own words (step 12)."""
    return ApiError(422, "invalid_definition", message, {"reason": reason, **details})


def check_definitions(definitions):
    """Names unique (as the library finds a name, 26.1), parents among the labels and never a
    loop, choices only and always on a choice attribute, attribute names unique within a label."""
    names = [key_of(d["name"]) for d in definitions]
    if len(set(names)) != len(names):
        raise _wrong("duplicate_labels", "Labels must be unique")
    by_name = {d["name"]: d for d in definitions}
    for definition in definitions:
        label, parent, seen = definition["name"], definition.get("parent"), set()
        if parent is not None and parent not in by_name:
            raise _wrong(
                "unknown_parent",
                "parent must be one of the labels",
                label=label,
                parent=parent,
            )
        while parent is not None:
            if parent == label or parent in seen:
                raise _wrong(
                    "parent_loop", "Parents of labels must not loop", label=label
                )
            seen.add(parent)
            parent = by_name[parent].get("parent")
        attributes = definition.get("attributes", [])
        if len({a["name"] for a in attributes}) != len(attributes):
            raise _wrong(
                "duplicate_attributes",
                "Attribute names must be unique within a label",
                label=label,
            )
        for attribute in attributes:
            choices = attribute.get("choices")
            if attribute["type"] == "choice" and (
                not choices or len(set(choices)) != len(choices)
            ):
                raise _wrong(
                    "choices_required",
                    "A choice attribute needs unique choices",
                    label=label,
                    attribute=attribute["name"],
                )
            if attribute["type"] != "choice" and choices:
                raise _wrong(
                    "choices_only_choice",
                    "Only a choice attribute has choices",
                    label=label,
                    attribute=attribute["name"],
                )


def label_form(definition, parent):
    """The form of one label's output: shape, parent (as the caller names it), scope and
    attributes (name, type, choices, scope). No choices (null or []) is one value (data-model
    13.2); descriptions and the order of attributes and choices do not count."""
    d = definition
    return [
        d["shape"],
        parent,
        d.get("scope", "image"),
        sorted(
            [
                a["name"],
                a["type"],
                sorted(a.get("choices") or []),
                a.get("scope", "image"),
            ]
            for a in d.get("attributes", [])
        ),
    ]


def label_requirement(definition, ids):
    """The part of one label definition that is the requirement: the label (its id, not its
    name: renamed, it is the same label; definition 23.3), its shape, its parent by id and its
    scope. The attributes are not (definition 85.17: an attribute added keeps the boxes; a value
    missing is counted, label_rules.unfilled). ids: name -> id of the same definitions (every
    label has one: label_ids.with_ids)."""
    parent = definition.get("parent")
    return [
        definition["id"],
        definition["shape"],
        ids[parent] if parent else None,
        definition.get("scope", "image"),
    ]


def requirement_key(definitions):
    """The same key for the same expected output; the text and the order of labels do not
    count either."""
    ids = {d["name"]: d["id"] for d in definitions}
    labels = sorted(label_requirement(d, ids) for d in definitions)
    return "req-" + hashlib.sha256(encoded(labels).encode()).hexdigest()[:16]


def criteria_key(payload):
    """The plan's criteria (definition 85.3, 85.16): what it leaves out, the order not counted.
    The text and the labels' and attributes' descriptions are how to draw, as the references
    are: said again, the results before are not stopped (nor said to mean the same; the version
    they were made by keeps its words). The output's form is the requirement's."""
    said = {"leave_out": sorted(payload.get("leave_out") or [])}
    return "crt-" + hashlib.sha256(encoded(said).encode()).hexdigest()[:16]


def basis_of(payload):
    """What a plan judges images by (definition 35.7, 85.4): (its requirement, its criteria);
    (None, None) for none or a blank one (49.1: every result is another plan's)."""
    if not payload or "label_definitions" not in payload:
        return None, None
    return requirement_key(payload["label_definitions"]), criteria_key(payload)


def save_instruction(
    db,
    dataset_id,
    body: InstructionInput,
    actor,
    *,
    decision_id,
    references=None,
    draft_write_id=None,
    origin=None,
):
    """The next version, made by the decision decision_id (definition 22.1: a run decided from a
    draft write, a label renamed or changed, a dataset taken in): the content, its references
    (pointers at results, definition 38.1) and, when a run made it, the draft write it was made
    from with where that was started from (definition 15.1; None: not known)."""
    payload = {
        **body.model_dump(mode="json"),
        "references": references or [],
    }
    check_definitions(payload["label_definitions"])
    check_references(db, payload["references"], payload["label_definitions"])
    with db.transaction():
        dataset_row(db, dataset_id)
        last = latest_row(db, dataset_id)
        # Each label is the library's (definition 26.1; 23.2 within the dataset), and the labels
        # new to the library enter it with this version.
        payload = with_library(
            db,
            payload,
            json.loads(last["payload_json"])["label_definitions"] if last else (),
        )
        # Named as the library names them, two labels can be one name.
        check_definitions(payload["label_definitions"])
        register(db, payload["label_definitions"], actor)
        key = requirement_key(payload["label_definitions"])
        revision = (last["revision"] if last else 0) + 1
        db.execute(
            "INSERT INTO instructions(dataset_id,revision,created_at,created_by,payload_json,"
            "requirement_key,decision_id,draft_write_id,from_kind,from_dataset_id,"
            "from_revision) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                dataset_id,
                revision,
                now(),
                actor,
                encoded(payload),
                key,
                decision_id,
                draft_write_id,
                *(
                    (origin["kind"], origin.get("dataset_id"), origin.get("revision"))
                    if origin
                    else (None, None, None)
                ),
            ),
        )
    return {
        "revision": revision,
        "requirement_key": key,
        "requirement_changed": last is None or last["requirement_key"] != key,
    }


def list_instructions(db, dataset_id):
    """The versions, newest first, with how the AI used each (S2, definition 15.2; the runs and
    trials of the plan's record, types design 20.2) and where each came from (15.1)."""
    dataset_row(db, dataset_id)
    usage = version_usage(db, dataset_id)
    found = []
    for r in reversed(version_rows(db, dataset_id)):
        used = usage.get(r["revision"]) or empty()
        found.append(
            {
                **{k: r[k] for k in ("revision", "created_at", "created_by")},
                "requirement_key": r["requirement_key"],
                "runs": used["runs"],
                "trials": used["trials"],
                "trial_images": used["trial_images"],
                "usage": used,
                "from": origin_of(r),
            }
        )
    return {"instructions": found}


def version_diff(db, dataset_id, revision):
    """What a version changed from the one before it (types design 20.3)."""
    from .draft_diff import payload_diff

    this = get_instruction(db, dataset_id, revision)
    before = (
        get_instruction(db, dataset_id, str(this["revision"] - 1))
        if this["revision"] > 1
        else None
    )
    # As a draft's: the version it is compared with (0: none before).
    return {"revision": this["revision"] - 1, **payload_diff(before, this)}


def latest_row(db, dataset_id):
    """The dataset's latest version as stored, None before one: the one place every reader of
    the latest version goes to (fact inventory 2; 2026-10-30: 21 places read it themselves)."""
    return db.one(
        "SELECT * FROM instructions WHERE dataset_id=? ORDER BY revision DESC LIMIT 1",
        (dataset_id,),
    )


def version_row(db, dataset_id, revision):
    """A version by its number as stored, None when there is none."""
    return db.one(
        "SELECT * FROM instructions WHERE dataset_id=? AND revision=?",
        (dataset_id, revision),
    )


def version_rows(db, dataset_id):
    """Every version of the dataset as stored, oldest first."""
    return db.execute(
        "SELECT * FROM instructions WHERE dataset_id=? ORDER BY revision", (dataset_id,)
    )


def all_versions(db):
    """Every version of every dataset as stored (a version's line crosses datasets, 15.1)."""
    return db.execute("SELECT * FROM instructions")


def latest_rows(db):
    """Every dataset's latest version as stored, in the order they were made."""
    return db.execute(
        "SELECT i.* FROM instructions i JOIN (SELECT dataset_id, max(revision) AS r FROM"
        " instructions GROUP BY dataset_id) m ON m.dataset_id=i.dataset_id AND m.r=i.revision"
        " ORDER BY i.created_at"
    )


def latest_revision(db, dataset_id):
    """The number of the dataset's latest version, None before one."""
    row = latest_row(db, dataset_id)
    return row["revision"] if row else None


def version_payload(db, dataset_id, revision):
    """A version's content (text, labels, leave out, references) by its number, None when
    there is none."""
    row = version_row(db, dataset_id, revision)
    return json.loads(row["payload_json"]) if row else None


def latest_requirement(db, dataset_id):
    """The requirement of the dataset's latest version (None before one): what its runs and
    training are of, the basis of Apply's views (definition 35.7)."""
    row = latest_row(db, dataset_id)
    return row["requirement_key"] if row else None


def latest_payload(db, dataset_id):
    """The content of the dataset's latest version, {} before one (a blank plan's, 49.1)."""
    return version_payload(db, dataset_id, latest_revision(db, dataset_id)) or {}


def latest_basis(db, dataset_id):
    """(requirement, criteria) of the dataset's latest version, (None, None) before one: what
    its images are judged by (definition 85.4)."""
    return basis_of(latest_payload(db, dataset_id))


def get_instruction(db, dataset_id, revision):
    dataset_row(db, dataset_id)
    if revision == "latest":
        row = latest_row(db, dataset_id)
    else:
        try:
            number = int(revision)
        except ValueError as exc:
            raise invalid("revision must be a number or latest") from exc
        row = version_row(db, dataset_id, number)
    if row is None:
        raise not_found("Instruction version")
    return {
        "revision": row["revision"],
        "created_at": row["created_at"],
        "created_by": row["created_by"],
        "requirement_key": row["requirement_key"],
        "from": origin_of(row),
        **json.loads(row["payload_json"]),
    }


def requirement(db, dataset_id):
    """(revision, requirement key, label definitions) of the latest instruction version."""
    row = latest_row(db, dataset_id)
    if row is None:
        raise ApiError(422, "instruction_required", "Create an instruction first")
    definitions = json.loads(row["payload_json"])["label_definitions"]
    return row["revision"], row["requirement_key"], definitions

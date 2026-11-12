"""A write into a result must follow the label definitions of the run's instruction version.

Copied from annotation_server/label_definitions.py (check_annotation, check_batch). A result
is written under one version only, so there is no older label or shape to keep. The two writes
of annotations (annotation_sets.fill and apply_batch) check every write with these.
"""

from types import SimpleNamespace

from .errors import invalid


def _value_ok(attribute, value):
    if value is None:
        return True
    if attribute["type"] == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if not isinstance(value, str):
        return False
    return attribute["type"] == "text" or value in (attribute.get("choices") or [])


def fitting(definition, attributes):
    """The values of attributes that the plan's label reads (definition 85.17): of its
    attributes and of their types. A value the plan does not have or cannot read is not kept
    (a result copied or fixed from another version's)."""
    defined = {a["name"]: a for a in (definition or {}).get("attributes", [])}
    return {
        name: value
        for name, value in (attributes or {}).items()
        if name in defined and value is not None and _value_ok(defined[name], value)
    }


def unfilled(definitions, objects):
    """The plan's attributes, in its order, that an object of their label has no value of the
    plan can read (definition 85.17): what is not filled, counted where attributes are used.
    objects: {label (the plan's name), attributes}."""
    by_name = {d["name"]: d for d in definitions or []}
    missing = set()
    for o in objects:
        definition = by_name.get(o["label"])
        if definition is None:
            continue
        kept = fitting(definition, o.get("attributes"))
        missing.update(
            a["name"] for a in definition.get("attributes", []) if a["name"] not in kept
        )
    return [
        a["name"]
        for d in definitions or []
        for a in d.get("attributes", [])
        if a["name"] in missing
    ]


def check_annotation(definitions, label, kind, parent_label, attributes, **checks):
    """A label of the definitions in its shape, a parent of its parent label, and only its
    attributes with values of their types. checks: check_parent, check_attributes."""
    by_name = {d["name"]: d for d in definitions}
    definition = by_name.get(label)
    if definition is None:
        raise invalid("Label must be one of the task's labels", labels=list(by_name))
    # An answer for the whole image (VQA) is kept as a box over the image; an outline's label
    # holds a mask too, an outline that is not one polygon (several, crossing; definition 60.12).
    if kind != definition["shape"] and (definition["shape"], kind) not in (
        ("image", "bbox"),
        ("polygon", "mask"),
    ):
        raise invalid(
            "Geometry type must match the label's shape",
            label=label,
            shape=definition["shape"],
        )
    if (
        checks.get("check_parent", True)
        and parent_label is not None
        and parent_label != definition.get("parent")
    ):
        raise invalid(
            "parent must be an annotation of the label's parent label",
            label=label,
            parent_label=definition.get("parent"),
        )
    if checks.get("check_attributes", True):
        defined = {a["name"]: a for a in definition.get("attributes", [])}
        for name, value in (attributes or {}).items():
            attribute = defined.get(name)
            if attribute is None:
                raise invalid(
                    "Attribute is not defined for this label",
                    label=label,
                    attribute=name,
                    attributes=list(defined),
                )
            if not _value_ok(attribute, value):
                raise invalid(
                    "Attribute value does not match its type",
                    label=label,
                    attribute=name,
                    type=attribute["type"],
                    choices=attribute.get("choices"),
                )


def check_creates(definitions, creates):
    """The creates that fill a new set (a parent is the ref of another create)."""
    check_batch(definitions, [], SimpleNamespace(operations=creates))


def check_batch(definitions, current, batch):
    """Creates and updates of a batch, with the set's annotations now (a parent may be an
    existing ID or the ref of a create in the batch)."""
    known = {ann["id"]: ann for ann in current}
    deleted = {op.id for op in batch.operations if op.op == "delete"}
    labels = {
        op.ref: op.label for op in batch.operations if op.op == "create" and op.ref
    }
    for op in batch.operations:
        if op.op == "delete":
            continue
        given = op.model_fields_set
        names_parent = op.op == "create" or "parent" in given
        parent_label = None
        if names_parent and op.parent is not None:
            if op.parent in labels:
                parent_label = labels[op.parent]
            elif op.parent in known and op.parent not in deleted:
                parent_label = known[op.parent]["label"]
        check_annotation(
            definitions,
            op.label,
            op.geometry.type,
            parent_label,
            op.attributes,
            check_parent=names_parent,
            check_attributes=op.op == "create" or "attributes" in given,
        )

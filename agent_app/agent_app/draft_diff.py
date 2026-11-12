"""What the instruction draft changed since the latest version, shown above ①'s cards (step 19
design 4): labels added, removed, renamed and changed, the sentences of the text added and
removed, the references, what is left out.
"""

import difflib
import json
import re

from .datasets import dataset_row
from .drafts import plan_draft
from .errors import not_found
from .instructions import label_form, latest_row

MOST = 8  # sentences listed each way; the rest counted


def sentences(text):
    """The text cut after each "。", "." or line end; empty pieces dropped."""
    return [
        s.strip() for s in re.split(r"(?<=[。.!?！？])|\n", text or "") if s.strip()
    ]


def _text(old, new):
    added, removed = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, old, new, autojunk=False
    ).get_opcodes():
        if tag in ("delete", "replace"):
            removed += old[i1:i2]
        if tag in ("insert", "replace"):
            added += new[j1:j2]
    return {
        "added": added[:MOST],
        "removed": removed[:MOST],
        "more": max(0, len(added) - MOST) + max(0, len(removed) - MOST),
    }


def _pairs(old, new):
    """Each label of new with the one of old it is (None: added), then old's left (removed):
    by the library's id when both have one (a renamed label is the same label; 2026-10-30: a
    version made by a rename said one label added and one removed), else by name."""
    left = list(old)
    by_id = {d["id"]: d for d in old if d.get("id")}
    pairs = []
    for d in new:
        was = by_id.get(d.get("id")) if d.get("id") else None
        if was is None or was not in left:
            was = next((o for o in left if o["name"] == d["name"]), None)
        if was is not None:
            left.remove(was)
        pairs.append((was, d))
    return pairs + [(o, None) for o in left]


def payload_diff(old, new):
    """How one instruction's content differs from another's: labels added, removed, renamed
    and changed (the requirement), labels whose description changed, the sentences of the
    text, the references. The same for a draft against a version or against an earlier
    draft."""
    old = old or {"text": "", "label_definitions": [], "references": []}
    pairs = _pairs(old.get("label_definitions", []), new.get("label_definitions", []))
    both = [(b, a) for b, a in pairs if b is not None and a is not None]
    # A parent named in old by its name then.
    named_now = {b["name"]: a["name"] for b, a in both}
    # A label whose output's form changed (whether it is the same label is the requirement's,
    # not the difference's).
    changed = [
        a["name"]
        for b, a in both
        if label_form(a, a.get("parent"))
        != label_form(b, named_now.get(b.get("parent"), b.get("parent")))
    ]

    # Descriptions are not the requirement, yet the person checks them before saving (Astra
    # 2026-10-06: a changed description showed "the same as the saved version").
    def as_said(d):
        return [d.get("description", "")] + [
            [a["name"], a.get("description", "")] for a in d.get("attributes", [])
        ]

    return {
        "added": [a["name"] for b, a in pairs if b is None],
        "removed": [b["name"] for b, a in pairs if a is None],
        "renamed": [[b["name"], a["name"]] for b, a in both if b["name"] != a["name"]],
        "changed": changed,
        "described": [
            a["name"]
            for b, a in both
            if a["name"] not in changed and as_said(a) != as_said(b)
        ],
        "text_changed": new.get("text", "") != old.get("text", ""),
        "references": [len(old.get("references", [])), len(new.get("references", []))],
        "text": _text(sentences(old.get("text", "")), sentences(new.get("text", ""))),
        "leave_out": _text(old.get("leave_out") or [], new.get("leave_out") or []),
    }


def plan_changes(old, new):
    """What a plan says differently from another, short, as a decision and a record show it
    (definition 11.10): None when it says the same."""
    found = payload_diff(old, new)
    short = {
        **{
            k: found[k] for k in ("added", "removed", "renamed", "changed", "described")
        },
        "text_added": found["text"]["added"][:3],
        "text_removed": found["text"]["removed"][:3],
        "text_more": max(0, len(found["text"]["added"]) - 3)
        + max(0, len(found["text"]["removed"]) - 3)
        + found["text"]["more"],
        "references": found["references"],
        "leave_out": found["leave_out"],
    }
    same = not (
        short["added"]
        or short["removed"]
        or short["renamed"]
        or short["changed"]
        or short["described"]
        or found["text_changed"]
        or short["references"][0] != short["references"][1]
        or found["leave_out"]["added"]
        or found["leave_out"]["removed"]
    )
    return None if same else short


def draft_changes(db, dataset_id):
    """The draft against the latest version."""
    dataset_row(db, dataset_id)
    row = plan_draft(db, dataset_id)
    if row is None:
        raise not_found("Instruction draft")
    latest = latest_row(db, dataset_id)
    return {
        "revision": latest["revision"] if latest else None,
        **payload_diff(
            json.loads(latest["payload_json"]) if latest else None,
            json.loads(row["payload_json"]),
        ),
    }

"""Deleting a dataset and making another one from the same images (data-model 3): images are
shared and never copied; deleting a dataset deletes the images no other dataset uses, rows and
files (user 2026-10-15: what no dataset uses is seen nowhere, so it goes). A copy can bring the
instruction (step 8; the masters it once brought were taken out, types design 6).
"""

import json
import os
from typing import Annotated

from pydantic import Field, StringConstraints

from . import decisions
from .datasets import (
    dataset_row,
    get_dataset,
    image_ids,
    image_rows,
    images_only_in,
    insert_dataset,
    insert_images,
    shared_with,
)
from .db import new_id, now
from .drafts import write_plan
from .errors import ApiError, Model
from .images import source_paths
from .instructions import latest_row, version_rows
from .run_queries import dataset_results, dataset_runs, going, is_trial

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CopyInput(Model):
    name: Annotated[Text, Field(max_length=100)]
    purpose: Annotated[Text, Field(max_length=200)]
    instruction: bool = Field(
        True, description="Start from the latest instruction version."
    )


class FromDatasetsInput(Model):
    name: Annotated[Text, Field(max_length=100)]
    purpose: Annotated[Text, Field(max_length=200)]
    dataset_ids: Annotated[list[str], Field(min_length=1, max_length=200)]
    instruction: bool = Field(
        False,
        description="Start from the latest instruction version (one dataset only).",
    )


def _made(db, op, body, dataset_ids, by, new):
    """The decision of a dataset made from others, of the library (definition 22.4)."""
    return decisions.record(
        db,
        None,
        "dataset",
        {
            "op": op,
            "name": body.name,
            "purpose": body.purpose,
            "dataset_ids": list(dataset_ids),
            "instruction": body.instruction,
        },
        by,
        {"id": new, "name": body.name},
    )


def make_from_datasets(db, body: FromDatasetsInput, by):
    """A new dataset with the images of these datasets (user 2026-10-15: making from several),
    in their order and each image once; the instruction only from a single one."""
    for dataset_id in body.dataset_ids:
        dataset_row(db, dataset_id)
    if len(body.dataset_ids) == 1:
        made = copy_dataset(
            db,
            body.dataset_ids[0],
            CopyInput(
                name=body.name, purpose=body.purpose, instruction=body.instruction
            ),
            by,
            op="from",
        )
        return made
    new = new_id()
    actor = by.who
    with db.transaction():
        decision_id = _made(db, "from", body, body.dataset_ids, by, new)
        insert_dataset(db, new, body.name, body.purpose, decision_id)
        files = {}
        for dataset_id in dict.fromkeys(body.dataset_ids):
            # Where it came from (definition 21.5).
            db.execute(
                "INSERT INTO dataset_sources(dataset_id, from_dataset_id, kind, made_by,"
                " made_at) VALUES(?,?,'images',?,?)",
                (new, dataset_id, actor, now()),
            )
            # Each image once, from the first dataset that holds it.
            for r in image_rows(db, dataset_id):
                files.setdefault(r["id"], r["source_path"])
        insert_images(db, new, list(files), files, decision_id)
    return get_dataset(db, new)


class DeletionInput(Model):
    dataset_ids: Annotated[list[str], Field(min_length=1, max_length=200)]


def copy_dataset(db, dataset_id, body: CopyInput, by, op="copy"):
    dataset_row(db, dataset_id)
    new = new_id()
    actor = by.who
    with db.transaction():
        decision_id = _made(db, op, body, [dataset_id], by, new)
        insert_dataset(db, new, body.name, body.purpose, decision_id)
        files = {r["id"]: r["source_path"] for r in image_rows(db, dataset_id)}
        insert_images(db, new, list(files), files, decision_id)
        # Where it came from (definition 21.5).
        db.execute(
            "INSERT INTO dataset_sources(dataset_id, from_dataset_id, kind, made_by,"
            " made_at) VALUES(?,?,'copy',?,?)",
            (new, dataset_id, actor, now()),
        )
        latest = latest_row(db, dataset_id)
        if body.instruction and latest:
            # The plan starts as a draft from that version (definition 15.1): a version is made
            # only when a run is decided (definition 1), here as anywhere. Its references are
            # results of the other dataset: the new one chooses its own (definition 38.1).
            payload = json.loads(latest["payload_json"])
            write_plan(
                db,
                new,
                lambda _plan: {**payload, "references": []},
                actor,
                origin={
                    "kind": "version",
                    "dataset_id": dataset_id,
                    "revision": latest["revision"],
                },
            )
    return get_dataset(db, new)


def _recoverable(db, image_id):
    """Its file can be imported again: a source path that is still on the disk."""
    return any(os.path.exists(path) for path in source_paths(db, image_id))


def delete_dataset(db, dataset_id, by):
    """The dataset and everything made in it; its images no other dataset uses go too. A
    decision of the library (definition 22.2: what is of the dataset goes with it)."""
    name = dataset_row(db, dataset_id)["name"]
    with db.transaction():
        if going(db, [dataset_id]):
            raise ApiError(
                409, "run_active", "Stop the dataset's run before deleting it"
            )
        freed = [(r["id"], r["byte_size"]) for r in images_only_in(db, [dataset_id])]
        runs = [r["id"] for r in dataset_runs(db, dataset_id)]
        # The results of its records, a run's or a person's fix's (definition 21.4).
        results = dataset_results(db, dataset_id)
        sets = [r["set_id"] for r in results]
        # What training uses points at results; the fixed training data with them (7.2, 7.3).
        for table in ("uses", "confirmations", "training_snapshots"):
            db.execute(f"DELETE FROM {table} WHERE dataset_id=?", (dataset_id,))
        for run_id in runs:
            db.execute("DELETE FROM run_logs WHERE run_id=?", (run_id,))
            db.execute("DELETE FROM views WHERE run_id=?", (run_id,))
        # A fix points at the result it was fixed from and its own result at the fix (user
        # 2026-10-27: a dataset a person fixed could not be deleted): the fixes let go of theirs
        # first, as when that record is gone.
        db.execute(
            "UPDATE fixes SET from_result_id=NULL WHERE dataset_id=?", (dataset_id,)
        )
        for r in results:
            # A copy's result points at the one it was made from (definition 79, 85.15); a
            # copy in another dataset lets go of one of these, keeping what it was copied as.
            db.execute("DELETE FROM copy_results WHERE result_id=?", (r["id"],))
            db.execute(
                "UPDATE copy_results SET from_result_id=NULL WHERE from_result_id=?",
                (r["id"],),
            )
        for r in results:
            db.execute("DELETE FROM results WHERE id=?", (r["id"],))
        # The records, then the decisions that made them, then the boxes they came from. A
        # library's decision asked in a box here outlives it and lets go of the box.
        for table in ("runs", "fixes", "imports", "copies", "decisions"):
            db.execute(f"DELETE FROM {table} WHERE dataset_id=?", (dataset_id,))
        db.execute(
            "UPDATE decisions SET proposal_id=NULL WHERE proposal_id IN"
            " (SELECT id FROM proposals WHERE dataset_id=?)",
            (dataset_id,),
        )
        sets += [
            r[0]
            for image_id, _ in freed
            for r in db.execute(
                "SELECT id FROM annotation_sets WHERE image_id=?", (image_id,)
            )
        ]
        for set_id in set(sets):
            db.execute("DELETE FROM views WHERE set_id=?", (set_id,))
            for table in ("batch_requests", "set_revisions", "annotations"):
                db.execute(f"DELETE FROM {table} WHERE set_id=?", (set_id,))
            db.execute("DELETE FROM annotation_sets WHERE id=?", (set_id,))
        for table in (
            "dataset_sources",
            "dataset_image_removals",
            "drafts",
            "draft_writes",
            "progress_events",
            "instructions",
            "recipes",
            "label_colors",
            "proposals",
            "jobs",
            "agent_events",
            # The workers' chats and notes (agent app, 10-09).
            "agent_chats",
            "notes",
            "dataset_images",
        ):
            db.execute(f"DELETE FROM {table} WHERE dataset_id=?", (dataset_id,))
        db.execute("DELETE FROM datasets WHERE id=?", (dataset_id,))
        for image_id, _ in freed:
            for table in ("views", "image_sources"):
                db.execute(f"DELETE FROM {table} WHERE image_id=?", (image_id,))
            db.execute("DELETE FROM images WHERE id=?", (image_id,))
        decisions.record(
            db,
            None,
            "dataset",
            {"op": "delete", "dataset_id": dataset_id, "name": name},
            by,
            {"removed_images": len(freed)},
        )
    # The files once the rows are gone: a failed removal leaves a file no row names, never a
    # row without its file.
    for image_id, _ in freed:
        db.files.remove("images", image_id.removeprefix("img-"))
    return {
        "deleted": dataset_id,
        "removed_images": len(freed),
        "freed_bytes": sum(size for _, size in freed),
    }


def deletion_preview(db, dataset_ids):
    """What deleting these datasets would remove, to show before asking: what was made in
    them, the images that go (rows and files), those kept for other datasets, and the ones
    that cannot be imported again (no source on the disk)."""
    for dataset_id in dataset_ids:
        dataset_row(db, dataset_id)
    freed = list(images_only_in(db, dataset_ids))
    shared = shared_with(db, dataset_ids)
    # Each run of them, whether it is a trial.
    runs = [
        is_trial(json.loads(r["settings_json"]))
        for d in dataset_ids
        for r in dataset_runs(db, d)
    ]
    return {
        "images": len({i for d in dataset_ids for i in image_ids(db, d)}),
        # Trials apart (Astra 2026-10-06); a trial is a run of a saved version marked as one
        # (user 2026-10-13), no longer a run of the draft (user 2026-10-15: counted wrong).
        "runs": len(runs) - sum(runs),
        "trials": sum(runs),
        "instructions": sum(len(version_rows(db, d)) for d in dataset_ids),
        "active_run": going(db, dataset_ids),
        "freed_images": len(freed),
        "freed_bytes": sum(r["byte_size"] for r in freed),
        "unrecoverable": sum(not _recoverable(db, r["id"]) for r in freed),
        "shared": shared,
    }


def deletion_counts(db, dataset_id):
    """What deleting one dataset would remove (deletion_preview of it)."""
    return deletion_preview(db, [dataset_id])

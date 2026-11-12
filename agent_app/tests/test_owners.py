"""Each table is read and written by its owner (fact inventory 2026-10-30, AGENTS.md: a fact is
derived in one place; 2026-10-30: "the latest version" was read in 27 places of its own). A
module that needs a table's fact calls its owner."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "agent_app"

# table -> the modules that read and write it.
OWNERS = {
    "datasets": {"datasets.py"},
    "dataset_images": {"datasets.py"},
    "dataset_numbers": {"datasets.py"},
    "dataset_image_removals": {"datasets.py"},
    "dataset_sources": {"dataset_admin.py"},
    "images": {"images.py"},
    "image_sources": {"images.py"},
    "instructions": {"instructions.py"},
    # The plan's draft and its writes; a person's fix being made is the other kind of draft.
    "drafts": {"drafts.py", "fixes.py"},
    "draft_writes": {"drafts.py"},
    "labels": {"label_library.py"},
    "label_aliases": {"label_library.py"},
    "label_colors": {"label_colors.py"},
    "views": {"views.py"},
    "app_settings": {"settings.py"},
    "notes": {"notes.py"},
    "shared_notes": {"shared_notes.py"},
    "sheets": {"sheets.py"},
    # Written as decided (adoption); what is used now is read by the images' states (S1).
    "uses": {"adoption.py", "image_state.py"},
    "confirmations": {"confirmations.py"},
    "training_snapshots": {"training.py"},
    "recipes": {"run_inputs.py"},
    "annotation_sets": {"annotation_sets.py"},
    "annotations": {"annotation_sets.py"},
    "set_revisions": {"annotation_sets.py"},
    "batch_requests": {"annotation_sets.py"},
    # Records and their results are read in run_queries and written by their makers.
    "runs": {"run_queries.py", "runs.py"},
    "results": {"run_queries.py", "runs.py"},
    "result_records": {"run_queries.py"},
    "fixes": {"fixes.py", "run_queries.py"},
    "imports": {"coco_import.py", "run_queries.py"},
    "copies": {"copies.py", "run_queries.py"},
    "copy_results": {"copies.py"},
    "run_logs": {"run_logs.py"},
    "progress_events": {"progress.py"},
    "proposals": {"proposals.py"},
    "decisions": {"decisions.py"},
    "agent_events": {"agent_chat.py"},
    "agent_chats": {"agent_chat.py"},
    "jobs": {"jobs.py"},
}
# Every table of a dataset: deleting it, writing it out and taking it in.
WHOLE = {"dataset_admin.py", "dataset_export.py", "dataset_import.py"}
# A dataset's images with each image's row (name, size), and when it was last worked on (the
# newest time of every record kind; definition 57).
JOINED = (
    {("datasets.py", "images")}
    | {
        ("datasets.py", t)
        for t in (
            "draft_writes",
            "instructions",
            "runs",
            "fixes",
            "imports",
            "copies",
        )
    }
    | {("datasets.py", "decisions")}
)

SQL = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+(\w+)", re.IGNORECASE)


def test_every_table_is_read_and_written_by_its_owner():
    outside = []
    for path in sorted(APP.glob("*.py")):
        if path.name == "db.py" or path.name in WHOLE:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if '"' not in line and "'" not in line:
                continue
            for table in SQL.findall(line):
                owners = OWNERS.get(table)
                if owners is None or path.name in owners:
                    continue
                if (path.name, table) in JOINED:
                    continue
                outside.append(f"{path.name}:{number} {table}")
    assert outside == [], "Read the table through its owner: " + ", ".join(outside)


def test_every_table_has_an_owner():
    schema = (APP / "db.py").read_text(encoding="utf-8")
    tables = set(re.findall(r"CREATE TABLE (\w+)", schema))
    assert tables - set(OWNERS) == set()


# Names one role keeps under one name on purpose: each class's own close and start, each store's
# subscribe, and a callback of the same role in several places.
SAME_ROLE = {"lifespan", "item", "view", "draw_sheet", "quit_app"}


def test_no_two_functions_share_a_name():
    # User 2026-10-30: "同じ名前で別な意味の関数とかありえないだろ" (apply, decide and 45 others).
    import ast
    from collections import defaultdict

    top, nested, methods = defaultdict(list), defaultdict(list), set()
    for path in sorted(APP.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                methods |= {
                    m.name
                    for m in node.body
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            top[node.name].append(path.name)
            for inner in ast.walk(node):
                if inner is not node and isinstance(
                    inner, (ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    nested[inner.name].append(f"{path.name}:{node.name}")
    twice = {name: where for name, where in top.items() if len(where) > 1}
    shadowing = {
        name: where for name, where in nested.items() if name in top or name in methods
    }
    nested_twice = {
        name: where
        for name, where in nested.items()
        if len(where) > 1 and name not in SAME_ROLE
    }
    assert (twice, shadowing, nested_twice) == ({}, {}, {})

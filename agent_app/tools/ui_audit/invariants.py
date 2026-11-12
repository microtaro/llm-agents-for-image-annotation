"""What holds for every answer of a worker, checked by machine on a database (definition 74; user
2026-10-29: the tests read the screen only, and 89 of 89 questions lost the words before them).

    uv run --project agent_app python agent_app/tools/ui_audit/invariants.py DB [--since ISO]

Prints one line per answer that breaks one, then the count; exits 1 when any does.

I1 every part of what the worker said (its words, question, options, the request it hands over,
   what it shows) is on a line the person sees, or a note says why not;
I2 its words are in the chat's language;
I3 a dataset it names by number and name is that one;
I4 a waiting decision it points at was waiting when it answered;
I5 no decision waits whose ground is gone;
I7 its words name nothing by the app's inner names (ids, fields of what it reads), which the
   person cannot read (user 2026-10-29: "わけのわからない応答ではなく").

And what holds for the data (2026-10-30 review: a label change wrote a child under another
parent, a dataset deleted took a decision other datasets' versions point at):
D1 every success's annotations follow the label rules of the plan it was made with;
D2 every version made by a decision points at one that is there;
D3 the boxes of one kind carry the same facts, the fields of their card and of what happens
   (2026-11-02: the run boxes made before definition 85 had no card.happens.other, and the
   screen, reading it, failed whole on one: a fact added, the older boxes were not moved).
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_app.agent_answer import misnamed

JAPANESE = re.compile(r"[ぁ-んァ-ン一-龥]")
# The app's inner names: ids (a box's, an image's, a job's, a uuid) and the fields of what a
# worker reads, never the screen's words.
INNER = re.compile(
    r"\b(?:prp|img|job|run|res)-[0-9a-f]{6,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}"
    r"|\b(?:draft_write_id|write_id|requirement_key|result_id|image_id|run_id|dataset_id"
    r"|proposal_ids?|label_definitions|leave_out|looking_at|open_boxes|context\.[a-z_]+)\b"
)


def _lines(db, job_id):
    return [
        dict(r, data=json.loads(r["data_json"] or "{}"))
        for r in db.execute(
            "SELECT id, kind, text, data_json, created_at FROM agent_events WHERE job_id=?"
            " ORDER BY id",
            (job_id,),
        )
    ]


def _chat(db, job):
    """The chat an answer is of: its request's line's (a job keeps no chat of its own)."""
    row = db.execute(
        "SELECT chat_id FROM agent_events WHERE id=?", (job["request_event_id"],)
    ).fetchone()
    return row[0] if row else job["chat_id"]


def _language(db, chat_id):
    row = db.execute(
        "SELECT json_extract(data_json,'$.lang') FROM agent_events WHERE chat_id=? AND"
        " json_extract(data_json,'$.lang') IS NOT NULL ORDER BY id DESC LIMIT 1",
        (chat_id,),
    ).fetchone()
    return row[0] if row else None


def check_answer(db, job):
    """What one answer breaks: [(rule, what)]."""
    turns = json.loads(job["said_json"])
    said, problems = turns[-1]["said"], turns[-1]["problems"]
    lines = _lines(db, job["id"])
    texts = [line["text"] for line in lines]
    noted = {p["part"] for line in lines for p in line["data"].get("parts") or []}
    broken = []
    message = (said.get("message") or "").strip()
    question = said.get("question") or {}
    if message and message not in texts:
        # A question's words above it, else the answer's own line (68.2).
        broken.append(("I1", f"words not shown: {message[:60]}"))
    if said.get("kind") == "question" and question:
        asked = next((line for line in lines if line["kind"] == "question"), None)
        if asked is None and "question" not in noted:
            broken.append(
                ("I1", f"question not shown: {question.get('text', '')[:60]}")
            )
        elif asked is not None:
            shown = {o.get("label") for o in asked["data"].get("options") or []}
            dropped = {p.get("label") for p in problems if p["part"] == "option"}
            for option in question.get("options") or []:
                if option["label"] not in shown and option["label"] not in dropped:
                    broken.append(("I1", f"option not shown: {option['label']}"))
    if said.get("kind") == "handoff" and said.get("handoff"):
        offered = next(
            (line for line in lines if line["kind"] == "handoff_offer"), None
        )
        if offered is None and "handoff" not in noted:
            broken.append(("I1", "the request handed over is not shown"))
    linked = any(line["data"].get("show") for line in lines)
    if said.get("show") and not linked and "show" not in noted:
        broken.append(("I1", "what it showed is not linked"))
    # The language the person wrote in, else their screen's (definition 75).
    asked = db.execute(
        "SELECT kind, text FROM agent_events WHERE id=?", (job["request_event_id"],)
    ).fetchone()
    # A person's words (a server's note waking the worker says nothing of a language), their
    # paths left out: a path says no language (2026-10-29: a folder's path read as English).
    words = asked["text"] if asked and asked["kind"] == "human" else ""
    plain = re.sub(r"\S*/\S*", " ", words)
    language = (
        "ja"
        if JAPANESE.search(plain)
        else "en"
        if re.search(r"[A-Za-z]{3}", plain)
        else _language(db, _chat(db, job))
    )
    if language == "ja" and message and not JAPANESE.search(message):
        broken.append(("I2", f"not in Japanese: {message[:60]}"))
    if (
        language == "en"
        and message
        and len(JAPANESE.findall(message)) > len(message) / 3
    ):
        broken.append(("I2", f"not in English: {message[:60]}"))
    for text in [message, question.get("text") or ""] + [
        o.get("label") or "" for o in question.get("options") or []
    ]:
        # What the person wrote is theirs to read (2026-10-29: an id in a path they gave).
        inner = [name for name in INNER.findall(text) if name not in words]
        if inner:
            broken.append(("I7", f"inner names in its words: {sorted(set(inner))}"))
    if misnamed(db, said) and "name" not in noted:
        broken.append(("I3", f"names a dataset wrongly: {misnamed(db, said)}"))
    for line in lines:
        for box in line["data"].get("proposal_ids") or []:
            row = db.execute(
                "SELECT decided_at FROM proposals WHERE id=?", (box,)
            ).fetchone()
            if row and row["decided_at"] and row["decided_at"] < line["created_at"]:
                broken.append(("I4", f"points at a decided decision {box}"))
    return broken


def check_waiting(db_path):
    """The waiting decisions whose ground is gone (I5), by the server's own check."""
    from agent_app.db import Database
    from agent_app.proposals import _outdated

    database = Database(db_path)
    try:
        return [
            ("I5", f"waits on a ground gone: {row['title']}")
            for row in database.execute("SELECT * FROM proposals WHERE state='open'")
            if _outdated(database, row) is not None
        ]
    finally:
        database.close()


def check_data(db_path):
    """The data's rules (D1, D2), by the server's own rules and readers."""
    from agent_app.annotation_sets import current
    from agent_app.db import Database
    from agent_app.decisions import get_decision
    from agent_app.errors import ApiError
    from agent_app.instructions import all_versions
    from agent_app.label_rules import check_annotation
    from agent_app.run_queries import SUCCESS, ran_plan

    database = Database(db_path)
    broken = []
    try:
        for r in database.execute(
            "SELECT * FROM result_records ORDER BY record_number"
        ):
            if r["status"] not in SUCCESS:
                continue
            settings = json.loads(r["settings_json"] or "{}")
            plan = ran_plan(
                database, r["dataset_id"], r["instruction_revision"], settings
            )
            objects = current(database, r["set_id"])
            label_of = {a["id"]: a["label"] for a in objects}
            for a in objects:
                try:
                    check_annotation(
                        plan.get("label_definitions") or [],
                        a["label"],
                        a["geometry"]["type"],
                        label_of.get(a["parent_id"]),
                        a["attributes"],
                    )
                except ApiError as exc:
                    where = f"record {r['record_number']} of dataset {r['dataset_id']}"
                    broken.append(("D1", f"{where}: {a['label']}: {exc.message}"))
        for v in all_versions(database):
            if v["decision_id"] and get_decision(database, v["decision_id"]) is None:
                where = f"version {v['revision']} of dataset {v['dataset_id']}"
                broken.append(("D2", f"{where} points at a decision gone"))
    finally:
        database.close()
    return broken


def _box_fields(preview):
    """The fields of a box's facts a screen reads by name: its own, its card's, and those of
    what its card says happens and fixes (the rest are data: images, plans, ids)."""
    card = preview.get("card") or {}
    return (
        set(preview)
        | {f"card.{k}" for k in card}
        | {
            f"card.{part}.{k}"
            for part in ("happens", "fixes")
            for k in card.get(part) or {}
        }
    )


def check_boxes(db):
    """D3: the boxes of one kind carry the same facts."""
    kinds = {}
    for box in db.execute(
        "SELECT id, tool, preview_json FROM proposals WHERE preview_json IS NOT NULL"
    ):
        kinds.setdefault(box["tool"], []).append(
            (box["id"], _box_fields(json.loads(box["preview_json"])))
        )
    broken = []
    for tool, boxes in kinds.items():
        every = set().union(*(fields for _, fields in boxes))
        for box_id, fields in boxes:
            for field in sorted(every - fields):
                broken.append(("D3", f"box {box_id} ({tool}) has no {field}"))
    return broken


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("db", type=Path)
    parser.add_argument(
        "--since", default="", help="Answers started from this time (ISO)."
    )
    args = parser.parse_args()
    db = sqlite3.connect(f"file:{args.db.resolve()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    found = 0
    for job in db.execute(
        "SELECT * FROM jobs WHERE kind='answer_heavy' AND said_json IS NOT NULL AND"
        " created_at>=? ORDER BY created_at",
        (args.since,),
    ):
        for rule, what in check_answer(db, job):
            found += 1
            print(f"{rule} {job['id']} chat {_chat(db, job)}: {what}")
    for rule, what in [
        *check_waiting(args.db.resolve()),
        *check_data(args.db.resolve()),
        *check_boxes(db),
    ]:
        found += 1
        print(f"{rule}: {what}")
    print(f"{found} broken")
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()

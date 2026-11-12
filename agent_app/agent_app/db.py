"""The app's SQLite database and file store (step 1 design 3-4, steps 2-4 design 3)."""

import json
import logging
import os
import shutil
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .config import APP
from .files import KINDS, Files, files_root

VERSION = 7
# The tables as they are now. Until 10-27 a database was moved into each new shape at its start,
# step by step; the steps went once every database had been moved (user 2026-10-27: no
# compatibility while developing; they are in git before the tag
# agent-app-before-schema-20261027). Version 2 (10-28, definition 60.11): a result may be a
# record taken in's (imports); the main and the copy's databases were moved then. Version 3
# (10-28, definition 61): a dataset has a number people call it by; the main and the copy's
# databases were moved then. Version 4 (10-28, definition 65): a run's cost limit is per
# image; the main and the copy's databases were moved then.
SCHEMA = """
CREATE TABLE images(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
  byte_size INTEGER NOT NULL, format TEXT NOT NULL,
  origin TEXT NOT NULL DEFAULT 'real' CHECK(origin IN ('real','generated')),
  origin_json TEXT, created_at TEXT NOT NULL);
CREATE TABLE image_sources(image_id TEXT NOT NULL REFERENCES images(id), path TEXT NOT NULL,
  PRIMARY KEY(image_id, path));
-- decision_id: the decision that made a dataset, added or took out an image of it, or made a
-- version (definition 22.3).
-- number: what people call it by, "#12" (definition 61): one line in the library, given when it
-- is made and never again (dataset_numbers holds the last one given, a deleted one's too).
CREATE TABLE datasets(id TEXT PRIMARY KEY, number INTEGER NOT NULL UNIQUE, name TEXT NOT NULL,
  purpose TEXT NOT NULL, created_at TEXT NOT NULL, decision_id TEXT);
CREATE TABLE dataset_numbers(last INTEGER NOT NULL);
CREATE TABLE dataset_images(
  dataset_id TEXT NOT NULL REFERENCES datasets(id), image_id TEXT NOT NULL REFERENCES images(id),
  position INTEGER NOT NULL, added_at TEXT NOT NULL, source_path TEXT, decision_id TEXT,
  PRIMARY KEY(dataset_id, image_id));
-- from_*: where a plan was started from, blank or a version of this dataset or another
-- (definition 15.1); draft_write_id: the draft's write a version was made from (11.1).
CREATE TABLE instructions(
  dataset_id TEXT NOT NULL REFERENCES datasets(id), revision INTEGER NOT NULL,
  created_at TEXT NOT NULL, created_by TEXT NOT NULL, payload_json TEXT NOT NULL,
  requirement_key TEXT NOT NULL, decision_id TEXT, draft_write_id INTEGER, from_kind TEXT,
  from_dataset_id TEXT, from_revision INTEGER, PRIMARY KEY(dataset_id, revision));
-- numbers_json: the last number given per label, so a deleted number is never given again.
CREATE TABLE annotation_sets(id TEXT PRIMARY KEY, image_id TEXT NOT NULL REFERENCES images(id),
  revision INTEGER NOT NULL DEFAULT 0, numbers_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE annotations(id TEXT PRIMARY KEY, set_id TEXT NOT NULL REFERENCES annotation_sets(id),
  label TEXT NOT NULL, kind TEXT NOT NULL, geometry_json TEXT NOT NULL, mask_sha256 TEXT,
  parent_id TEXT, attributes_json TEXT NOT NULL DEFAULT '{}', number INTEGER);
CREATE TABLE set_revisions(set_id TEXT NOT NULL REFERENCES annotation_sets(id),
  revision INTEGER NOT NULL, snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY(set_id, revision));
CREATE TABLE batch_requests(set_id TEXT NOT NULL REFERENCES annotation_sets(id),
  request_id TEXT NOT NULL, body_sha256 TEXT NOT NULL, response_json TEXT NOT NULL,
  PRIMARY KEY(set_id, request_id));
CREATE TABLE views(id TEXT PRIMARY KEY, image_id TEXT NOT NULL REFERENCES images(id),
  set_id TEXT, revision INTEGER, request_json TEXT NOT NULL, frame_json TEXT NOT NULL,
  run_id TEXT, result_id TEXT, created_at TEXT NOT NULL);
-- number: the record's; decision_id, stop_decision_id: the decisions that made and stopped it
-- (definition 21.3, 21.4); recipe_id: its way of running (11.1).
CREATE TABLE runs(id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(id),
  status TEXT NOT NULL, instruction_revision INTEGER NOT NULL, requirement_key TEXT NOT NULL,
  requested_json TEXT NOT NULL, worker_prompt TEXT NOT NULL, worker_prompt_sha256 TEXT NOT NULL,
  settings_json TEXT NOT NULL, request_json TEXT NOT NULL, budget_per_image_usd TEXT,
  started_at TEXT NOT NULL, ended_at TEXT, elapsed_ms REAL, error TEXT, error_code TEXT,
  number INTEGER, decision_id TEXT, stop_decision_id TEXT, recipe_id TEXT);
-- A result is a run's, a person's fix's, a record taken in's or a label change's (definition
-- 21.4, 60.11, 79).
CREATE TABLE results(id TEXT PRIMARY KEY, run_id TEXT REFERENCES runs(id),
  fix_id TEXT REFERENCES fixes(id), image_id TEXT NOT NULL REFERENCES images(id),
  set_id TEXT NOT NULL UNIQUE REFERENCES annotation_sets(id), position INTEGER NOT NULL,
  status TEXT NOT NULL, message TEXT, started_at TEXT, elapsed_ms REAL, usage_json TEXT,
  cost_json TEXT, final_view_id TEXT, import_id TEXT REFERENCES imports(id),
  copy_id TEXT REFERENCES copies(id),
  UNIQUE(run_id, image_id),
  CHECK((run_id IS NOT NULL) + (fix_id IS NOT NULL) + (import_id IS NOT NULL)
    + (copy_id IS NOT NULL) = 1));
-- A record taken in from outside (definition 60.11): a COCO JSON's objects, of the version made
-- from it; source_json: the file it came from.
CREATE TABLE imports(id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(id),
  number INTEGER NOT NULL, instruction_revision INTEGER NOT NULL, requirement_key TEXT NOT NULL,
  source_json TEXT NOT NULL, imported_by TEXT NOT NULL, imported_at TEXT NOT NULL);
-- Results copied from others as one record, of the version they are made for (definition 79,
-- 85.15): a label changed in one dataset (reason label, content {from, to}) or results carried
-- from another requirement or dataset (reason carry, content {from_dataset_id, from_revision});
-- each result made from one (copy_results).
CREATE TABLE copies(id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(id),
  number INTEGER NOT NULL, instruction_revision INTEGER NOT NULL, requirement_key TEXT NOT NULL,
  decision_id TEXT, reason TEXT NOT NULL CHECK(reason IN ('label','carry')),
  content_json TEXT NOT NULL, copied_by TEXT NOT NULL, copied_at TEXT NOT NULL);
-- What each copied result was copied from, as it was when copied: the result (let go when its
-- dataset is deleted or it was not taken in with this one), who made it and the criteria it was
-- made by (definition 85.15: a result carried from another dataset outlives its source).
CREATE TABLE copy_results(result_id TEXT PRIMARY KEY REFERENCES results(id),
  from_result_id TEXT REFERENCES results(id),
  from_by TEXT NOT NULL CHECK(from_by IN ('ai','human','import')), from_criteria TEXT NOT NULL);
CREATE TABLE run_logs(seq INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runs(id), result_id TEXT, at TEXT NOT NULL,
  kind TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE app_settings(key TEXT PRIMARY KEY, value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL);
-- created_at: when a draft was begun, what it changed is counted from then (step 19);
-- write_id: the write that is the plan draft's content (definition 11.1).
CREATE TABLE drafts(dataset_id TEXT NOT NULL REFERENCES datasets(id),
  kind TEXT NOT NULL CHECK(kind IN ('instruction','fix')),
  image_id TEXT NOT NULL DEFAULT '', requirement_key TEXT, payload_json TEXT NOT NULL,
  written_by TEXT NOT NULL, updated_at TEXT NOT NULL, created_at TEXT, write_id INTEGER,
  from_kind TEXT, from_dataset_id TEXT, from_revision INTEGER,
  PRIMARY KEY(dataset_id, kind, image_id));
CREATE INDEX annotations_set ON annotations(set_id);
CREATE INDEX results_image ON results(image_id);
CREATE INDEX runs_dataset ON runs(dataset_id, started_at);
CREATE INDEX run_logs_run ON run_logs(run_id, seq);
-- The progress panel's talk (step 10, before the workers' own).
CREATE TABLE progress_events(id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_id TEXT NOT NULL REFERENCES datasets(id), kind TEXT NOT NULL, text TEXT NOT NULL,
  look TEXT, by_actor TEXT NOT NULL, created_at TEXT NOT NULL, model TEXT, elapsed_ms REAL,
  cost_json TEXT, tools_json TEXT, changes_json TEXT, plan_json TEXT, session_id TEXT,
  prompt_sha TEXT, pick TEXT, chat_id TEXT);
-- The label colors chosen per dataset (step 8).
CREATE TABLE label_colors(dataset_id TEXT NOT NULL REFERENCES datasets(id), label TEXT NOT NULL,
  color TEXT NOT NULL, PRIMARY KEY(dataset_id, label));
-- A box (step 22, 24): a decision a worker or the screen made ready, the tool and its arguments,
-- waiting for a person, kept with what came of it; its worker, what it showed and stood on, the
-- values a person changed, the line it came from. No dataset: the library's (definition 22.3).
CREATE TABLE proposals(id TEXT PRIMARY KEY, dataset_id TEXT REFERENCES datasets(id),
  bot TEXT NOT NULL, tool TEXT NOT NULL, args_json TEXT NOT NULL, title TEXT NOT NULL,
  reason TEXT NOT NULL, made_by TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL,
  decided_at TEXT, decided_by TEXT, outcome_json TEXT, agent TEXT, premise_json TEXT,
  preview_json TEXT, changed_json TEXT, from_event_id TEXT, seen_at TEXT, step TEXT,
  chat_id INTEGER);
-- What a worker left for the others (agent app design 3.7).
CREATE TABLE notes(id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_id TEXT NOT NULL REFERENCES datasets(id), agent TEXT, text TEXT NOT NULL,
  created_at TEXT NOT NULL);
-- The server's line of work (step 24): every answer and run is one job, started when a slot and
-- memory allow, in order. No dataset: the library's reception (types design 17.1);
-- bound_dataset_id: the dataset an answer is bound to (definition 48.10). said_json: a worker's
-- answer as it gave it, each turn (asked again too) with what of it the server could not use,
-- for checking what reached the person (definition 74; never shown).
CREATE TABLE jobs(id TEXT PRIMARY KEY, dataset_id TEXT REFERENCES datasets(id), agent TEXT,
  kind TEXT NOT NULL, state TEXT NOT NULL, title TEXT NOT NULL, request_event_id INTEGER,
  run_id TEXT, wait_reason TEXT, error TEXT, created_at TEXT NOT NULL, started_at TEXT,
  ended_at TEXT, chat_id INTEGER, bound_dataset_id TEXT, said_json TEXT);
-- Each worker's talk and its chats, in its place: a dataset or the library (null; definition
-- 48.2). A chat deleted is hidden, its lines kept (21.5).
CREATE TABLE agent_events(id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_id TEXT REFERENCES datasets(id), agent TEXT NOT NULL, kind TEXT NOT NULL,
  text TEXT NOT NULL, by_actor TEXT NOT NULL, created_at TEXT NOT NULL, model TEXT,
  elapsed_ms REAL, cost_json TEXT, tools_json TEXT, session_id TEXT, prompt_sha TEXT,
  job_id TEXT, data_json TEXT, closed_at TEXT, chat_id INTEGER);
CREATE TABLE agent_chats(id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_id TEXT REFERENCES datasets(id), agent TEXT NOT NULL, created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL, deleted_at TEXT, deleted_by TEXT);
-- A decision (definition 21.3, 22.2): what a press fixed (a run, its stop, what training uses, a
-- dataset, its images, a label's name), who decided it, who asked for it, the box it came from
-- (one at most); only added to. No dataset: the library's (22.3).
CREATE TABLE decisions(id TEXT PRIMARY KEY, dataset_id TEXT REFERENCES datasets(id),
  kind TEXT NOT NULL CHECK(kind IN
    ('run','stop','use','dataset','images','label','confirm','carry')),
  content_json TEXT NOT NULL, decided_by TEXT NOT NULL, requested_by TEXT NOT NULL,
  proposal_id TEXT UNIQUE REFERENCES proposals(id), outcome_json TEXT, decided_at TEXT NOT NULL);
-- A person's fix (definition 21.4); no result it was fixed from: that record was deleted.
CREATE TABLE fixes(id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(id),
  image_id TEXT NOT NULL REFERENCES images(id), from_result_id TEXT REFERENCES results(id),
  requirement_key TEXT NOT NULL, instruction_revision INTEGER NOT NULL, fixed_by TEXT NOT NULL,
  fixed_at TEXT NOT NULL, number INTEGER NOT NULL);
-- What training uses, per image, only added to (definition 19.3, 21.3); the images' states read
-- the last rows (image_state.use_now).
CREATE TABLE uses(id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_id TEXT NOT NULL REFERENCES datasets(id), image_id TEXT NOT NULL REFERENCES images(id),
  kind TEXT NOT NULL CHECK(kind IN ('pick','rule','out','in','fix')),
  result_id TEXT REFERENCES results(id), decision_id TEXT REFERENCES decisions(id),
  fix_id TEXT REFERENCES fixes(id));
CREATE INDEX uses_image ON uses(dataset_id, image_id, id);
-- Every write of the plan's draft (types design 20.3): who wrote it, for a worker the job;
-- from_event_id: the question a person's answer wrote it from (definition 26.4).
CREATE TABLE draft_writes(id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_id TEXT NOT NULL REFERENCES datasets(id), payload_json TEXT NOT NULL,
  written_by TEXT NOT NULL, job_id TEXT, written_at TEXT NOT NULL, from_event_id INTEGER,
  from_kind TEXT, from_dataset_id TEXT, from_revision INTEGER);
-- The training data fixed at one time (types design 7.3, DatasetSnapshot).
CREATE TABLE training_snapshots(dataset_id TEXT NOT NULL REFERENCES datasets(id),
  number INTEGER NOT NULL, created_at TEXT NOT NULL, created_by TEXT NOT NULL,
  items_json TEXT NOT NULL, note TEXT, PRIMARY KEY(dataset_id, number));
-- A way of running (definition 11.1): its plan version, model, effort and shared notes' version,
-- made the first time it runs.
CREATE TABLE recipes(id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(id),
  instruction_revision INTEGER NOT NULL, model TEXT NOT NULL, effort TEXT NOT NULL,
  shared_revision INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(dataset_id, instruction_revision, model, effort, shared_revision));
-- Where a dataset came from, and the images taken out of it (definition 21.5).
CREATE TABLE dataset_sources(dataset_id TEXT NOT NULL REFERENCES datasets(id),
  from_dataset_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('copy','images')),
  made_by TEXT NOT NULL, made_at TEXT NOT NULL);
CREATE TABLE dataset_image_removals(dataset_id TEXT NOT NULL REFERENCES datasets(id),
  image_id TEXT NOT NULL REFERENCES images(id), removed_by TEXT NOT NULL,
  removed_at TEXT NOT NULL, decision_id TEXT);
-- The shared notes for every worker AI, in versions of their own (shared_notes.py).
CREATE TABLE shared_notes(revision INTEGER PRIMARY KEY, text TEXT NOT NULL,
  created_at TEXT NOT NULL, created_by TEXT NOT NULL);
-- The labels of the whole library (definition 26.1): one name per label, the words a person
-- said a label is (aliases).
CREATE TABLE labels(id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, created_by TEXT NOT NULL);
CREATE TABLE label_aliases(alias_key TEXT PRIMARY KEY, alias TEXT NOT NULL,
  label_id TEXT NOT NULL REFERENCES labels(id), created_at TEXT NOT NULL,
  created_by TEXT NOT NULL);
-- A person checked an image's annotation now by a version's criteria (definition 85.5).
CREATE TABLE confirmations(id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(id),
  image_id TEXT NOT NULL REFERENCES images(id), result_id TEXT NOT NULL REFERENCES results(id),
  revision INTEGER NOT NULL, decision_id TEXT, confirmed_by TEXT NOT NULL,
  confirmed_at TEXT NOT NULL);
-- A sheet made of the same facts is read, not made again (definition 25.2).
CREATE TABLE sheets(key TEXT PRIMARY KEY, sha256 TEXT NOT NULL, tiles_json TEXT NOT NULL,
  created_at TEXT NOT NULL);
"""

# A result and its record (a run, a person's fix, one taken in, or a copy: a label change or
# results carried over) in one row (definition 21.4, 60.11, 79, 85.15). record_kind is the
# record's (a copy's by its reason: relabel or carry); result_by who made what it holds: a copy
# keeps the maker of the result it was made from, as copied (user 2026-10-30: a person's fix
# changed to another label is still the person's); copied_criteria the criteria that one was
# made by (85.15).
RESULT_RECORDS = """CREATE VIEW result_records AS SELECT r.*,
  coalesce(r.run_id, r.fix_id, r.import_id, r.copy_id) AS record_id,
  coalesce(u.number, f.number, m.number, c.number) AS record_number,
  coalesce(u.dataset_id, f.dataset_id, m.dataset_id, c.dataset_id) AS dataset_id,
  coalesce(u.started_at, f.fixed_at, m.imported_at, c.copied_at) AS record_at,
  u.settings_json AS settings_json,
  coalesce(u.instruction_revision, f.instruction_revision, m.instruction_revision,
  c.instruction_revision) AS instruction_revision,
  coalesce(u.requirement_key, f.requirement_key, m.requirement_key, c.requirement_key)
  AS requirement_key,
  CASE WHEN r.fix_id IS NOT NULL THEN 'fix' WHEN r.import_id IS NOT NULL THEN 'import'
  WHEN r.copy_id IS NOT NULL THEN (CASE c.reason WHEN 'label' THEN 'relabel' ELSE 'carry' END)
  ELSE 'run' END AS record_kind,
  CASE WHEN r.fix_id IS NOT NULL THEN 'human' WHEN r.import_id IS NOT NULL THEN 'import'
  WHEN r.copy_id IS NOT NULL THEN cr.from_by ELSE 'ai' END AS result_by,
  cr.from_criteria AS copied_criteria,
  coalesce(f.from_result_id, cr.from_result_id) AS fixed_from
  FROM results r LEFT JOIN runs u ON u.id=r.run_id LEFT JOIN fixes f ON f.id=r.fix_id
  LEFT JOIN imports m ON m.id=r.import_id LEFT JOIN copies c ON c.id=r.copy_id
  LEFT JOIN copy_results cr ON cr.result_id=r.id"""

log = logging.getLogger("agent_app")


def now():
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id(prefix=""):
    return prefix + str(uuid.uuid4())


def encoded(value):
    """Canonical JSON: sorted keys, no NaN."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def default_path():
    return Path(os.environ.get("AGENT_APP_DB") or APP / "agent.db")


class Database:
    """One connection used by one thread at a time (routes run on worker threads)."""

    def __init__(self, path=None):
        path = Path(path or default_path())
        if not path.is_absolute():
            raise ValueError("AGENT_APP_DB must be an absolute path")
        created = not path.exists()
        self.path = path
        # Made just now, by this start (dataset_import.take_in_samples).
        self.created = created
        self.files = Files(files_root(path))
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(
            path, check_same_thread=False, isolation_level=None
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            from .shared_notes import FIRST  # shared_notes uses this module's now()

            self.connection.executescript(SCHEMA + f"PRAGMA user_version={VERSION};")
            self.connection.execute("INSERT INTO dataset_numbers(last) VALUES(0)")
            # A database starts with the shared notes' first version (definition 18.15).
            self.connection.execute(
                "INSERT INTO shared_notes(revision, text, created_at, created_by)"
                " VALUES(1,?,?,'server')",
                (FIRST, now()),
            )
            if created:
                log.info("Created a new database at %s", path)
        elif version != VERSION:
            raise RuntimeError(f"Database version {version} is not {VERSION}")
        # A result with its record as one row, for every reader: made again at each start, so
        # it follows the tables.
        self.connection.execute("DROP VIEW IF EXISTS result_records")
        self.connection.execute(RESULT_RECORDS)

    def storage(self):
        """Where the data is kept and how big it is, measured on disk (user 2026-10-28: the app
        keeps its own copy of every image, so it grows): the database (with its write-ahead
        log), the files by kind, and the room left on the disk they are on."""
        database = sum(
            p.stat().st_size
            for p in (self.path, Path(f"{self.path}-wal"), Path(f"{self.path}-shm"))
            if p.exists()
        )
        room = shutil.disk_usage(
            self.files.root if self.files.root.exists() else self.path.parent
        )
        return {
            "database": {"path": str(self.path), "bytes": database},
            "files": {
                "path": str(self.files.root),
                **{
                    kind: dict(zip(("count", "bytes"), self.files.usage(kind)))
                    for kind in KINDS
                },
            },
            "disk": {"free": room.free, "total": room.total},
        }

    def execute(self, sql, parameters=()):
        with self.lock:
            return self.connection.execute(sql, parameters).fetchall()

    def columns(self, table):
        """The names of a table's columns."""
        return {r["name"] for r in self.execute(f"PRAGMA table_info({table})")}

    def one(self, sql, parameters=()):
        rows = self.execute(sql, parameters)
        return rows[0] if rows else None

    @contextmanager
    def transaction(self):
        """Everything inside commits together; nested use joins the outer one."""
        with self.lock:
            if self.connection.in_transaction:
                yield
                return
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.connection.execute("COMMIT")
            except BaseException:
                self.connection.execute("ROLLBACK")
                raise

    def close(self):
        with self.lock:
            self.connection.close()

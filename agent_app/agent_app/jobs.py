"""The server's line of work (step 24 design 3.3): every answer of a worker and every run is a
job, asked for at once (202, never refused for being busy) and started in order when its kind
has a free slot and the machine has memory. The order is the server's, never an LLM's
(user 2026-10-08; Grok Bot's main kept its order in its conversation only and could not notice
a worker that stopped answering).

run: runs (run_slots); chat: the workers' answers (chat_slots, each chat's CLI kept running,
residents.py; apart from the runs so a person can talk while runs go, user 2026-10-20; the
quick answers of a fast model before them were let go, definition 28). Measured
(logs/parallel-check): four runs at once took as long per image as one; a worker CLI holds
210-300 MB (logs/resident-check), and on Windows promises (commits) about 420 MB (2026-11-02).
"""

import asyncio
import logging

from fastapi import APIRouter, Request

from .datasets import dataset_row
from .db import encoded, new_id, now
from .errors import ApiError, not_found
from .residents import Residents
from .settings import read_settings
from .system import free_mb

logger = logging.getLogger("agent_app.jobs")
router = APIRouter(prefix="/v1")
# Every worker's answer is one kind, at its place: a dataset, or the library (definition 48.3).
GROUPS = {"run": ("run",), "chat": ("answer_heavy",)}
# Free memory kept for the machine, and what one more worker CLI takes: on Windows (2026-11-02,
# six at once with their Python, Claude Opus 5.5) 220 MB in memory and 420 MB committed each.
# 2026-10-30: 4096 MB (from the 10-09 prototype, never measured) held every answer back on a
# 16 GB Windows machine with 4.0 GB free.
FLOOR_MB, WORKER_MB = 1024, 450
# Memory frees with no event to wake the line (no job ends, none is asked): a job held for it is
# looked at again this often (2026-10-28: on Windows, just started, a run waited for ever).
MEMORY_RECHECK_SECONDS = 10


# A job's state (jobs.state) while it waits or goes.
ACTIVE = ("queued", "running")


def job_row(db, job_id):
    """A job as stored, None when there is none: the one place a job is read by its id (fact
    inventory 8)."""
    return db.one("SELECT * FROM jobs WHERE id=?", (job_id,)) if job_id else None


def run_job(db, run_id):
    """The job of a run, None when it has none."""
    return db.one("SELECT * FROM jobs WHERE run_id=?", (run_id,))


def active_jobs(db, dataset_id):
    """The jobs waiting or going at a place (a dataset, the library: None)."""
    return db.execute(
        f"SELECT * FROM jobs WHERE dataset_id IS ? AND state IN ({','.join('?' * len(ACTIVE))})",
        (dataset_id, *ACTIVE),
    )


def bound_answers(db, dataset_id):
    """The answers waiting or going bound to a dataset, of any worker (one of the library
    reading it too): they may write its plan (definition 11.10, 48.10)."""
    return db.execute(
        "SELECT * FROM jobs WHERE bound_dataset_id IS ? AND kind<>'run'"
        f" AND state IN ({','.join('?' * len(ACTIVE))})",
        (dataset_id, *ACTIVE),
    )


def job_chat(db, row):
    """The chat a job's lines go to: the run's (set from its box, definition 81), else its
    request line's."""
    from .agent_chat import event_chat  # a job answers a line

    return row["chat_id"] or event_chat(db, row["request_event_id"])


def tell_run_in(db, run_id, agent, chat_id):
    """A run's end is told to that worker in that chat (the box's worker, the chat it was decided
    in)."""
    db.execute(
        "UPDATE jobs SET agent=?, chat_id=? WHERE run_id=?", (agent, chat_id, run_id)
    )


def keep_said(db, job_id, said):
    """The answer as the worker gave it, kept to check what reached the person (74)."""
    db.execute("UPDATE jobs SET said_json=? WHERE id=?", (encoded(said), job_id))


def queued_runs(db):
    """The runs whose job waits to start them."""
    return {
        r["run_id"]
        for r in db.execute(
            "SELECT run_id FROM jobs WHERE run_id IS NOT NULL AND state='queued'"
        )
    }


def workers_of(kind, settings):
    """The worker CLIs a job of the kind brings at once: a run up to image_slots (definition
    50.2), an answer one."""
    return settings["image_slots"] if kind == "run" else 1


def memory_needed(workers):
    """The free memory that many more worker CLIs wait for, in MB, the machine's floor kept."""
    return FLOOR_MB + WORKER_MB * workers


def _job_out(row, position=None, doing=None):
    """A job; doing: an answer's tool calls going now and the tools of those done (48.7)."""
    return {
        "id": row["id"],
        "dataset_id": row["dataset_id"],
        "agent": row["agent"],
        "kind": row["kind"],
        "state": row["state"],
        "active": row["state"] in ACTIVE,
        "title": row["title"],
        "run_id": row["run_id"],
        "request_event_id": row["request_event_id"],
        "wait_reason": row["wait_reason"],
        "error": row["error"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "position": position,
        "doing": doing,
    }


class JobQueue:
    def __init__(self, db, runners, memory=free_mb):
        """runners: kind -> async function(job row) doing the job to its end."""
        self.db = db
        self.runners = runners
        self.memory = memory
        self.tasks = {}  # job_id -> task
        self.going = {}  # job_id -> what its answer's worker is doing (definition 48.7)
        self.residents = Residents(lambda: read_settings(db)["chat_slots"])
        self.recheck = None  # the look again while a job is held for memory
        # The app is closing: a job stopped now is stopped by it, not by a person (definition
        # 72: both said alike, as the app stopped).
        self.closing = False
        # Routes without async run in worker threads; jobs start on the server's loop.
        self.loop = asyncio.get_running_loop()
        with db.transaction():
            # A job going when the server stopped did not finish; waiting ones go on. Those
            # are told where they were asked once the app has started (app.py; definition 72).
            self.restarted = [
                dict(r) for r in db.execute("SELECT * FROM jobs WHERE state='running'")
            ]
            db.execute(
                "UPDATE jobs SET state='failed', error='app_stopped', ended_at=?"
                " WHERE state='running'",
                (now(),),
            )

    # ---------- asking ----------

    def enqueue(
        self,
        dataset_id,
        agent,
        kind,
        title,
        request_event_id=None,
        run_id=None,
        bound=None,
    ):
        """A job at its place (dataset_id: a dataset, or the library), bound to a dataset (an
        answer's tools read and propose there; none: its place's; definition 48.10)."""
        job_id = new_id("job-")
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO jobs(id,dataset_id,agent,kind,state,title,request_event_id,"
                "run_id,created_at,bound_dataset_id) VALUES(?,?,?,?,'queued',?,?,?,?,?)",
                (
                    job_id,
                    dataset_id,
                    agent,
                    kind,
                    title,
                    request_event_id,
                    run_id,
                    now(),
                    bound or dataset_id,
                ),
            )
        self.kick()
        return self.get(job_id)

    def get(self, job_id):
        row = job_row(self.db, job_id)
        if row is None:
            raise not_found("Job")
        return _job_out(row, self._position(row), self.going.get(job_id))

    def _position(self, row):
        if row["state"] != "queued":
            return None
        return self.db.one(
            "SELECT count(*) FROM jobs WHERE state='queued' AND rowid<=?",
            (self._rowid(row["id"]),),
        )[0]

    def _rowid(self, job_id):
        return self.db.one("SELECT rowid FROM jobs WHERE id=?", (job_id,))[0]

    # ---------- starting ----------

    def now_doing(self, job_id, doing):
        """What an answer's worker is doing: its tool calls going now and the tools of those
        done ({going, done}); none when the answer ended."""
        if doing:
            self.going[job_id] = doing
        else:
            self.going.pop(job_id, None)

    def talk(self, row):
        """The conversation an answer with tools goes on in, and the key of its kept CLI:
        its dataset (none for the reception), worker and chat."""
        return (row["dataset_id"], row["agent"], job_chat(self.db, row))

    def answer_in(self, agent, chat_id):
        """The answer with tools going in a chat now: at most one (a chat's go one at a time).
        A kept CLI's MCP calls are told apart by its chat (definition 27.4)."""
        for r in self.db.execute(
            "SELECT * FROM jobs WHERE state='running' AND agent=? AND kind IN"
            f" ({','.join('?' * len(GROUPS['chat']))})",
            (agent, *GROUPS["chat"]),
        ):
            if job_chat(self.db, r) == chat_id:
                return r["id"]
        return None

    def memory_short(self, workers):
        """(free, need) in MB when the machine has not the memory for that many more worker
        CLIs, else None (also when the free memory is not known)."""
        free, need = self.memory(), memory_needed(workers)
        return (free, need) if free is not None and free < need else None

    def held_for_memory(self, run_id, held):
        """A run going says whether its next image waits for memory, as a job waiting to start
        does (2026-11-02: a run started its worker CLIs with the memory gone, and they ended at
        once): its job's wait_reason."""
        with self.db.transaction():
            self.db.execute(
                "UPDATE jobs SET wait_reason=? WHERE run_id=? AND state='running'",
                ("memory" if held else None, run_id),
            )

    def kick(self):
        """Start every waiting job its turn allows; note why the others wait."""
        try:
            here = asyncio.get_running_loop()
        except RuntimeError:
            here = None
        if here is not self.loop:
            self.loop.call_soon_threadsafe(self.kick)
            return
        settings = read_settings(self.db)
        limits = {group: settings[f"{group}_slots"] for group in GROUPS}
        rows = self.db.execute(
            "SELECT * FROM jobs WHERE state IN ('queued','running') ORDER BY rowid"
        )
        going = dict.fromkeys(GROUPS, 0)
        busy_talks = set()
        for r in rows:
            if r["state"] == "running":
                going[_class(r["kind"])] += 1
                if _class(r["kind"]) == "chat":
                    busy_talks.add(self.talk(r))
        queued = [r for r in rows if r["state"] == "queued"]
        held = dict.fromkeys(GROUPS)  # the reason a group stopped (no overtaking)
        for r in queued:
            kind = _class(r["kind"])
            reason = held[kind]
            if reason is None and kind == "chat" and self.talk(r) in busy_talks:
                # The conversation goes on in one CLI at a time, and that CLI is the chat's
                # (each chat its own since 2026-10-09 evening; the wait was left per worker
                # until 2026-10-13, so another chat of the worker waited too).
                reason = "same_agent"
            # Two runs never hold the same image: the second is refused when it is decided
            # (definition 18.13), so a run does not wait for one here.
            if reason is None and going[kind] >= limits[kind]:
                reason = held[kind] = "slots"
            if reason is None and self.memory_short(workers_of(kind, settings)):
                reason = held[kind] = "memory"
            if reason is not None:
                if r["wait_reason"] != reason:
                    with self.db.transaction():
                        self.db.execute(
                            "UPDATE jobs SET wait_reason=? WHERE id=?",
                            (reason, r["id"]),
                        )
                continue
            with self.db.transaction():
                self.db.execute(
                    "UPDATE jobs SET state='running', started_at=?, wait_reason=NULL"
                    " WHERE id=? AND state='queued'",
                    (now(), r["id"]),
                )
            going[kind] += 1
            if kind == "chat":
                busy_talks.add(self.talk(r))
            row = self.db.one("SELECT * FROM jobs WHERE id=?", (r["id"],))
            self.tasks[r["id"]] = asyncio.create_task(
                self._go(row), name=f"job-{r['id']}"
            )
        if "memory" in held.values() and self.recheck is None:
            self.recheck = self.loop.call_later(MEMORY_RECHECK_SECONDS, self._recheck)

    def _recheck(self):
        self.recheck = None
        self.kick()

    async def _go(self, row):
        state, error = "done", None
        try:
            await self.runners[row["kind"]](row)
        except asyncio.CancelledError:
            state = "cancelled"
        except Exception as exc:
            logger.exception("Job failed")
            state, error = "failed", str(exc) or type(exc).__name__
        finally:
            with self.db.transaction():
                self.db.execute(
                    "UPDATE jobs SET state=?, error=?, ended_at=? WHERE id=?",
                    (state, error, now(), row["id"]),
                )
            self.tasks.pop(row["id"], None)
            self.kick()

    # ---------- stopping ----------

    def cancel(self, job_id):
        """A waiting job leaves the line; a going answer is stopped (its CLI is ended by the
        server, not asked to stop). A going run is stopped through its run."""
        row = self.db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if row is None:
            raise not_found("Job")
        if row["state"] not in ("queued", "running"):
            raise ApiError(409, "job_ended", "The job has ended already")
        if row["kind"] == "run":
            raise ApiError(
                409, "job_is_run", "Stop the run instead", {"run_id": row["run_id"]}
            )
        if row["state"] == "queued":
            with self.db.transaction():
                self.db.execute(
                    "UPDATE jobs SET state='cancelled', ended_at=? WHERE id=?"
                    " AND state='queued'",
                    (now(), job_id),
                )
        elif job_id in self.tasks:
            self.tasks[job_id].cancel()
        return self.get(job_id)

    def cancel_run(self, run_id):
        """A queued run was stopped: its job leaves the line."""
        with self.db.transaction():
            self.db.execute(
                "UPDATE jobs SET state='cancelled', ended_at=? WHERE run_id=?"
                " AND state='queued'",
                (now(), run_id),
            )
        self.kick()

    def forget_chat(self, agent, chat_id):
        """A chat was deleted: its kept CLI goes (called from a route's thread)."""
        asyncio.run_coroutine_threadsafe(
            self.residents.stop_chat(agent, chat_id), self.loop
        )

    async def close(self):
        self.closing = True
        if self.recheck is not None:
            self.recheck.cancel()
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        await self.residents.close()

    # ---------- reading ----------

    def listing(self, dataset_id=None):
        """Waiting and going jobs in order, then the last 20 ended, newest first; a dataset's:
        those bound to it, whichever worker's (definition 48.10)."""
        where, params = "", ()
        if dataset_id:
            dataset_row(self.db, dataset_id)
            where, params = " AND bound_dataset_id=?", (dataset_id,)
        live = self.db.execute(
            f"SELECT * FROM jobs WHERE state IN ('queued','running'){where}"
            " ORDER BY created_at, rowid",
            params,
        )
        ended = self.db.execute(
            f"SELECT * FROM jobs WHERE state NOT IN ('queued','running'){where}"
            " ORDER BY ended_at DESC LIMIT 20",
            params,
        )
        jobs = [
            _job_out(r, self._position(r), self.going.get(r["id"]))
            for r in [*live, *ended]
        ]
        # A job held for memory says how much is free and how much it waits for (2026-10-30: the
        # talk said only "thinking" while an answer waited for memory): to start, or, a run
        # going, to start its next image's worker.
        held = [j for j in jobs if j["active"] and j["wait_reason"] == "memory"]
        if held:
            settings, free = read_settings(self.db), self.memory()
            for job in held:
                workers = (
                    1
                    if job["state"] == "running"
                    else workers_of(_class(job["kind"]), settings)
                )
                job["memory"] = {"free_mb": free, "need_mb": memory_needed(workers)}
        for job in jobs:
            # What an answer ended in (Sol 2026-10-08: "done" while a question waited for the
            # person): the kind of the line it wrote, none when it gave way to one with tools.
            if job["kind"] != "run" and job["state"] == "done":
                from .agent_chat import job_last_line  # a job's answer is a line

                said = job_last_line(self.db, job["id"])
                job["said"] = said["kind"] if said else None
        return {
            "jobs": jobs,
            "running": sum(r["state"] == "running" for r in live),
            "queued": sum(r["state"] == "queued" for r in live),
        }


def _class(kind):
    return next(group for group, kinds in GROUPS.items() if kind in kinds)


def queue_of(request: Request) -> JobQueue:
    return request.app.state.jobs


@router.get("/jobs")
def list_jobs_route(request: Request, dataset: str | None = None):
    return queue_of(request).listing(dataset)


@router.get("/jobs/{job_id}")
def get_job_route(request: Request, job_id: str):
    return queue_of(request).get(job_id)


@router.post("/jobs/{job_id}/cancel")
def cancel_route(request: Request, job_id: str):
    if request.headers.get("x-annotation-agent"):
        raise ApiError(403, "agent_scope", "Only a person cancels a job")
    return queue_of(request).cancel(job_id)

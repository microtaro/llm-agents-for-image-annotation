"""Runs: one AI agent per image, each writing only into its own result (step 2 design 4).

Copied from annotation_server/runs.py without auto-adoption: adoption is computed from
rules in a later step. Failures and stops leave every result as it is.
"""

import asyncio
import hashlib
import json
import logging
import re
import tempfile
import time
from decimal import Decimal
from pathlib import Path

from . import decisions, run_logs, shared_notes
from . import settings as app_settings
from .agents import worker_at
from .annotation_sets import new_set, set_row
from .codex_execution import selected_execution_settings, worker_prompt
from .costs import api_cost
from .datasets import dataset_row
from .db import encoded, new_id, now
from .drafts import CONTENT, version_from_write
from .errors import ApiError
from .inference import infer
from .instructions import version_row
from .jobs import MEMORY_RECHECK_SECONDS, queued_runs
from .label_colors import dataset_colors
from .run_checks import Trace
from .run_inputs import (
    default_choice,
    plan_to_run,
    recipe_for,
    refuse_writing,
    run_limit,
    start_targets,
)
from .run_queries import WAITING, get_run, next_number, requested_items, run_row, task
from .worker_boundary import ImageWork, WorkerBoundary

logger = logging.getLogger("agent_app")
# The provider's words for a failure that passes by itself (seen 2026-10-05: "Selected model
# is at capacity. Please try a different model.").
PASSING = re.compile(
    r"at capacity|rate.?limit|overloaded|too many requests|\b429\b|\b50[234]\b"
    r"|temporarily|try again later|reconnect|connection (?:reset|refused|closed|error)",
    re.IGNORECASE,
)
# Why a run did not succeed: code for screens, text for the API (else run_failed).
RUN_ERRORS = {
    "some_failed": "Some images failed.",
    # 2026-11-02: with the memory gone, the worker CLIs ended at once, said only as "exit=1".
    "memory_short": "Some images failed for want of memory. Close other programs, then run them again.",
    "stopped": "Stopped.",
    "budget_reached": "The cost limit was reached.",
    # The app stopped while it went (closed, or ended without closing; definition 72).
    "app_stopped": "Interrupted because the app stopped; runs do not resume by themselves.",
    "signed_out_codex": "The Codex CLI sign-in has expired. Sign in again (codex logout, codex login), then run again.",
    "signed_out_claude": "The Claude Code sign-in has expired. Start claude and sign in again, then run again.",
}


class SignedOut(RuntimeError):
    """A CLI's sign-in has expired: the run stops, with the CLI's own words (its code)."""

    def __init__(self, code):
        super().__init__(RUN_ERRORS[code])
        self.code = code


class RunExecution(WorkerBoundary):
    """One run going: its worker's boundary and its images, image_slots of them at once, each
    its own work (step 24: runs go at once, each its own execution; definition 50: a run's
    images at once, they went one at a time)."""

    def __init__(self, db, run_id, notify, jobs):
        super().__init__(db, run_id, notify)
        self.jobs = (
            jobs  # the line of work: the machine's memory for one more worker CLI
        )
        self.closing = False  # the app is closing (Runs.close)
        self.started = time.monotonic()
        self.memory_failed = False  # an image failed while the memory was short

    def _set_result(self, result_id, **values):
        columns = ",".join(f"{k}=?" for k in values)
        with self.db.transaction():
            self.db.execute(
                f"UPDATE results SET {columns} WHERE id=?",
                (*values.values(), result_id),
            )
            if "status" in values:
                run_logs.append(
                    self.db,
                    self.active_id,
                    result_id,
                    "state",
                    {"status": values["status"], "message": values.get("message")},
                )
        self.notify()

    async def take_event(self, work, event):
        """Receive one CLI event of an image: keep it for its check and log it without
        images."""
        body = work.trace.take(event)
        if body is None:
            return
        run_logs.append(self.db, self.active_id, work.result_id, "agent", body)
        self.notify()

    def take(self, result):
        """Begin the work on one image: its result, its task and a fresh trace."""
        work = ImageWork(
            result["id"],
            task(self.db, self.run, result),
            Trace(self.run["settings"].get("method")),
        )
        self.images[result["id"]] = work
        return work

    async def _run_image(self, run, result, work, directory):
        self._set_result(result["id"], status="running", started_at=now())

        async def on_event(event):
            await self.take_event(work, event)

        try:
            answer, usage, evidence = await infer(
                directory, run, result["id"], self.stop, on_event
            )
        except BaseException as exc:
            # The CLI ran, so the image has a cost even when it failed or was cut off.
            self._record_usage(
                run,
                result,
                getattr(exc, "usage", None),
                getattr(exc, "evidence", None),
                "The CLI ended before it reported usage (failure, stop or time limit)",
            )
            raise
        self._record_usage(run, result, usage, evidence, "CLI usage was not returned")
        run_logs.append(self.db, run["id"], result["id"], "final", answer)
        if self.stop.is_set():
            raise InterruptedError(RUN_ERRORS["stopped"])
        fresh = self.db.one("SELECT * FROM results WHERE id=?", (result["id"],))
        status, view_id = work.trace.check(self.db, fresh, answer)
        self._set_result(
            result["id"],
            status=status,
            final_view_id=view_id,
            message=answer.get("explanation"),
        )

    def _record_usage(self, run, result, usage, evidence, reason):
        cost = api_cost(usage, run["settings"], reason=None if usage else reason)
        self._set_result(
            result["id"],
            usage_json=encoded(usage) if usage else None,
            cost_json=encoded(cost),
        )
        run_logs.append(
            self.db,
            run["id"],
            result["id"],
            "usage",
            {"usage": usage, "cost": cost, "evidence": evidence},
        )

    def _over_budget(self, run):
        """The next image would go over the run's limit, its limit per image times its images
        (user 2026-10-28): known costs, each image whose cost is unknown (the images going
        too, definition 50.2) at the run's average known cost, and the next image at that
        average (found 2026-10-05 by Astra: a $3 limit ended at $3.26,
        the last image went over)."""
        if not run["budget_per_image_usd"]:
            return False
        limit = (
            Decimal(run["budget_per_image_usd"])
            * self.db.one(
                "SELECT count(*) AS n FROM results WHERE run_id=?", (run["id"],)
            )["n"]
        )
        costs = [
            json.loads(r[0]).get("usd") if r[0] else None
            for r in self.db.execute(
                "SELECT cost_json FROM results WHERE run_id=?"
                " AND (cost_json IS NOT NULL OR status='running')",
                (run["id"],),
            )
        ]
        known = [Decimal(c) for c in costs if c is not None]
        spent = sum(known, Decimal(0))
        average = spent / len(known) if known else Decimal(0)
        spent += average * (len(costs) - len(known))
        return spent + average > limit or spent >= limit

    async def _memory_for_a_worker(self):
        """Waits, its job saying so, until the machine has the memory for one more worker CLI
        (2026-11-02: the line looked at the memory when a run started only, and the run's CLIs,
        started with the memory gone, ended at once)."""
        while self.jobs.memory_short(1) and not self.stop.is_set():
            self.jobs.held_for_memory(self.active_id, True)
            self.notify()
            try:
                await asyncio.wait_for(self.stop.wait(), MEMORY_RECHECK_SECONDS)
            except TimeoutError:
                pass
        self.jobs.held_for_memory(self.active_id, False)

    async def _one(self, run, result):
        """Run one image, trying again after a passing failure (the provider busy, a rate
        limit, a dropped connection) while nothing was saved, as the settings allow."""
        tries = run["settings"].get("retry_count", 0)
        wait = run["settings"].get("retry_wait_seconds", 30)
        for attempt in range(tries + 1):
            failure = await self._try(run, result)
            if (
                failure is None
                or attempt == tries
                or not self._passing(result, failure)
            ):
                return
            run_logs.append(
                self.db,
                run["id"],
                result["id"],
                "state",
                {
                    "status": "failed",
                    "message": f"Trying again in {wait} s ({attempt + 1}/{tries}): {failure}",
                },
            )
            self.notify()
            try:
                await asyncio.wait_for(self.stop.wait(), wait)
            except TimeoutError:
                pass
            if self.stop.is_set():
                self._set_result(
                    result["id"],
                    status="interrupted",
                    message="Stopped before this image finished.",
                )
                raise InterruptedError(RUN_ERRORS["stopped"])

    def _passing(self, result, failure):
        """A failure worth trying again: the provider's own words say it passes, and the
        worker saved nothing (a try again starts from an empty result)."""
        saved = set_row(self.db, result["set_id"])["revision"]
        return bool(PASSING.search(failure)) and saved == 0

    async def _try(self, run, result):
        """One try of one image; returns the failure message, or None when the image ended
        otherwise (done, timed out, or an error that stops the run is raised)."""
        started = time.monotonic()
        failure = None
        work = self.take(result)
        try:
            with tempfile.TemporaryDirectory(prefix="annotation-run-") as directory:
                async with asyncio.timeout(run["settings"]["target_timeout_seconds"]):
                    await self._run_image(run, result, work, Path(directory))
        except (InterruptedError, asyncio.CancelledError):
            self._set_result(
                result["id"],
                status="interrupted",
                message="Stopped before this image finished.",
            )
            raise
        except TimeoutError:
            self._set_result(
                result["id"],
                status="failed",
                message="Exceeded the time limit per image "
                f"({run['settings']['target_timeout_seconds']} s).",
            )
        except Exception as exc:
            logger.exception("Run image failed")
            failure = work.trace.failure or str(exc)
            short = self.jobs.memory_short(1)
            if short:
                # Its worker could not have been started now: the memory is the likely cause,
                # and what the CLI said (often "exit=1") does not tell it.
                self.memory_failed = True
                failure = (
                    f"Not enough memory for the AI ({short[0]} MB free, {short[1]} MB"
                    f" needed): close other programs, then run it again. ({failure})"
                )
            self._set_result(result["id"], status="failed", message=failure)
        finally:
            self._set_result(
                result["id"], elapsed_ms=(time.monotonic() - started) * 1000
            )
            self.images.pop(result["id"], None)
        if work.trace.auth_failure:
            self._set_result(result["id"], message=RUN_ERRORS[work.trace.auth_failure])
            raise SignedOut(work.trace.auth_failure)
        return failure

    def load(self):
        """The run as its worker reads it."""
        row = run_row(self.db, self.active_id)
        self.run = {
            "id": row["id"],
            "dataset_id": row["dataset_id"],
            "instruction_revision": row["instruction_revision"],
            "settings": json.loads(row["settings_json"]),
            "worker_prompt": row["worker_prompt"],
            "budget_per_image_usd": row["budget_per_image_usd"],
        }
        return self.run

    async def go(self):
        run_id = self.active_id
        self.started = time.monotonic()
        run = self.load()
        results = [
            dict(r)
            for r in self.db.execute(
                "SELECT * FROM results WHERE run_id=? ORDER BY position", (run_id,)
            )
        ]
        # Images image_slots at once (definition 50.2): each takes a slot, then starts unless
        # the run was stopped or its cost limit would be passed; the ones going go on.
        slots = asyncio.Semaphore(run["settings"].get("image_slots", 1))
        over_budget = []

        async def image(result):
            async with slots:
                await self._memory_for_a_worker()
                if self.stop.is_set() or over_budget:
                    return
                if self._over_budget(run):
                    over_budget.append(result["id"])
                    return
                try:
                    await self._one(run, result)
                except SignedOut:
                    self.stop.set()  # the others would fail the same way
                    raise

        terminal, code, error = "succeeded", None, None
        try:
            ended = await asyncio.gather(
                *(image(result) for result in results), return_exceptions=True
            )
            stopped = (InterruptedError, asyncio.CancelledError)
            failures = [
                e
                for e in ended
                if isinstance(e, BaseException) and not isinstance(e, stopped)
            ]
            if failures:
                logger.error("Run failed", exc_info=failures[0])
                first = failures[0]
                terminal, code, error = (
                    "failed",
                    first.code if isinstance(first, SignedOut) else "run_failed",
                    str(first),
                )
            elif over_budget:
                terminal, code = "stopped", "budget_reached"
            elif self.stop.is_set() or any(isinstance(e, stopped) for e in ended):
                terminal, code = "stopped", "stopped"
            elif self.db.one(
                "SELECT 1 FROM results WHERE run_id=? AND status='failed'", (run_id,)
            ):
                terminal = "failed"
                code = "memory_short" if self.memory_failed else "some_failed"
        except BaseException as exc:
            logger.exception("Run failed")
            terminal, code, error = "failed", "run_failed", str(exc)
        finally:
            if self.closing:
                # The app closing stopped it: interrupted, as a run the app ended without
                # closing is found at its next start (definition 72; it said "failed").
                terminal, code, error = "interrupted", "app_stopped", None
            await self._finish(run, terminal, code, error)

    async def _finish(self, run, terminal, code, error):
        self.stop.set()
        try:
            await asyncio.wait_for(
                self.drained.wait(),
                timeout=app_settings.tool_time_limit(run["settings"]) + 5,
            )
        except TimeoutError:
            logger.error("MCP call completion could not be confirmed")
        with self.db.transaction():
            error = RUN_ERRORS.get(code, error)
            self.db.execute(
                "UPDATE results SET status='interrupted', message=? WHERE run_id=?"
                " AND status IN (?,?)",
                ("Not run because the run stopped.", run["id"], *WAITING),
            )
            self.db.execute(
                "UPDATE runs SET status=?, ended_at=?, elapsed_ms=?, error=?, error_code=?"
                " WHERE id=?",
                (
                    terminal,
                    now(),
                    (time.monotonic() - self.started) * 1000,
                    error,
                    code,
                    run["id"],
                ),
            )
            run_logs.append(
                self.db,
                run["id"],
                None,
                "state",
                {"status": terminal, "error": error, "error_code": code},
            )
        self.notify()


class Runs:
    """Every run: admission into the line of work (jobs.JobQueue starts a run when a heavy
    slot and memory allow, step 24 design 3.4), the executions going, and the change counter
    run waits follow."""

    def __init__(self, db):
        self.db = db
        self.jobs = None  # the line of work, set by the app
        self.on_end = None  # the workers' conversations hear a run end (agent_chat)
        self.active = {}  # run_id -> RunExecution
        self.version = 0
        self._changed = asyncio.Event()
        # The runs this start interrupted, told as ended once the app has started (app.py).
        self.interrupted = []
        with db.transaction():
            # Going when the server stopped, or waiting with no job to start it (issue #5-11:
            # the run and its job are made one after the other; a stop between left a queued
            # run nothing starts, holding its images' lock for ever).
            started = queued_runs(db)
            for row in [
                r
                for r in db.execute("SELECT id, status FROM runs")
                if r["status"] in ("running", "stopping")
                or (r["status"] == "queued" and r["id"] not in started)
            ]:
                db.execute(
                    "UPDATE results SET status='interrupted', message=? WHERE run_id=?"
                    " AND status IN (?,?)",
                    ("Interrupted by a server restart.", row["id"], *WAITING),
                )
                db.execute(
                    "UPDATE runs SET status='interrupted', ended_at=?, error=?,"
                    " error_code='app_stopped' WHERE id=?",
                    (now(), RUN_ERRORS["app_stopped"], row["id"]),
                )
                self.interrupted.append(row["id"])

    # ---------- progress notification ----------

    def notify(self):
        self.version += 1
        changed, self._changed = self._changed, asyncio.Event()
        changed.set()

    async def wait_change(self, seen, timeout):
        """Return the current version; unchanged when the timeout elapses first."""
        if self.version == seen:
            try:
                await asyncio.wait_for(self._changed.wait(), timeout)
            except TimeoutError:
                pass
        return self.version

    # ---------- the worker's calls, by its run ----------

    def execution(self, run_id):
        found = self.active.get(run_id)
        if found is None:
            raise ApiError(409, "run_inactive", "This run no longer owns the image")
        return found

    def image(self, run_id, result_id):
        """The work on one image of a run going now (definition 50.1)."""
        return self.execution(run_id).image(result_id)

    def check_worker(self, run_id, result_id, *, write):
        self.execution(run_id).check_worker(run_id, result_id, write=write)

    async def begin_call(self, run_id, result_id):
        await self.execution(run_id).begin_call(run_id, result_id)

    def validate_call(self, run_id, result_id, tool, args):
        self.execution(run_id).validate_call(result_id, tool, args)

    async def end_call(self, run_id, result_id, tool, arguments, envelope, duration_ms):
        found = self.active.get(run_id)
        if found is not None:
            await found.end_call(result_id, tool, arguments, envelope, duration_ms)

    # ---------- admission ----------

    def _admitted(self, dataset_id, run_id, request):
        """The existing run for this ID, or None; refuses a conflicting start. A busy server
        no longer refuses: the run waits in the line of work (step 24)."""
        old = self.db.one(
            "SELECT dataset_id,request_json FROM runs WHERE id=?", (run_id,)
        )
        if old:
            if (old[0], old[1]) != (dataset_id, request):
                raise ApiError(409, "run_conflict", "Run ID has different input")
            return get_run(self.db, run_id, self.version)
        return None

    async def start(self, dataset_id, run_id, body, by):
        """The decision to annotate with AI carried out (definition 1 D1, 21.3): its version
        made (if from a write), its way, the run, a result to make for each image, the decision
        the run holds, its turn in the line."""
        request = encoded(body.model_dump(mode="json"))
        db = self.db
        with db.lock:
            existing = self._admitted(dataset_id, run_id, request)
            if existing:
                return existing, False
            dataset_row(db, dataset_id)
            # The plan it runs, by value: the draft write or version given (what the box
            # showed), else the plan now (definition 11.3).
            plan = plan_to_run(db, dataset_id, body.draft_write_id, body.revision)
            targets = start_targets(
                db,
                dataset_id,
                body.image_ids,
                body.trial,
                body.revision,
                body.draft_write_id,
            )
        # Checking the CLIs runs subprocesses; keep them off the event loop.
        model, effort, tier = body.model, body.effort, body.tier
        if model is None and effort is None and tier is None:
            # Nothing chosen (an AI's run, an API call): the settings' default.
            model, effort, tier = default_choice(db)
        settings = await asyncio.to_thread(
            selected_execution_settings, model, effort, tier
        )
        settings.update(app_settings.read_settings(db))
        # The shared notes of the version the decision holds (else the version now): the same
        # way gets the same words (definition 18.15).
        notes = (
            shared_notes.notes_at(db, body.shared_revision)
            if body.shared_revision is not None
            else shared_notes.latest(db)
        )
        settings["worker_extra_instructions"] = notes["text"] if notes else ""
        settings["shared_revision"] = notes["revision"] if notes else None
        with db.transaction():
            # Another start may have been admitted while the CLIs were checked.
            existing = self._admitted(dataset_id, run_id, request)
            if existing:
                return existing, False
            refuse_writing(db, dataset_id, targets)
            number = next_number(db, dataset_id)
            decision_id = decisions.record(
                db,
                dataset_id,
                "run",
                body.model_dump(mode="json"),
                by,
                {"id": run_id, "number": number},
            )
            # The version is made here, with its run (no version left unused when a run
            # cannot start), from the write the decision pointed at, by that decision.
            revision = (
                version_from_write(db, dataset_id, plan["write"], by.who, decision_id)
                if "write" in plan
                else plan["revision"]
            )
            instruction = version_row(db, dataset_id, revision)
            recipe_id = recipe_for(
                db,
                dataset_id,
                revision,
                settings["model"],
                settings["effort"],
                settings["shared_revision"],
                by.who,
            )
            payload = json.loads(instruction["payload_json"])
            definitions = payload["label_definitions"]
            # The dataset's colors now; later changes do not reach this run's worker.
            chosen = dataset_colors(db, dataset_id)
            settings["label_colors"] = {
                d["name"]: chosen[d["name"]] for d in definitions
            }
            if body.trial:
                # Marks the run a trial, the plan's samples (a few images of the version, run
                # from the plan; definition 38.1): what the worker gets of the version.
                settings["trial_instruction"] = {k: payload[k] for k in CONTENT}
            prompt = worker_prompt(settings)
            db.execute(
                "INSERT INTO runs(id,dataset_id,status,instruction_revision,requirement_key,"
                "requested_json,worker_prompt,worker_prompt_sha256,settings_json,request_json,"
                "budget_per_image_usd,started_at,recipe_id,number,decision_id)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    dataset_id,
                    "queued",
                    instruction["revision"],
                    instruction["requirement_key"],
                    encoded(requested_items(definitions)),
                    prompt,
                    hashlib.sha256(prompt.encode()).hexdigest(),
                    encoded(settings),
                    request,
                    run_limit(
                        db,
                        dataset_id,
                        instruction["requirement_key"],
                        (settings.get("model"), settings.get("effort")),
                        body.budget_per_image_usd,
                    ),
                    now(),
                    recipe_id,
                    number,
                    decision_id,
                ),
            )
            for position, image_id in enumerate(targets):
                db.execute(
                    "INSERT INTO results(id,run_id,image_id,set_id,position,status)"
                    " VALUES(?,?,?,?,?,'pending')",
                    (new_id("res-"), run_id, image_id, new_set(db, image_id), position),
                )
            run_logs.append(db, run_id, None, "state", {"status": "queued"})
        self.jobs.enqueue(
            dataset_id,
            # A dataset's runs are its worker's (definition 35.1).
            worker_at(dataset_id),
            "run",
            run_title(len(targets), body.trial),
            run_id=run_id,
        )
        self.notify()
        return get_run(db, run_id, self.version), True

    async def launch(self, run_id):
        """Start a queued run (its job's turn came) and wait for it to end."""
        with self.db.transaction():
            if run_row(self.db, run_id)["status"] != "queued":
                return  # stopped while it waited
            self.db.execute("UPDATE runs SET status='running' WHERE id=?", (run_id,))
            run_logs.append(self.db, run_id, None, "state", {"status": "running"})
        execution = RunExecution(self.db, run_id, self.notify, self.jobs)
        self.active[run_id] = execution
        self.notify()
        try:
            await execution.go()
        finally:
            self.active.pop(run_id, None)
            self.notify()
            if self.on_end:
                self.on_end(run_id)

    def request_stop(self, run_id, by):
        """The decision to stop a run carried out (definition 6, 21.3), when it still goes."""
        with self.db.transaction():
            run = run_row(self.db, run_id)
            status = run["status"]
            if status in ("queued", "running"):
                decision_id = decisions.record(
                    self.db, run["dataset_id"], "stop", {"run_id": run_id}, by
                )
                self.db.execute(
                    "UPDATE runs SET stop_decision_id=? WHERE id=?",
                    (decision_id, run_id),
                )
            if status == "queued":
                # Never started: stopped where it waited, its images not run.
                self.db.execute(
                    "UPDATE results SET status='interrupted', message=? WHERE run_id=?"
                    " AND status='pending'",
                    ("Not run because the run stopped.", run_id),
                )
                self.db.execute(
                    "UPDATE runs SET status='stopped', ended_at=?, error=?,"
                    " error_code='stopped' WHERE id=?",
                    (now(), RUN_ERRORS["stopped"], run_id),
                )
                run_logs.append(self.db, run_id, None, "state", {"status": "stopped"})
            elif status == "running":
                self.db.execute(
                    "UPDATE runs SET status='stopping' WHERE id=?", (run_id,)
                )
                if run_id in self.active:
                    self.active[run_id].stop.set()
        if status == "queued" and self.jobs:
            self.jobs.cancel_run(run_id)
        self.notify()
        return get_run(self.db, run_id, self.version)

    async def close(self):
        for execution in self.active.values():
            execution.closing = True
            execution.stop.set()
        await asyncio.sleep(0)


def run_title(count, trial):
    return f"{'trial' if trial else 'run'}:{count}"

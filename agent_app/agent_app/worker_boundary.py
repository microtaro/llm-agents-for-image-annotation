"""What a run's worker may touch: only the images of its run going now, each its own result,
one MCP call at a time per image, at most max_mcp_calls per image. Copied from
annotation_server/runs.py (step 2 design 5). One per run since step 24 (runs go at once); a
run's images go at once since definition 50, each its own work (ImageWork). The change counter
run waits follow is the manager's (runs.Runs), given as notify.
"""

import asyncio

from . import run_logs
from .claude_execution import WORKER_TOOLS
from .errors import ApiError


class ImageWork:
    """One image a run's worker works on (definition 50.1): its result, its task, its trace
    and its MCP calls."""

    def __init__(self, result_id, task_info, trace):
        self.result_id = result_id
        self.task_info = task_info
        self.trace = trace
        self.calls = 0
        self.inflight = False


class WorkerBoundary:
    def __init__(self, db, run_id, notify):
        self.db = db
        self.notify = notify
        self.active_id = run_id
        self.run = None
        self.images = {}  # result_id -> ImageWork, the images going now
        self.stop = asyncio.Event()
        self.drained = asyncio.Event()
        self.drained.set()

    # ---------- worker boundary ----------

    def image(self, result_id):
        """The work on one image of this run going now."""
        found = self.images.get(result_id)
        if found is None:
            raise ApiError(409, "run_inactive", "This run no longer owns the image")
        return found

    def check_worker(self, run_id, result_id, *, write):
        """Only the images of the active run going now may use worker routes."""
        if run_id != self.active_id:
            raise ApiError(409, "run_inactive", "This run no longer owns the image")
        self.image(result_id)
        if write and self.stop.is_set():
            raise ApiError(409, "run_inactive", "A stopped run cannot write")

    async def begin_call(self, run_id, result_id):
        if run_id != self.active_id:
            raise ApiError(409, "run_inactive", "This run does not own the image")
        work = self.image(result_id)
        work.calls += 1
        limit = self.run["settings"]["max_mcp_calls"]
        if work.calls > limit:
            work.trace.failure = "tool_call_limit"
            raise ApiError(
                409, "tool_call_limit", f"At most {limit} MCP calls per image"
            )
        if work.inflight:
            raise ApiError(409, "run_call_busy", "One MCP call at a time")
        work.inflight = True
        self.drained.clear()

    def validate_call(self, result_id, tool, args):
        """Worker tools touch only the target image and its own result."""
        if tool not in WORKER_TOOLS:
            raise ApiError(403, "run_scope", "Tool is outside the run's worker tools")
        work = self.image(result_id)
        if tool == "observe":
            target = args.target
            if target.result_id is not None:
                if target.result_id != result_id:
                    raise ApiError(
                        403, "run_scope", "Only your own result can be observed"
                    )
            elif target.image_id != work.task_info["image_id"]:
                raise ApiError(403, "run_scope", "Image is outside the target")
        if tool == "save_and_observe" and (
            args.result_id != result_id or args.batch.request_id is None
        ):
            raise ApiError(
                403, "run_scope", "Save to your own result with a batch UUID"
            )

    async def end_call(self, result_id, tool, arguments, envelope, duration_ms):
        try:
            run_logs.append(
                self.db,
                self.active_id,
                result_id,
                "tool",
                {
                    "tool": tool,
                    "arguments": arguments,
                    "ok": envelope.get("ok"),
                    "error": (envelope.get("error") or {}).get("code"),
                    "view_id": (envelope.get("view") or {}).get("view_id"),
                    "duration_ms": duration_ms,
                },
            )
            self.notify()
        finally:
            work = self.images.get(result_id)
            if work is not None:
                work.inflight = False
            if not any(w.inflight for w in self.images.values()):
                self.drained.set()

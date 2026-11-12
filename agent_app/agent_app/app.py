"""The HTTP app: the API under /v1 and the built screen (ui/dist) at /."""

import asyncio
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.routing import Route

from . import errors
from .adoption_routes import router as adoption_router
from .agent_answer import Answers
from .agent_chat import note_run_end
from .agent_chat import router as agent_chat_router
from .agents import router as agents_router
from .annotation_sets import number_missing
from .carry import router as carry_router
from .config import APP, UI_DIST
from .confirmations import router as confirm_router
from .dataset_export import router as export_router
from .dataset_import import router as import_router
from .dataset_import import take_in_samples
from .db import Database
from .draft_routes import router as draft_router
from .fixes import router as fixes_router
from .handoff import router as handoff_router
from .instruction_sources import router as sources_router
from .jobs import JobQueue
from .jobs import router as jobs_router
from .label_change import router as change_router
from .label_library import router as labels_router
from .label_rename import router as rename_router
from .mcp_worker import create_mcp_app
from .notes import router as notes_router
from .object_types import router as objects_router
from .past_requirements import router as past_router
from .plan_questions import router as plan_questions_router
from .plan_starts import router as starts_router
from .plan_state import router as plan_state_router
from .proposals import router as proposals_router
from .proposals import settle, settle_applying
from .references import router as references_router
from .routes import router
from .run_routes import router as run_router
from .runs import Runs
from .screen_routes import router as screen_router
from .shared_notes import router as shared_notes_router
from .sheets import router as sheets_router
from .training import router as training_router
from .turns import router as turns_router


def _names_this_machine(place):
    try:
        return urlsplit(f"//{place}").hostname in ("127.0.0.1", "localhost", "::1")
    except ValueError:
        return False


class OnlyThisMachine:
    """Answers only requests addressed to this machine and, from a page, from a page of this
    machine. Listening on 127.0.0.1 keeps out the network, not a web page open in the browser: it
    can send a plain POST here, or point a name of its own at 127.0.0.1 (DNS rebinding). The MCP
    SDK checks this for /mcp; 2026-11-06, /v1 did not, and a false Host made and deleted a
    dataset."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        if not _names_this_machine(headers.get("host", "")):
            refused = (421, "not_this_machine", "This app answers only on this machine")
        elif origin and not (
            origin.startswith("http://")
            and _names_this_machine(origin[len("http://") :])
        ):
            refused = (403, "not_this_machine", "This app answers only its own pages")
        else:
            await self.app(scope, receive, send)
            return
        status, code, message = refused
        await JSONResponse(errors.body(code, message), status)(scope, receive, send)


class SettleAfterWrites:
    """After every write under /v1 that succeeded, before its answer goes: the waiting boxes
    whose ground it moved are withdrawn (proposals.settle, definition 19.7). A person's press, a
    worker's tool and the outer MCP all write through /v1, so none is missed; reads write
    nothing (issue #5-4)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] in ("GET", "HEAD", "OPTIONS")
            or not scope["path"].startswith("/v1/")
        ):
            return await self.app(scope, receive, send)
        status = 500

        async def sending(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            elif (
                message["type"] == "http.response.body"
                and not message.get("more_body")
                and status < 400
            ):
                settle(scope["app"].state.db)
            await send(message)

        await self.app(scope, receive, sending)


def run_ended(db, run_id, jobs):
    """A run ended away from any request: the waiting boxes it moved the ground of are withdrawn
    first, as after a write (2026-10-29: "stop record 3" waited 40 s after record 3 had ended,
    until the worker's next write), then its end is told."""
    settle(db)
    note_run_end(db, run_id, jobs)


def create_app(db_path=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.db = Database(db_path)
        number_missing(app.state.db)
        take_in_samples(app.state.db)
        settle_applying(app.state.db)
        db = app.state.db
        app.state.runs = runs = Runs(db)
        # The line of work (step 24): runs and the workers' answers start by their turn.
        answers = Answers(db, None)
        app.state.jobs = jobs = JobQueue(
            db,
            {
                "run": lambda job: runs.launch(job["run_id"]),
                "answer_heavy": answers.heavy,
            },
        )
        answers.jobs = runs.jobs = jobs
        runs.on_end = lambda run_id: run_ended(db, run_id, jobs)
        # What the server stopped in the middle is said where it was asked, as when it ends
        # (definition 72; 2026-10-29: after a restart a run said nothing in the talk, and an
        # answer going was never answered nor said to have failed).
        for run_id in runs.interrupted:
            run_ended(db, run_id, jobs)
        for job in jobs.restarted:
            if job["kind"] == "answer_heavy":
                answers.cut_off(job)
        jobs.kick()
        try:
            async with mcp_app.router.lifespan_context(mcp_app):
                yield
        finally:
            await runs.close()
            await jobs.close()
            db.close()

    app = FastAPI(title="agent-app", lifespan=lifespan)
    app.add_middleware(SettleAfterWrites)
    app.add_middleware(OnlyThisMachine)
    errors.install(app)
    app.include_router(router)
    app.include_router(run_router)
    app.include_router(adoption_router)
    app.include_router(fixes_router)
    app.include_router(training_router)
    app.include_router(objects_router)
    app.include_router(draft_router)
    app.include_router(screen_router)
    app.include_router(rename_router)
    app.include_router(change_router)
    app.include_router(confirm_router)
    app.include_router(carry_router)
    app.include_router(labels_router)
    app.include_router(plan_state_router)
    app.include_router(plan_questions_router)
    app.include_router(past_router)
    app.include_router(sheets_router)
    app.include_router(turns_router)
    app.include_router(sources_router)
    app.include_router(starts_router)
    app.include_router(references_router)
    app.include_router(proposals_router)
    app.include_router(agents_router)
    app.include_router(handoff_router)
    app.include_router(agent_chat_router)
    app.include_router(jobs_router)
    app.include_router(notes_router)
    app.include_router(shared_notes_router)
    app.include_router(export_router)
    app.include_router(import_router)
    mcp_app = create_mcp_app(app)
    app.router.routes.append(Route("/mcp", mcp_app, methods=["GET", "POST", "DELETE"]))

    @app.post("/v1/quit", status_code=202)
    async def quit_app(request: Request):
        """The app ends from its screen (user 2026-10-29: the zip's runs with no window to
        close; the same screen everywhere, the work's own too); the answer goes out before it
        ends. A server not started by __main__ (a test's, the zip build's) has no quit."""
        if not hasattr(request.app.state, "quit"):
            raise errors.ApiError(
                409, "quit_not_here", "This server is not quit from its screen"
            )
        request.app.state.quitting = True
        asyncio.get_running_loop().call_later(0.5, request.app.state.quit)
        return {"quitting": True}

    @app.get("/health")
    def health(request: Request):
        # The folder, so the launcher knows its own app from another's on the port (2026-10-29:
        # the zip's start opened an old one). Once told to quit it is not up any more (2026-10-30: the launcher, asking this, kept the app's
        # window open while the server ended its work).
        if getattr(request.app.state, "quitting", False):
            return JSONResponse({"ok": False, "quitting": True}, 503)
        return {"ok": True, "app": "agent-app", "folder": str(APP)}

    if (UI_DIST / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def serve_screen(path: str):
            # The screen routes itself; every non-API path gets the same page.
            if path.startswith(("v1/", "mcp")):
                return JSONResponse(errors.body("not_found", "No such endpoint"), 404)
            # A file of the built screen's top (copied from ui/public: the page's mark, 2026-10-30),
            # never one outside it.
            found = (UI_DIST / path).resolve()
            if found.parent == UI_DIST.resolve() and found.is_file():
                return FileResponse(found)
            return FileResponse(UI_DIST / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        def no_screen():
            return PlainTextResponse(
                "The screen is not built. Run: npm ci, then npm run build",
                status_code=503,
            )

    return app

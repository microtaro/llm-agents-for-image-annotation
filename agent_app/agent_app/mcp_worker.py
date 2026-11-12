"""/mcp: the tools a run's worker uses on its own image and result (step 2 design 5), and
the AI's tools for everyone else (mcp_general.py, step 4 design 5).

Copied from annotation_server/mcp_api.py (worker tools only). A tool calls the HTTP API of
the same app in process, with the run and result IDs the server gave the worker's CLI.
Tools for setting up datasets and starting runs come in a later step.
"""

import asyncio
import base64
import json
import logging
import time
from contextlib import asynccontextmanager

import anyio
import httpx
from mcp import types
from mcp.server import CacheHint, Server
from pydantic import ValidationError

from . import authority, config
from .actions import DECISIONS
from .datasets import has_image, image_id_of
from .errors import ApiError
from .mcp_general import GENERAL, Tool, kept_in_place, result_drawn, run_tool
from .mcp_general import NEXT as GENERAL_NEXT
from .mcp_schemas import (
    Envelope,
    ObserveInput,
    SaveAndObserveInput,
    TaskGetInput,
    ToolError,
)
from .run_queries import has_result, has_run
from .seen import seen, without_geometry
from .settings import read_settings, tool_time_limit

logger = logging.getLogger("agent_app.mcp")
MCP_BODY_LIMIT = 16 * 1024 * 1024
# One map for every caller (issue #3 U-04; the SDK gives one text to all): each sees only its own
# tools in tools/list.
INSTRUCTIONS = """Annotation app. Three kinds of caller, each seeing its own tools:
- A run's worker (task_get, observe, save_and_observe): annotate one target image into your own
  result.
- Coordinates are always in the pixels of a returned image: give them with that image's view_id
  (coordinate_view_id); the server converts them. Coordinates you are shown come with an image
  (its drawn list) and are in its pixels.
- A worker of a dataset or the library (proposal_make among its tools): read freely, write the
  plan's draft and notes, choose its references, and make every decision (a run, what training uses, a
  dataset's images, a label's name, making or deleting a dataset) ready with proposal_make; a
  person decides it. Things are read by type and conditions (read) and seen as pictures (look);
  start from read type dataset (at the library: every dataset).
- Any other caller: the decision tools are called directly.
Display returned images; HTTP success alone is not observation. Never blindly resend a write
whose outcome is unknown."""
TOOLS = {
    "task_get": Tool(
        "Your task: labels, label_definitions (each label's shape, parent label, description and attributes), label_colors, instruction_text, leave_out (what not to annotate) and refs (example images of how to annotate, not of every label: their objects drawn, with a note; one image each in reference_views).",
        TaskGetInput,
        "read",
    ),
    "observe": Tool(
        "Look at your target image ({image_id}) or your result ({result_id}); crop, shrink and overlay. Returns the image, its view_id (for coordinate_view_id) and what is drawn on it in its pixels.",
        ObserveInput,
        "read",
    ),
    "save_and_observe": Tool(
        "Save an atomic batch (coordinates in the pixels of the image named by coordinate_view_id) into your own result, then return its overlay in the same call (in view; when view asks a crop, the whole image too in whole), each annotation's id and geometry in the image's pixels. Rendering failure keeps the save: observe again, do not resend.",
        SaveAndObserveInput,
        "write",
    ),
}
NEXT = {
    "task_get": ["observe"],
    "observe": ["save_and_observe", "observe"],
    "save_and_observe": ["observe", "save_and_observe"],
}


class _Done(Exception):
    """An AI tool finished; skips the worker steps."""


async def written(view, path, body, drawn):
    """What was just written, drawn (definition 32.1, 5 and 7): in the range asked, and the
    whole image too when that range is a crop."""
    shown = [await view(path, body, drawn)]
    if body.get("crop_xywh") is not None:
        whole = {
            k: v
            for k, v in body.items()
            if k not in ("crop_xywh", "coordinate_view_id", "margin")
        }
        shown.append(await view(path, whole, drawn))
    return shown


def _image_content(response):
    mime = response.headers["content-type"].split(";")[0]
    if mime != "image/jpeg":
        raise ValueError("Unexpected image content type")
    data = base64.b64encode(response.content).decode()
    return types.ImageContent(type="image", mime_type=mime, data=data)


def _view_of(response):
    """The recorded frame (crop, scale: the server's, never shown) and the image content."""
    return json.loads(response.headers["x-annotation-view"]), _image_content(response)


def _http_error(exc, out, committed):
    try:
        details = exc.response.json().get("error", {})
    except ValueError:
        details = {}
    code = details.get("code", "api_unavailable")
    if out["save_status"] == "unknown":
        if 400 <= exc.response.status_code < 500:
            # This write was refused; earlier writes of the same call stay saved.
            out["save_status"] = "saved" if committed else "not_attempted"
        else:
            code = "save_failed"
    return ToolError(
        code=code,
        message=details.get("message", "HTTP API rejected the operation"),
        details={"http_status": exc.response.status_code, **details.get("details", {})},
    )


# What to do instead when a call was refused (issue #3 U-07: a refusal said only no).
INSTEAD = {
    "invalid_input": "Fix the arguments as error.details.problems says, then call again",
    "images_writing": "Another record holds those images: wait for it to end (run_wait), or"
    " ask the person to stop it",
    "proposal_withdrawn": "What it was based on changed: make a new proposal from the data"
    " now if it is still wanted",
    "workers_answering": "A worker is answering and may write the plan: decide after it"
    " answers",
    "library_decision": "Hand the request to the reception (answer kind=handoff): making and"
    " deleting datasets are the library's",
    "run_active": "A run of the dataset is going: wait for it to end (run_wait) or propose"
    " stopping it (run_stop)",
    "requirement_mismatch": "The labels changed since that result: use a result of the plan"
    " now (read type dataset), or annotate the image again",
    "not_found": "Read what exists now (read) and name it by its id or name",
}


def instead(tool, code):
    """The next actions of a refused call: the way that is open instead, if there is one."""
    if code == "agent_tool":
        if tool in DECISIONS:
            return [
                (
                    f"Make it ready for the person: proposal_make(tool={tool}, args=…), with"
                    f" {tool}'s own arguments"
                )
            ]
        return ["This worker cannot do it: tell the person, who can"]
    return [INSTEAD[code]] if code in INSTEAD else []


def annotations(name, tool):
    """The MCP hints of a tool, by its kind (issue #3 U-12: a proposal was as destructive as
    deleting a dataset): only reading is read-only and idempotent; a decision that removes,
    stops or overwrites is destructive."""
    return types.ToolAnnotations(
        read_only_hint=tool.kind == "read",
        destructive_hint=tool.kind == "decision" and DECISIONS[name].destructive,
        idempotent_hint=tool.kind == "read",
        open_world_hint=False,
    )


def outside(db, dataset_id, tool, args):
    """A worker of the work screen names only its dataset's images, runs and results
    (authority.references); anything else is refused."""
    named = authority.references(tool, args)
    checks = {
        "image": has_image,
        "run": has_run,
        "result": has_result,
    }
    for kind, values in named.items():
        for value in values:
            if not checks[kind](db, dataset_id, value):
                raise ApiError(
                    403,
                    "agent_scope",
                    f"The {kind} {value} is not of this work's dataset",
                )


def create_mcp_app(owner):
    """The MCP app; owner is the FastAPI app whose HTTP API the tools call."""

    @asynccontextmanager
    async def lifespan(server):
        transport = httpx.ASGITransport(app=owner)
        async with httpx.AsyncClient(
            transport=transport, base_url=config.INSIDE, timeout=None
        ) as http:
            yield http

    async def list_tools(ctx, params):
        # Each caller sees only the tools it may call: a run's worker (told apart by the
        # headers the server gave its CLI) the worker tools, everyone else the AI tools.
        headers = ctx.request.headers if ctx.request is not None else {}
        # A worker of the work screen (step 24) sees only its own tools.
        tools = (
            TOOLS
            if headers.get("X-Annotation-Run-Id")
            else authority.tools_of(authority.caller_of(headers), GENERAL)
        )
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=name,
                    description=tool.description,
                    input_schema=tool.input.model_json_schema(),
                    output_schema=Envelope[dict].model_json_schema(),
                    annotations=annotations(name, tool),
                )
                for name, tool in tools.items()
            ]
        )

    async def call_tool(ctx, params):
        runs = owner.state.runs
        headers = ctx.request.headers if ctx.request is not None else {}
        run_id = headers.get("X-Annotation-Run-Id")
        result_id = headers.get("X-Annotation-Result-Id")
        caller = authority.caller_of(headers)
        forward = (
            {"X-Annotation-Run-Id": run_id, "X-Annotation-Result-Id": result_id}
            if run_id
            else {"X-Actor": "ai"}
        )
        if caller.kind == "agent":
            # What the API should know of the worker: which worker and job made a proposal.
            # The job is the answer going in the worker's chat now (its CLI is the chat's, kept
            # across answers; definition 27.4).
            job = owner.state.jobs.answer_in(caller.agent, caller.chat_id)
            forward.update(
                {
                    "X-Annotation-Agent": caller.agent,
                    "X-Annotation-Dataset": caller.dataset_id or "",
                    "X-Annotation-Job": job or "",
                }
            )
        out = {
            "save_status": "not_attempted",
            "data": None,
            "view": None,
            "whole": None,
        }
        pictures, error, begun = [], None, False
        began = time.monotonic()

        async def request(method, path, allow=(), **kwargs):
            """An HTTP API call; statuses in allow are returned instead of raised."""
            await anyio.lowlevel.checkpoint()
            response = await ctx.lifespan_context.request(
                method, kept_in_place(path), headers=forward, **kwargs
            )
            if response.status_code not in allow:
                response.raise_for_status()
            return response

        committed = []

        async def write(method, path, **kwargs):
            out["save_status"] = "unknown"
            response = await request(method, path, **kwargs)
            out["save_status"] = "saved"
            committed.append(path)
            return response

        async def view(path, body, drawn=()):
            """The image, as the AI is told it; drawn: what is drawn on it (original
            pixels), or an async function of the frame that reads it."""
            frame, picture = _view_of(await request("POST", path, json=body))
            pictures.append(picture)
            objects = await drawn(frame) if callable(drawn) else drawn
            return seen(frame, objects)

        async def picture(path):
            """An image as it is (a sheet): no frame, nothing to give coordinates in."""
            pictures.append(_image_content(await request("GET", path)))

        try:
            if params.name not in TOOLS and params.name not in GENERAL:
                raise ValueError("Unknown tool; call tools/list")
            if run_id and params.name not in TOOLS:
                raise ApiError(403, "run_scope", "Only worker tools inside a run")
            if not run_id and params.name not in GENERAL:
                raise ApiError(
                    403, "run_scope", "These tools are only for a run's worker"
                )
            if not run_id:
                given = params.arguments or {}
                decided = authority.permit(caller, params.name, given)
                if isinstance(decided, authority.Denied):
                    raise ApiError(403, decided.code, decided.message)
                given = decided.args
                if caller.kind == "agent" and decided.dataset_id:
                    db = owner.state.db
                    given = authority.with_image_ids(
                        params.name,
                        given,
                        lambda value: image_id_of(db, decided.dataset_id, value),
                    )
                    outside(db, decided.dataset_id, params.name, given)
                args = GENERAL[params.name].input.model_validate(given)
                limit = tool_time_limit(read_settings(owner.state.db))
                with anyio.fail_after(limit):
                    out["data"], shown = await run_tool(
                        params.name, args, request, write, view, picture
                    )
                out["view"], out["whole"] = (shown + [None, None])[:2]
                raise _Done
            args = TOOLS[params.name].input.model_validate(params.arguments or {})
            await runs.begin_call(run_id, result_id)
            begun = True
            runs.validate_call(run_id, result_id, params.name, args)
            settings = runs.execution(run_id).run["settings"]
            with anyio.fail_after(tool_time_limit(settings)):
                if params.name == "task_get":
                    out["data"] = (
                        await request("GET", f"/v1/results/{args.result_id}/task")
                    ).json()
                    # One image per reference, its example objects drawn, in refs order.
                    out["reference_views"] = [
                        await view(
                            f"/v1/results/{args.result_id}/references/{ref['index']}/views",
                            {},
                            ref["annotations"],
                        )
                        for ref in out["data"]["refs"]
                    ]
                elif params.name == "observe":
                    target = args.target
                    path = (
                        f"/v1/results/{target.result_id}/views"
                        if target.result_id
                        else f"/v1/images/{target.image_id}/views"
                    )
                    body = args.view.model_dump(mode="json", exclude_unset=True)
                    out["view"] = await view(
                        path,
                        body,
                        result_drawn(request, target.result_id)
                        if target.result_id
                        else (),
                    )
                else:
                    out["save_status"] = "unknown"
                    response = await request(
                        "POST",
                        f"/v1/results/{args.result_id}/annotations",
                        # Only what the AI gave: a left-out parent or values are kept.
                        json=args.batch.model_dump(mode="json", exclude_unset=True),
                    )
                    out["save_status"] = "saved"
                    out["data"] = response.json()
                    out["view"], out["whole"] = (
                        await written(
                            view,
                            f"/v1/results/{args.result_id}/views",
                            {
                                **args.view.model_dump(mode="json", exclude_unset=True),
                                "overlay": True,
                                "revision": out["data"]["revision"],
                            },
                            result_drawn(request, args.result_id),
                        )
                        + [None]
                    )[:2]
        except _Done:
            pass
        except ApiError as exc:
            error = ToolError(code=exc.code, message=exc.message, details=exc.details)
        except asyncio.CancelledError:
            if begun:
                await asyncio.shield(
                    runs.end_call(
                        run_id,
                        result_id,
                        params.name,
                        params.arguments or {},
                        {"ok": False, "error": {"code": "cancelled"}},
                        (time.monotonic() - began) * 1000,
                    )
                )
            raise
        except ValidationError as exc:
            error = ToolError(
                code="invalid_input"
                if out["save_status"] == "not_attempted"
                else "internal_error",
                message="Request or API response does not match its schema",
                details={
                    "issues": [
                        {
                            "location": list(e["loc"]),
                            "type": e["type"],
                            "message": e["msg"],
                        }
                        for e in exc.errors()
                    ]
                },
            )
        except httpx.HTTPStatusError as exc:
            error = _http_error(exc, out, committed)
        except TimeoutError:
            error = ToolError(
                code="timeout",
                message="Operation exceeded its time limit; check saved state before retrying a write",
            )
        except ValueError as exc:
            error = ToolError(code="invalid_input", message=str(exc))
        except Exception:
            logger.exception("MCP operation failed")
            error = ToolError(
                code="internal_error",
                message="Operation failed; check saved state before retrying a write",
            )
        if (
            error
            and out["save_status"] == "saved"
            and params.name == "save_and_observe"
        ):
            error = ToolError(
                code="render_failed",
                message="Saved, but the overlay was not returned; call observe instead of resending",
                details={"cause": error.model_dump()},
            )
        actions = (NEXT if run_id else GENERAL_NEXT).get(params.name, [])
        if error is not None and out["save_status"] != "unknown":
            actions = instead(params.name, error.code) or actions
        if out["save_status"] == "unknown":
            actions = ["Observe your result before retrying; never blindly resend"]
        # Original pixels never reach the AI: coordinates come only with an image (definition
        # 29.1).
        out["data"] = without_geometry(out["data"])
        structured = Envelope[dict](
            ok=error is None, error=error, next_actions=actions, **out
        ).model_dump(mode="json")
        content = [
            types.TextContent(
                type="text", text=json.dumps(structured, ensure_ascii=False)
            )
        ]
        content.extend(pictures)
        if begun:
            await runs.end_call(
                run_id,
                result_id,
                params.name,
                params.arguments or {},
                structured,
                (time.monotonic() - began) * 1000,
            )
        return types.CallToolResult(
            content=content, structured_content=structured, is_error=error is not None
        )

    server = Server(
        "agent-app",
        version="1",
        instructions=INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        lifespan=lifespan,
        cache_hints={
            "server/discover": CacheHint(ttl_ms=300000, scope="public"),
            "tools/list": CacheHint(ttl_ms=300000, scope="private"),
        },
    )
    return server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=False,
        max_request_body_size=MCP_BODY_LIMIT,
    )

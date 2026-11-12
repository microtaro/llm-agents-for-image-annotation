"""Codex and Claude Code for runs: usable models, Codex arguments and the worker prompt.

Copied from annotation_server/codex_execution.py; running one image is inference.py.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from string import Template

import tomllib

from .claude_execution import WORKER_TOOLS
from .config import base_url
from .errors import ApiError
from .model_catalog import (
    API_PRICE_VERSION,
    CLAUDE_MODELS,
    CLAUDE_PRICE_VERSION,
    claude_models,
    codex_models,
)
from .run_queries import SUCCESS
from .run_schemas import RunModels as ExecutionModels
from .run_schemas import RunSettings as ExecutionSettings
from .settings import tool_time_limit

# The run's own time limit (app setting) is enforced by runs.py; these later backstops only
# fire if that cancellation fails, so a limit reached always reports the run's own value.
BACKSTOP_SECONDS = 10


def execution_settings():
    """Only publish explicit invocation values; never expose the full user config."""
    values = {"api_price_version": API_PRICE_VERSION}
    missing = {}
    path = (
        Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
    )
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
        profile = config.get("profiles", {}).get(config.get("profile"), {})
        for public, key in (
            ("model", "model"),
            ("effort", "model_reasoning_effort"),
            ("tier", "service_tier"),
        ):
            value = profile.get(key, config.get(key))
            if isinstance(value, str) and value:
                values[public] = value
            else:
                missing[public] = (
                    "No explicit value in the invocation configuration; CLI default is unknown"
                )
    except (OSError, ValueError):
        missing.update(
            {
                k: "Invocation configuration could not be read"
                for k in ("model", "effort", "tier")
            }
        )
    try:
        result = subprocess.run(
            [shutil.which("codex") or "codex", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        version = result.stdout.strip()
        if not re.fullmatch(r"codex-cli [A-Za-z0-9.+_-]+", version):
            raise ValueError("Unrecognized version output")
        values["cli_version"] = version
    except (OSError, ValueError, subprocess.SubprocessError):
        missing["cli_version"] = "Installed CLI version could not be obtained"
    return ExecutionSettings(**values, missing_reasons=missing).model_dump(mode="json")


def cli_status():
    """Which agent CLIs this server can use: missing, signed_out or ok.

    Codex reports its sign-in state; Claude Code is checked by presence only. An expired
    session can still pass here and is reported by the run (see runs.AUTH_HINTS).
    """
    status = {"claude": "ok" if shutil.which("claude") else "missing"}
    codex = shutil.which("codex")
    if codex is None:
        status["codex"] = "missing"
    else:
        try:
            result = subprocess.run(
                [codex, "login", "status"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            status["codex"] = "ok" if result.returncode == 0 else "signed_out"
        except (OSError, subprocess.SubprocessError):
            status["codex"] = "signed_out"
    return status


def execution_models():
    """Models of the CLIs that are usable here; the first one is the default."""
    status = cli_status()
    models = []
    # Opus first: so far the cheapest accurate choice in our runs (2026-09-27).
    if status["claude"] == "ok":
        models.extend(claude_models())
    if status["codex"] == "ok":
        models.extend(codex_models())
    defaults = execution_settings()
    if models:
        defaults.update(model=models[0]["model"], effort=models[0]["default_effort"])
    return ExecutionModels(
        defaults=defaults,
        models=models,
        clis=status,
        unavailable_reason=None
        if models
        else "No usable AI CLI: install and sign in to Codex CLI or Claude Code",
    ).model_dump(mode="json")


def effort_for(model, effort=None, option=None):
    """The effort a run of the model uses: the one chosen, else medium when the model has it,
    else its own default (user 2026-10-05: the catalog's low for Sol was not chosen). A box and
    the run take it from here, so what a box shows is what runs (definition 11.4)."""
    if effort is not None:
        return effort
    if option is None:
        option = model_option(model)
    if option is None:
        return None
    return "medium" if "medium" in option["efforts"] else option["default_effort"]


def catalog_models():
    """Every model of the catalog, whichever CLI is signed in now."""
    return [*claude_models(), *codex_models()]


def model_option(model):
    """A model of the catalog by its id; none for another name (a display name such as
    "GPT-6.1-Sol" is not an id)."""
    return next((m for m in catalog_models() if m["model"] == model), None)


def check_choice(option, effort, tier, models):
    """A run's model, effort and speed as the catalog offers them (option: the model's entry,
    none when it has none). The same when a run starts and when a decision to run is made
    (review 2026-10-28 C#9: a decision naming the model by its display name was taken, and
    failed only once decided)."""
    if option is None:
        raise ApiError(
            422,
            "invalid_model",
            "Choose one of the available models",
            {"models": models},
        )
    if tier is not None and tier not in [s["id"] for s in option.get("speeds", [])]:
        raise ApiError(422, "invalid_tier", "Choose a speed the selected model offers")
    if effort not in option["efforts"]:
        raise ApiError(
            422, "invalid_effort", "Choose an effort the selected model supports"
        )


def selected_execution_settings(model=None, effort=None, tier=None):
    """The run's model, effort and speed: medium unless asked otherwise (user 2026-10-05: the
    catalog's low for Sol was not chosen), standard speed unless a faster tier is asked."""
    catalog = execution_models()
    if not catalog["models"]:
        raise ApiError(
            422,
            "no_ai_cli",
            "No usable AI CLI: install and sign in to Codex CLI or Claude Code",
            {"clis": catalog["clis"]},
        )
    settings = catalog["defaults"]
    selected_model = model if model is not None else catalog["models"][0]["model"]
    option = next((m for m in catalog["models"] if m["model"] == selected_model), None)
    selected_effort = effort_for(selected_model, effort, option)
    check_choice(option, selected_effort, tier, [m["model"] for m in catalog["models"]])
    settings.update(model=selected_model, effort=selected_effort)
    if tier is not None:
        settings.update(tier=tier)
        settings["missing_reasons"].pop("tier", None)
    if selected_model in CLAUDE_MODELS:
        settings.update(
            tier=tier or "standard",
            method="claude_code_annotation_mcp",
            api_price_version=CLAUDE_PRICE_VERSION,
        )
        settings["missing_reasons"].pop("tier", None)
        try:
            version = subprocess.run(
                [shutil.which("claude"), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            settings["cli_version"] = version.stdout.strip()
            settings["missing_reasons"].pop("cli_version", None)
        except (OSError, subprocess.SubprocessError):
            settings["cli_version"] = None
            settings["missing_reasons"]["cli_version"] = (
                "Claude Code version unavailable"
            )
    for key in ("model", "effort"):
        settings["missing_reasons"].pop(key, None)
    return settings


def codex_executable():
    executable = shutil.which("codex")
    if executable is None:
        raise RuntimeError(
            "Codex CLI was not found; start the server on a host where it is signed in."
        )
    return executable


def codex_argv(directory, **given):
    """One turn of codex exec: its answer in directory/result.json, by schema.json."""
    return [
        codex_executable(),
        "exec",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--ephemeral",
        "--json",
        *codex_flags(**given),
        "--output-schema",
        str(directory / "schema.json"),
        "--output-last-message",
        str(directory / "result.json"),
        "-",
    ]


def codex_flags(
    *,
    run_id=None,
    result_id=None,
    settings=None,
    tools=None,
    headers=None,
    mcp=True,
):
    """What Codex may do, the same for codex exec and a worker kept running (codex app-server,
    residents.py). tools and headers: for a caller that is not a run's worker (a worker's
    answer). mcp=False: no tools at all (the LLM judge of text answers reads only its prompt)."""
    argv = ["-c", 'approval_policy="never"']
    for feature in (
        "shell_tool",
        "unified_exec",
        "apps",
        "plugins",
        "hooks",
        "browser_use",
        "browser_use_external",
        "computer_use",
        "multi_agent",
        "multi_agent_v2",
        "memories",
        "code_mode",
        "image_generation",
        "view_image",
        "goals",
        "skill_search",
        "unbounded_connection_retries",
    ):
        argv.extend(["--disable", feature])
    argv.extend(["-c", 'web_search="disabled"'])
    for public, key in (
        ("model", "model"),
        ("effort", "model_reasoning_effort"),
        ("tier", "service_tier"),
    ):
        if settings and settings.get(public) is not None:
            argv.extend(["-c", key + "=" + json.dumps(settings[public])])
    config = (
        Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
    )
    if config.exists():
        for name in tomllib.loads(config.read_text(encoding="utf-8")).get(
            "mcp_servers", {}
        ):
            if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
                raise ValueError(
                    "Codex is not started: an MCP server name cannot be disabled safely."
                )
            argv.extend(["-c", f"mcp_servers.{name}.enabled=false"])
    argv.extend(["--enable", "code_mode_host"])
    allowed = list(tools or WORKER_TOOLS)
    settings = {
        "mcp_servers.annotation_execution.url": base_url() + "/mcp",
        "mcp_servers.annotation_execution.enabled": True,
        "mcp_servers.annotation_execution.required": True,
        "mcp_servers.annotation_execution.startup_timeout_sec": 10,
        # Wait past the server's own tool limit so its timeout error reaches the agent.
        "mcp_servers.annotation_execution.tool_timeout_sec": tool_time_limit(
            settings or {}
        )
        + 5,
        "mcp_servers.annotation_execution.default_tools_approval_mode": "approve",
        "mcp_servers.annotation_execution.enabled_tools": allowed,
        "mcp_servers.annotation_execution.http_headers": headers
        or {
            "X-Annotation-Run-Id": run_id,
            "X-Annotation-Result-Id": result_id,
        },
        "project_doc_max_bytes": 0,
    }
    if not mcp:
        settings = {"project_doc_max_bytes": 0}
    for key, value in settings.items():
        # TOML inline tables use equals rather than JSON's colon.
        toml = (
            (
                "{"
                + ",".join(
                    json.dumps(k) + "=" + json.dumps(v) for k, v in value.items()
                )
                + "}"
            )
            if isinstance(value, dict)
            else json.dumps(value)
        )
        argv.extend(["-c", key + "=" + toml])
    return argv


def output_schema():
    # Whether the image was searched comes first, apart from what was found (user 2026-10-16:
    # a worker that did not annotate could only answer not_detected, counted as done; "worked"
    # read as "saved something", wrong for an image with nothing in it).
    properties = {
        "searched": {
            "type": "boolean",
            "description": "true when you searched the target image for the labels' instances in order to annotate them, whatever you found (nothing found is true, with status=not_detected). false when you did not search the image for them (for example you stopped before looking at it), or when you decided not to annotate it even if you looked at it.",
        },
        "not_searched_reason": {
            "type": "string",
            "description": "Why you did not search or annotate the image, when searched is false; empty when searched is true.",
        },
        "status": {"type": "string", "enum": list(SUCCESS)},
        "view_id": {"type": "string"},
        "explanation": {"type": "string"},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


# Every worker prompt: YAML text, one rule per line, so git shows which rule changed. The run's settings are
# filled in, and a run records the filled text and its hash.
WORKER_PROMPT = Template(
    (Path(__file__).parent / "worker_prompt.yaml").read_text(encoding="utf-8")
)


def worker_prompt(settings):
    """The fixed protocol the server checks runs against, then the user's shared advice."""
    prompt = WORKER_PROMPT.substitute(settings)
    extra = (settings.get("worker_extra_instructions") or "").strip()
    if not extra:
        return prompt
    # A YAML block scalar keeps the advice as written, whatever it contains.
    block = "\n".join(
        f"  {line}" if line.strip() else "" for line in extra.splitlines()
    )
    return f"{prompt}additional_instructions: |\n{block}\n"


def inference_prompt(run, result_id):
    return (
        run["worker_prompt"]
        + f"identifiers:\n  run_id: {run['id']}\n  result_id: {result_id}\n"
    )

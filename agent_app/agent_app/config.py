"""Where the port and the app's files come from: this project's fixed port
(.claude/project.config.json), or, in a folder given to someone, which has none, the one its
server found free (given_socket); and the software's version (pyproject.toml, the one place it
is written)."""

import json
import socket
from functools import cache
from pathlib import Path

import tomllib

from .system import REUSE_ADDRESS

PACKAGE = Path(__file__).resolve().parent
APP = PACKAGE.parent
REPO = APP.parent
UI_DIST = APP / "ui" / "dist"
# Read from the file, not an installed package's facts: the zip's Windows Python runs the app
# from its folder, installed nowhere (2026-10-30).
VERSION = tomllib.loads((APP / "pyproject.toml").read_text(encoding="utf-8"))[
    "project"
]["version"]


# The port the app given to someone as a zip tries first, on every start (user 2026-10-28): apart
# from this project's own (3110, the copy's 4110), so trying a zip on this machine meets neither.
# When something else has it, the next free one (user 2026-11-04).
PORT_GIVEN = 3900
PORTS_TRIED = 100
# The port its server found free: the launcher and its workers read it here.
PORT_FILE = APP / "server.port"


def given():
    """The app given to someone, as a zip (user 2026-10-28) or a clone of its public repository:
    it has no project file. It listens on a port it finds free (given_socket), runs with no
    window (its log in LOG) and is quit from its screen."""
    return not (REPO / ".claude/project.config.json").is_file()


# The given app's log: its start runs it with no window (user 2026-10-29).
LOG = APP / "server.log"


@cache
def _project_port():
    # Read once: the server keeps the port it started on, and its workers are sent to that
    # same server (found 2026-10-09: the copy on 4110 had its file put back to 110 while it
    # ran, and its workers wrote to the old app's server on 3110).
    project = REPO / ".claude/project.config.json"
    return 3000 + int(json.loads(project.read_text(encoding="utf-8"))["portSuffix"])


def server_port():
    if not given():
        return _project_port()
    # Not written yet, or being written: the one it tries first. One left by an earlier run is
    # only asked, and answers as someone else or not at all (launch.running).
    try:
        return int(PORT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return PORT_GIVEN


def given_socket():
    """The given app's server's socket, on PORT_GIVEN or else the next free port, written down
    for the launcher and the workers. Bound here and handed to the server, so nothing can take
    the port in between."""
    for port in range(PORT_GIVEN, PORT_GIVEN + PORTS_TRIED):
        held = socket.socket()
        if REUSE_ADDRESS:
            held.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            held.bind(("127.0.0.1", port))
        except OSError:
            held.close()
            continue
        PORT_FILE.write_text(str(port), encoding="utf-8")
        return held
    raise OSError(f"no free port from {PORT_GIVEN} to {PORT_GIVEN + PORTS_TRIED - 1}")


def base_url():
    return f"http://127.0.0.1:{server_port()}"


# The app calling its own API in the same process (a tool, a decision carried out): no port, as
# no socket is used; this machine's name, as the app answers no other (app.OnlyThisMachine).
INSIDE = "http://127.0.0.1"

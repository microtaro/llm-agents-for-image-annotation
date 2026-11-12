import os
import socket
import subprocess
import sys
import time

import httpx
from agent_app.config import VERSION

from agent_app import settings

# The server __main__ starts, with each connection left counted when it closes, as Windows'
# asyncio left one (2026-10-30: it raised closing a connection a client had cut).
LEFT_COUNTED = """
import asyncio.base_events, sys
Server = asyncio.base_events.Server
kept, attach = [], Server._attach
Server._attach = lambda self, transport: (kept.append(transport), attach(self, transport))
Server._detach = lambda self, transport: None
import agent_app.__main__ as main
main.server_port = lambda: int(sys.argv[1])
main.given = lambda: False  # on this port, in a clone too (it finds its own otherwise)
main.serve()
"""


def test_every_setting_is_shown_in_one_group_with_the_version(client):
    # 2026-10-29: the settings screen shows its groups in the server's order; a setting in no
    # group would not be shown. A model's effort is shown with its model.
    shown = [key for _, keys in settings.GROUPS for key in keys]
    expected = [key for key in settings.ITEMS if not key.endswith("_effort")]
    assert sorted(shown) == sorted(expected)
    body = client.get("/v1/settings").json()
    assert body["groups"] == settings.GROUPS
    assert body["machine"]["version"] == VERSION


def test_a_new_database_needs_only_claude(client):
    # 2026-11-06: only the zip set its models; a clone, on a new database, asked Codex for the
    # workers' answers and Claude for the runs.
    said = client.get("/v1/settings").json()
    assert said["agent_model"] == said["run_model"] == "claude-opus-5-5"


def test_the_app_quits_from_its_screen_when_started_to(client):
    # 2026-10-29: the screen's power sign quits the server __main__ started (the zip's, which
    # runs with no window, and the work's own alike); a server started otherwise has no quit.
    refused = client.post("/v1/quit")
    assert (refused.status_code, refused.json()["error"]["code"]) == (
        409,
        "quit_not_here",
    )
    quits = []
    client.app.state.quit = lambda: quits.append(True)
    assert client.get("/health").status_code == 200
    assert client.post("/v1/quit").status_code == 202
    # Not up once told to quit (2026-10-30: the app's window stayed while the server ended).
    assert client.get("/health").status_code == 503


def test_the_app_quits_with_a_connection_never_counted_out(tmp_path):
    # 2026-10-30: the zip's server, quit from its screen, waited for such a connection forever,
    # with no window, holding its folder against deleting it.
    with socket.socket() as free:
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
    server = subprocess.Popen(
        [sys.executable, "-c", LEFT_COUNTED, str(port)],
        env={**os.environ, "AGENT_APP_DB": str(tmp_path / "agent.db")},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        url = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                httpx.get(f"{url}/health", timeout=1).raise_for_status()
                break
            except httpx.HTTPError:
                time.sleep(0.1)
        assert httpx.post(f"{url}/v1/quit", json={}).status_code == 202
        server.wait(timeout=15)
    finally:
        server.kill()
        server.wait()

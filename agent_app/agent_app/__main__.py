"""Fixed-port, single-process startup (no reload: a reload would cut runs in progress)."""

import faulthandler
import logging
import os
import sys

import uvicorn

from .app import create_app
from .config import LOG, given, given_socket, server_port


def serve():
    if given():
        # No window shows it (the zip's start runs it hidden): what it says goes to its file,
        # open as long as the server is.
        sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    # A crash outside Python (an image library's C code, a Windows exception) writes where it
    # was, to the log in the zip's app (2026-11-02: an app went away and its log said nothing).
    faulthandler.enable()
    logging.basicConfig(level=logging.INFO)
    try:
        sockets = [given_socket()] if given() else None
        port = server_port()
        if not given() and int(os.environ.get("PORT", port)) != port:
            raise ValueError("PORT must match the configured fixed backend port")
    except (OSError, KeyError, ValueError) as exc:
        logging.getLogger("agent_app").error("Cannot start agent-app: %s", exc)
        raise SystemExit(1) from exc
    if sockets:
        # uvicorn says its address only when it binds the port itself.
        logging.getLogger("agent_app").info("Listening on 127.0.0.1:%s", port)
    # Request access logs only with DEBUG=1 (AGENTS.md); startup and errors always go out.
    app = create_app()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            workers=1,
            reload=False,
            access_log=os.environ.get("DEBUG") == "1",
            # Quitting waits for the connections to close this long at most, then the runs and
            # the workers end (2026-10-30: on Windows asyncio raised closing a connection a
            # client had cut and never counted it out; the server quit from its screen waited
            # for it forever, unseen, holding the zip's folder).
            timeout_graceful_shutdown=3,
        )
    )
    # Its screen's quit ends it as Ctrl+C does: the runs and the workers' CLIs end with it
    # (npm run dev ends the screen's server with it, scripts/dev.cjs).
    app.state.quit = lambda: setattr(server, "should_exit", True)
    server.run(sockets=sockets)


if __name__ == "__main__":
    serve()

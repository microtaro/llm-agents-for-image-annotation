import socket
import sys

import pytest
from agent_app.config import APP
from agent_app.system import hold_file

from agent_app import config, launch


@pytest.fixture(autouse=True)
def _a_lock_of_its_own(tmp_path, monkeypatch):
    monkeypatch.setattr(launch, "LOCK", tmp_path / "launcher.lock")
    # Run from a clone on Windows (its .venv's python.exe), open_app would make the real
    # shortcut in that clone, through these tests' own Popen (2026-11-11).
    monkeypatch.setattr(launch, "SHORTCUT", tmp_path / "Annotation.lnk")
    monkeypatch.setattr(launch, "make_shortcut", lambda *args: None)


def _free_pair():
    """A port whose next one is free too."""
    while True:
        with socket.socket() as first:
            first.bind(("127.0.0.1", 0))
            port = first.getsockname()[1]
        with socket.socket() as second:
            try:
                second.bind(("127.0.0.1", port + 1))
            except OSError:
                continue
        return port


def _given(tmp_path, monkeypatch, port):
    monkeypatch.setattr(config, "given", lambda: True)
    monkeypatch.setattr(config, "PORT_FILE", tmp_path / "server.port")
    monkeypatch.setattr(config, "PORT_GIVEN", port)


def test_the_launcher_keeps_one_window(monkeypatch):
    # 2026-10-29: the zip's shortcut runs the launcher with no console. This folder's app
    # running already gets the window too (it showed none, and the app ran with nothing in
    # view); a second launch while a window shows opens the browser only.
    windows, opened = [], []
    monkeypatch.setattr(launch, "app_browser", lambda: None)
    monkeypatch.setattr(launch, "window", windows.append)
    monkeypatch.setattr(launch.webbrowser, "open", opened.append)
    monkeypatch.setattr(launch, "running", lambda: {"app": "agent-app"})
    assert launch.open_app() == 0
    assert windows == [None]
    hold = hold_file(launch.LOCK)
    try:
        assert launch.open_app() == 0
        assert windows == [None] and opened
    finally:
        hold.close()


def test_only_its_own_lock_stops_the_launcher_starting_the_app(monkeypatch):
    # 2026-11-04: with the port next to the app's in another program's hands, the launcher took
    # it for a window already showing and ended without a word, nothing started. It holds no
    # port now, and only its own folder's lock stops it.
    windows, started = [], []
    monkeypatch.setattr(launch, "app_browser", lambda: None)
    monkeypatch.setattr(launch, "window", windows.append)
    monkeypatch.setattr(launch, "running", lambda: None)
    monkeypatch.setattr(
        launch.subprocess, "Popen", lambda argv, **_: started.append(argv) or "server"
    )
    assert launch.open_app() == 0
    assert windows == ["server"] and started[0][1:] == ["-m", "agent_app"]
    # Pressed twice while it starts: the first one will show it, the second starts nothing.
    hold = hold_file(launch.LOCK)
    try:
        assert launch.open_app() == 0
        assert len(started) == 1
    finally:
        hold.close()


def test_a_server_failing_as_it_reads_its_modules_leaves_why_in_its_log(
    tmp_path, monkeypatch
):
    # 2026-11-04: its output was thrown away, and it opens its log only once its modules are
    # read: it stopped, the launcher said to send the log, and the log said nothing.
    package = tmp_path / "agent_app"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(
        'raise ImportError("部品が読めません")', encoding="utf-8"
    )
    log = tmp_path / "server.log"
    monkeypatch.setattr(launch, "APP", tmp_path)
    monkeypatch.setattr(launch, "LOG", log)
    monkeypatch.setattr(launch, "app_browser", lambda: None)
    monkeypatch.setattr(launch, "running", lambda: None)
    monkeypatch.setattr(launch, "window", lambda server: server.wait(timeout=60))
    assert launch.open_app() == 0
    assert "部品が読めません" in log.read_text(encoding="utf-8")


def test_with_no_display_a_server_that_ended_is_said_at_once(monkeypatch):
    # 2026-11-04: with no display to show the small window on, the launcher waited its five
    # minutes for a server that had already failed, and ended without a word.
    said = []

    class Ended:
        def poll(self):
            return 1

    monkeypatch.setitem(sys.modules, "tkinter", None)
    monkeypatch.setattr(launch, "running", lambda: None)
    monkeypatch.setattr(launch, "tell", said.append)
    launch.window(Ended())
    assert said and said[0].startswith(launch.launcher_words()["failed"])


def test_only_this_folders_app_counts_as_running(monkeypatch):
    # 2026-11-04: the port written down may be someone else's by the next start.
    answers = [
        {"app": "agent-app", "folder": str(APP)},
        {"app": "agent-app", "folder": "/another/agent_app"},
        {"app": "something else"},
        ["not", "ours"],
        None,
    ]
    monkeypatch.setattr(launch, "ask_app", lambda path: answers.pop(0))
    assert launch.running() == {"app": "agent-app", "folder": str(APP)}
    assert [launch.running() for _ in answers.copy()] == [None] * 4


def test_the_given_app_tries_its_port_first_then_the_next_free_one(
    tmp_path, monkeypatch
):
    # User 2026-11-04: 3900 first, another only when it is not free; every start from 3900 again.
    port = _free_pair()
    _given(tmp_path, monkeypatch, port)
    assert config.server_port() == port  # nothing written yet
    first = config.given_socket()
    assert first.getsockname()[1] == port and config.server_port() == port
    first.listen()
    second = config.given_socket()
    assert second.getsockname()[1] == port + 1
    assert config.base_url() == f"http://127.0.0.1:{port + 1}"
    second.close()
    first.close()
    third = config.given_socket()
    assert third.getsockname()[1] == port and config.server_port() == port
    third.close()


def test_a_port_its_server_closed_a_moment_ago_is_used_again(tmp_path, monkeypatch):
    # 2026-10-29: right after the app quit, the port was taken for another program's (the
    # server's closed connections wait out TIME_WAIT on its port, which the server's own bind
    # takes no notice of).
    port = _free_pair()
    _given(tmp_path, monkeypatch, port)
    server = config.given_socket()
    server.listen()
    client = socket.create_connection(("127.0.0.1", port))
    accepted, _ = server.accept()
    accepted.close()
    client.close()
    server.close()
    again = config.given_socket()
    assert again.getsockname()[1] == port
    again.close()


def test_closing_the_app_window_quits_the_app(monkeypatch):
    # 2026-10-30 (user: one thing on the taskbar, and closing it ends the app even mid-work):
    # with Chrome or Edge, the app opens in its own window, no small window, and the app quits
    # when that window closes.
    opened, asked, windows = [], [], []
    monkeypatch.setattr(launch, "app_browser", lambda: "browser.exe")
    monkeypatch.setattr(
        launch, "running", lambda: {"app": "agent-app", "folder": str(APP)}
    )
    monkeypatch.setattr(launch, "window", windows.append)

    class Closed:
        returncode = 0

        def poll(self):
            return 0

    def popen(argv, **_):
        opened.append(argv)
        return Closed()

    monkeypatch.setattr(launch.subprocess, "Popen", popen)
    monkeypatch.setattr(
        launch, "ask_app", lambda path, body=None: asked.append(path) or {}
    )
    said = []
    monkeypatch.setattr(launch, "tell", said.append)
    assert launch.open_app() == 0
    assert opened[0][0] == "browser.exe" and opened[0][1].startswith("--app=")
    assert asked == ["/v1/quit"] and windows == [] and said == []


def test_the_app_window_opens_large_in_the_middle(monkeypatch):
    # 2026-10-30: opened at the browser's own small size, the screen put the talk above the
    # right (it does under 1000 px); a laptop's 1366 x 728 room gives 1229 wide.
    opened = []
    monkeypatch.setattr(launch, "work_area", lambda: (0, 0, 1366, 728))
    monkeypatch.setattr(
        launch.subprocess, "Popen", lambda argv, **_: opened.append(argv)
    )
    launch.app_window("browser.exe", "http://127.0.0.1:3900/")
    assert "--window-size=1229,655" in opened[0]
    assert "--window-position=68,36" in opened[0]


def test_the_app_quit_from_its_screen_closes_its_window(monkeypatch):
    # 2026-10-30 (user): quit with the screen's power sign, the app's window stayed open.
    answers, closed = [{"app": "agent-app", "folder": str(APP)}, None], []

    class Shown:
        def poll(self):
            return None

        def wait(self, timeout):
            return 0

    monkeypatch.setattr(launch, "running", lambda: answers.pop(0))
    monkeypatch.setattr(launch, "app_window", lambda browser, url: Shown())
    monkeypatch.setattr(launch, "close_windows", closed.append)
    launch.in_app_window("browser.exe", None, {})
    assert len(closed) == 1


def test_the_app_going_away_on_its_own_is_said(tmp_path, monkeypatch):
    # 2026-10-30: on a 16 GB machine the app went away without a word; the launcher took any
    # end of its server, and any late answer, for a quit from the screen.
    said, closed, windows, answers = [], [], [], []
    words = launch.WORDS["en"]
    monkeypatch.setattr(launch, "close_windows", closed.append)
    monkeypatch.setattr(launch, "tell", said.append)
    monkeypatch.setattr(launch, "ask_app", lambda path, body=None: {})
    monkeypatch.setattr(launch.time, "sleep", lambda seconds: None)
    # How it ended, written in the app's log too (2026-11-02: its code shown, and kept).
    monkeypatch.setattr(launch, "LOG", tmp_path / "server.log")
    # Up when its window opens, then answering no more (too busy to, or gone).
    monkeypatch.setattr(launch, "running", lambda: answers.pop(0) if answers else None)
    monkeypatch.setattr(launch, "app_window", lambda browser, url: windows.pop(0))

    class Process:
        def __init__(self, *polls):
            self.polls, self.returncode = list(polls), polls[-1]

        def poll(self):
            return self.polls.pop(0)

        def wait(self, timeout):
            return self.returncode

    def run(window, server):
        said.clear()
        closed.clear()
        answers.append({"app": "agent-app"})
        windows.append(window)
        launch.in_app_window("browser.exe", server, words)

    # Not answering but running: the window stays; then it stopped on its own (not 0).
    window = Process(None, None, None, 0)
    run(window, Process(None, None, 1))
    assert closed == [window] and said[0].startswith(words["stopped"].format(code="1"))
    # Quit from its screen: it ends with 0, its window closes, nothing is said.
    run(Process(None, None, 0), Process(None, 0))
    assert len(closed) == 1 and said == []
    # Its window going away on its own (crashed, killed): the app is quit, and that is said.
    run(Process(-1), Process(None))
    gone = words["window_gone"].format(code="0xFFFFFFFF")
    assert said == [f"{gone}\n{words['open_again']}"]
    log = (tmp_path / "server.log").read_text(encoding="utf-8")
    assert "the server ended on its own, exit code 1" in log
    assert "the app window ended on its own, exit code 0xFFFFFFFF" in log


def test_shortcut_only_from_a_clone(tmp_path):
    """The shortcut is made at a start from a clone (the .venv's python.exe or pythonw.exe) and
    opens its pythonw.exe; not from the zip's Python (2026-11-11)."""
    app = tmp_path / "agent_app"
    scripts = app / ".venv" / "Scripts"
    for started in ("python.exe", "pythonw.exe"):
        assert launch.shortcut_target(scripts / started, app) == scripts / "pythonw.exe"
    zipped = tmp_path / "python-windows" / "pythonw.exe"
    assert launch.shortcut_target(zipped, app) is None

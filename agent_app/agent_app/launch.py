"""Start the app and keep a small window while it runs: what the zip's start runs
(Annotation.exe on Windows, start.sh elsewhere; user 2026-10-29: a shortcut through the classic
console was refused on another machine, and a Windows Terminal set never to close kept start's
tab; then "users always get it wrong": an app running with nothing in view held its folder
against deleting it). The server starts apart (its log in config.LOG) unless this folder's runs
already; it finds its port itself (config.given_socket), so another folder's app or another
program on a port is not this launcher's concern.

The window comes first, minimized, so its sign is on the taskbar from the start (user
2026-10-29: on a first start no sign came, and nothing was said; the server's first start can
be slow, and the launcher with no console ended without a word). It says the app is starting,
then running (the browser opens), or that it did not start (shown, with the log). Closing it,
or its Quit, quits the app (as a desktop app's window does); the screen's power sign quits it
too, and the window then closes. One launcher at a time (it holds a lock, LOCK): opened again,
the launcher opens the browser only.

On Windows the app opens in a window of its own, Chrome's or Edge's (user 2026-10-30: one thing
on the taskbar with the app's mark, not the browser and a small window apart): no small window;
closing the app's window quits the app, work going or not; opened again, another app window.
From a clone on Windows (start.cmd), it also makes the shortcut "Annotation" in the folder, the
start by double-click there (source_shortcut).

python -m agent_app.launch
"""

import json
import locale
import os
import subprocess
import sys
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

from .config import APP, LOG, PACKAGE, REPO, base_url
from .system import (
    APART,
    WINDOWS,
    app_browser,
    close_windows,
    console_python,
    hold_file,
    make_shortcut,
    tell,
    work_area,
)

# How long a start may take before it is said not to have started (a first start, every module
# read for the first time under a virus scanner, was slow on another machine).
START_SECONDS = 300
LOCK = APP / "launcher.lock"
# The start by double-click from a clone on Windows (shortcut_target).
SHORTCUT = REPO / "Annotation.lnk"

# The window's and the messages' words, by the machine's language (the screen's own choice is
# the browser's, out of reach here).
WORDS = {
    "ja": {
        "starting": "Annotation を起こしています…",
        "starting_note": "初めての時は、数分かかる事があります。",
        "running": "Annotation は動いています。",
        "close": "画面はブラウザで使います。この窓を閉じると、アプリが終了します。",
        "open": "ブラウザで開く",
        "quit": "終了",
        "going": "動いている AI のアノテーションと係の答え {count}件も止まります。終了しますか？",
        "failed": "アプリが起きませんでした。",
        "failed_note": "{log} を、このアプリの作者に送ってください。",
        "stopped": "アプリが途中で止まりました（終了コード {code}）。",
        "window_gone": "アプリの窓が途中で閉じたので、アプリを終了しました（終了コード {code}）。",
        "open_again": "もう一度開いてください。",
        "broken": "起動役が止まりました。{log} を、このアプリの作者に送ってください。",
    },
    "en": {
        "starting": "Starting Annotation…",
        "starting_note": "The first start can take a few minutes.",
        "running": "Annotation is running.",
        "close": "Its screen is in the browser. Closing this window quits the app.",
        "open": "Open in the browser",
        "quit": "Quit",
        "going": "{count} AI annotations and workers' answers going stop too. Quit?",
        "failed": "The app did not start.",
        "failed_note": "Please send {log} to this app's author.",
        "stopped": "The app stopped unexpectedly (exit code {code}).",
        "window_gone": "The app's window closed unexpectedly (exit code {code}), so the app was quit.",
        "open_again": "Please open it again.",
        "broken": "The launcher stopped. Please send {log} to this app's author.",
    },
}


def launcher_words():
    language = (locale.getlocale()[0] or "").lower()
    return WORDS["ja" if language.startswith(("ja", "japanese")) else "en"]


def ask_app(path, body=None):
    """The app's answer as JSON, or None when it does not answer."""
    request = urllib.request.Request(
        base_url() + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as answer:
            return json.loads(answer.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def app_url():
    """Asked when it is wanted: a server just started writes the port it found."""
    return base_url() + "/"


def running():
    """This folder's app's health, or None (the port written down may be another program's or
    another folder's app's by now)."""
    there = ask_app("/health")
    if (
        isinstance(there, dict)
        and there.get("app") == "agent-app"
        and Path(there["folder"]).resolve() == APP.resolve()
    ):
        return there
    return None


def server_ended(server):
    """The app's server has ended. The one started here is looked at as a process, not by its
    answer: it may be too busy to answer (2026-10-30: on a machine short of memory, a late answer
    taken for its end could close the window on a server still running). One not started here
    has ended when it answers no more (quitting, it answers 503)."""
    return running() is None if server is None else server.poll() is not None


def stopped_on_its_own(server):
    """It ended without being asked (2026-10-30: on a 16 GB machine the app went away without a
    word): every quit (its screen's power sign, its window closing, the small window's Quit)
    goes through /v1/quit and the server then ends with exit code 0; a crash or a kill does not.
    One not started here is not this launcher's child: how it ended cannot be read."""
    return server is not None and server.returncode != 0


def note_end(what, code):
    """Writes in the app's log that a part of it ended on its own, and returns its exit code as
    it is said: Windows' own (a crash, 0xC0000005) in hex (2026-11-02: a tester's app went away;
    the log said nothing of how)."""
    said = f"0x{code & 0xFFFFFFFF:08X}" if code < 0 or code > 255 else str(code)
    with open(LOG, "a", encoding="utf-8") as log:
        when = time.strftime("%Y-%m-%d %H:%M:%S")
        log.write(f"{when} launcher: the {what} ended on its own, exit code {said}\n")
    return said


def window(server):
    """The window kept while the app runs (server: the process started here, else None).
    Without a screen to show it on (no display), the browser opens once the app answers and
    the app runs on, quit from its screen."""
    said = launcher_words()
    try:
        import tkinter as tk
        from tkinter import font, messagebox

        root = tk.Tk()
    except Exception:  # noqa: BLE001 - no display, no Tk: nothing to show it on
        for _ in range(START_SECONDS):
            if running():
                webbrowser.open(app_url())
                return
            if server_ended(server):
                break
            time.sleep(1)
        # 2026-11-04: its server had failed, and this waited its five minutes without a word.
        tell(f"{said['failed']}\n{said['failed_note'].format(log=LOG)}")
        return
    root.title("Annotation")
    # The app's mark (tools/handout/make_icon.py), not Tk's lone feather (user 2026-10-30): this
    # window's, the taskbar's and every dialog's after it.
    root.iconphoto(True, tk.PhotoImage(file=str(PACKAGE / "icon.png")))
    root.resizable(False, False)
    frame = tk.Frame(root, padx=18, pady=14)
    frame.pack()
    # The window's own font made bold (a font named "" fell back to one that spread Japanese out).
    bold = font.nametofont("TkDefaultFont").copy()
    bold.configure(weight="bold")
    head = tk.Label(frame, text=said["starting"], font=bold)
    head.pack(anchor="w")
    note = tk.Label(frame, text=said["starting_note"], fg="#5c6776", justify="left")
    note.pack(anchor="w", pady=(4, 12))
    row = tk.Frame(frame)
    row.pack(anchor="e")
    state = {"up": False, "failed": False, "since": time.monotonic()}

    def show():
        # Brought in front: Windows keeps a window of a process in the background behind the
        # others, so it stays on top a moment (2026-10-29: the failure was said behind them).
        root.deiconify()
        root.attributes("-topmost", True)
        root.lift()
        root.after(1500, lambda: root.attributes("-topmost", False))

    def quit_app():
        if state["failed"]:
            root.destroy()
            return
        if not state["up"]:
            # Still starting: the server started here ends with the window.
            if server is not None:
                server.kill()
            root.destroy()
            return
        jobs = ask_app("/v1/jobs") or {}
        going = jobs.get("running", 0) + jobs.get("queued", 0)
        if going:
            # Closed from the taskbar while minimized: shown, so the question is seen.
            show()
        if going and not messagebox.askokcancel(
            "Annotation", said["going"].format(count=going), parent=root
        ):
            return
        ask_app("/v1/quit", {})
        root.destroy()

    open_button = tk.Button(
        row,
        text=said["open"],
        state="disabled",
        command=lambda: webbrowser.open(app_url()),
    )
    open_button.pack(side="left", padx=(0, 8))
    quit_button = tk.Button(row, text=said["quit"], command=quit_app)
    quit_button.pack(side="left")
    root.protocol("WM_DELETE_WINDOW", quit_app)

    def watch_app():
        if state["up"]:
            if server_ended(server):
                if stopped_on_its_own(server):
                    state["failed"] = True
                    code = note_end("server", server.returncode)
                    head.configure(text=said["stopped"].format(code=code))
                    note.configure(text=said["failed_note"].format(log=LOG))
                    show()
                    return
                root.destroy()  # quit from its screen
                return
            root.after(2000, watch_app)
            return
        if running():
            state["up"] = True
            head.configure(text=said["running"])
            note.configure(text=said["close"])
            open_button.configure(state="normal")
            webbrowser.open(app_url())
            root.after(2000, watch_app)
            return
        if server_ended(server) or time.monotonic() - state["since"] > START_SECONDS:
            state["failed"] = True
            head.configure(text=said["failed"])
            note.configure(text=said["failed_note"].format(log=LOG))
            show()
            return
        root.after(1000, watch_app)

    root.after(200, watch_app)
    root.iconify()
    root.mainloop()


def app_window(browser, url):
    """The app's own window (Chrome's or Edge's --app): its own profile in the app's folder, so
    the process opened here is the window's and ends when it closes (another opened while it
    runs is handed to it). Nine tenths of the screen's room, in its middle (2026-10-30: opened
    at the browser's own small size, the screen put the talk above the right, under 1000 px)."""
    room = work_area()
    placed = []
    if room:
        left, top, width, height = room
        w, h = width * 9 // 10, height * 9 // 10
        placed = [
            f"--window-size={w},{h}",
            f"--window-position={left + (width - w) // 2},{top + (height - h) // 2}",
        ]
    return subprocess.Popen(
        [
            browser,
            # The page knows it is the app's window: it says nothing when the app quits, the
            # window closing at once (2026-10-30: "it should just go").
            f"--app={url}?window=app",
            f"--user-data-dir={APP / 'browser'}",
            "--no-first-run",
            "--no-default-browser-check",
            *placed,
        ]
    )


def in_app_window(browser, server, said):
    """Wait for the app to answer, open its window, and quit the app when the window closes,
    work going or not (user 2026-10-30: "otherwise, doing dozens of images, it never ends").
    Quit from its screen (its power sign), the window closes too (user 2026-10-30: it stayed)."""
    since = time.monotonic()
    while running() is None:
        if server_ended(server) or time.monotonic() - since > START_SECONDS:
            tell(f"{said['failed']}\n{said['failed_note'].format(log=LOG)}")
            return
        time.sleep(0.5)
    shown = app_window(browser, app_url())
    # Looked at each second: quit from its screen, the window goes within one (the page says
    # nothing meanwhile; user 2026-10-30: "a second is fine if nothing is shown").
    while shown.poll() is None:
        if server_ended(server):
            close_windows(shown)
            try:
                shown.wait(timeout=10)
            except subprocess.TimeoutExpired:
                shown.terminate()
            if stopped_on_its_own(server):
                code = note_end("server", server.returncode)
                tell(
                    f"{said['stopped'].format(code=code)}\n"
                    f"{said['failed_note'].format(log=LOG)}"
                )
            return
        time.sleep(1)
    ask_app("/v1/quit", {})
    # Closed with its close button, Chrome's or Edge's window ends with 0; one that went away
    # otherwise (crashed, killed) does not (measured 2026-10-30).
    if shown.returncode != 0:
        code = note_end("app window", shown.returncode)
        tell(f"{said['window_gone'].format(code=code)}\n{said['open_again']}")


def shortcut_target(executable, app):
    """What the shortcut opens, when this start is from a clone on Windows (its start.cmd, the
    shortcut itself or npm start, all by the app's .venv): that .venv's pythonw.exe, which opens
    no terminal (user 2026-11-11: the public repository has no zip, and people on Windows start
    by double-click). None otherwise: the zip's (python-windows, by Annotation.exe) and other
    systems."""
    executable = Path(executable)
    beside_venv = os.path.normcase(executable.parent) == os.path.normcase(
        app / ".venv" / "Scripts"
    )
    if beside_venv and executable.name.lower() in ("python.exe", "pythonw.exe"):
        return executable.with_name("pythonw.exe")
    return None


def source_shortcut():
    """The shortcut "Annotation" in the clone's folder, made again at every start, so a folder
    moved gets its new paths. Not made, the app starts all the same: start.cmd opens it."""
    target = shortcut_target(sys.executable, APP) if WINDOWS else None
    if target is None:
        return
    new = not SHORTCUT.exists()
    try:
        make_shortcut(
            SHORTCUT, target, "-m agent_app.launch", APP, PACKAGE / "icon.ico"
        )
    except (OSError, subprocess.SubprocessError) as error:
        with open(LOG, "a", encoding="utf-8") as log:
            print(f"The shortcut was not made ({SHORTCUT}): {error!r}", file=log)
        return
    if new:
        # In view when a terminal started it (npm start); start.cmd hands over to pythonw.exe,
        # which has none.
        print(
            f'Made the shortcut "{SHORTCUT.stem}" in {REPO}. Next time, double-click it.'
        )


def open_app():
    said = launcher_words()
    browser = app_browser()
    # One launcher at a time. A second one watching would take the app's window for closed (the
    # browser hands it to the first and ends) and quit the app.
    hold = hold_file(LOCK)
    if hold is None:
        # The one holding it has the app, or is starting it and will show it.
        if running():
            if browser:
                app_window(browser, app_url())
            else:
                webbrowser.open(app_url())
        return 0
    server = None
    if running() is None:
        # What it says goes to its log from its first line: failing as it reads its modules, it
        # has not opened the log itself (2026-11-04: it stopped, and no log told why). In the
        # log's own encoding, whatever the machine's is.
        with open(LOG, "a", encoding="utf-8") as log:
            server = subprocess.Popen(
                [console_python(), "-m", "agent_app"],
                cwd=APP,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                **APART,
            )
    source_shortcut()
    if browser:
        in_app_window(browser, server, said)
    else:
        window(server)
    hold.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(open_app())
    except Exception:  # noqa: BLE001 - whatever stopped it, with no console to show it
        # Run with no console: what stopped it goes to the log and is said.
        with open(LOG, "a", encoding="utf-8") as log:
            traceback.print_exc(file=log)
        tell(launcher_words()["broken"].format(log=LOG))
        sys.exit(1)

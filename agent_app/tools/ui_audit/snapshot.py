"""A copy of the app at one commit, for the screen checks to run apart from the work (user
2026-10-07: check while the software is being changed; the commits may run ahead of the
checked copy, the findings that still apply are used).

    uv run --project agent_app python agent_app/tools/ui_audit/snapshot.py prepare [--commit HEAD]
    uv run --project agent_app python agent_app/tools/ui_audit/snapshot.py stop

prepare: a detached worktree (.worktrees/ui-audit, no branch) at the commit, its screen built,
a copy of the database (the images are shared: they are named by their content; --keep-db
keeps the copy's own data), and its server on port 4110 (the work's server stays on 3110). Run the checks against it with
run.py --app-url http://127.0.0.1:4110.
"""

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TREE = ROOT / ".worktrees/ui-audit"
SUFFIX = "1110"  # the copy's server: 3000 + 1110 = 4110
PORT = 3000 + int(SUFFIX)
LOG = ROOT / "logs/ui-audit-server.log"


def run(*argv, cwd=None):
    subprocess.run(argv, cwd=cwd, check=True)


def listening_pid():
    out = subprocess.run(
        ["ss", "-ltnpH", f"sport = :{PORT}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    for part in out.split("pid=")[1:]:
        return int(part.split(",")[0])
    return None


def stop():
    pid = listening_pid()
    if pid is None:
        return
    os.killpg(os.getpgid(pid), signal.SIGTERM)
    for _ in range(20):
        if listening_pid() is None:
            return
        time.sleep(0.5)
    raise SystemExit(f"The server on {PORT} did not stop")


def prepare(commit, keep_db=False):
    stop()
    sha = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--verify", f"{commit}^{{commit}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if TREE.exists():
        run("git", "-C", str(TREE), "checkout", "--force", "--detach", sha)
    else:
        run("git", "-C", str(ROOT), "worktree", "add", "--detach", str(TREE), sha)
    # Its own port; the file is the tracked one, changed in the copy only.
    (TREE / ".claude/project.config.json").write_text(
        json.dumps({"portSuffix": SUFFIX}, indent=2) + "\n"
    )
    modules = TREE / "node_modules"
    if not modules.exists():
        modules.symlink_to(ROOT / "node_modules")
    run("uv", "sync", "--project", str(TREE / "agent_app"), "--locked")
    run("npm", "--prefix", str(TREE), "run", "build:agent-ui")
    # The data as it is now: the database copied, the images shared. With --keep-db the copy's
    # own data stays (a person is using the copy; user 2026-10-09: a rebuild lost their talk).
    db = TREE / "agent_app/agent.db"
    if not (keep_db and db.exists()):
        for stale in (
            db,
            db.with_name(db.name + "-wal"),
            db.with_name(db.name + "-shm"),
        ):
            stale.unlink(missing_ok=True)
        source = sqlite3.connect(ROOT / "agent_app/agent.db")
        target = sqlite3.connect(db)
        source.backup(target)
        target.close()
        source.close()
    files = TREE / "agent_app/agent-files"
    if not files.exists():
        files.symlink_to(ROOT / "agent_app/agent-files")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as log:
        subprocess.Popen(
            [
                "uv",
                "run",
                "--project",
                str(TREE / "agent_app"),
                "--locked",
                "python",
                "-m",
                "agent_app",
            ],
            cwd=TREE,
            env={**os.environ, "AGENT_APP_DB": str(db)},
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2)
            print(f"{sha[:7]} on http://127.0.0.1:{PORT}")
            return
        except OSError:
            time.sleep(1)
    raise SystemExit(f"The server on {PORT} did not start; see {LOG}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "stop"])
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument(
        "--keep-db", action="store_true", help="Keep the copy's own data."
    )
    args = parser.parse_args()
    if args.action == "stop":
        stop()
    else:
        prepare(args.commit, args.keep_db)


if __name__ == "__main__":
    main()

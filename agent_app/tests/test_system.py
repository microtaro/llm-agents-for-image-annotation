"""What differs between Linux and Windows (user 2026-10-28: the app runs on Windows too, from
the same source): run on each, these check that system's way."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from agent_app.system import NEW_GROUP, WINDOWS, end_group, free_mb

CHILD = Path(__file__).resolve().parent.parent / "agent_app" / "execution_child.py"


def _alive(pid):
    if WINDOWS:
        listed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in listed.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _gone(pid):
    for _ in range(50):
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return False


def test_a_cli_and_what_it_started_end_together():
    # A worker's CLI starts processes of its own (Codex its tools): stopped, none is left.
    started = (
        "import subprocess, sys, time;"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
        "print(p.pid, flush=True); time.sleep(60)"
    )
    head = subprocess.Popen(
        [sys.executable, "-c", started], stdout=subprocess.PIPE, text=True, **NEW_GROUP
    )
    grandchild = int(head.stdout.readline())
    end_group(head.pid, force=True)
    head.wait(timeout=10)
    assert _gone(grandchild)


def test_a_runs_supervisor_ends_its_cli_at_its_time_limit():
    # execution_child.py, as a run starts it (a script beside system.py): the CLI past its time
    # is ended with what it started, and the supervisor says so (124).
    started = (
        "import subprocess, sys, time;"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
        "open(sys.argv[1], 'w').write(str(p.pid)); time.sleep(60)"
    )
    marker = Path(os.environ.get("TMP", "/tmp")) / f"grandchild-{os.getpid()}.txt"
    spec = {
        "argv": [sys.executable, "-c", started, str(marker)],
        "prompt": "",
        "timeout": 3,
    }
    supervisor = subprocess.run(
        [sys.executable, str(CHILD)],
        input=json.dumps(spec) + "\n",
        text=True,
        timeout=60,
        check=False,
    )
    assert supervisor.returncode == 124
    assert _gone(int(marker.read_text(encoding="utf-8")))
    marker.unlink()


def test_the_free_memory_is_known():
    free = free_mb()
    assert isinstance(free, int) and free > 0

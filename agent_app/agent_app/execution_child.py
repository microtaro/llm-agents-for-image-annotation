"""Own and reap a CLI's process group, including when the server disappears."""

import json
import os
import signal
import subprocess
import sys
import time

# Run as a script (python execution_child.py): system.py beside it is on its path.
from system import NEW_GROUP, end_group


def supervise(argv, prompt, timeout):
    parent = os.getppid()
    stopping = False

    def on_signal(_signal, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    child = subprocess.Popen(argv, stdin=subprocess.PIPE, **NEW_GROUP)
    try:
        child.stdin.write(prompt.encode())
        child.stdin.close()
        end = time.monotonic() + timeout
        while child.poll() is None:
            if stopping or os.getppid() != parent or time.monotonic() >= end:
                return 124
            time.sleep(0.1)
        return child.returncode
    finally:
        # Reap the group even if the direct child exited before its descendants.
        end_group(child.pid)
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        end_group(child.pid, force=True)
        child.wait()


if __name__ == "__main__":
    # stdin is private server-to-supervisor IPC, never an HTTP input.
    spec = json.loads(sys.stdin.readline())
    raise SystemExit(supervise(spec["argv"], spec["prompt"], spec["timeout"]))

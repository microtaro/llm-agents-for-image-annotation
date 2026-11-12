# Put a process (and the programs it starts later) in a Windows job whose committed memory is
# capped: past the cap, their new memory is refused, as on a machine whose commit room ran out.
# The cap lasts while this runs (until the stop file appears).
import ctypes
import os
import sys
import time
from ctypes import wintypes

k = ctypes.WinDLL("kernel32", use_last_error=True)


class Basic(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class Io(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]


class Extended(ctypes.Structure):
    _fields_ = [
        ("Basic", Basic),
        ("Io", Io),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


pid, cap_mb, stop, log_path = (
    int(sys.argv[1]),
    int(sys.argv[2]),
    sys.argv[3],
    sys.argv[4],
)
job = k.CreateJobObjectW(None, None)
info = Extended()
info.Basic.LimitFlags = 0x200  # JOB_OBJECT_LIMIT_JOB_MEMORY
info.JobMemoryLimit = cap_mb << 20
assert k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)), (
    ctypes.get_last_error()
)
process = k.OpenProcess(0x1F0FFF, False, pid)
assert process, ctypes.get_last_error()
assert k.AssignProcessToJobObject(job, process), ctypes.get_last_error()
with open(log_path, "a", encoding="utf-8") as log:
    print(time.strftime("%H:%M:%S"), "capped", pid, cap_mb, "MB", file=log, flush=True)
    while not os.path.exists(stop):
        now = Extended()
        k.QueryInformationJobObject(job, 9, ctypes.byref(now), ctypes.sizeof(now), None)
        print(
            time.strftime("%H:%M:%S"),
            "peak job MB",
            now.PeakJobMemoryUsed >> 20,
            file=log,
            flush=True,
        )
        time.sleep(2)

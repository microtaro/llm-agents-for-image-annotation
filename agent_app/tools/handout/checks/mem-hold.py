# Hold memory so that only TARGET MB stays free (a machine with little memory), for a test.
# Grows until free memory is down to the target, then holds that much (the machine's other
# programs), letting go when free memory or the commit room (what new memory can still be
# promised: past it, programs fail) falls under its floor, at the time limit, or on the stop file.
import ctypes
import os
import sys
import time


class Status(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_ulong),
        ("load", ctypes.c_ulong),
        ("total_phys", ctypes.c_ulonglong),
        ("avail_phys", ctypes.c_ulonglong),
        ("total_commit", ctypes.c_ulonglong),
        ("avail_commit", ctypes.c_ulonglong),
        ("total_virtual", ctypes.c_ulonglong),
        ("avail_virtual", ctypes.c_ulonglong),
        ("avail_extended", ctypes.c_ulonglong),
    ]


def status():
    s = Status()
    s.length = ctypes.sizeof(Status)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
    return s.avail_phys >> 20, s.avail_commit >> 20


target, minutes, stop, log_path = (
    int(sys.argv[1]),
    float(sys.argv[2]),
    sys.argv[3],
    sys.argv[4],
)
FREE_FLOOR, COMMIT_FLOOR, CHUNK = 1536, 3072, 256
held, growing = [], True
end = time.time() + minutes * 60
with open(log_path, "a", encoding="utf-8") as log:
    while time.time() < end and not os.path.exists(stop):
        free, room = status()
        if free < FREE_FLOOR or room < COMMIT_FLOOR:
            growing = False
            while held and (free < FREE_FLOOR + 1024 or room < COMMIT_FLOOR + 1024):
                held.pop()
                free, room = status()
            print(
                time.strftime("%H:%M:%S"),
                "LET GO to",
                len(held) * CHUNK,
                file=log,
                flush=True,
            )
        elif growing and free > target + CHUNK and room > COMMIT_FLOOR + 2 * CHUNK:
            held.append(bytearray(b"\x01") * (CHUNK << 20))
            continue
        elif growing:
            growing = False
            print(
                time.strftime("%H:%M:%S"),
                "HOLDING",
                len(held) * CHUNK,
                file=log,
                flush=True,
            )
        print(
            time.strftime("%H:%M:%S"),
            "held",
            len(held) * CHUNK,
            "free",
            free,
            "room",
            room,
            file=log,
            flush=True,
        )
        time.sleep(1)
    print(time.strftime("%H:%M:%S"), "END", file=log, flush=True)

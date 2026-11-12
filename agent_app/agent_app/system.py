"""What differs between Linux (WSL) and Windows, in one place (user 2026-10-28: the app runs on
Windows too, from the same source): a CLI and everything it starts as one group ended whole, the
machine's free memory, how a port is bound, Windows' own windows opened from either (PowerShell 7 and the paths
Windows sees), how a folder of this machine is written in a worker's example, and how the
launcher starts the server apart and speaks to the person. Every other part calls these and
does not ask which system it is on.
"""

import ctypes
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

WINDOWS = os.name == "nt"

# A folder of this machine as a worker writes it in an example (2026-10-29: on Windows the
# reception's example was "/home/…/images"; 2026-11-02: the steward's, writing out, was
# "/home/…/export": every tool naming a folder gives this one).
FOLDER_EXAMPLE = "C:\\Users\\…\\images" if WINDOWS else "/home/…/images"
# Where the folders the workers' tools name are, in their words (2026-11-02: told "a folder on
# the server", the steward said "サーバー上" to a person whose server is their own computer).
THIS_COMPUTER = "of this computer (the one the app runs on)"
# The person's usual folders (Windows' known folders: moved, as into OneDrive, they are where
# they were moved to).
_KNOWN = {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
}

# The keywords that start a process (subprocess.Popen, asyncio.create_subprocess_exec) as the
# head of a group of its own, so the group is ended whole: a session on Linux, a process group
# on Windows.
NEW_GROUP = (
    {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    if WINDOWS
    else {"start_new_session": True}
)


# Whether a port is bound as the server binds it (asyncio's own default): with SO_REUSEADDR off
# Windows, so a port its last server closed a moment ago, its connections still in TIME_WAIT, is
# free (2026-10-29: the launcher said another program held it, on Linux, right after a quit);
# not on Windows, where that option would share a port that is in use.
REUSE_ADDRESS = not WINDOWS


# The server the launcher starts apart, with no window (2026-10-29: the zip's shortcut): on
# Windows a console of its own that no window shows, which the CLIs it starts share (with no
# console at all, each CLI would open a window of its own); elsewhere a session of its own.
APART = (
    {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    if WINDOWS
    else {"start_new_session": True}
)


def app_browser():
    """A browser that opens the app as a window of its own (--app; user 2026-10-30: the app and
    its browser one thing on the taskbar, with the app's mark): on Windows Chrome, else Edge
    (every Windows 10 and 11 has it), by the paths Windows records for them; None elsewhere
    (there the browser opens and the small window stays)."""
    if not WINDOWS:
        return None
    import winreg

    for exe in ("chrome.exe", "msedge.exe"):
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(
                    root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
                ) as key:
                    path = winreg.QueryValue(key, None).strip('"')
            except OSError:
                continue
            if path and Path(path).is_file():
                return path
    return None


class _Rect(ctypes.Structure):
    _fields_ = [(side, ctypes.c_long) for side in ("left", "top", "right", "bottom")]


def work_area():
    """The screen's room for windows (the taskbar's left out) as (left, top, width, height),
    in the sizes a browser's window takes; None where it is not known."""
    if not WINDOWS:
        return None
    room = _Rect()
    if not ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(room), 0):
        return None
    return room.left, room.top, room.right - room.left, room.bottom - room.top


def close_windows(process):
    """Asks the windows of a process to close, as their close button does (WM_CLOSE: Chrome
    shuts down cleanly, no "did not shut down correctly" next time); ended at once elsewhere."""
    if not WINDOWS:
        process.terminate()
        return
    user32 = ctypes.windll.user32
    owner = ctypes.c_ulong()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def each(window, _):
        user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == process.pid and user32.IsWindowVisible(window):
            user32.PostMessageW(window, 0x0010, 0, 0)
        return True

    user32.EnumWindows(each, 0)


def console_python():
    """The Python the server runs on: python.exe beside the launcher's pythonw.exe on Windows
    (the server needs a console for the CLIs it starts)."""
    executable = Path(sys.executable)
    if WINDOWS and executable.name.lower() == "pythonw.exe":
        return str(executable.with_name("python.exe"))
    return str(executable)


def hold_file(path):
    """The file, open and locked, or None while another process holds it. The machine lets go of
    it when the holder ends, however it ends; a child started by the holder does not keep it."""
    file = open(path, "a+b")  # noqa: SIM115 - kept open: the lock lasts as long as the file is
    try:
        if WINDOWS:
            import msvcrt

            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        file.close()
        return None
    return file


def tell(message):
    """Say something to the person from the launcher: a message box on Windows (the shortcut's
    launcher has no window), the terminal elsewhere."""
    if WINDOWS:
        ctypes.windll.user32.MessageBoxW(None, message, "Annotation", 0x40)
    else:
        print(message, file=sys.stderr)


def make_shortcut(link, target, arguments, folder, icon):
    """A Windows shortcut (.lnk) at link that opens target with arguments in folder, with icon
    (launch.shortcut_target). Made by Windows PowerShell, which every Windows 10 and 11 has; the
    paths go by the environment, so no quoting meets a folder's name."""
    shell = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    subprocess.run(
        [
            str(shell / "System32/WindowsPowerShell/v1.0/powershell.exe"),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK_LINK);"
                " $s.TargetPath = $env:LNK_TARGET; $s.Arguments = $env:LNK_ARGUMENTS;"
                " $s.WorkingDirectory = $env:LNK_FOLDER; $s.IconLocation = $env:LNK_ICON;"
                " $s.Save()"
            ),
        ],
        env={
            **os.environ,
            "LNK_LINK": str(link),
            "LNK_TARGET": str(target),
            "LNK_ARGUMENTS": arguments,
            "LNK_FOLDER": str(folder),
            "LNK_ICON": str(icon),
        },
        capture_output=True,
        check=True,
        timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def end_group(pid, force=False):
    """Ends the group a process started with NEW_GROUP heads: asked first, then forced. Nothing
    when it is gone already. Windows ends the process and the ones under it (taskkill /T); one
    whose head has already ended is not found there (Linux ends the whole group still)."""
    if WINDOWS:
        subprocess.run(
            ["taskkill", "/T", *(["/F"] if force else []), "/PID", str(pid)],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        pass


def stop_supervisor(process):
    """Asks a run's supervisor (execution_child.py) to end. Linux sends it SIGTERM and it ends its
    CLI's group itself; Windows has no such asking (terminate ends a process at once, before its
    clean-up), so the supervisor is ended with every process under it."""
    if WINDOWS:
        end_group(process.pid, force=True)
    else:
        process.terminate()


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class _Guid(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    ]


def _known_folder(text):
    """A Windows known folder's path, None when it has none."""
    import uuid

    found = uuid.UUID(text)
    guid = _Guid(*found.fields[:3], (ctypes.c_ubyte * 8)(*found.bytes[8:]))
    path = ctypes.c_wchar_p()
    shell = ctypes.windll.shell32
    if shell.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path)):
        return None
    try:
        return path.value
    finally:
        ctypes.windll.ole32.CoTaskMemFree(path)


def usual_folders():
    """The person's desktop, documents and downloads folders that are there, as this computer
    writes them: a worker asking where to write out offers them (2026-11-02: the steward told
    the person to type a folder that had to be there already)."""
    if WINDOWS:
        found = [_known_folder(guid) for guid in _KNOWN.values()]
    else:
        home = Path.home()
        found = [str(home / name) for name in ("Desktop", "Documents", "Downloads")]
    return [path for path in found if path and Path(path).is_dir()]


def free_mb():
    """The memory free for more work, in MB; None when not known (memory then holds no job back).
    On Windows the less of the free memory and the commit room, what can still be promised:
    past it, new memory is refused and programs fail (2026-11-02, measured: with the commit room
    gone, the worker CLIs ended at once, "exit=1", while free memory was plenty)."""
    if WINDOWS:
        status = _MemoryStatus(dwLength=ctypes.sizeof(_MemoryStatus))
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return min(status.ullAvailPhys, status.ullAvailPageFile) // (1024 * 1024)
        return None
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return None


# PowerShell 7 as WSL sees it, when it is not on WSL's PATH.
_WSL_PWSH = Path("/mnt/c/Program Files/PowerShell/7/pwsh.exe")


def powershell():
    """PowerShell 7, to open a Windows window: on Windows itself, or from WSL (with wslpath to
    give it paths); None when there is none."""
    found = shutil.which("pwsh.exe") or shutil.which("pwsh")
    if WINDOWS:
        return found
    if not found and _WSL_PWSH.is_file():
        found = str(_WSL_PWSH)
    return found if found and shutil.which("wslpath") else None


def windows_path(path):
    """A path as Windows sees it (from WSL, wslpath -w)."""
    return str(path) if WINDOWS else _wslpath("-w", path)


def server_path(path):
    """A path Windows gave, as this server sees it (in WSL, wslpath -u)."""
    return str(path) if WINDOWS else _wslpath("-u", path)


def _wslpath(flag, path):
    return subprocess.run(
        ["wslpath", flag, str(path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    ).stdout.strip()

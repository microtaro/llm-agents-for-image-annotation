"""The Windows window to choose a folder of images (definition 43; carried from annotation_server,
carry-over list 2.4): opened by the server on its own desktop (Windows, or WSL with PowerShell 7),
as a file dialog that shows the folder's images. Open on the prefilled name takes the whole
folder; choosing some images takes only those."""

import base64
import json
import subprocess
import threading
from pathlib import Path

from pydantic import Field

from .errors import ApiError, Model
from .images import SUFFIXES, scan_paths
from .system import powershell, server_path, windows_path

_open = threading.Lock()


class PickFolderInput(Model):
    directory: str | None = Field(
        None,
        max_length=4096,
        description="The folder the window opens in (the one chosen last); default the"
        " server's working folder.",
    )
    title: str = Field(
        max_length=200, description="The window's title, in the UI language."
    )
    whole_folder: str = Field(
        max_length=200,
        description="The file name box's text; Open on it takes every image of the folder.",
    )


class PickedFolder(Model):
    directory: str = Field(
        description="The folder chosen (or opened in, when cancelled)."
    )
    left_out: list[str] = Field(
        description="The folder's images not chosen (none when the whole folder was taken)."
    )
    cancelled: bool


def pick_folder(body: PickFolderInput):
    """The folder chosen in the window and its images left out; one window at a time."""
    if not _open.acquire(blocking=False):
        raise ApiError(
            409, "picker_busy", "The window to choose a folder is open already"
        )
    try:
        executable = powershell()
        if executable is None:
            raise ApiError(
                503,
                "native_picker_unavailable",
                "The Windows window needs Windows (or WSL) and PowerShell 7",
            )
        directory = Path(body.directory or Path.cwd()).expanduser()
        if not directory.is_dir():
            directory = Path.cwd()
        options = {
            "directory": windows_path(directory.resolve()),
            "title": body.title,
            "whole_folder": body.whole_folder,
            "patterns": ";".join(f"*{suffix}" for suffix in sorted(SUFFIXES)),
        }
        encoded = base64.b64encode(json.dumps(options).encode()).decode()
        script = Path(__file__).with_suffix(".ps1").read_text(encoding="utf-8")
        command = base64.b64encode(
            script.replace("__OPTIONS__", encoded).encode("utf-16le")
        ).decode()
        completed = subprocess.run(
            [executable, "-NoProfile", "-STA", "-EncodedCommand", command],
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        chosen = [Path(server_path(p)) for p in json.loads(completed.stdout)["paths"]]
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        raise ApiError(
            503,
            "native_picker_failed",
            "The Windows window could not open; check the Windows desktop and PowerShell 7",
        ) from exc
    finally:
        _open.release()
    if not chosen:
        return {"directory": str(directory), "left_out": [], "cancelled": True}
    folder = chosen[0].parent.resolve()
    picked = {str(p.resolve()) for p in chosen if p.is_file()}
    found = scan_paths([str(folder)])["files"]
    return {
        "directory": str(folder),
        "left_out": [f["path"] for f in found if picked and f["path"] not in picked],
        "cancelled": False,
    }

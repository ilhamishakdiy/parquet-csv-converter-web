"""Desktop shortcut to Start.bat, created on first launch.

* The desktop folder comes from Windows (SHGetKnownFolderPath), so OneDrive-redirected desktops work.
* Created once: a marker in the data folder remembers it, so a shortcut the user deleted is not recreated.
* If the converter is extracted somewhere else later, the shortcut is updated to the new Start.bat.
* Failures (e.g. PowerShell or COM blocked by policy) never stop the converter from starting.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

SHORTCUT_NAME = "Parquet to CSV Converter.lnk"
FOLDERID_DESKTOP = uuid.UUID("B4BFCC3A-DB2C-424C-B029-7FE99A87C641")
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_PS_CREATE = (
    "$ErrorActionPreference = 'Stop'; "
    "$lnk = (New-Object -ComObject WScript.Shell).CreateShortcut($env:PQ_LNK); "
    "$lnk.TargetPath = $env:PQ_TARGET; "
    "$lnk.WorkingDirectory = $env:PQ_WORKDIR; "
    "if ($env:PQ_ICON) { $lnk.IconLocation = $env:PQ_ICON + ',0' }; "
    "$lnk.Description = 'Open the Parquet to CSV Converter'; "
    "$lnk.WindowStyle = 1; "
    "$lnk.Save()"
)


def desktop_dir() -> Path | None:
    if sys.platform != "win32":
        return None

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

    u = FOLDERID_DESKTOP
    guid = GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8).from_buffer_copy(u.bytes[8:]))
    ptr = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(ptr)) != 0:
        return None
    try:
        return Path(ptr.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(ptr)


def create_shortcut(lnk: Path, target: Path, icon: Path | None) -> None:
    env = {
        **os.environ,
        "PQ_LNK": str(lnk),
        "PQ_TARGET": str(target),
        "PQ_WORKDIR": str(target.parent),
        "PQ_ICON": str(icon) if icon and icon.exists() else "",
    }
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _PS_CREATE],
        env=env,
        capture_output=True,
        timeout=30,
        creationflags=CREATE_NO_WINDOW,
    )
    if result.returncode != 0 or not lnk.exists():
        raise OSError(result.stderr.decode("utf-8", errors="replace").strip() or "shortcut was not created")


def ensure_desktop_shortcut(app_dir: Path, marker: Path, desktop: Path | None = None) -> str | None:
    """Create or update the shortcut when needed. Returns a message to print, or None."""
    target = app_dir / "Start.bat"
    if sys.platform != "win32" or not target.exists():
        return None
    try:
        state = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    if state.get("target") and os.path.normcase(state["target"]) == os.path.normcase(str(target)):
        return None  # already handled for this folder; respect a deleted shortcut

    desktop = desktop or desktop_dir()
    if not desktop or not desktop.is_dir():
        return None
    lnk = desktop / SHORTCUT_NAME
    moved = bool(state.get("target"))
    try:
        create_shortcut(lnk, target, app_dir / "converter.ico")
    except (OSError, subprocess.SubprocessError) as exc:
        return f"Note: could not create a desktop shortcut ({exc}). You can still start the converter with Start.bat."
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"target": str(target), "shortcut": str(lnk)}), encoding="utf-8")
    if moved:
        return f'Updated the desktop shortcut "{lnk.stem}" to this folder.'
    return f'Created a desktop shortcut "{lnk.stem}". Next time, just double-click it.'

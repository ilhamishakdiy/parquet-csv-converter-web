"""Native Windows "Browse" dialogs, shown by the local converter on behalf of the page.

Browsers never reveal real file paths, so the page asks the loopback API to open the
dialog on this PC. Each dialog runs in a short-lived child process:

    python -m backend.dialog <file|folder> [initial_dir]

which prints {"path": "..."} or {"path": null} (cancelled) as JSON on stdout.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from .errors import AppError
from .settings import APP_DIR

KINDS = ("file", "folder")
DIALOG_TIMEOUT = 15 * 60
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_lock = threading.Lock()


def _tk_dialog(kind: str, initial: str | None) -> str | None:
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)  # appear above the browser window
    root.lift()
    root.focus_force()
    try:
        if kind == "file":
            path = filedialog.askopenfilename(
                parent=root,
                title="Choose a Parquet file (pick any shard to use its whole folder)",
                initialdir=initial or None,
                filetypes=[("Parquet files", "*.parquet"), ("All files", "*.*")],
            )
        else:
            path = filedialog.askdirectory(parent=root, title="Choose a folder", initialdir=initial or None, mustexist=True)
    finally:
        root.destroy()
    return str(Path(path)) if path else None


def _powershell_dialog(kind: str, initial: str | None) -> str | None:
    init = (initial or "").replace("'", "''")
    if kind == "file":
        body = (
            "$d = New-Object System.Windows.Forms.OpenFileDialog; "
            "$d.Title = 'Choose a Parquet file'; "
            "$d.Filter = 'Parquet files (*.parquet)|*.parquet|All files (*.*)|*.*'; "
            f"if ('{init}') {{ $d.InitialDirectory = '{init}' }}; "
            "if ($d.ShowDialog() -eq 'OK') { [Console]::Out.Write($d.FileName) }"
        )
    else:
        body = (
            "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$d.Description = 'Choose a folder'; "
            f"if ('{init}') {{ $d.SelectedPath = '{init}' }}; "
            "if ($d.ShowDialog() -eq 'OK') { [Console]::Out.Write($d.SelectedPath) }"
        )
    script = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Add-Type -AssemblyName System.Windows.Forms; " + body
    out = subprocess.run(
        ["powershell.exe", "-NoProfile", "-STA", "-NonInteractive", "-Command", script],
        capture_output=True,
        timeout=DIALOG_TIMEOUT,
        creationflags=CREATE_NO_WINDOW,
    )
    text = out.stdout.decode("utf-8", errors="replace").strip()
    return text or None


def open_in_shell(path: Path) -> None:
    """Open a folder in Explorer, or a file in its default app (e.g. catalog.csv in Excel)."""
    if not path.exists():
        raise AppError("not_found", f"It no longer exists: {path}", 404)
    if sys.platform != "win32":
        raise AppError("unsupported", "Opening files is only supported on Windows.", 501)
    try:
        os.startfile(str(path))  # noqa: S606 - path comes from a verified job result, never from the client
    except OSError as exc:
        raise AppError("open_failed", f"Windows could not open {path}: {exc}", 500) from exc


def sibling_parquet(path: Path) -> tuple[Path, int]:
    """The picked file's folder and how many .parquet files sit directly in it (marker/temp names excluded)."""
    folder = path.parent
    try:
        count = sum(
            1 for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".parquet" and not p.name.startswith((".", "_"))
        )
    except OSError:
        count = 0
    return folder, count


def run_dialog(kind: str, initial: str | None) -> str | None:
    """Child-process entry: try Tk first, then the Windows Forms dialog."""
    try:
        return _tk_dialog(kind, initial)
    except ImportError:
        return _powershell_dialog(kind, initial)


def browse(kind: str, initial: str | None = None) -> str | None:
    """Called by the API: show one dialog at a time and return the chosen path (None if cancelled)."""
    if kind not in KINDS:
        raise AppError("invalid_request", f"kind must be one of: {', '.join(KINDS)}")
    if initial:
        p = Path(initial.strip().strip('"'))
        while p != p.parent and not p.is_dir():  # start at the nearest existing folder
            p = p.parent
        initial = str(p) if p.is_dir() else None
    if not _lock.acquire(blocking=False):
        raise AppError("dialog_open", "A Browse window is already open. It may be behind the browser window.", 409)
    try:
        args = [sys.executable, "-m", "backend.dialog", kind] + ([initial] if initial else [])
        try:
            out = subprocess.run(
                args,
                cwd=str(APP_DIR),
                capture_output=True,
                timeout=DIALOG_TIMEOUT,
                creationflags=CREATE_NO_WINDOW,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
        except subprocess.TimeoutExpired as exc:
            raise AppError("dialog_timeout", "The Browse window was open too long and was closed.", 408) from exc
        try:
            return json.loads(out.stdout.decode("utf-8"))["path"]
        except (ValueError, KeyError) as exc:
            detail = out.stderr.decode("utf-8", errors="replace").strip().splitlines()[-1:] or ["no output"]
            raise AppError("dialog_failed", f"Could not open the Browse window ({detail[0]}). Type or paste the path instead.", 500) from exc
    finally:
        _lock.release()


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else ""
    if kind not in KINDS:
        print("usage: python -m backend.dialog <file|folder> [initial_dir]", file=sys.stderr)
        return 2
    initial = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps({"path": run_dialog(kind, initial)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

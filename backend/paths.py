"""Local path validation: approved roots, traversal and network paths (PRD 05)."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

from .errors import AppError

DRIVE_REMOTE = 4


def _is_network_drive(path: Path) -> bool:
    if sys.platform != "win32" or not path.drive or path.drive.startswith("\\\\"):
        return path.drive.startswith("\\\\")
    root = path.drive + "\\"
    return ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)) == DRIVE_REMOTE


def _within(path: Path, root: Path) -> bool:
    # WindowsPath comparison is case-insensitive.
    return path == root or root in path.parents


def resolve_local_path(raw: str, roots: list[Path], allow_network: bool = False, label: str = "Path") -> Path:
    """Normalise a typed or pasted path and enforce the approved roots."""
    text = (raw or "").strip().strip('"').strip()
    if not text:
        raise AppError("path_required", f"{label} is required.")
    if "\x00" in text:
        raise AppError("invalid_path", f"{label} contains invalid characters.")
    if text.startswith(("\\\\?\\", "\\\\.\\", "//?/", "//./")):
        raise AppError("invalid_path", f"{label} uses a device path, which is not supported.")
    unc = text.startswith(("\\\\", "//"))
    if unc and not allow_network:
        raise AppError("network_path", f"{label} is a network path. Only local drives are allowed.")
    candidate = Path(text)
    if not candidate.is_absolute():
        raise AppError("relative_path", f"{label} must be a full path, for example C:\\Data\\sales.parquet.")
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise AppError("invalid_path", f"{label} is not a valid path: {exc}") from exc
    if not allow_network and (str(resolved).startswith("\\\\") or _is_network_drive(resolved)):
        raise AppError("network_path", f"{label} is on a network drive. Only local drives are allowed.")
    approved = [Path(os.path.abspath(r)).resolve(strict=False) for r in roots]
    if not any(_within(resolved, r) for r in approved):
        allowed = "; ".join(str(r) for r in approved)
        raise AppError(
            "path_not_approved",
            f"{label} is outside the approved folders ({allowed}). Move the data there or ask IT to add the folder to config.json.",
            403,
        )
    return resolved

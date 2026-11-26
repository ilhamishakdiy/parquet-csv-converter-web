"""Used by Start.bat (stdlib only, runs before dependencies exist).

  python -m backend.envcheck check   exit 0 if requirements.txt is unchanged since the last install
                                     AND the runtime packages import; exit 1 if (re)install is needed
  python -m backend.envcheck stamp   record requirements.txt's hash after a successful install
"""

from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements.txt"
STAMP = ROOT / ".venv" / "requirements.sha256"
MODULES = ("duckdb", "fastapi", "uvicorn", "pydantic", "starlette")


def _hash() -> str:
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def check() -> int:
    try:
        if STAMP.read_text(encoding="utf-8").strip() != _hash():
            return 1
    except OSError:
        return 1
    for name in MODULES:
        try:
            importlib.import_module(name)
        except Exception:  # noqa: BLE001 - any import failure means reinstall
            return 1
    return 0


def stamp() -> int:
    STAMP.write_text(_hash(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action not in ("check", "stamp"):
        print("usage: python -m backend.envcheck check|stamp", file=sys.stderr)
        sys.exit(2)
    sys.exit(check() if action == "check" else stamp())

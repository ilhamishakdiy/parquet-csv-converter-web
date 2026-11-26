"""Conversion subprocess entry point: python -m backend.worker <job_dir>."""

from __future__ import annotations

import sys
from pathlib import Path

from .exporter import run_job


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m backend.worker <job_dir>", file=sys.stderr)
        return 2
    run_job(Path(sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

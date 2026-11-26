"""Constants and the optional config.json next to app.py."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

API_VERSION = "1.0.0"
APP_NAME = "parquet-csv-converter"

HOST = "127.0.0.1"
PORT = 8765

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = APP_DIR / "config.json"
# Compiled frontend served by FastAPI when the hosted site is blocked (PRD 02).
LOCAL_WEB_DIR = APP_DIR / "web"

DEFAULT_ROW_LIMIT = 800_000
EXCEL_MAX_DATA_ROWS = 1_048_575
MAX_PARTS = 100_000
WINDOWS_MAX_PATH = 259

DUCKDB_MEMORY_LIMIT = "6GB"
DUCKDB_THREADS = 4

DEV_FRONTEND_URL = "http://localhost:3000/"

# Restrictive CSP for the compiled frontend (also in frontend/public/_headers for Cloudflare).
# 'unsafe-inline' scripts are required by Next.js static export bootstrap code.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    f"img-src 'self' data:; font-src 'self'; connect-src 'self' http://{HOST}:{PORT}; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'none'; object-src 'none'"
)


def default_data_dir() -> Path:
    base = os.environ.get("PQCSV_DATA_DIR")
    if base:
        return Path(base)
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "ParquetConverter"


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


@dataclass
class Config:
    """Runtime configuration. Every field can be set in config.json."""

    approved_roots: list[Path] = field(default_factory=lambda: [Path.home()])
    frontend_url: str = ""
    extra_trusted_origins: list[str] = field(default_factory=list)
    allow_network_paths: bool = False
    data_dir: Path = field(default_factory=default_data_dir)
    memory_limit: str = DUCKDB_MEMORY_LIMIT
    threads: int = DUCKDB_THREADS

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"

    @property
    def session_file(self) -> Path:
        return self.data_dir / "session.json"

    @property
    def self_origins(self) -> list[str]:
        return [f"http://{HOST}:{PORT}", f"http://localhost:{PORT}"]

    @property
    def trusted_origins(self) -> set[str]:
        origins = set(self.self_origins)
        if self.frontend_url:
            origins.add(origin_of(self.frontend_url))
        origins.update(o.rstrip("/") for o in self.extra_trusted_origins)
        return origins

    @property
    def allowed_hosts(self) -> set[str]:
        return {f"{HOST}:{PORT}", f"localhost:{PORT}"}


def load_config(path: Path = CONFIG_FILE) -> Config:
    cfg = Config()
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if "approved_roots" in raw:
            cfg.approved_roots = [Path(os.path.expandvars(os.path.expanduser(r))) for r in raw["approved_roots"]]
        cfg.frontend_url = raw.get("frontend_url", cfg.frontend_url) or ""
        cfg.extra_trusted_origins = list(raw.get("extra_trusted_origins", []))
        cfg.allow_network_paths = bool(raw.get("allow_network_paths", False))
        if raw.get("data_dir"):
            cfg.data_dir = Path(os.path.expandvars(raw["data_dir"]))
        cfg.memory_limit = raw.get("memory_limit", cfg.memory_limit)
        cfg.threads = int(raw.get("threads", cfg.threads))
    if not cfg.frontend_url:
        # No hosted URL configured: serve the bundled build locally if present.
        cfg.frontend_url = f"http://{HOST}:{PORT}/" if LOCAL_WEB_DIR.exists() else DEV_FRONTEND_URL
    return cfg

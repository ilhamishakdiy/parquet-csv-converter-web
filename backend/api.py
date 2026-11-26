"""FastAPI app bound to 127.0.0.1:8765 (PRD 05 endpoint contract)."""

from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import dialog, naming
from .errors import AppError
from .exporter import remove_tree
from .inspection import SourceInfo, current_fingerprint, inspect_source
from .jobs import JobManager
from .paths import resolve_local_path
from .planner import Plan, PlanRequest, build_plan
from .security import LoopbackGuard, token_valid
from .settings import (
    API_VERSION,
    APP_NAME,
    CONTENT_SECURITY_POLICY,
    DEFAULT_ROW_LIMIT,
    LOCAL_WEB_DIR,
    WINDOWS_MAX_PATH,
    Config,
)

KEEP_PREVIEWS = 10


class InspectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_path: str


class PreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fingerprint: str
    mode: Literal["single", "rows", "group"]
    filter_column: str | None = None
    group_columns: list[str] = Field(default_factory=list)
    row_limit: int = DEFAULT_ROW_LIMIT
    oversize_policy: Literal["strict", "group_priority"] = "strict"
    output_prefix: str


class JobBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: str
    destination_dir: str
    collision_policy: Literal["fail", "new_folder", "overwrite"] = "fail"
    acknowledge_oversize: bool = False


class BrowseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["file", "folder"]
    initial_path: str | None = None


class OpenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    target: Literal["folder", "catalog"]


class State:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.inspections: dict[str, SourceInfo] = {}
        self.previews: dict[str, tuple[Plan, Path]] = {}
        self.lock = threading.Lock()
        self.jobs = JobManager(cfg.work_dir)

    @property
    def previews_dir(self) -> Path:
        return self.cfg.work_dir / "previews"

    def spill(self, name: str) -> Path:
        return self.cfg.work_dir / "spill" / name


def _gib(n: float) -> str:
    return f"{n / 1024**3:.1f} GB"


def create_app(cfg: Config, token: str) -> FastAPI:
    state = State(cfg)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        cfg.work_dir.mkdir(parents=True, exist_ok=True)
        state.jobs.cleanup_stale()
        remove_tree(state.previews_dir)
        remove_tree(cfg.work_dir / "spill")
        yield
        state.jobs.shutdown()

    app = FastAPI(title="Parquet to CSV Converter", version=API_VERSION, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.converter = state
    app.add_middleware(LoopbackGuard, token=token, allowed_hosts=cfg.allowed_hosts, trusted_origins=cfg.trusted_origins)

    @app.exception_handler(AppError)
    async def app_error(_request: Request, exc: AppError):
        return JSONResponse({"detail": exc.to_dict()}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", [])[1:])
        return JSONResponse(
            {"detail": {"code": "invalid_request", "message": f"{where}: {first.get('msg', 'invalid value')}"}},
            status_code=422,
        )

    @app.get("/health")
    def health(request: Request):
        paired = token_valid(request, token)
        body = {"status": "ok", "app": APP_NAME, "api_version": API_VERSION, "paired": paired}
        if paired:
            running = state.jobs.running()
            body["running_job_id"] = running.job_id if running else None
            body["approved_roots"] = [str(r) for r in cfg.approved_roots]
        return body

    @app.post("/browse")
    def browse(body: BrowseBody):
        # Opens a native dialog on this PC; the chosen path is still validated by /inspect and /jobs.
        initial = body.initial_path or (str(cfg.approved_roots[0]) if cfg.approved_roots else None)
        path = dialog.browse(body.kind, initial)
        out: dict = {"path": path, "folder": None, "folder_parquet_count": 0}
        if path and body.kind == "file":
            # A picked shard (e.g. 000000000000.parquet) lets the user choose the whole folder.
            folder, count = dialog.sibling_parquet(Path(path))
            if count > 1:
                out.update(folder=str(folder), folder_parquet_count=count)
        return out

    @app.post("/open")
    def open_output(body: OpenBody):
        # Only paths from a succeeded job's own result can be opened; the client never sends a path.
        result = state.jobs.result(body.job_id)
        target = Path(result["destination"] if body.target == "folder" else result["catalog_path"])
        dialog.open_in_shell(target)
        return {"opened": str(target)}

    @app.post("/inspect")
    def inspect(body: InspectBody):
        path = resolve_local_path(body.source_path, cfg.approved_roots, cfg.allow_network_paths, "Source")
        spill = state.spill(f"inspect-{uuid.uuid4().hex[:8]}")
        try:
            info = inspect_source(path, spill, cfg.memory_limit, cfg.threads)
        finally:
            remove_tree(spill)
        with state.lock:
            state.inspections[info.fingerprint] = info
        return info.to_public()

    @app.post("/preview")
    def preview(body: PreviewBody):
        info = state.inspections.get(body.fingerprint)
        if not info:
            raise AppError("unknown_fingerprint", "Inspect the source file again before previewing.", 409)
        spill = state.spill(f"preview-{uuid.uuid4().hex[:8]}")
        try:
            if current_fingerprint(info, spill, cfg.memory_limit, cfg.threads) != info.fingerprint:
                raise AppError("source_changed", "The source file changed since it was inspected. Inspect it again.", 409)
            preview_id = uuid.uuid4().hex[:16]
            plan_db = state.previews_dir / f"{preview_id}.duckdb"
            req = PlanRequest(
                mode=body.mode,
                filter_column=body.filter_column or None,
                group_columns=body.group_columns,
                row_limit=body.row_limit,
                oversize_policy=body.oversize_policy,
                output_prefix=body.output_prefix,
            )
            try:
                plan = build_plan(req, info, plan_db, spill, preview_id, cfg.memory_limit, cfg.threads)
            except Exception:
                _remove_plan_db(plan_db)
                raise
        finally:
            remove_tree(spill)
        with state.lock:
            state.previews[preview_id] = (plan, plan_db)
            _prune_previews(state)
        return plan.to_public()

    @app.post("/jobs")
    def create_job(body: JobBody):
        entry = state.previews.get(body.preview_id)
        if not entry:
            raise AppError("unknown_preview", "This preview has expired. Preview again before converting.", 409)
        plan, plan_db = entry
        info = state.inspections.get(plan.fingerprint)
        if not info:
            raise AppError("unknown_fingerprint", "Inspect the source file again.", 409)
        if plan.blocking:
            raise AppError("plan_blocked", "The preview has blocking problems. Fix them and preview again.", 409)
        if plan.requires_acknowledgement and not body.acknowledge_oversize:
            raise AppError("acknowledge_required", "Acknowledge the oversized files before converting.", 409)
        spill = state.spill(f"job-check-{uuid.uuid4().hex[:8]}")
        try:
            if current_fingerprint(info, spill, cfg.memory_limit, cfg.threads) != plan.fingerprint:
                raise AppError("source_changed", "The source file changed since the preview. Inspect and preview again.", 409)
        finally:
            remove_tree(spill)

        destination, created, warnings = _prepare_destination(cfg, plan, info, body)
        spec = {
            "source": info.to_spec(),
            "plan": plan.to_dict(),
            "plan_db": str(plan_db),
            "destination": str(destination),
            "create_destination": created,
            "overwrite": body.collision_policy == "overwrite",
            "memory_limit": cfg.memory_limit,
            "threads": cfg.threads,
        }
        try:
            job_id = state.jobs.start(spec)
        except Exception:
            if created:
                try:
                    destination.rmdir()
                except OSError:
                    pass
            raise
        return {"job_id": job_id, "destination": str(destination), "warnings": warnings}

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str):
        return state.jobs.status(job_id)

    @app.post("/jobs/{job_id}/cancel")
    def job_cancel(job_id: str):
        return state.jobs.cancel(job_id)

    @app.get("/jobs/{job_id}/result")
    def job_result(job_id: str):
        return state.jobs.result(job_id)

    if LOCAL_WEB_DIR.exists():
        # Fallback when the hosted site or loopback access is blocked (PRD 02).
        app.mount("/", StaticFiles(directory=str(LOCAL_WEB_DIR), html=True), name="web")

        @app.middleware("http")
        async def csp(request: Request, call_next):
            response = await call_next(request)
            response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
            return response

    return app


def _remove_plan_db(plan_db: Path) -> None:
    for p in (plan_db, plan_db.with_suffix(".duckdb.wal")):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def _prune_previews(state: State) -> None:
    running = state.jobs.running()
    in_use = set()
    if running:
        spec_plan = (running.job_dir / "spec.json").read_text(encoding="utf-8")
        in_use = {pid for pid in state.previews if pid in spec_plan}
    for pid in list(state.previews)[:-KEEP_PREVIEWS]:
        if pid in in_use:
            continue
        _, db = state.previews.pop(pid)
        _remove_plan_db(db)


def _prepare_destination(cfg: Config, plan: Plan, info: SourceInfo, body: JobBody) -> tuple[Path, bool, list[str]]:
    dest = resolve_local_path(body.destination_dir, cfg.approved_roots, cfg.allow_network_paths, "Destination folder")
    warnings: list[str] = []
    created = False
    if dest.exists() and not dest.is_dir():
        raise AppError("destination_not_folder", "The destination is a file, not a folder.")
    if not dest.exists():
        if not dest.parent.exists():
            raise AppError("destination_missing", f"The parent folder does not exist: {dest.parent}")
        dest.mkdir()
        created = True
    if body.collision_policy == "new_folder":
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = dest / f"{plan.output_prefix}_{stamp}"
        candidate, n = base, 1
        while candidate.exists():
            n += 1
            candidate = base.with_name(f"{base.name}_{n}")
        if created:
            dest.rmdir()
        candidate.mkdir(parents=True)
        dest, created = candidate, True

    try:
        probe = dest / f".pqcsv-write-test-{uuid.uuid4().hex[:8]}"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as exc:
        _undo(dest, created)
        raise AppError("destination_not_writable", f"Cannot write to the destination folder: {exc}", 403) from exc

    names = [f.file_name for f in plan.files] + [naming.CATALOG_NAME]
    clashes = [n for n in names if (dest / n).exists()]
    if clashes and body.collision_policy == "overwrite":
        not_files = [n for n in clashes if not (dest / n).is_file()]
        if not_files:
            _undo(dest, created)
            raise AppError(
                "destination_collision",
                f"These names are folders in the destination and cannot be overwritten: {', '.join(not_files[:5])}.",
                409,
            )
        warnings.append(f"{len(clashes)} existing file(s) with the same names will be replaced.")
    elif clashes:
        _undo(dest, created)
        shown = ", ".join(clashes[:5]) + (f" and {len(clashes) - 5} more" if len(clashes) > 5 else "")
        raise AppError(
            "destination_collision",
            f"These files already exist in the destination: {shown}. Choose another folder, 'Create a new dated subfolder' or 'Overwrite existing files'.",
            409,
        )

    longest = max(len(str(dest / n)) for n in names)
    staging_len = len(str(dest)) + len(r"\.pqcsv-staging-xxxxxxxxxxxx\_raw\__pqcsv_part=") + len(str(len(plan.files))) + len(r"\data_0.csv")
    if max(longest, staging_len) > WINDOWS_MAX_PATH:
        _undo(dest, created)
        raise AppError(
            "path_too_long",
            f"Output paths would exceed Windows' {WINDOWS_MAX_PATH}-character limit. Use a shorter destination folder or prefix.",
        )

    free = shutil.disk_usage(dest).free
    estimate = int(max(info.uncompressed_bytes * 1.5, info.size_bytes * 3))
    if free < info.size_bytes:
        _undo(dest, created)
        raise AppError(
            "insufficient_disk",
            f"Only {_gib(free)} is free on the destination drive; the CSV output needs well over {_gib(info.size_bytes)}.",
            507,
        )
    if free < estimate:
        warnings.append(f"Low disk space: {_gib(free)} free, the CSV output may need about {_gib(estimate)}.")
    spill_free = shutil.disk_usage(cfg.data_dir if cfg.data_dir.exists() else Path(os.path.abspath(os.sep))).free
    if spill_free < 10 * 1024**3:
        warnings.append(f"Only {_gib(spill_free)} free for DuckDB temporary files ({cfg.work_dir}). Large jobs may fail.")
    return dest, created, warnings


def _undo(dest: Path, created: bool) -> None:
    if created:
        try:
            dest.rmdir()
        except OSError:
            pass

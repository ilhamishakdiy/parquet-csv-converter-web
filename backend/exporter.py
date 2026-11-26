"""Export engine run inside the worker subprocess.

Stages: checking_source -> exporting -> validating -> writing_catalog -> publishing.
Everything is written to a staging folder inside the destination; only validated
parts and the catalogue are published, and nothing is ever overwritten.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path

import duckdb

from . import naming
from .db import connect, qi, ql
from .errors import AppError, friendly_duckdb_error
from .inspection import Column, SourceInfo, current_fingerprint, scan_sql
from .planner import Plan

PART_COLUMN = "__pqcsv_part"
MAX_LINE_SIZE = 256 * 1024 * 1024

STAGE_PROGRESS = {
    "checking_source": (0.00, 0.02),
    "exporting": (0.02, 0.80),
    "validating": (0.80, 0.95),
    "writing_catalog": (0.95, 0.97),
    "publishing": (0.97, 1.00),
}


def write_json_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05 * (attempt + 1))
    os.replace(tmp, path)


def read_json(path: Path) -> dict | None:
    for attempt in range(20):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (PermissionError, json.JSONDecodeError):
            time.sleep(0.02 * (attempt + 1))
    return None


def remove_tree(path: Path) -> None:
    for attempt in range(10):
        if not path.exists():
            return
        try:
            shutil.rmtree(path)
            return
        except OSError:
            time.sleep(0.2 * (attempt + 1))


class Status:
    def __init__(self, path: Path, parts_total: int):
        self.path = path
        self.data = {
            "state": "running",
            "stage": "checking_source",
            "progress": 0.0,
            "parts_completed": 0,
            "parts_total": parts_total,
            "started_at": time.time(),
            "finished_at": None,
            "error": None,
            "pid": os.getpid(),
        }
        self.flush()

    def flush(self) -> None:
        write_json_atomic(self.path, self.data)

    def stage(self, name: str) -> None:
        self.data["stage"] = name
        self.data["progress"] = STAGE_PROGRESS[name][0]
        self.flush()

    def within(self, fraction: float) -> None:
        lo, hi = STAGE_PROGRESS[self.data["stage"]]
        self.data["progress"] = round(lo + (hi - lo) * max(0.0, min(1.0, fraction)), 4)
        self.flush()

    def finish(self, state: str, error: dict | None = None) -> None:
        self.data.update(state=state, finished_at=time.time(), error=error)
        if state == "succeeded":
            self.data["progress"] = 1.0
        self.flush()


def _part_column(columns: list[Column]) -> str:
    name = PART_COLUMN
    names = {c.name.casefold() for c in columns}
    while name.casefold() in names:
        name += "_"
    return name


def build_export_query(plan: Plan, info: SourceInfo, part_col: str) -> str:
    src = f"{scan_sql(info)} AS s"
    p = qi(part_col)
    fcond = f"s.{qi(plan.filter_column)} IS NOT DISTINCT FROM {{t}}.k_f" if plan.filter_column else None
    if plan.mode == "single" and not plan.filter_column:
        return f"SELECT s.*, 1 AS {p} FROM {src}"
    if plan.mode == "rows" and not plan.filter_column:
        return f"SELECT s.*, ((row_number() OVER () - 1) // {int(plan.row_limit)}) + 1 AS {p} FROM {src}"
    if plan.mode == "single":
        return f"SELECT s.*, f.part_base AS {p} FROM {src} JOIN plan.filters f ON {fcond.format(t='f')}"
    if plan.mode == "rows":
        return (
            f"SELECT s.*, f.part_base + ((row_number() OVER (PARTITION BY f.f_idx) - 1) // {int(plan.row_limit)}) AS {p} "
            f"FROM {src} JOIN plan.filters f ON {fcond.format(t='f')}"
        )
    conds = [f"s.{qi(g)} IS NOT DISTINCT FROM m.k_g{i}" for i, g in enumerate(plan.group_columns)]
    if fcond:
        conds.insert(0, fcond.format(t="m"))
    return f"SELECT s.*, m.part_id AS {p} FROM {src} JOIN plan.mapping m ON {' AND '.join(conds)}"


def _run_with_progress(con: duckdb.DuckDBPyConnection, sql: str, status: Status) -> None:
    error: list[BaseException] = []

    def target() -> None:
        try:
            con.execute(sql)
        except BaseException as exc:  # re-raised in the caller thread
            error.append(exc)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    while thread.is_alive():
        thread.join(0.5)
        try:
            pct = con.query_progress()
        except duckdb.Error:
            pct = -1
        if pct is not None and pct >= 0:
            status.within(pct / 100.0)
    if error:
        raise error[0]


def count_csv_records(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    return int(
        con.execute(
            "SELECT count(*) FROM read_csv(?, header = true, all_varchar = true, delim = ',', quote = '\"', "
            f"escape = '\"', max_line_size = {MAX_LINE_SIZE})",
            [str(path)],
        ).fetchone()[0]
    )


def run_job(job_dir: Path) -> None:
    spec = json.loads((job_dir / "spec.json").read_text(encoding="utf-8"))
    plan = Plan.from_dict(spec["plan"])
    info = SourceInfo.from_spec(spec["source"])
    destination = Path(spec["destination"])
    staging = Path(spec["staging"])
    temp_dir = Path(spec["temp_dir"])
    status = Status(job_dir / "status.json", len(plan.files))
    started = time.time()
    con = None
    try:
        status.stage("checking_source")
        if current_fingerprint(info, temp_dir, spec["memory_limit"], spec["threads"]) != plan.fingerprint:
            raise AppError("source_changed", "The source file changed after the preview. Inspect it and preview again.", 409)
        staging.mkdir(parents=False, exist_ok=False)

        con = connect(temp_dir, spec["memory_limit"], spec["threads"])
        con.execute(f"ATTACH {ql(spec['plan_db'])} AS plan (READ_ONLY)")

        status.stage("exporting")
        raw_dir = staging / "_raw"
        part_col = _part_column(info.columns)
        if plan.total_rows == 0:
            empty = raw_dir / f"{part_col}=1"
            empty.mkdir(parents=True)
            con.execute(
                f"COPY (SELECT * FROM {scan_sql(info)} LIMIT 0) TO {ql(str(empty / 'data_0.csv'))} (FORMAT csv, HEADER true)"
            )
        else:
            query = build_export_query(plan, info, part_col)
            _run_with_progress(
                con,
                f"COPY ({query}) TO {ql(str(raw_dir))} (FORMAT csv, HEADER true, PARTITION_BY ({qi(part_col)}))",
                status,
            )

        status.stage("validating")
        actual_rows = _validate_and_stage(con, plan, info, raw_dir, staging, part_col, status)

        if current_fingerprint(info, temp_dir, spec["memory_limit"], spec["threads"]) != plan.fingerprint:
            raise AppError("source_changed", "The source file changed during the conversion. Nothing was published.", 409)

        status.stage("writing_catalog")
        catalog_rows = _write_catalog(con, plan, actual_rows, staging / naming.CATALOG_NAME)
        con.close()
        con = None

        status.stage("publishing")
        published = _publish(plan, staging, destination)
        remove_tree(staging)

        files = [
            {
                "file_name": f.file_name,
                "path": str(destination / f.file_name),
                "filter_value": f.filter_value,
                "filter_is_null": f.filter_is_null,
                "part_no": f.part_no,
                "rows": actual_rows[f.part_id],
                "groups": f.groups,
                "oversized": f.oversized,
            }
            for f in plan.files
        ]
        result = {
            "job_id": spec["job_id"],
            "destination": str(destination),
            "catalog_path": str(destination / naming.CATALOG_NAME),
            "catalog_rows": catalog_rows,
            "files": files,
            "file_count": len(files),
            "total_rows": sum(actual_rows.values()),
            "source_rows": info.row_count,
            "oversized_files": [f["file_name"] for f in files if f["oversized"]],
            "duration_seconds": round(time.time() - started, 2),
            "warnings": plan.warnings,
            "validation": {
                "status": "passed",
                "checks": [
                    {"name": "source_unchanged", "passed": True, "detail": "Source fingerprint matched before and after export."},
                    {"name": "file_counts", "passed": True, "detail": f"All {len(files)} file(s) match their planned row counts."},
                    {"name": "conservation", "passed": True, "detail": f"Exported {sum(actual_rows.values()):,} rows = {info.row_count:,} source rows."},
                    {"name": "catalog", "passed": True, "detail": f"_catalog.csv lists every file ({catalog_rows} row(s))."},
                ],
            },
            "published": published,
        }
        write_json_atomic(job_dir / "result.json", result)
        status.finish("succeeded")
    except AppError as exc:
        _fail(status, staging, exc.to_dict())
    except duckdb.Error as exc:
        _fail(status, staging, friendly_duckdb_error(exc).to_dict())
    except OSError as exc:
        err = AppError("io_error", f"A file operation failed: {exc}")
        if getattr(exc, "winerror", None) == 112 or "space" in str(exc).lower():
            err = AppError("disk_full", "The disk ran out of space. Free up space on the destination drive and try again.")
        _fail(status, staging, err.to_dict())
    except Exception as exc:  # noqa: BLE001 - last resort, still never publish
        _fail(status, staging, {"code": "internal_error", "message": f"Unexpected error: {exc!r}"})
    finally:
        if con is not None:
            con.close()
        remove_tree(temp_dir)


def _fail(status: Status, staging: Path, error: dict) -> None:
    remove_tree(staging)
    status.finish("failed", error)


def _validate_and_stage(
    con: duckdb.DuckDBPyConnection,
    plan: Plan,
    info: SourceInfo,
    raw_dir: Path,
    staging: Path,
    part_col: str,
    status: Status,
) -> dict[int, int]:
    expected_dirs = {f"{part_col}={f.part_id}".casefold() for f in plan.files}
    present = {p.name.casefold() for p in raw_dir.iterdir()} if raw_dir.exists() else set()
    unexpected = present - expected_dirs
    if unexpected:
        raise AppError("validation_failed", f"Rows were routed to unplanned parts: {sorted(unexpected)[:5]}")

    actual: dict[int, int] = {}
    for i, f in enumerate(plan.files, start=1):
        part_dir = raw_dir / f"{part_col}={f.part_id}"
        csvs = sorted(part_dir.glob("*.csv")) if part_dir.exists() else []
        if len(csvs) != 1:
            raise AppError("validation_failed", f"{f.file_name}: expected one output file, found {len(csvs)}.")
        rows = count_csv_records(con, csvs[0])
        if rows != f.rows:
            raise AppError(
                "validation_failed",
                f"{f.file_name}: wrote {rows:,} rows but the plan expected {f.rows:,}. Nothing was published.",
            )
        os.rename(csvs[0], staging / f.file_name)
        actual[f.part_id] = rows
        status.data["parts_completed"] = i
        status.within(i / len(plan.files))
    remove_tree(raw_dir)

    total = sum(actual.values())
    if total != info.row_count:
        raise AppError(
            "validation_failed",
            f"Exported {total:,} rows but the source has {info.row_count:,}. Nothing was published.",
        )
    return actual


def _write_catalog(con: duckdb.DuckDBPyConnection, plan: Plan, actual_rows: dict[int, int], target: Path) -> int:
    headers = plan.catalog_headers
    con.execute("CREATE TEMP TABLE part_files(part_id BIGINT, file_name VARCHAR, filter_raw VARCHAR, rows BIGINT)")
    con.executemany(
        "INSERT INTO part_files VALUES (?, ?, ?, ?)",
        [(f.part_id, f.file_name, f.filter_value, actual_rows[f.part_id]) for f in plan.files],
    )
    out_cols = [f"pf.file_name AS {qi(headers[0])}"]
    if plan.mode == "group" and plan.total_rows > 0:
        mapped = con.execute(
            "SELECT count(*) FROM (SELECT part_id, sum(n) AS n FROM plan.mapping GROUP BY part_id) m "
            "JOIN part_files pf USING (part_id) WHERE m.n = pf.rows"
        ).fetchone()[0]
        if mapped != len(plan.files):
            raise AppError("validation_failed", "Group counts do not match the exported file counts. Nothing was published.")
        idx = 1
        if plan.filter_column:
            out_cols.append(f"CAST(m.k_f AS VARCHAR) AS {qi(headers[idx])}")
            idx += 1
        for i in range(len(plan.group_columns)):
            out_cols.append(f"CAST(m.k_g{i} AS VARCHAR) AS {qi(headers[idx])}")
            idx += 1
        out_cols.append(f"m.n AS {qi(headers[-1])}")
        sql = f"SELECT {', '.join(out_cols)} FROM plan.mapping m JOIN part_files pf USING (part_id) ORDER BY pf.part_id, m.g_idx"
    else:
        idx = 1
        if plan.filter_column:
            out_cols.append(f"pf.filter_raw AS {qi(headers[idx])}")
            idx += 1
        for _ in plan.group_columns:  # empty source in group mode: keep the schema, NULL values
            out_cols.append(f"NULL::VARCHAR AS {qi(headers[idx])}")
            idx += 1
        out_cols.append(f"pf.rows AS {qi(headers[-1])}")
        sql = f"SELECT {', '.join(out_cols)} FROM part_files pf ORDER BY pf.part_id"

    con.execute(f"CREATE TEMP TABLE catalog AS {sql}")
    rows, total, files = con.execute(
        f"SELECT count(*), coalesce(sum({qi(headers[-1])}), 0), count(DISTINCT {qi(headers[0])}) FROM catalog"
    ).fetchone()
    if total != sum(actual_rows.values()) or files != len(plan.files):
        raise AppError("validation_failed", "_catalog.csv does not agree with the exported files. Nothing was published.")
    con.execute(f"COPY catalog TO {ql(str(target))} (FORMAT csv, HEADER true)")
    return int(rows)


def _publish(plan: Plan, staging: Path, destination: Path) -> list[str]:
    """Move validated parts, then the catalogue, into place. Never overwrites; rolls back on failure."""
    names = [f.file_name for f in plan.files] + [naming.CATALOG_NAME]
    clashes = [n for n in names if (destination / n).exists()]
    if clashes:
        raise AppError(
            "destination_collision",
            f"These files appeared in the destination during the conversion: {', '.join(clashes[:5])}. Nothing was published.",
            409,
        )
    moved: list[str] = []
    try:
        for name in names:
            os.rename(staging / name, destination / name)  # raises if the target exists
            moved.append(name)
    except OSError:
        for name in reversed(moved):
            try:
                os.rename(destination / name, staging / name)
            except OSError:
                pass
        raise
    return [str(destination / n) for n in moved]

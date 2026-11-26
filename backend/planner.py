"""Stage 2 planning: filter separation and group-aware next-fit allocation (PRD 04).

The plan is stored in a DuckDB file so the export worker can join the source to it
without re-aggregating:

  filters(k_f, raw, n, f_idx, part_base, part_count)   one row per filter value
  grp(k_f, k_g0.., n, f_idx, g_idx)                     group mode: one row per filter+group tuple
  parts(part_id, f_idx, part_no, g_start, g_end, rows)  group mode: contiguous group ranges
  mapping(k_f, k_g0.., n, part_id)                      group mode: tuple -> part
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import duckdb

from . import naming
from .db import connect, qi
from .errors import AppError, friendly_duckdb_error
from .inspection import SourceInfo, scan_sql
from .settings import EXCEL_MAX_DATA_ROWS, MAX_PARTS

MODES = ("single", "rows", "group")
OVERSIZE_POLICIES = ("strict", "group_priority")
FETCH_BATCH = 100_000
PREVIEW_FILE_LIMIT = 2_000


@dataclass
class PlanRequest:
    mode: str
    filter_column: str | None
    group_columns: list[str]
    row_limit: int
    oversize_policy: str
    output_prefix: str


@dataclass
class PlannedFile:
    part_id: int
    file_name: str
    filter_value: str | None
    filter_is_null: bool
    part_no: int
    rows: int
    groups: int
    largest_group_rows: int
    oversized: bool


@dataclass
class Plan:
    preview_id: str
    fingerprint: str
    mode: str
    filter_column: str | None
    group_columns: list[str]
    row_limit: int
    oversize_policy: str
    output_prefix: str
    total_rows: int
    filter_count: int
    group_count: int
    files: list[PlannedFile]
    largest_group: dict | None
    warnings: list[dict] = field(default_factory=list)
    catalog_headers: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return any(w["severity"] == "blocking" for w in self.warnings)

    @property
    def requires_acknowledgement(self) -> bool:
        return any(f.oversized for f in self.files)

    def to_public(self) -> dict:
        files = [asdict(f) for f in self.files[:PREVIEW_FILE_LIMIT]]
        return {
            "preview_id": self.preview_id,
            "fingerprint": self.fingerprint,
            "mode": self.mode,
            "filter_column": self.filter_column,
            "group_columns": self.group_columns,
            "row_limit": self.row_limit,
            "oversize_policy": self.oversize_policy,
            "output_prefix": self.output_prefix,
            "total_rows": self.total_rows,
            "part_count": len(self.files),
            "filter_count": self.filter_count,
            "group_count": self.group_count,
            "largest_group": self.largest_group,
            "files": files,
            "files_truncated": len(self.files) > len(files),
            "catalog_file": naming.CATALOG_NAME,
            "catalog_headers": self.catalog_headers,
            "warnings": self.warnings,
            "can_convert": not self.blocking,
            "requires_acknowledgement": self.requires_acknowledgement,
        }

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Plan":
        data = dict(data)
        data["files"] = [PlannedFile(**f) for f in data["files"]]
        return Plan(**data)


def _warn(severity: str, code: str, message: str) -> dict:
    return {"severity": severity, "code": code, "message": message}


def validate_request(req: PlanRequest, info: SourceInfo) -> tuple[PlanRequest, list[dict]]:
    notes: list[dict] = []
    if req.mode not in MODES:
        raise AppError("invalid_mode", f"Mode must be one of: {', '.join(MODES)}.")
    if req.oversize_policy not in OVERSIZE_POLICIES:
        raise AppError("invalid_policy", f"Oversize policy must be one of: {', '.join(OVERSIZE_POLICIES)}.")
    if req.mode != "single" and (not isinstance(req.row_limit, int) or req.row_limit < 1):
        raise AppError("invalid_row_limit", "The row limit must be a whole number of at least 1.")
    prefix = naming.validate_prefix(req.output_prefix)

    def check_column(name: str, role: str) -> None:
        col = info.column(name)
        if col is None:
            raise AppError("unknown_column", f"{role} column '{name}' is not in the source file. Inspect the file again.", 409)
        if not col.scalar:
            raise AppError("non_scalar_column", f"{role} column '{name}' has type {col.type}, which cannot be used for {role.lower()}.")

    filter_column = req.filter_column or None
    if filter_column:
        check_column(filter_column, "Filter")

    groups: list[str] = []
    if req.mode == "group":
        for g in req.group_columns:
            check_column(g, "Grouping")
            if g not in groups:
                groups.append(g)
        if filter_column in groups:
            groups.remove(filter_column)
            notes.append(_warn("info", "filter_in_groups", f"'{filter_column}' is the filter column, so it was removed from the grouping columns."))
        if not groups:
            raise AppError("groups_required", "Group-aware split needs at least one grouping column other than the filter column.")
    elif req.group_columns:
        notes.append(_warn("info", "groups_ignored", "Grouping columns only apply to group-aware split and were ignored."))

    clean = PlanRequest(
        mode=req.mode,
        filter_column=filter_column,
        group_columns=groups,
        row_limit=req.row_limit if req.mode != "single" else 0,
        oversize_policy=req.oversize_policy,
        output_prefix=prefix,
    )
    return clean, notes


def build_plan(
    req: PlanRequest,
    info: SourceInfo,
    plan_db: Path,
    temp_dir: Path,
    preview_id: str,
    memory_limit: str,
    threads: int,
) -> Plan:
    req, warnings = validate_request(req, info)
    plan_db.parent.mkdir(parents=True, exist_ok=True)
    con = connect(temp_dir, memory_limit, threads, database=str(plan_db))
    try:
        plan = _plan(con, req, info, preview_id, warnings)
        con.execute("CHECKPOINT")
        return plan
    except duckdb.Error as exc:
        raise friendly_duckdb_error(exc) from exc
    finally:
        con.close()


def _plan(con: duckdb.DuckDBPyConnection, req: PlanRequest, info: SourceInfo, preview_id: str, warnings: list[dict]) -> Plan:
    src = scan_sql(info)
    has_filter = req.filter_column is not None
    gcols = req.group_columns
    fexpr = qi(req.filter_column) if has_filter else "NULL"

    # One aggregate scan reading only the filter and grouping columns.
    if req.mode == "group":
        gsel = ", ".join(f"{qi(g)} AS k_g{i}" for i, g in enumerate(gcols))
        con.execute(f"CREATE TABLE agg AS SELECT {fexpr} AS k_f, {gsel}, count(*)::BIGINT AS n FROM {src} GROUP BY ALL")
        con.execute("CREATE TABLE fsum AS SELECT k_f, sum(n)::BIGINT AS n FROM agg GROUP BY k_f")
    elif has_filter:
        con.execute(f"CREATE TABLE fsum AS SELECT {fexpr} AS k_f, count(*)::BIGINT AS n FROM {src} GROUP BY ALL")
    else:
        con.execute("CREATE TABLE fsum AS SELECT NULL AS k_f, ?::BIGINT AS n", [info.row_count])

    con.execute(
        "CREATE TABLE filters AS SELECT k_f, CAST(k_f AS VARCHAR) AS raw, n, "
        "row_number() OVER (ORDER BY k_f ASC NULLS LAST)::BIGINT AS f_idx FROM fsum WHERE n > 0"
    )
    filters = con.execute("SELECT f_idx, raw, k_f IS NULL, n FROM filters ORDER BY f_idx").fetchall()
    total_rows = sum(int(r[3]) for r in filters)

    if total_rows == 0:
        return _empty_plan(con, req, info, preview_id, warnings)

    tokens = naming.filter_tokens([r[1] for r in filters]) if has_filter else [None] * len(filters)

    # Per filter: list of parts (part_no, rows, groups, largest, oversized, g_start, g_end).
    per_filter: dict[int, list[tuple]] = {}
    oversized_groups = 0
    group_count = 0
    largest_group = None

    if req.mode == "single":
        for f_idx, _, _, n in filters:
            per_filter[f_idx] = [(1, int(n), 0, 0, False, None, None)]
    elif req.mode == "rows":
        for f_idx, _, _, n in filters:
            parts = math.ceil(n / req.row_limit)
            if parts > MAX_PARTS:
                raise AppError("too_many_parts", f"This would create more than {MAX_PARTS:,} files. Increase the row limit.")
            per_filter[f_idx] = [
                (p + 1, int(min(req.row_limit, n - p * req.row_limit)), 0, 0, False, None, None) for p in range(parts)
            ]
    else:
        order = ", ".join(f"a.k_g{i} ASC NULLS LAST" for i in range(len(gcols)))
        con.execute(
            "CREATE TABLE grp AS SELECT a.*, f.f_idx, "
            f"row_number() OVER (PARTITION BY f.f_idx ORDER BY {order})::BIGINT AS g_idx "
            "FROM agg a JOIN filters f ON a.k_f IS NOT DISTINCT FROM f.k_f"
        )
        con.execute("DROP TABLE agg")
        group_count = con.execute("SELECT count(*) FROM grp").fetchone()[0]
        per_filter, oversized_groups = _next_fit(con, req)
        largest_group = _largest_group(con, req, filters)

    # Assign global part ids and filenames, with per-filter numbering.
    files: list[PlannedFile] = []
    part_rows: list[tuple] = []
    filter_rows: list[tuple] = []
    next_id = 1
    for (f_idx, raw, is_null, _n), token in zip(filters, tokens):
        parts = per_filter.get(f_idx, [])
        width = naming.part_width(len(parts))
        filter_rows.append((f_idx, next_id, len(parts)))
        for part_no, rows, groups, largest, oversized, g_start, g_end in parts:
            name = naming.file_name(req.output_prefix, req.mode, token, part_no, width)
            files.append(
                PlannedFile(
                    part_id=next_id,
                    file_name=name,
                    filter_value=raw if has_filter else None,
                    filter_is_null=bool(is_null) if has_filter else False,
                    part_no=part_no,
                    rows=rows,
                    groups=groups,
                    largest_group_rows=largest,
                    oversized=oversized,
                )
            )
            part_rows.append((next_id, f_idx, part_no, g_start, g_end, rows))
            next_id += 1
        if len(files) > MAX_PARTS:
            raise AppError("too_many_parts", f"This would create more than {MAX_PARTS:,} files. Increase the row limit.")

    _store_parts(con, req, part_rows, filter_rows)

    # Warnings.
    if oversized_groups:
        if req.oversize_policy == "strict":
            lg = largest_group or {}
            warnings.append(
                _warn(
                    "blocking",
                    "oversized_group",
                    f"{oversized_groups:,} group(s) exceed the {req.row_limit:,}-row limit (largest: {lg.get('rows', 0):,} rows). "
                    "Strict mode never splits a group. Raise the row limit, choose other grouping columns, "
                    "or switch to group-priority to give each oversized group its own file.",
                )
            )
        else:
            warnings.append(
                _warn(
                    "warning",
                    "oversized_parts",
                    f"{oversized_groups:,} group(s) exceed the {req.row_limit:,}-row limit and will each get a dedicated "
                    "oversized file. You must acknowledge this before converting.",
                )
            )
    excel = [f for f in files if f.rows > EXCEL_MAX_DATA_ROWS]
    if excel:
        warnings.append(
            _warn(
                "warning",
                "excel_limit",
                f"{len(excel):,} file(s) have more than {EXCEL_MAX_DATA_ROWS:,} data rows. Excel cannot open all rows of these files.",
            )
        )
    if has_filter and len(filters) > 1_000:
        warnings.append(_warn("warning", "many_filter_values", f"The filter column has {len(filters):,} distinct values, so at least that many files will be created."))
    if has_filter and any(r[2] for r in filters):
        warnings.append(_warn("info", "null_filter", f"Rows where '{req.filter_column}' is empty (NULL) go to files named {naming.NULL_TOKEN}."))

    return Plan(
        preview_id=preview_id,
        fingerprint=info.fingerprint,
        mode=req.mode,
        filter_column=req.filter_column,
        group_columns=gcols,
        row_limit=req.row_limit,
        oversize_policy=req.oversize_policy,
        output_prefix=req.output_prefix,
        total_rows=total_rows,
        filter_count=len(filters) if has_filter else 0,
        group_count=int(group_count),
        files=files,
        largest_group=largest_group,
        warnings=warnings,
        catalog_headers=naming.catalog_headers(req.filter_column, gcols),
    )


def _next_fit(con: duckdb.DuckDBPyConnection, req: PlanRequest) -> tuple[dict[int, list[tuple]], int]:
    """Sequential next-fit over groups sorted deterministically within each filter.

    Streams (f_idx, g_idx, n) in batches; each part is a contiguous g_idx range.
    """
    limit = req.row_limit
    priority = req.oversize_policy == "group_priority"
    per_filter: dict[int, list[tuple]] = {}
    oversized = 0
    cur_f = None
    cur = None  # [rows, groups, largest, g_start, g_end]

    def close(f_idx: int) -> None:
        nonlocal cur
        if cur and cur[1]:
            parts = per_filter.setdefault(f_idx, [])
            parts.append((len(parts) + 1, cur[0], cur[1], cur[2], False, cur[3], cur[4]))
        cur = None

    result = con.execute("SELECT f_idx, g_idx, n FROM grp ORDER BY f_idx, g_idx")
    while True:
        batch = result.fetchmany(FETCH_BATCH)
        if not batch:
            break
        for f_idx, g_idx, n in batch:
            if f_idx != cur_f:
                if cur_f is not None:
                    close(cur_f)
                cur_f = f_idx
            if n > limit:
                oversized += 1
                if priority:
                    close(f_idx)
                    parts = per_filter.setdefault(f_idx, [])
                    parts.append((len(parts) + 1, int(n), 1, int(n), True, g_idx, g_idx))
                continue  # strict: plan is blocked; skip allocation.
            if cur and cur[0] + n > limit:
                close(f_idx)
            if cur is None:
                cur = [0, 0, 0, g_idx, g_idx]
            cur[0] += int(n)
            cur[1] += 1
            cur[2] = max(cur[2], int(n))
            cur[4] = g_idx
    if cur_f is not None:
        close(cur_f)
    return per_filter, oversized


def _largest_group(con: duckdb.DuckDBPyConnection, req: PlanRequest, filters: list[tuple]) -> dict | None:
    cols = ", ".join(f"CAST(k_g{i} AS VARCHAR)" for i in range(len(req.group_columns)))
    row = con.execute(f"SELECT f_idx, n, {cols} FROM grp ORDER BY n DESC, f_idx, g_idx LIMIT 1").fetchone()
    if not row:
        return None
    raw_filter = next((f[1] for f in filters if f[0] == row[0]), None)
    return {
        "filter_value": raw_filter if req.filter_column else None,
        "values": dict(zip(req.group_columns, row[2:])),
        "rows": int(row[1]),
    }


def _store_parts(con: duckdb.DuckDBPyConnection, req: PlanRequest, part_rows: list[tuple], filter_rows: list[tuple]) -> None:
    con.execute("CREATE TABLE filter_parts(f_idx BIGINT, part_base BIGINT, part_count BIGINT)")
    if filter_rows:
        con.executemany("INSERT INTO filter_parts VALUES (?, ?, ?)", filter_rows)
    con.execute(
        "CREATE TABLE filters2 AS SELECT f.*, p.part_base, p.part_count FROM filters f JOIN filter_parts p USING (f_idx)"
    )
    con.execute("DROP TABLE filters")
    con.execute("ALTER TABLE filters2 RENAME TO filters")
    con.execute("DROP TABLE filter_parts")
    con.execute("DROP TABLE IF EXISTS fsum")
    if req.mode != "group":
        return
    con.execute("CREATE TABLE parts(part_id BIGINT, f_idx BIGINT, part_no BIGINT, g_start BIGINT, g_end BIGINT, rows BIGINT)")
    con.executemany("INSERT INTO parts VALUES (?, ?, ?, ?, ?, ?)", part_rows)
    gsel = ", ".join(f"g.k_g{i}" for i in range(len(req.group_columns)))
    con.execute(
        f"CREATE TABLE mapping AS SELECT g.k_f, {gsel}, g.n, g.f_idx, g.g_idx, p.part_id FROM grp g "
        "JOIN parts p ON g.f_idx = p.f_idx AND g.g_idx BETWEEN p.g_start AND p.g_end"
    )


def _empty_plan(con: duckdb.DuckDBPyConnection, req: PlanRequest, info: SourceInfo, preview_id: str, warnings: list[dict]) -> Plan:
    """A valid empty source produces one header-only file and a zero-count catalogue entry."""
    name = naming.file_name(req.output_prefix, req.mode, None, 1, 2)
    con.execute("DROP TABLE IF EXISTS filters")
    con.execute("CREATE TABLE filters(k_f VARCHAR, raw VARCHAR, n BIGINT, f_idx BIGINT, part_base BIGINT, part_count BIGINT)")
    warnings.append(_warn("info", "empty_source", "The source has no rows. One header-only file will be created."))
    return Plan(
        preview_id=preview_id,
        fingerprint=info.fingerprint,
        mode=req.mode,
        filter_column=req.filter_column,
        group_columns=req.group_columns,
        row_limit=req.row_limit,
        oversize_policy=req.oversize_policy,
        output_prefix=req.output_prefix,
        total_rows=0,
        filter_count=0,
        group_count=0,
        files=[PlannedFile(1, name, None, False, 1, 0, 0, 0, False)],
        largest_group=None,
        warnings=warnings,
        catalog_headers=naming.catalog_headers(req.filter_column, req.group_columns),
    )

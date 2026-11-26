"""Stage 1 inspection: schema, row count and fingerprint from Parquet metadata only (PRD 04).

The source is either one .parquet file or a folder of .parquet shards (e.g. a BigQuery
export of 000000000000.parquet, 000000000001.parquet, ...). Shards are read together as
one dataset.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import duckdb

from .db import connect, ql
from .errors import AppError, friendly_duckdb_error

_NON_SCALAR_PREFIXES = ("STRUCT", "MAP", "UNION", "LIST", "ARRAY", "VARIANT")
_NON_SCALAR_TYPES = {"BLOB", "BIT", "GEOMETRY", "NULL"}
SAMPLE_FILES = 20


def is_scalar_type(type_name: str) -> bool:
    t = type_name.strip().upper()
    if "[" in t or t.startswith(_NON_SCALAR_PREFIXES):
        return False
    return t not in _NON_SCALAR_TYPES


@dataclass
class Column:
    name: str
    type: str
    scalar: bool


@dataclass
class SourceInfo:
    path: str
    file_name: str
    is_folder: bool
    files: list[list]  # [path, size_bytes, modified_ns] per Parquet file, sorted by path
    size_bytes: int
    modified_ns: int
    row_count: int
    row_groups: int
    uncompressed_bytes: int
    created_by: str | None
    columns: list[Column]
    fingerprint: str

    def to_public(self) -> dict:
        data = asdict(self)
        data.pop("modified_ns")
        data.pop("files")
        data["file_count"] = len(self.files)
        data["sample_files"] = [os.path.relpath(f[0], self.path) if self.is_folder else Path(f[0]).name for f in self.files[:SAMPLE_FILES]]
        return data

    def to_spec(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_spec(data: dict) -> "SourceInfo":
        return SourceInfo(**{**data, "columns": [Column(**c) for c in data["columns"]]})

    def column(self, name: str) -> Column | None:
        return next((c for c in self.columns if c.name == name), None)


def scan_sql(info: SourceInfo) -> str:
    """read_parquet() over the source file or all shards, as a SQL fragment with quoted literals."""
    paths = [f[0] for f in info.files]
    if len(paths) == 1:
        return f"read_parquet({ql(paths[0])})"
    return "read_parquet([" + ", ".join(ql(p) for p in paths) + "], union_by_name = true)"


def _skip(rel: Path) -> bool:
    # Hidden/temp folders and marker files (e.g. _SUCCESS, _temporary, .staging).
    return any(part.startswith((".", "_")) for part in rel.parts)


def list_parquet_files(path: Path) -> list[list]:
    if not path.exists():
        raise AppError("source_not_found", f"File or folder not found: {path}", 404)
    if path.is_file():
        if path.suffix.lower() != ".parquet":
            raise AppError("source_not_parquet", "Choose a .parquet file or a folder that contains .parquet files.")
        found = [path]
    else:
        try:
            found = sorted(
                (p for p in path.rglob("*") if p.is_file() and p.suffix.lower() == ".parquet" and not _skip(p.relative_to(path))),
                key=lambda p: str(p).casefold(),
            )
        except OSError as exc:
            raise AppError("source_unreadable", f"Windows denied reading the folder: {exc}", 403) from exc
        if not found:
            raise AppError(
                "no_parquet_files",
                "No .parquet files were found in this folder (or its subfolders). Shard files must end in .parquet.",
            )
    files = []
    for p in found:
        try:
            st = p.stat()
            with open(p, "rb") as fh:
                fh.read(4)
        except OSError as exc:
            raise AppError("source_unreadable", f"Windows denied reading {p}: {exc}", 403) from exc
        files.append([str(p), st.st_size, st.st_mtime_ns])
    return files


def compute_fingerprint(path: Path, files: list[list], rows: int, columns: list[Column]) -> str:
    payload = json.dumps(
        [os.path.normcase(str(path)), [[os.path.normcase(f[0]), f[1], f[2]] for f in files], rows, [[c.name, c.type] for c in columns]],
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def inspect_source(path: Path, temp_dir: Path, memory_limit: str, threads: int) -> SourceInfo:
    files = list_parquet_files(path)
    file_list = "[" + ", ".join(ql(f[0]) for f in files) + "]"
    partial = SourceInfo(str(path), path.name, path.is_dir(), files, 0, 0, 0, 0, 0, None, [], "")
    con = connect(temp_dir, memory_limit, threads)
    try:
        described = con.execute(f"DESCRIBE SELECT * FROM {scan_sql(partial)}").fetchall()
        rows, row_groups, created_by = con.execute(
            f"SELECT coalesce(sum(num_rows), 0), coalesce(sum(num_row_groups), 0), min(created_by) FROM parquet_file_metadata({file_list})"
        ).fetchone()
        uncompressed = con.execute(
            f"SELECT coalesce(sum(total_uncompressed_size), 0) FROM parquet_metadata({file_list})"
        ).fetchone()[0]
    except duckdb.Error as exc:
        raise friendly_duckdb_error(exc) from exc
    finally:
        con.close()

    columns = [Column(name=r[0], type=r[1], scalar=is_scalar_type(r[1])) for r in described]
    return SourceInfo(
        path=str(path),
        file_name=path.name,
        is_folder=path.is_dir(),
        files=files,
        size_bytes=sum(f[1] for f in files),
        modified_ns=max(f[2] for f in files),
        row_count=int(rows),
        row_groups=int(row_groups),
        uncompressed_bytes=int(uncompressed),
        created_by=created_by,
        columns=columns,
        fingerprint=compute_fingerprint(path, files, int(rows), columns),
    )


def current_fingerprint(info: SourceInfo, temp_dir: Path, memory_limit: str, threads: int) -> str:
    """Detect a source that changed since inspection (any shard added, removed or modified)."""
    path = Path(info.path)
    try:
        files = list_parquet_files(path)
    except AppError as exc:
        raise AppError("source_changed", f"The source changed since it was inspected: {exc.message} Inspect it again.", 409) from exc
    if files == info.files:
        return info.fingerprint
    return inspect_source(path, temp_dir, memory_limit, threads).fingerprint

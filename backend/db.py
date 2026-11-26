"""DuckDB connection setup and SQL quoting helpers."""

from __future__ import annotations

from pathlib import Path

import duckdb


def qi(name: str) -> str:
    """Quote an identifier. Column names come from the inspected schema only."""
    return '"' + name.replace('"', '""') + '"'


def ql(value: str) -> str:
    """Quote a string literal (used where DuckDB does not accept parameters, e.g. COPY targets)."""
    return "'" + value.replace("'", "''") + "'"


def connect(temp_dir: Path, memory_limit: str, threads: int, database: str = ":memory:") -> duckdb.DuckDBPyConnection:
    temp_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(
        database,
        config={
            "autoinstall_known_extensions": False,
            "autoload_known_extensions": False,
        },
    )
    con.execute(f"SET memory_limit = {ql(memory_limit)}")
    con.execute(f"SET threads = {int(threads)}")
    con.execute(f"SET temp_directory = {ql(str(temp_dir))}")
    con.execute("SET preserve_insertion_order = false")
    con.execute("SET enable_progress_bar = true")
    con.execute("SET enable_progress_bar_print = false")
    return con

"""User-facing error type shared by the API and the worker."""

from __future__ import annotations


class AppError(Exception):
    """An error with a stable code and a message a non-technical user can act on."""

    def __init__(self, code: str, message: str, status: int = 400, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}

    def to_dict(self) -> dict:
        out = {"code": self.code, "message": self.message}
        if self.details:
            out["details"] = self.details
        return out


def friendly_duckdb_error(exc: Exception) -> AppError:
    """Map DuckDB exceptions to actionable messages."""
    text = str(exc)
    name = type(exc).__name__
    lowered = text.lower()
    if "OutOfMemory" in name or "out of memory" in lowered:
        return AppError(
            "out_of_memory",
            "The conversion ran out of memory. Close other applications, choose fewer grouping "
            "columns, or lower memory_limit/threads in config.json.",
            500,
        )
    if "no space left" in lowered or "not enough space" in lowered or "disk is full" in lowered:
        return AppError("disk_full", "The disk ran out of space. Free up space on the destination drive and try again.", 500)
    if "permission" in lowered or "access is denied" in lowered:
        return AppError("permission_denied", f"Windows denied access to a file: {text}", 500)
    if any(s in lowered for s in ("magic bytes", "not a parquet file", "invalid parquet", "to be a parquet file", "parquet file is corrupt")):
        return AppError("invalid_parquet", "The file is not a valid Parquet file.", 400)
    return AppError("engine_error", f"DuckDB error: {text}", 500)

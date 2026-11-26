"""Output filename rules (PRD 08, FR-11).

Template: <prefix>_<filter_value>_partXX.csv. Filter values become Windows-safe
tokens; the raw values are kept in catalog.csv.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from .errors import AppError

CATALOG_NAME = "catalog.csv"
NULL_TOKEN = "__NULL__"
EMPTY_TOKEN = "__EMPTY__"
MAX_PREFIX = 100
MAX_TOKEN = 60

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
_RESERVED |= {f"COM{i}" for i in "123456789¹²³"} | {f"LPT{i}" for i in "123456789¹²³"}


def _short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def is_reserved_name(stem: str) -> bool:
    return stem.split(".")[0].rstrip(" ").upper() in _RESERVED


def validate_prefix(prefix: str | None) -> str:
    value = unicodedata.normalize("NFC", (prefix or "").strip())
    if not value:
        raise AppError("invalid_prefix", "Enter a filename prefix.")
    if len(value) > MAX_PREFIX:
        raise AppError("invalid_prefix", f"The prefix is too long (maximum {MAX_PREFIX} characters).")
    bad = sorted(set(_INVALID.findall(value)))
    if bad:
        shown = " ".join(repr(c)[1:-1] for c in bad)
        raise AppError("invalid_prefix", f"The prefix contains characters Windows does not allow in filenames: {shown}")
    if value.endswith("."):
        raise AppError("invalid_prefix", "The prefix cannot end with a dot.")
    if is_reserved_name(value):
        raise AppError("invalid_prefix", f"'{value}' is a reserved Windows device name.")
    if value.casefold() == "catalog":
        raise AppError("invalid_prefix", "'catalog' is reserved for catalog.csv. Choose another prefix.")
    return value


def sanitize_token(raw: str) -> str:
    text = unicodedata.normalize("NFC", raw)
    token = _INVALID.sub("_", text).strip(" ").rstrip(".")
    if not token:
        token = "_"
    if len(token) > MAX_TOKEN:
        token = token[: MAX_TOKEN - 9].rstrip(" .") + "~" + _short_hash(raw)
    return token


def filter_tokens(values: list[str | None]) -> list[str]:
    """Map raw filter values (None = NULL) to unique, case-insensitively distinct tokens.

    Values whose tokens collide (after sanitisation or case folding) all get a stable
    ~hash suffix derived from the raw value, so the result does not depend on order.
    """
    base = [NULL_TOKEN if v is None else EMPTY_TOKEN if v == "" else sanitize_token(v) for v in values]
    owners: dict[str, set] = {}
    for raw, tok in zip(values, base):
        owners.setdefault(tok.casefold(), set()).add(raw)
    tokens = []
    for raw, tok in zip(values, base):
        if len(owners[tok.casefold()]) > 1:
            key = "\x00NULL" if raw is None else "V" + raw
            tok = f"{tok}~{_short_hash(key)}"
        tokens.append(tok)
    folded = [t.casefold() for t in tokens]
    if len(set(folded)) != len(folded):
        raise AppError("filename_collision", "Filter values could not be turned into unique filenames.")
    return tokens


def part_width(part_count: int) -> int:
    return max(2, len(str(part_count)))


def file_name(prefix: str, mode: str, token: str | None, part_no: int, width: int) -> str:
    if mode == "single" and token is None:
        return f"{prefix}.csv"
    if token is None:
        return f"{prefix}_part{part_no:0{width}d}.csv"
    return f"{prefix}_{token}_part{part_no:0{width}d}.csv"


def catalog_headers(filter_column: str | None, group_columns: list[str]) -> list[str]:
    """file_name, optional filter column, grouping columns, row_count; reserved names disambiguated."""
    source_cols = ([filter_column] if filter_column else []) + [g for g in group_columns if g != filter_column]
    taken = {"file_name", "row_count"}
    headers = ["file_name"]
    for col in source_cols:
        name = col
        while name.casefold() in taken:
            name = f"source_{name}"
        taken.add(name.casefold())
        headers.append(name)
    headers.append("row_count")
    return headers

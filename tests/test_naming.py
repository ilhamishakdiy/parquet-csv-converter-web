import pytest

from backend import naming
from backend.errors import AppError


@pytest.mark.parametrize("prefix", ["", "  ", "a/b", "x:y", 'q"', "CON", "con.txt", "LPT1", "catalog", "Catalog", "ends."])
def test_invalid_prefixes_rejected(prefix):
    with pytest.raises(AppError):
        naming.validate_prefix(prefix)


def test_valid_prefix_kept():
    assert naming.validate_prefix(" Malaysia_Sales_Nov2026 ") == "Malaysia_Sales_Nov2026"
    assert naming.validate_prefix("Jualan_Mélange_数据") == "Jualan_Mélange_数据"


def test_tokens_null_empty_unicode_invalid():
    tokens = naming.filter_tokens(["HARDWARE", None, "", "Café/Bar", "数据", "a:b*c"])
    assert tokens[0] == "HARDWARE"
    assert tokens[1] == naming.NULL_TOKEN
    assert tokens[2] == naming.EMPTY_TOKEN
    assert tokens[3] == "Café_Bar"
    assert tokens[4] == "数据"
    assert tokens[5] == "a_b_c"


def test_tokens_case_and_sanitisation_collisions_get_stable_suffix():
    values = ["Hardware", "HARDWARE", "a/b", "a:b", "unique"]
    tokens = naming.filter_tokens(values)
    assert len({t.casefold() for t in tokens}) == len(tokens)
    assert tokens[4] == "unique"
    assert all("~" in t for t in tokens[:4])
    # Stable regardless of order.
    again = naming.filter_tokens(list(reversed(values)))
    assert dict(zip(values, tokens)) == dict(zip(reversed(values), again))


def test_real_value_matching_null_token_is_disambiguated():
    tokens = naming.filter_tokens([None, "__NULL__"])
    assert tokens[0] != tokens[1]


def test_long_value_truncated_with_hash():
    token = naming.sanitize_token("x" * 500)
    assert len(token) <= naming.MAX_TOKEN and "~" in token


def test_file_names_and_width():
    assert naming.file_name("P", "single", None, 1, 2) == "P.csv"
    assert naming.file_name("P", "single", "HW", 1, 2) == "P_HW_part01.csv"
    assert naming.file_name("P", "rows", None, 3, 2) == "P_part03.csv"
    assert naming.part_width(99) == 2 and naming.part_width(100) == 3
    assert naming.file_name("P", "group", "HW", 7, 3) == "P_HW_part007.csv"


def test_catalog_headers_dedupe_and_reserved():
    assert naming.catalog_headers("department_code", ["store_code"]) == ["file_name", "department_code", "store_code", "row_count"]
    assert naming.catalog_headers(None, []) == ["file_name", "row_count"]
    assert naming.catalog_headers("row_count", ["file_name"]) == ["file_name", "source_row_count", "source_file_name", "row_count"]

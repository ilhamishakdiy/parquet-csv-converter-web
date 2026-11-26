"""End-to-end acceptance tests (PRD 06) through the API and the worker subprocess."""

import csv
import io
import sys
import time
import types

import duckdb
import pytest

from backend.errors import AppError

from .conftest import convert, inspect, make_parquet, preview, read_outputs

PRD_EXAMPLE = """
SELECT dept AS department_code, store AS store_code, i AS id, 'v' || i AS val
FROM (VALUES ('HARDWARE','MY001',250), ('HARDWARE','MY002',300), ('HARDWARE','MY003',400),
             ('ELECTRICAL','MY001',150), ('ELECTRICAL','MY004',350)) t(dept, store, n),
     range(n) r(i)
"""


def test_prd_example_filter_and_group(env):
    src = make_parquet(env.root / "sales.parquet", PRD_EXAMPLE)
    info = inspect(env.client, src)
    assert info["row_count"] == 1450
    assert [c["name"] for c in info["columns"]] == ["department_code", "store_code", "id", "val"]

    plan = preview(
        env.client, info["fingerprint"], mode="group", filter_column="department_code",
        group_columns=["store_code"], row_limit=800, output_prefix="Malaysia_Sales_Nov2026",
    )
    assert plan["can_convert"]
    files = {f["file_name"]: f["rows"] for f in plan["files"]}
    assert files == {
        "Malaysia_Sales_Nov2026_ELECTRICAL_part01.csv": 500,
        "Malaysia_Sales_Nov2026_HARDWARE_part01.csv": 550,
        "Malaysia_Sales_Nov2026_HARDWARE_part02.csv": 400,
    }
    assert plan["largest_group"]["rows"] == 400

    out = env.root / "out"
    status, result = convert(env.client, plan["preview_id"], out)
    assert status["state"] == "succeeded", status
    assert result["total_rows"] == 1450 == result["source_rows"]
    assert result["validation"]["status"] == "passed"

    with open(out / "_catalog.csv", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["file_name", "department_code", "store_code", "row_count"]
    assert rows[1:] == [
        ["Malaysia_Sales_Nov2026_ELECTRICAL_part01.csv", "ELECTRICAL", "MY001", "150"],
        ["Malaysia_Sales_Nov2026_ELECTRICAL_part01.csv", "ELECTRICAL", "MY004", "350"],
        ["Malaysia_Sales_Nov2026_HARDWARE_part01.csv", "HARDWARE", "MY001", "250"],
        ["Malaysia_Sales_Nov2026_HARDWARE_part01.csv", "HARDWARE", "MY002", "300"],
        ["Malaysia_Sales_Nov2026_HARDWARE_part02.csv", "HARDWARE", "MY003", "400"],
    ]

    con, rel = read_outputs(out)
    # Filter isolation: each part holds exactly one filter value.
    assert con.execute(f"SELECT max(c) FROM (SELECT filename, count(DISTINCT department_code) c FROM {rel} GROUP BY 1)").fetchone()[0] == 1
    # Group integrity: each filter+group tuple maps to one part.
    assert con.execute(f"SELECT max(c) FROM (SELECT department_code, store_code, count(DISTINCT filename) c FROM {rel} GROUP BY ALL)").fetchone()[0] == 1
    # Conservation: no loss or duplicates.
    assert con.execute(f"SELECT count(*), count(DISTINCT department_code || '|' || store_code || '|' || id) FROM {rel}").fetchone() == (1450, 1450)
    assert sorted(p.name for p in out.iterdir()) == sorted(list(files) + ["_catalog.csv"])


def test_null_keys_and_csv_correctness(env):
    src = make_parquet(
        env.root / "tricky.parquet",
        """SELECT * FROM (VALUES
            (1, 'A', 'g1', 'comma, inside'),
            (2, 'A', NULL, 'line1
line2'),
            (3, NULL, 'g1', 'quote "here"'),
            (4, NULL, NULL, 'Unicode: café 数据 ✓'),
            (5, '', 'g2', ''),
            (6, '', 'g2', NULL)) t(id, f, g, txt)""",
    )
    info = inspect(env.client, src)
    plan = preview(env.client, info["fingerprint"], mode="group", filter_column="f", group_columns=["g"], row_limit=10)
    names = sorted(f["file_name"] for f in plan["files"])
    assert names == ["Out_A_part01.csv", "Out___EMPTY___part01.csv", "Out___NULL___part01.csv"]

    out = env.root / "out"
    status, result = convert(env.client, plan["preview_id"], out)
    assert status["state"] == "succeeded", status

    # Multiline, quotes, commas, Unicode and NULL vs empty survive a round trip.
    con = duckdb.connect()
    back = con.execute(
        f"SELECT id::INT, f, g, txt FROM read_csv('{out}/Out_*_part01.csv', header=true, all_varchar=true, allow_quoted_nulls=false) ORDER BY 1"
    ).fetchall()
    orig = con.execute(f"SELECT id, f, g, txt FROM read_parquet('{src}') ORDER BY 1").fetchall()
    assert back == orig

    text = (out / "_catalog.csv").read_text(encoding="utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == ["file_name", "f", "g", "row_count"]
    # NULL is an empty unquoted field; empty string is written as "".
    assert 'Out___EMPTY___part01.csv,"",g2,2' in text
    assert "Out___NULL___part01.csv,,,1" in text
    assert sum(int(r[-1]) for r in rows[1:]) == 6


def test_rows_mode_with_filter_resets_numbering_and_100_plus_parts(env):
    src = make_parquet(env.root / "r.parquet", "SELECT CASE WHEN i < 1050 THEN 'X' ELSE 'Y' END AS k, i FROM range(1100) r(i)")
    info = inspect(env.client, src)
    plan = preview(env.client, info["fingerprint"], mode="rows", filter_column="k", row_limit=10)
    names = [f["file_name"] for f in plan["files"]]
    assert plan["part_count"] == 105 + 5
    assert names[0] == "Out_X_part001.csv" and names[104] == "Out_X_part105.csv"
    assert names[105] == "Out_Y_part01.csv" and names[-1] == "Out_Y_part05.csv"

    out = env.root / "out"
    status, result = convert(env.client, plan["preview_id"], out)
    assert status["state"] == "succeeded", status
    assert all(f["rows"] == 10 for f in result["files"])
    con, rel = read_outputs(out)
    assert con.execute(f"SELECT count(*), count(DISTINCT i) FROM {rel}").fetchone() == (1100, 1100)
    assert con.execute(f"SELECT max(c) FROM (SELECT filename, count(DISTINCT k) c FROM {rel} GROUP BY 1)").fetchone()[0] == 1


def test_rows_mode_no_filter_and_single_modes(env):
    src = make_parquet(env.root / "s.parquet", "SELECT i, i % 3 AS k FROM range(25) r(i)")
    info = inspect(env.client, src)

    plan = preview(env.client, info["fingerprint"], mode="rows", row_limit=10)
    assert [(f["file_name"], f["rows"]) for f in plan["files"]] == [("Out_part01.csv", 10), ("Out_part02.csv", 10), ("Out_part03.csv", 5)]
    status, _ = convert(env.client, plan["preview_id"], env.root / "a")
    assert status["state"] == "succeeded", status

    plan = preview(env.client, info["fingerprint"], mode="single")
    assert [f["file_name"] for f in plan["files"]] == ["Out.csv"]
    status, result = convert(env.client, plan["preview_id"], env.root / "b")
    assert status["state"] == "succeeded" and result["total_rows"] == 25
    assert (env.root / "b" / "_catalog.csv").read_text(encoding="utf-8").splitlines() == ["file_name,row_count", "Out.csv,25"]

    plan = preview(env.client, info["fingerprint"], mode="single", filter_column="k")
    assert [f["file_name"] for f in plan["files"]] == ["Out_0_part01.csv", "Out_1_part01.csv", "Out_2_part01.csv"]
    status, _ = convert(env.client, plan["preview_id"], env.root / "c")
    assert status["state"] == "succeeded", status
    assert (env.root / "c" / "_catalog.csv").read_text(encoding="utf-8").splitlines()[0] == "file_name,k,row_count"


def test_boundary_and_oversize_policies(env):
    src = make_parquet(env.root / "o.parquet", "SELECT g, i FROM (VALUES ('a', 5), ('b', 5), ('c', 12), ('d', 3)) t(g, n), range(n) r(i)")
    info = inspect(env.client, src)

    exact = preview(env.client, info["fingerprint"], group_columns=["g"], row_limit=12)
    assert exact["can_convert"] and not exact["requires_acknowledgement"]
    assert [f["rows"] for f in exact["files"]] == [10, 12, 3]  # a group of exactly the limit fits

    strict =preview(env.client, info["fingerprint"], group_columns=["g"], row_limit=10, oversize_policy="strict")
    assert not strict["can_convert"]
    assert any(w["code"] == "oversized_group" and w["severity"] == "blocking" for w in strict["warnings"])
    r = env.client.post("/jobs", json={"preview_id": strict["preview_id"], "destination_dir": str(env.root / "x")})
    assert r.status_code == 409

    prio = preview(env.client, info["fingerprint"], group_columns=["g"], row_limit=10, oversize_policy="group_priority")
    assert prio["can_convert"] and prio["requires_acknowledgement"]
    # a+b = 10 fits exactly; c gets a dedicated oversized part; d starts a new part.
    assert [(f["rows"], f["oversized"]) for f in prio["files"]] == [(10, False), (12, True), (3, False)]
    r = env.client.post("/jobs", json={"preview_id": prio["preview_id"], "destination_dir": str(env.root / "y")})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "acknowledge_required"
    status, result = convert(env.client, prio["preview_id"], env.root / "y", acknowledge_oversize=True)
    assert status["state"] == "succeeded", status
    assert result["oversized_files"] == ["Out_part02.csv"]


def test_empty_source_header_only(env):
    src = make_parquet(env.root / "e.parquet", "SELECT 1::INT AS a, 'x' AS b WHERE false")
    info = inspect(env.client, src)
    assert info["row_count"] == 0
    plan = preview(env.client, info["fingerprint"], group_columns=["b"], filter_column="a", row_limit=5)
    out = env.root / "out"
    status, result = convert(env.client, plan["preview_id"], out)
    assert status["state"] == "succeeded", status
    assert (out / "Out_part01.csv").read_text(encoding="utf-8") == "a,b\n"
    assert (out / "_catalog.csv").read_text(encoding="utf-8").splitlines() == ["file_name,a,b,row_count", "Out_part01.csv,,,0"]


def test_collision_never_overwrites_and_new_folder(env):
    src = make_parquet(env.root / "c.parquet", "SELECT i FROM range(5) r(i)")
    info = inspect(env.client, src)
    out = env.root / "out"
    out.mkdir()
    (out / "_catalog.csv").write_text("keep me", encoding="utf-8")
    plan = preview(env.client, info["fingerprint"], mode="single")
    r = env.client.post("/jobs", json={"preview_id": plan["preview_id"], "destination_dir": str(out)})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "destination_collision"
    assert (out / "_catalog.csv").read_text(encoding="utf-8") == "keep me"

    status, result = convert(env.client, plan["preview_id"], out, collision_policy="new_folder")
    assert status["state"] == "succeeded"
    assert result["destination"].startswith(str(out)) and result["destination"] != str(out)


def test_overwrite_replaces_only_same_names(env):
    src = make_parquet(env.root / "o.parquet", "SELECT i FROM range(5) r(i)")
    info = inspect(env.client, src)
    out = env.root / "out"
    out.mkdir()
    (out / "_catalog.csv").write_text("old catalog", encoding="utf-8")
    (out / "Out.csv").write_text("old data", encoding="utf-8")
    (out / "notes.txt").write_text("unrelated", encoding="utf-8")
    plan = preview(env.client, info["fingerprint"], mode="single", output_prefix="Out")
    status, result = convert(env.client, plan["preview_id"], out, collision_policy="overwrite")
    assert status["state"] == "succeeded", status
    assert result["destination"] == str(out)
    assert (out / "Out.csv").read_text(encoding="utf-8").splitlines() == ["i", "0", "1", "2", "3", "4"]
    assert (out / "_catalog.csv").read_text(encoding="utf-8").startswith("file_name,row_count")
    assert (out / "notes.txt").read_text(encoding="utf-8") == "unrelated"
    assert sorted(p.name for p in out.iterdir()) == ["Out.csv", "_catalog.csv", "notes.txt"]


def test_overwrite_locked_file_restores_originals(env, tmp_path):
    from backend import exporter

    if sys.platform != "win32":
        pytest.skip("Windows file locking")
    dest = tmp_path / "dest"
    staging = dest / ".pqcsv-staging-x"
    staging.mkdir(parents=True)
    (dest / "_catalog.csv").write_text("old catalog", encoding="utf-8")
    (dest / "P.csv").write_text("old data", encoding="utf-8")
    (staging / "_catalog.csv").write_text("new catalog", encoding="utf-8")
    (staging / "P.csv").write_text("new data", encoding="utf-8")

    plan = types.SimpleNamespace(files=[types.SimpleNamespace(file_name="P.csv")])
    with open(dest / "_catalog.csv", "rb"):  # held open: Windows refuses the rename
        with pytest.raises(AppError) as err:
            exporter._publish(plan, staging, dest, overwrite=True)
    assert err.value.code == "destination_locked"
    assert (dest / "P.csv").read_text(encoding="utf-8") == "old data"
    assert (dest / "_catalog.csv").read_text(encoding="utf-8") == "old catalog"
    assert (staging / "P.csv").read_text(encoding="utf-8") == "new data"


def test_schema_change_invalidates_preview(env):
    path = env.root / "d.parquet"
    make_parquet(path, "SELECT 1 AS a")
    first = inspect(env.client, path)
    plan = preview(env.client, first["fingerprint"], mode="single")
    make_parquet(path, "SELECT 1 AS a, 'n' AS new_col")
    r = env.client.post("/jobs", json={"preview_id": plan["preview_id"], "destination_dir": str(env.root / "o")})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "source_changed"
    second = inspect(env.client, path)
    assert second["fingerprint"] != first["fingerprint"]
    assert [c["name"] for c in second["columns"]] == ["a", "new_col"]


def test_invalid_sources(env):
    bad = env.root / "bad.parquet"
    for content in ("x", "not parquet " * 1000):
        bad.write_text(content, encoding="utf-8")
        r = env.client.post("/inspect", json={"source_path": str(bad)})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_parquet", r.text
    r = env.client.post("/inspect", json={"source_path": str(env.root / "missing.parquet")})
    assert r.status_code == 404
    r = env.client.post("/inspect", json={"source_path": "relative\\file.parquet"})
    assert r.json()["detail"]["code"] == "relative_path"


def test_cancellation_publishes_nothing(env):
    src = make_parquet(env.root / "big.parquet", "SELECT i, i % 50 AS g, md5(i::VARCHAR) AS h FROM range(6000000) r(i)")
    info = inspect(env.client, src)
    plan = preview(env.client, info["fingerprint"], mode="group", group_columns=["g"], row_limit=200000)
    out = env.root / "out"
    r = env.client.post("/jobs", json={"preview_id": plan["preview_id"], "destination_dir": str(out)})
    job_id = r.json()["job_id"]
    for _ in range(300):  # cancel while DuckDB is writing parts
        if env.client.get(f"/jobs/{job_id}").json()["stage"] == "exporting":
            break
        time.sleep(0.05)
    assert env.client.get(f"/jobs/{job_id}").json()["stage"] == "exporting"
    st = env.client.post(f"/jobs/{job_id}/cancel").json()
    assert st["state"] == "cancelled"
    assert env.client.get(f"/jobs/{job_id}/result").status_code == 409
    assert not out.exists() or list(out.iterdir()) == []

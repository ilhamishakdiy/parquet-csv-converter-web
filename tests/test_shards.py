"""Folder sources: sharded Parquet exports such as BigQuery's 000000000000.parquet, 000000000001.parquet, ..."""

from .conftest import convert, inspect, make_parquet, preview, read_outputs


def _bigquery_export(folder):
    folder.mkdir()
    for i, (dept, n) in enumerate([("HARDWARE", 300), ("HARDWARE", 250), ("ELECTRICAL", 400)]):
        make_parquet(
            folder / f"{i:012d}.parquet",
            f"SELECT '{dept}' AS department_code, 'MY00' || (r % 4) AS store_code, {i} AS shard, r AS id FROM range({n}) t(r)",
        )
    (folder / "_SUCCESS").write_text("", encoding="utf-8")
    (folder / "_temporary").mkdir()
    make_parquet(folder / "_temporary" / "partial.parquet", "SELECT 'X' AS department_code")
    return folder


def test_folder_of_shards_is_one_dataset(env):
    folder = _bigquery_export(env.root / "bq_export")
    info = inspect(env.client, folder)
    assert info["is_folder"] and info["file_count"] == 3
    assert info["sample_files"] == ["000000000000.parquet", "000000000001.parquet", "000000000002.parquet"]
    assert info["row_count"] == 950

    plan = preview(env.client, info["fingerprint"], filter_column="department_code", group_columns=["store_code"], row_limit=300)
    assert plan["can_convert"]
    out = env.root / "out"
    status, result = convert(env.client, plan["preview_id"], out)
    assert status["state"] == "succeeded", status
    assert result["total_rows"] == 950

    con, rel = read_outputs(out)
    assert con.execute(f"SELECT count(*), count(DISTINCT shard || '|' || id) FROM {rel}").fetchone() == (950, 950)
    assert con.execute(f"SELECT count(*) FROM {rel} WHERE department_code = 'X'").fetchone()[0] == 0
    assert con.execute(
        f"SELECT max(c) FROM (SELECT department_code, store_code, count(DISTINCT filename) c FROM {rel} GROUP BY ALL)"
    ).fetchone()[0] == 1


def test_added_shard_invalidates_preview(env):
    folder = _bigquery_export(env.root / "bq_export")
    info = inspect(env.client, folder)
    plan = preview(env.client, info["fingerprint"], mode="single")
    make_parquet(folder / "000000000003.parquet", "SELECT 'HARDWARE' AS department_code, 'MY009' AS store_code, 3 AS shard, 1::BIGINT AS id")
    r = env.client.post("/jobs", json={"preview_id": plan["preview_id"], "destination_dir": str(env.root / "o")})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "source_changed"


def test_folder_without_parquet_files(env):
    empty = env.root / "nothing"
    empty.mkdir()
    (empty / "readme.txt").write_text("x", encoding="utf-8")
    r = env.client.post("/inspect", json={"source_path": str(empty)})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "no_parquet_files"

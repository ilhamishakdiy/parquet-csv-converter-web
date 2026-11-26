from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.settings import Config

TOKEN = "test-token-123"
BASE_URL = "http://127.0.0.1:8765"


def make_parquet(path: Path, sql: str) -> Path:
    con = duckdb.connect()
    con.execute(f"COPY ({sql}) TO '{path}' (FORMAT parquet)")
    con.close()
    return path


def read_outputs(folder: Path, pattern: str = "*_part*.csv"):
    """All data rows from the CSV parts with their file name, as VARCHAR."""
    con = duckdb.connect()
    glob = str(folder / pattern).replace("'", "''")
    return con, f"read_csv('{glob}', header=true, all_varchar=true, filename=true, union_by_name=true)"


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    cfg = Config(
        approved_roots=[root],
        frontend_url="http://localhost:3000/",
        data_dir=tmp_path / "appdata",
        memory_limit="1GB",
        threads=2,
    )
    app = create_app(cfg, TOKEN)
    with TestClient(app, base_url=BASE_URL) as client:
        client.headers["Authorization"] = f"Bearer {TOKEN}"
        yield SimpleNamespace(client=client, root=root, cfg=cfg, tmp=tmp_path)


def inspect(client, path: Path) -> dict:
    r = client.post("/inspect", json={"source_path": str(path)})
    assert r.status_code == 200, r.text
    return r.json()


def preview(client, fingerprint: str, **kw) -> dict:
    body = {"fingerprint": fingerprint, "mode": "group", "output_prefix": "Out", **kw}
    r = client.post("/preview", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def wait_job(client, job_id: str, timeout: float = 120) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = client.get(f"/jobs/{job_id}").json()
        if st["state"] != "running":
            return st
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} did not finish")


def convert(client, preview_id: str, dest: Path, **kw) -> tuple[dict, dict | None]:
    r = client.post("/jobs", json={"preview_id": preview_id, "destination_dir": str(dest), **kw})
    assert r.status_code == 200, r.text
    st = wait_job(client, r.json()["job_id"])
    res = client.get(f"/jobs/{r.json()['job_id']}/result")
    return st, (res.json() if res.status_code == 200 else None)

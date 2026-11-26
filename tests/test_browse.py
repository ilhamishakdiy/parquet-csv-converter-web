import json
import subprocess

from backend import dialog


class FakeRun:
    def __init__(self, path):
        self.path = path
        self.args = None

    def __call__(self, args, **kwargs):
        self.args = args
        out = json.dumps({"path": self.path}).encode()
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr=b"")


def test_browse_requires_token(env):
    r = env.client.post("/browse", json={"kind": "file"}, headers={"Authorization": ""})
    assert r.status_code == 401


def test_browse_returns_picked_path_and_starts_in_nearest_existing_folder(env, monkeypatch):
    fake = FakeRun("C:\\Data\\sales.parquet")
    monkeypatch.setattr(dialog.subprocess, "run", fake)
    r = env.client.post("/browse", json={"kind": "file", "initial_path": str(env.root / "missing" / "x.parquet")})
    assert r.status_code == 200 and r.json()["path"] == "C:\\Data\\sales.parquet"
    assert fake.args[-3:] == ["backend.dialog", "file", str(env.root)]


def test_picked_shard_offers_whole_folder(env, monkeypatch):
    folder = env.root / "bq"
    folder.mkdir()
    for name in ("000000000000.parquet", "000000000001.parquet", "000000000002.parquet", "_SUCCESS"):
        (folder / name).write_bytes(b"")
    monkeypatch.setattr(dialog.subprocess, "run", FakeRun(str(folder / "000000000001.parquet")))
    body = env.client.post("/browse", json={"kind": "file"}).json()
    assert body["folder"] == str(folder) and body["folder_parquet_count"] == 3

    lone = env.root / "single"
    lone.mkdir()
    (lone / "only.parquet").write_bytes(b"")
    monkeypatch.setattr(dialog.subprocess, "run", FakeRun(str(lone / "only.parquet")))
    body = env.client.post("/browse", json={"kind": "file"}).json()
    assert body == {"path": str(lone / "only.parquet"), "folder": None, "folder_parquet_count": 0}


def test_browse_cancel_and_bad_kind(env, monkeypatch):
    monkeypatch.setattr(dialog.subprocess, "run", FakeRun(None))
    assert env.client.post("/browse", json={"kind": "folder"}).json()["path"] is None
    assert env.client.post("/browse", json={"kind": "everything"}).status_code == 422


def test_open_only_paths_of_a_succeeded_job(env, monkeypatch):
    from .conftest import convert, inspect, make_parquet, preview

    opened = []
    monkeypatch.setattr(dialog, "open_in_shell", lambda p: opened.append(p))
    src = make_parquet(env.root / "a.parquet", "SELECT 1 AS a")
    plan = preview(env.client, inspect(env.client, src)["fingerprint"], mode="single")
    out = env.root / "out"
    status, result = convert(env.client, plan["preview_id"], out)
    job_id = result["job_id"]

    assert env.client.post("/open", json={"job_id": job_id, "target": "folder"}).status_code == 200
    assert env.client.post("/open", json={"job_id": job_id, "target": "catalog"}).status_code == 200
    assert [str(p) for p in opened] == [str(out), str(out / "_catalog.csv")]

    assert env.client.post("/open", json={"job_id": "nope", "target": "folder"}).status_code == 404
    assert env.client.post("/open", json={"job_id": job_id, "target": "C:\\Windows"}).status_code == 422
    assert env.client.post("/open", json={"job_id": job_id, "target": "folder", "path": "C:\\"}).status_code == 422
    assert env.client.post("/open", json={"job_id": job_id, "target": "folder"}, headers={"Authorization": ""}).status_code == 401


def test_browse_reports_dialog_failure(env, monkeypatch):
    def broken(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"Traceback...\nTclError: no display")

    monkeypatch.setattr(dialog.subprocess, "run", broken)
    r = env.client.post("/browse", json={"kind": "file"})
    assert r.status_code == 500 and "TclError" in r.json()["detail"]["message"]

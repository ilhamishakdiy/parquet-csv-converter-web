from .conftest import BASE_URL, make_parquet


def test_health_is_public_but_unpaired_without_token(env):
    r = env.client.get("/health", headers={"Authorization": ""})
    assert r.status_code == 200 and r.json()["paired"] is False
    assert "approved_roots" not in r.json()
    assert env.client.get("/health").json()["paired"] is True


def test_invalid_token_rejected(env):
    r = env.client.post("/inspect", json={"source_path": "C:\\x.parquet"}, headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "invalid_token"
    r = env.client.get("/jobs/abc", headers={"Authorization": ""})
    assert r.status_code == 401


def test_host_header_validated(env):
    r = env.client.get("/health", headers={"Host": "evil.example:8765"})
    assert r.status_code == 421


def test_untrusted_origin_rejected_and_trusted_gets_exact_cors(env):
    r = env.client.get("/health", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and "access-control-allow-origin" not in r.headers
    r = env.client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_private_network_preflight(env):
    r = env.client.options(
        "/inspect",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
            "Access-Control-Request-Private-Network": "true",
        },
    )
    assert r.status_code == 204
    assert r.headers["access-control-allow-private-network"] == "true"
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_unapproved_traversal_and_network_paths(env):
    outside = env.tmp / "outside.parquet"
    make_parquet(outside, "SELECT 1 AS a")
    for path, code in [
        (str(outside), "path_not_approved"),
        (str(env.root / ".." / "outside.parquet"), "path_not_approved"),
        ("\\\\server\\share\\x.parquet", "network_path"),
        ("\\\\?\\C:\\x.parquet", "invalid_path"),
    ]:
        r = env.client.post("/inspect", json={"source_path": path})
        assert r.json()["detail"]["code"] == code, (path, r.text)


def test_unknown_fields_and_sql_like_columns_rejected(env):
    src = make_parquet(env.root / "a.parquet", "SELECT 1 AS a")
    fp = env.client.post("/inspect", json={"source_path": str(src)}).json()["fingerprint"]
    r = env.client.post("/preview", json={"fingerprint": fp, "mode": "group", "group_columns": ['a"; DROP TABLE x; --'], "output_prefix": "P"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "unknown_column"
    r = env.client.post("/preview", json={"fingerprint": fp, "mode": "single", "output_prefix": "P", "sql": "select 1"})
    assert r.status_code == 422


def test_base_url_is_loopback():
    assert BASE_URL == "http://127.0.0.1:8765"

"""Real public cohort + explicitly synthetic attack/isolation tests."""

import shutil
import sqlite3

from fastapi.testclient import TestClient
import pytest

from quantgraph.api.web import create_web_app
from quantgraph.api.web_read_model import calculation_axis, revision, safe_url
from quantgraph.db import project_root
from quantgraph.graph.public import public_release


@pytest.fixture(scope="module")
def public_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("web-public-isolation")
    source = project_root()
    for rel in ("datasets/raw/source_lock.json", "models/id_registry.json"):
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, dest)
    shutil.copytree(
        source / "datasets/raw/sources/qlib", root / "datasets/raw/sources/qlib"
    )
    shutil.copytree(source / "datasets/public", root / "datasets/public")
    return root


@pytest.fixture(scope="module")
def client(public_root):
    return TestClient(create_web_app(public_root))


def test_real_counts_and_independent_statuses(client):
    meta = client.get("/v1/web/meta").json()
    assert meta["mode"] == "PUBLIC"
    assert meta["counts"] == dict(variant=508, concept=43, strategy=0)
    assert meta["result_count"] == 0
    row = client.get("/v1/web/search").json()["items"][0]
    assert len(row["statuses"]) == 5
    assert row["statuses"]["catalog"] == "已收录"
    assert row["statuses"]["result"] == "尚未研究"
    assert row["economic_logic"] is None


@pytest.mark.parametrize(
    "query", ["均线", "MA5", "ma5", "Alpha158:MA5", "Mean($close, 5)", "ＭＡ５"]
)
def test_multilingual_name_alias_description_search(client, query):
    result = client.get("/v1/web/search", params={"q": query}).json()
    assert result["total"] > 0
    assert any(r["name"] == "MA5" for r in result["items"])


def test_filters_empty_pagination_and_invalid_parameters(client):
    first = client.get("/v1/web/search?page=1&page_size=3").json()
    second = client.get("/v1/web/search?page=2&page_size=3").json()
    assert len(first["items"]) == len(second["items"]) == 3
    assert not {r["entity_id"] for r in first["items"]} & {
        r["entity_id"] for r in second["items"]
    }
    assert first["total"] == second["total"] == 508
    assert client.get("/v1/web/search?page=999").json()["items"] == []
    for query in (
        "q=zz-no-such-record",
        "market=crypto",
        "kind=strategy",
        "result_status=researched",
    ):
        result = client.get("/v1/web/search?" + query).json()
        assert result["items"] == [] and result["total"] == 0
    assert all(
        "close" in r["required_fields"]
        for r in client.get("/v1/web/search?field=close").json()["items"]
    )
    assert all(
        r["family"] == "MA"
        for r in client.get("/v1/web/search?family=MA").json()["items"]
    )
    for params in ("page=0", "page_size=51", "kind=private", "q=" + "a" * 201):
        response = client.get("/v1/web/search?" + params)
        assert response.status_code == 422
        assert response.json() == {"detail": "请求参数格式不正确"}


def test_search_detail_comparison_real_public_data(client):
    items = client.get("/v1/web/search?family=MA").json()["items"]
    row = items[0]
    detail = client.get("/v1/web/entities/variant/" + row["entity_id"]).json()
    assert detail["formula"] and detail["implementations"] and detail["papers"]
    assert detail["economic_logic"] is None and detail["results"]["items"] == []
    assert detail["definition_revision"] == row["definition_revision"]
    assert all(
        e["source"] is None or e["source"].startswith("https://")
        for e in detail["relations"]
    )
    assert detail["concept"]["kind"] == "concept"
    assert all(e["kind"] == "variant" for e in detail["related"])
    refs = [("ref", "variant/" + i["entity_id"]) for i in items[:4]]
    assert len(client.get("/v1/web/compare", params=refs).json()["items"]) == 4
    assert client.get("/v1/web/compare", params=refs[:1]).status_code == 422
    assert client.get("/v1/web/compare", params=refs + [refs[0]]).status_code == 422
    assert client.get("/v1/web/compare", params=[refs[0], refs[0]]).status_code == 422
    assert client.get("/v1/web/entities/variant/missing").status_code == 404
    assert (
        client.get(
            "/v1/web/compare", params=[refs[0], ("ref", "variant/missing")]
        ).status_code
        == 404
    )


def test_missing_comparison_fields_stay_missing(client):
    concepts = client.get("/v1/web/search?kind=concept&page_size=2").json()["items"]
    result = client.get(
        "/v1/web/compare",
        params=[("ref", "concept/" + c["entity_id"]) for c in concepts],
    ).json()
    assert all(
        r["formula"] is None and r["parameters"] == {} and r["axis"] == "未补充"
        for r in result["items"]
    )


def test_bookmark_import_revision_validation(client):
    row = client.get("/v1/web/search?q=MA5").json()["items"][0]
    ref = {k: row[k] for k in ("entity_type", "entity_id", "definition_revision")}
    assert (
        client.post("/v1/web/references/resolve", json={"refs": [ref]}).status_code
        == 200
    )
    for bad in (
        {**ref, "entity_id": "TEST_ONLY_PRIVATE_SENTINEL"},
        {**ref, "definition_revision": "stale"},
    ):
        response = client.post("/v1/web/references/resolve", json={"refs": [bad]})
        assert response.status_code == 409
        assert "SENTINEL" not in response.text
    assert (
        client.post(
            "/v1/web/references/resolve", json={"refs": [ref] * 501}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v1/web/references/resolve", json={"refs": [], "profile": "research"}
        ).status_code
        == 422
    )


def test_real_results_empty_and_contract_unavailability_not_faked(client):
    result = client.get("/v1/web/results").json()
    assert result["items"] == [] and result["total"] == 0
    assert set(result["levels"]) == {
        "computational_test",
        "exploratory",
        "retrospective",
        "confirmatory",
    }
    assert client.get("/v1/web/results?kind=variant&eid=missing").status_code == 404
    assert client.get("/v1/web/results?kind=variant").status_code == 422
    # No local second schema is invented while task A is absent.
    assert client.get("/v1/web/meta").json()["contracts"]["export_enabled"] is False
    assert client.post("/v1/web/research-requests", json={}).status_code == 503


def test_public_ignores_private_profile_database_journal_and_client_switches(
    public_root, monkeypatch
):
    private = public_root / "datasets/curated/current"
    (private / "commercial").mkdir(parents=True)
    for dest in (
        private / "quantgraph.sqlite",
        private / "commercial/quantgraph.sqlite",
    ):
        with sqlite3.connect(dest) as con:
            con.execute("CREATE TABLE private_records (value TEXT)")
            con.execute(
                "INSERT INTO private_records VALUES (?)",
                ("TEST_ONLY_PRIVATE_SENTINEL",),
            )
    monkeypatch.setenv("QUANTGRAPH_PROFILE", "research")
    monkeypatch.setenv(
        "QUANTGRAPH_INGEST_DB", str(private / "must-not-be-opened.sqlite")
    )
    app = create_web_app(public_root)
    c = TestClient(app)
    assert (
        app.state.db.path
        == (public_release(public_root) / "quantgraph.sqlite").resolve()
    )
    for path in [
        "/v1/web/meta",
        "/v1/stats",
        "/health",
        "/v1/ontology/factor-concepts",
        "/v1/web/search",
        "/v1/factors",
        "/v1/relationships/TEST_ONLY_PRIVATE_SENTINEL",
    ]:
        response = c.get(path + "?profile=research&mode=PRIVATE&database=private")
        assert response.status_code == 200 and "SENTINEL" not in response.text
    assert c.get("/v1/stats").json()["counts"]["factor_variants"] == 508
    assert c.get("/v1/web/search?q=TEST_ONLY_PRIVATE_SENTINEL").json()["total"] == 0
    assert c.get("/v1/entities/Source/TEST_ONLY_PRIVATE_SENTINEL").status_code == 404
    paths = c.get("/openapi.json").json()["paths"]
    assert not any("ingest" in p or "admin" in p for p in paths)
    assert not (private / "must-not-be-opened.sqlite").exists()


def test_tampered_public_release_fails_closed(public_root, tmp_path):
    shutil.copytree(public_root / "datasets", tmp_path / "datasets")
    shutil.copytree(public_root / "models", tmp_path / "models")
    with (public_release(tmp_path) / "factor_variants.jsonl").open("a") as file:
        file.write('{"name":"TEST_ONLY_PRIVATE_SENTINEL"}\n')
    with pytest.raises(ValueError, match="checksums"):
        create_web_app(tmp_path)


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,evil",
        "//evil.example",
        "file:///etc/passwd",
        "https://user:password@example.com",
        "https://example.com\n/evil",
        "https://[malformed",
    ],
)
def test_reject_dangerous_links(url):
    assert safe_url(url) is None


def test_security_headers_no_private_path_error(client, monkeypatch):
    response = client.get("/v1/web/meta")
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert "unsafe-inline" not in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert (
        client.get("/health", headers={"host": "attacker.example"}).status_code == 400
    )

    def fail(**kwargs):
        raise RuntimeError("TEST_ONLY_PRIVATE_SENTINEL /private/path")

    monkeypatch.setattr(client.app.state.web_model, "search", fail)
    c = TestClient(client.app, raise_server_exceptions=False)
    response = c.get("/v1/web/search")
    assert (
        response.status_code == 500
        and "SENTINEL" not in response.text
        and "/private/" not in response.text
    )


def test_definition_revision_and_axis_are_not_guessed():
    assert revision({"raw_formula": "a", "created_at": "old"}) == revision(
        {"raw_formula": "a", "created_at": "new"}
    )
    assert revision({"raw_formula": "a"}) != revision({"raw_formula": "b"})
    assert (
        calculation_axis({"formula_ast": {"op": "rank"}, "dialect": "unknown"})
        == "未补充"
    )
    assert safe_url("https://example.org/a#b") == "https://example.org/a#b"

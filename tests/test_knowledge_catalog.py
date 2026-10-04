"""Unified discovery, identity, attribution and read-only query contracts."""
from copy import deepcopy
import json
from pathlib import Path
from shutil import copytree
from uuid import NAMESPACE_URL, uuid5

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from quantgraph.api.app import create_app
from quantgraph.api.knowledge import install_knowledge
from quantgraph.db import AmbiguousAliasError
from quantgraph.graph.knowledge_catalog import KnowledgeCatalog, stable_id
from quantgraph.graph.metadata_catalog import canonical_hash
from quantgraph.graph.metadata_pilot import digest, encoded


ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else encoded(value)
    path.write_bytes(raw)
    return dict(sha256=digest(raw), bytes=len(raw))


def load(path):
    return json.loads(path.read_bytes())


def reviewed_record(namespace="Example/Library", native="Volume"):
    row = load(ROOT / "metadata/public-web/20261004-v1/factors/AverageDollarVolume.json")
    row.update(identity_namespace=namespace, record_id=native, native_source_id=native,
               name="Synthetic volume definition", lab=None, relations=[])
    source = row["sources"][0]
    source.update(id="synthetic-code", revision="a" * 40, sha256="1" * 64,
                  url=f"https://github.com/{namespace}/blob/{'a' * 40}/src/volume.py")
    row["sources"] = [source]
    for field in row["factor_fields"].values():
        field["evidence"] = [source["id"]]
    return row


def write_reviewed(root, batch_name, records, matches=None):
    """Create a small independent upstream-review batch with no raw snapshot."""
    folder = root / "metadata/web" / batch_name
    write(folder / "schema.json", (ROOT / "metadata/schema.json").read_bytes())
    refs, declarations, locks = [], [], {}
    for row in records:
        namespace = digest(row["identity_namespace"].encode())[:24]
        kind = "strategies" if row["entity_type"] == "strategy" else "factors"
        path = f"{kind}/{namespace}/{row['record_id']}.json"
        ref = dict(path=path, **write(folder / path, row), **{
            key: row[key] for key in ("identity_namespace", "record_id", "entity_type")
        })
        refs.append(ref)
        declarations.append({**{key: ref[key] for key in ("path", "identity_namespace", "record_id", "entity_type")},
            "catalog_matches": deepcopy((matches or {}).get(row["record_id"], [])),
            "markets": ["EQUITY"], "representation": "SOURCE_IMPLEMENTATION",
            "new_economic_concept_claimed": False,
            "admission": dict(metadata="SOURCE_CODE_REVIEWED", computation_semantics="NOT_EXECUTED",
                              economic_validity="NOT_TESTED", commercial_profile="REVIEW_REQUIRED")})
        for source in row["sources"]:
            locks[source["id"]] = dict(id=source["id"], repository=row["identity_namespace"],
                revision=source["revision"], path="src/volume.py", url=source["url"],
                fetch_url=f"https://raw.githubusercontent.com/{row['identity_namespace']}/{source['revision']}/src/volume.py",
                sha256=source["sha256"], bytes=123, role="SOURCE_CODE", license_spdx="MIT",
                retrieved_at="2026-10-04T01:00:00+00:00",
                private_snapshot_path=f"datasets/raw/sources/public-web/{batch_name}/volume.py")
    write(folder / "index.json", dict(schema_version="quantgraph-metadata-index/v1", records=refs))
    write(folder / "manifest.json", dict(schema_version="quantgraph-public-web-batch/v1",
        batch_id=batch_name, records=declarations))
    write(folder / "source-lock.json", dict(schema_version="quantgraph-public-web-source-lock/v1",
        batch_id=batch_name, files=list(locks.values())))


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repository"
    metadata = root / "metadata/corpus/first/metadata"
    for schema in ("schema.json", "source-record.schema.json"):
        write(metadata / schema, (ROOT / "metadata" / schema).read_bytes())
    original = load(ROOT / "metadata/corpus-checkpoints/grokbot-6973-20261003/batches/batch-0001-v2/metadata/source-records/M0050.json")
    refs = []
    for number, rid in enumerate(("M9901", "M9902"), 1):
        row = deepcopy(original)
        values = {key: "" for key in row["reported_fields"]}
        values.update(id=rid, 名称="Synthetic " + rid, 市场="EQUITY", 规则="Synthetic rule needing review",
                      source_url="https://github.com/Example/Library/blob/main/src/volume.py")
        row.update(record_id=rid, native_source_id=rid)
        for key, value in values.items():
            row["reported_fields"][key]["value"] = value
        row["provenance"].update(csv_row_ordinal=number, row_sha256=canonical_hash(values),
                                 rule_sha256=digest(values["规则"].encode()))
        path = f"source-records/{rid}.json"
        refs.append(dict(path=path, **write(metadata / path, row), **{
            key: row[key] for key in ("record_id", "identity_namespace", "entity_type")
        }))
    write(metadata / "index.json", dict(schema_version="quantgraph-metadata-index/v1", records=refs))
    frozen_files = {
        str(path.relative_to(metadata.parent)): dict(sha256=digest(path.read_bytes()), bytes=path.stat().st_size)
        for path in metadata.rglob("*.json")
    }
    pin = write(metadata.parent / "manifest.json", dict(record_ids=["M9901", "M9902"], files=frozen_files))
    write(root / "metadata/corpus-index.json", dict(
        batches=[dict(path="corpus/first", record_count=2, manifest_sha256=pin["sha256"])],
        counts=dict(public_source_records=2)))

    original = load(metadata / "source-records/M9901.json")
    match = dict(record_id="M9901", source_record_path="metadata/corpus/first/metadata/source-records/M9901.json",
        row_sha256=original["provenance"]["row_sha256"], match_type="SAME_SOURCE_PATH",
        reason="Synthetic source locator match only", equivalence_claimed=False,
        role="SOURCE_LOCATOR_MATCH", confidence="HIGH",
        evidence=["catalog:M9901:row_sha256", "synthetic-code"],
        source=[original["reported_fields"]["source_url"]["value"]])
    write(root / "metadata/web/README.md", b"Synthetic review batches\n")
    write_reviewed(root, "first", [reviewed_record()], {"Volume": [match]})

    factor_index = load(ROOT / "metadata/factor-sources/index.json")
    template = load(ROOT / "metadata/factor-sources" / factor_index["records"][0]["path"])
    schema_pin = write(root / "metadata/factors/schema.json", (ROOT / "metadata/factor-sources/schema.json").read_bytes())
    refs = []
    for source_name, status, record_kind in (("qlib", "ALLOWED", "signal"), ("jkp", "REVIEW_REQUIRED", "placebo")):
        row = deepcopy(template)
        row.update(record_id="qkg:factor:" + str(uuid5(NAMESPACE_URL, "synthetic:" + source_name)),
                   name="Synthetic shared signal", native_source_ids=["SharedSignal"], record_kind=record_kind)
        row["sources"] = [row["sources"][0]]
        source_record_id = "qkg:record:" + str(uuid5(NAMESPACE_URL, "source:" + source_name))
        row["sources"][0].update(source_id=source_name, native_id="SharedSignal", record_id=source_record_id)
        row["identity"]["source_record_ids"] = [source_record_id]
        row["provenance"]["source_lines"] = [row["provenance"]["source_lines"][0]]
        row["provenance"]["source_lines"][0]["record_id"] = source_record_id
        row["rights"]["commercial_use"] = [status]
        row["sources"][0]["rights"]["commercial_use"] = status
        path = f"records/{row['record_id']}.json"
        refs.append(dict(path=path, record_id=row["record_id"], **write(root / "metadata/factors" / path, row)))
    write(root / "metadata/factors/index.json", dict(schema_version="quantgraph-factor-metadata-index/v1",
        records=refs, schema_reference=dict(path="schema.json", **schema_pin), license_notices=[],
        source_snapshot=deepcopy(factor_index["source_snapshot"]),
        counts=dict(variants=len(refs), source_records=len(refs))))
    write(root / "metadata/catalog.json", dict(schema_version="quantgraph-catalog-registry/v1", overlays=[],
        collections=[dict(id="sources", kind="csv_corpus", path="metadata/corpus-index.json"),
                     dict(id="web", kind="reviewed_batches", path="metadata/web"),
                     dict(id="factors", kind="factor_records", path="metadata/factors/index.json")]))
    return root


def test_evidence_aggregation_preserves_ids_and_does_not_count_versions_as_entries(repository):
    catalog = KnowledgeCatalog(repository)
    stats = catalog.stats()
    assert stats["unique_entries"] == 4
    assert stats["kinds"] == {"factor": 3, "unclassified": 1}
    assert stats["source_rows"] == {"csv": 2, "factor_sources": 2}
    assert stats["reviewed_representations"] == 1 and stats["factor_variants"] == 2
    reviewed = catalog.get("Example/Library:Volume")
    assert reviewed["entity_id"] == catalog.get("M9901")["entity_id"]
    assert len(reviewed["versions"]) == 2
    assert reviewed["current_version"] is None
    assert catalog.get("M9902")["kind"] == "unclassified"
    assert all(edge["equivalence_claimed"] is False for edge in catalog.relations("M9901"))


def test_source_and_status_filter_one_factor_directory_without_promoting_permissions(repository):
    catalog = KnowledgeCatalog(repository)
    assert catalog.search(kind="factor")["total"] == 3
    assert catalog.search(kind="factor", source="qlib")["total"] == 1
    beta = catalog.search(kind="factor", source="jkp", status="REVIEW_REQUIRED")["items"][0]
    assert beta["record_kinds"] == ["placebo"]
    assert catalog.search(kind="factor", source="jkp", status="ALLOWED")["total"] == 0
    assert catalog.search(status="VERIFIED")["total"] == 0
    assert catalog.search(kind="factor", record_kind="placebo")["total"] == 1
    assert catalog.search(kind="factor", market="equity", frequency="daily")["total"] == 2


def test_native_alias_ambiguity_requires_source_and_classification_never_changes_id(repository):
    catalog = KnowledgeCatalog(repository)
    with pytest.raises(AmbiguousAliasError):
        catalog.get("SharedSignal")
    assert catalog.get("qlib:SharedSignal")["entity_id"] != catalog.get("jkp:SharedSignal")["entity_id"]
    with pytest.raises(KeyError):
        catalog.get("no-such-entry")
    before = catalog.get("M9901")["entity_id"]
    registry = load(repository / "metadata/catalog.json")
    registry["collections"] = [c for c in registry["collections"] if c["kind"] != "reviewed_batches"]
    write(repository / "metadata/catalog.json", registry)
    source_only = KnowledgeCatalog(repository).get("M9901")
    assert source_only["entity_id"] == before and source_only["kind"] == "unclassified"


def test_dynamic_batches_keep_distinct_namespaces_and_all_versions(repository):
    original = KnowledgeCatalog(repository)
    row = reviewed_record("Other/Library", "Volume")
    row["sources"][0]["id"] = "other-code"
    for field in row["factor_fields"].values():
        field["evidence"] = ["other-code"]
    write_reviewed(repository, "second", [row])
    next_version = deepcopy(row)
    next_version["one_line"] = "Synthetic independently retained revised summary"
    write_reviewed(repository, "third", [next_version])
    catalog = KnowledgeCatalog(repository)
    assert catalog.stats()["unique_entries"] == original.stats()["unique_entries"] + 1
    assert catalog.get("Other/Library:Volume")["entity_id"] != catalog.get("Example/Library:Volume")["entity_id"]
    assert len(catalog.get("Other/Library:Volume")["versions"]) == 2
    assert catalog.get("Other/Library:Volume")["current_version"] is None
    with pytest.raises(AmbiguousAliasError):
        catalog.get("Volume")


def test_concept_overlap_is_a_relation_not_automatic_identity_merge(repository):
    path = repository / "metadata/web/first/manifest.json"
    manifest = load(path)
    match = manifest["records"][0]["catalog_matches"][0]
    match.update(match_type="POSSIBLE_CONCEPT_OVERLAP", confidence="MEDIUM",
                 role="CONCEPT_COMPARISON_ONLY_NOT_ASSERTED_FACTOR_USE")
    write(path, manifest)
    catalog = KnowledgeCatalog(repository)
    original, reviewed = catalog.get("M9901"), catalog.get("Example/Library:Volume")
    assert original["entity_id"] != reviewed["entity_id"]
    assert original["kind"] == "unclassified" and reviewed["kind"] == "factor"
    assert catalog.stats()["unique_entries"] == 5
    edge = catalog.relations("M9901")[0]
    assert edge["from_id"] != edge["to_id"] and edge["equivalence_claimed"] is False


def test_conflicting_classification_remains_visible_and_row_pinned(repository):
    source_path = repository / "metadata/corpus/first/metadata/source-records/M9901.json"
    source = load(source_path)
    view = dict(record_id="M9901", classification=dict(entity_type="strategy",
        row_sha256=source["provenance"]["row_sha256"], rule_sha256=source["provenance"]["rule_sha256"]),
        source=dict(path="corpus/first/metadata/source-records/M9901.json",
                    sha256=digest(source_path.read_bytes()), bytes=source_path.stat().st_size),
        view=dict(path="reading/M9901.md", **write(repository / "metadata/reading/M9901.md", b"Synthetic reading\n")))
    write(repository / "metadata/classification.json", dict(records=[view]))
    registry = load(repository / "metadata/catalog.json")
    registry["collections"].append(dict(id="reading", kind="classification", path="metadata/classification.json"))
    write(repository / "metadata/catalog.json", registry)
    catalog = KnowledgeCatalog(repository)
    row = catalog.get("M9901")
    assert row["classification_conflict"] is True and row["kind"] == "unclassified"
    assert {c["kind"] for c in row["classifications"]} == {"strategy", "factor", "unclassified"}
    assert catalog.stats()["reading_views"] == 1
    view["classification"]["row_sha256"] = "0" * 64
    write(repository / "metadata/classification.json", dict(records=[view]))
    with pytest.raises(ValueError, match="different source version"):
        KnowledgeCatalog(repository)


def test_duplicate_registry_location_cannot_inflate_counts(repository):
    registry = load(repository / "metadata/catalog.json")
    registry["collections"].append(dict(id="duplicate-location", kind="factor_records",
                                        path="metadata/factors/index.json"))
    write(repository / "metadata/catalog.json", registry)
    with pytest.raises(ValueError):
        KnowledgeCatalog(repository)


def test_factor_record_id_cannot_repeat_at_another_file_path(repository):
    folder = repository / "metadata/factors"
    index = load(folder / "index.json")
    duplicate = deepcopy(index["records"][0])
    raw = (folder / duplicate["path"]).read_bytes()
    duplicate["path"] = "records/another-location.json"
    duplicate.update(write(folder / duplicate["path"], raw))
    index["records"].append(duplicate)
    index["counts"]["variants"] += 1
    write(folder / "index.json", index)
    with pytest.raises(ValueError, match="Factor metadata identity mismatch"):
        KnowledgeCatalog(repository)


@pytest.mark.parametrize("collision", ["record-id", "source-native-id"])
def test_factor_source_identity_cannot_belong_to_different_variants(repository, collision):
    folder = repository / "metadata/factors"
    index = load(folder / "index.json")
    first = load(folder / index["records"][0]["path"])
    ref = index["records"][1]
    second = load(folder / ref["path"])
    if collision == "record-id":
        record_id = first["sources"][0]["record_id"]
        second["sources"][0]["record_id"] = record_id
        second["identity"]["source_record_ids"] = [record_id]
        second["provenance"]["source_lines"][0]["record_id"] = record_id
    else:
        # Keep a distinct source record ID; only the source's native identity collides.
        second["sources"][0]["source_id"] = first["sources"][0]["source_id"]
        second["sources"][0]["native_id"] = first["sources"][0]["native_id"]
    ref.update(write(folder / ref["path"], second))
    write(folder / "index.json", index)
    with pytest.raises(ValueError, match="Duplicate factor source identity"):
        KnowledgeCatalog(repository)


def test_factor_record_snapshot_must_match_its_collection_even_with_valid_file_hash(repository):
    folder = repository / "metadata/factors"
    index = load(folder / "index.json")
    ref = index["records"][0]
    row = load(folder / ref["path"])
    row["provenance"]["source_snapshot_sha256"] = "0" * 64
    ref.update(write(folder / ref["path"], row))
    write(folder / "index.json", index)
    with pytest.raises(ValueError, match="Factor source snapshot mismatch"):
        KnowledgeCatalog(repository)


@pytest.mark.parametrize("mapping", ["identity", "source-lines"])
def test_factor_source_record_ids_must_match_identity_and_line_provenance(repository, mapping):
    folder = repository / "metadata/factors"
    index = load(folder / "index.json")
    ref = index["records"][0]
    row = load(folder / ref["path"])
    unknown = "qkg:record:" + str(uuid5(NAMESPACE_URL, "unknown:source"))
    if mapping == "identity":
        row["identity"]["source_record_ids"] = [unknown]
    else:
        row["provenance"]["source_lines"][0]["record_id"] = unknown
    ref.update(write(folder / ref["path"], row))
    write(folder / "index.json", index)
    with pytest.raises(ValueError, match="Factor source identity mapping mismatch"):
        KnowledgeCatalog(repository)


def test_identical_factor_collection_at_second_location_keeps_unique_versions_and_counts(repository):
    before = KnowledgeCatalog(repository)
    copytree(repository / "metadata/factors", repository / "metadata/factor-mirror")
    registry = load(repository / "metadata/catalog.json")
    registry["collections"].append(dict(id="factor-mirror", kind="factor_records",
                                        path="metadata/factor-mirror/index.json"))
    write(repository / "metadata/catalog.json", registry)
    mirrored = KnowledgeCatalog(repository)
    for key in ("unique_entries", "factor_variants", "source_rows", "versions", "kinds"):
        assert mirrored.stats()[key] == before.stats()[key]
    for alias in ("qlib:SharedSignal", "jkp:SharedSignal"):
        assert mirrored.get(alias)["versions"] == before.get(alias)["versions"]
    assert mirrored.search(kind="factor")["total"] == before.search(kind="factor")["total"]


def test_csv_review_overlay_requires_explicit_source_and_metadata_version_pins(repository):
    row = reviewed_record("grokbot", "M9902")
    write_reviewed(repository, "native", [row])
    registry = load(repository / "metadata/catalog.json")
    registry["collections"] = [c for c in registry["collections"] if c["kind"] != "reviewed_batches"]
    registry["collections"].append(dict(id="native", kind="reviewed_metadata", path="metadata/web/native/index.json"))
    write(repository / "metadata/catalog.json", registry)
    with pytest.raises(ValueError):
        KnowledgeCatalog(repository)
    source = load(repository / "metadata/corpus/first/metadata/source-records/M9902.json")
    ref = load(repository / "metadata/web/native/index.json")["records"][0]
    registry["overlays"] = [dict(namespace="grokbot", native_id="M9902",
        row_sha256=source["provenance"]["row_sha256"], metadata_sha256=ref["sha256"])]
    write(repository / "metadata/catalog.json", registry)
    assert KnowledgeCatalog(repository).get("M9902")["kind"] == "factor"
    registry["overlays"][0]["metadata_sha256"] = "f" * 64
    write(repository / "metadata/catalog.json", registry)
    with pytest.raises(ValueError, match="version mismatch"):
        KnowledgeCatalog(repository)


@pytest.mark.parametrize("change", ["row-pin", "evidence", "equivalence", "hostname"])
def test_false_or_unresolved_source_matches_fail_closed(repository, change):
    path = repository / "metadata/web/first/manifest.json"
    manifest = load(path)
    match = manifest["records"][0]["catalog_matches"][0]
    if change == "row-pin":
        match["row_sha256"] = "f" * 64
    elif change == "evidence":
        match["evidence"] = ["imaginary-source"]
    elif change == "equivalence":
        match["equivalence_claimed"] = True
    else:
        row = reviewed_record()
        row["sources"][0]["url"] = row["sources"][0]["url"].replace("github.com", "evil.example")
        write_reviewed(repository, "first", [row], {"Volume": [match]})
    if change != "hostname":
        write(path, manifest)
    with pytest.raises(ValueError):
        KnowledgeCatalog(repository)


def test_mutable_source_ref_is_rejected_even_when_record_and_lock_agree(repository):
    declaration = load(repository / "metadata/web/first/manifest.json")["records"][0]
    row = reviewed_record()
    row["sources"][0]["revision"] = "master"
    row["sources"][0]["url"] = row["sources"][0]["url"].replace("a" * 40, "master")
    write_reviewed(repository, "first", [row], {"Volume": declaration["catalog_matches"]})
    with pytest.raises(ValueError):
        KnowledgeCatalog(repository)


def test_incomplete_new_batch_and_changed_indexed_bytes_are_not_silently_ignored(repository):
    write(repository / "metadata/web/incomplete/factors/unlisted.json", reviewed_record())
    with pytest.raises(ValueError):
        KnowledgeCatalog(repository)
    (repository / "metadata/web/incomplete/factors/unlisted.json").unlink()
    (repository / "metadata/web/incomplete/factors").rmdir()
    (repository / "metadata/web/incomplete").rmdir()
    ref = load(repository / "metadata/factors/index.json")["records"][0]
    target = repository / "metadata/factors" / ref["path"]
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="digest"):
        KnowledgeCatalog(repository)


def test_read_only_snapshot_pagination_and_defensive_copies(repository):
    write(repository / "runtime/catalog.sqlite", b"Do not import or open this sentinel")
    write(repository / "runtime/personal.sqlite", b"Preserve user notes")
    before = {str(p.relative_to(repository)): digest(p.read_bytes()) for p in repository.rglob("*") if p.is_file()}
    catalog = KnowledgeCatalog(repository)
    first = catalog.search(limit=2)
    second = catalog.search(limit=2, offset=2)
    assert len(first["items"] + second["items"]) == first["total"] == 4
    assert not {r["entity_id"] for r in first["items"]} & {r["entity_id"] for r in second["items"]}
    returned = catalog.get("M9901")
    returned["versions"].clear()
    assert len(catalog.get("M9901")["versions"]) == 2
    after = {str(p.relative_to(repository)): digest(p.read_bytes()) for p in repository.rglob("*") if p.is_file()}
    assert before == after


def test_http_queries_resolve_source_qualified_aliases_and_do_not_write(repository):
    app = FastAPI()
    install_knowledge(app, repository)
    client = TestClient(app)
    assert client.get("/v1/knowledge/stats").json()["unique_entries"] == 4
    lookup = client.get("/v1/knowledge/lookup", params={"identity": "Example/Library:Volume"})
    assert lookup.status_code == 200
    eid = lookup.json()["entity_id"]
    assert client.get(f"/v1/knowledge/{eid}").json()["entity_id"] == eid
    assert client.get(f"/v1/knowledge/{eid}/relations").json()["items"]
    assert client.get("/v1/knowledge/lookup", params={"identity": "SharedSignal"}).status_code == 409
    assert client.get("/v1/knowledge/missing").status_code == 404
    assert client.get("/v1/knowledge", params={"kind": "factor", "source": "jkp"}).json()["total"] == 1
    for params in ({"limit": 0}, {"offset": -1}, {"kind": "nonexistent"}):
        assert client.get("/v1/knowledge", params=params).status_code == 422
    assert client.post("/v1/knowledge", json={"name": "not authorized"}).status_code == 405


def test_cli_and_existing_graph_app_are_wired_to_unified_queries(repository, monkeypatch, capsys):
    from quantgraph.cli import main
    monkeypatch.setattr("sys.argv", ["quantgraph", "--root", str(repository), "catalog-search",
                                    "SharedSignal", "--kind", "factor", "--source", "jkp"])
    main()
    assert json.loads(capsys.readouterr().out)["total"] == 1
    app = create_app(ROOT)
    assert {"/v1/knowledge", "/v1/knowledge/stats", "/v1/knowledge/lookup"} <= {r.path for r in app.routes}
    public_app = create_app(ROOT, public_only=True)
    assert not any(r.path.startswith("/v1/knowledge") for r in public_app.routes)


def test_real_registry_reconciles_source_rows_and_keeps_one_factor_directory():
    catalog = KnowledgeCatalog(ROOT)
    stats = catalog.stats()
    corpus = load(ROOT / "metadata/corpus-index.json")
    factors = load(ROOT / "metadata/factor-sources/index.json")
    assert stats["source_rows"]["csv"] == corpus["counts"]["public_source_records"]
    assert stats["factor_variants"] == len(factors["records"])
    assert sum(stats["kinds"].values()) == stats["unique_entries"]
    assert stats["reading_views"] == len(load(ROOT / "metadata/directory-index.json")["records"])
    for source in factors["counts"]["source_variants"]:
        assert catalog.search(kind="factor", source=source)["total"] == factors["counts"]["source_variants"][source]
    assert catalog.get("M2904")["entity_id"] == catalog.get("QuantConnect/Lean:MovingAverageCrossAlgorithm")["entity_id"]
    for row in catalog.search(kind="factor", source="zipline")["items"]:
        assert "REVIEW_REQUIRED" in row["statuses"]["commercial_rights"]


def test_content_batch_keeps_identity_and_admission_separate_and_exposes_subtype(repository, monkeypatch, capsys):
    from quantgraph.cli import main
    from quantgraph.graph.classification_batch import build

    before = KnowledgeCatalog(repository)
    original = before.get("M9902")
    folder = repository / "metadata/classifications/synthetic"
    build(repository, folder, ["M9902"], [dict(record_id="M9902", kind="reference",
        subtype="technical_demo", reason="Synthetic reviewed demo for adapter integration",
        evidence=[dict(field="规则", quote="Synthetic rule needing review")])])
    registry = load(repository / "metadata/catalog.json")
    registry["collections"].append(dict(id="content", kind="classification_batch",
        path="metadata/classifications/synthetic/index.json"))
    write(repository / "metadata/catalog.json", registry)

    catalog = KnowledgeCatalog(repository)
    row = catalog.get("M9902")
    assert row["kind"] == "reference" and not row["classification_conflict"]
    assert row["entity_id"] == original["entity_id"]
    assert row["versions"] == original["versions"]
    assert row["content_subtypes"] == ["technical_demo"]
    for key in original["statuses"]:
        if key != "classification":
            assert row["statuses"][key] == original["statuses"][key]
    decision = next(c for c in row["classifications"] if c["status"] == "CONTENT_INFERRED")
    assert decision["definition_status"] == "UNVERIFIED"
    assert decision["evidence_quotes"] == [dict(field="规则", quote="Synthetic rule needing review")]
    assert catalog.stats()["classification_decisions"] == 1
    assert catalog.stats()["unique_entries"] == before.stats()["unique_entries"]
    assert catalog.search(kind="reference", subtype="technical_demo")["total"] == 1
    assert row["statuses"]["definition_verification"] == ["UNVERIFIED"]
    assert catalog.search(status="UNVERIFIED")["total"] == 1
    assert catalog.search(status="VERIFIED")["total"] == 0

    app = FastAPI()
    install_knowledge(app, repository)
    response = TestClient(app).get("/v1/knowledge", params={"kind": "reference", "subtype": "technical_demo", "status": "UNVERIFIED"})
    assert response.status_code == 200 and response.json()["total"] == 1
    monkeypatch.setattr("sys.argv", ["quantgraph", "--root", str(repository), "catalog-search",
        "--kind", "reference", "--subtype", "technical_demo", "--status", "UNVERIFIED"])
    main()
    assert json.loads(capsys.readouterr().out)["total"] == 1


def test_real_source_followups_resolve_three_rows_without_replacing_original_versions():
    catalog = KnowledgeCatalog(ROOT)
    for rid in ("M0115", "M0196", "M2122"):
        row = catalog.get(rid)
        assert row["entity_id"] == stable_id("grokbot", rid)
        assert row["kind"] == "strategy" and not row["classification_conflict"]
        assert row["statuses"]["source_followup"] == ["SOURCE_CODE_REVIEWED"]
        reviews = [v for v in row["versions"] if v["representation"] == "SOURCE_FOLLOWUP"]
        assert len(reviews) == 1 and reviews[0]["record"]["record_id"] == rid
        assert any(v["representation"] == "SOURCE_RECORD" for v in row["versions"])
        assert reviews[0]["record"]["computation_semantics"] == "NOT_EXECUTED"
        assert reviews[0]["record"]["economic_validity"] == "NOT_TESTED"
        assert reviews[0]["record"]["commercial_use"] == "REVIEW_REQUIRED"
        assert any(c["kind"] == "unclassified" for c in row["classifications"])
    unknown = catalog.get("M0176")
    assert unknown["kind"] == "unclassified"
    assert unknown["statuses"]["source_followup"] == ["SOURCE_UNAVAILABLE"]
    assert catalog.search(status="SOURCE_UNAVAILABLE")["total"] == 1
    assert catalog.stats()["source_reviews"] == 4
    assert catalog.stats()["unique_entries"] == 8546 + catalog.stats()["source_collection_entries"]
    assert catalog.search("M0115", source="QuantConnect", frequency="Daily")["total"] == 1
    assert catalog.search("M0196", source="TradingView", frequency="1分钟")["total"] == 1
    assert catalog.search("M0176", frequency="15分钟")["total"] == 0


def test_mirrored_followup_does_not_inflate_counts_or_duplicate_versions(repository):
    from quantgraph.graph.source_review import INDEX_FORMAT, schema
    original = load(repository / "metadata/corpus/first/metadata/source-records/M9902.json")
    row = load(ROOT / "metadata/source-reviews/20261004-v1/records/M2122.json")
    row.update(record_id="M9902", name="Synthetic reviewed strategy")
    origin_path = "metadata/corpus/first/metadata/source-records/M9902.json"
    raw = (repository / origin_path).read_bytes()
    row["origin"] = dict(path=origin_path, sha256=digest(raw), bytes=len(raw),
        **{k: original["provenance"][k] for k in ("row_sha256", "rule_sha256")})
    folder = repository / "metadata/followup"
    schema_pin = write(folder / "schema.json", schema())
    ref = dict(path="records/M9902.json", record_id="M9902", **write(folder / "records/M9902.json", row))
    write(folder / "index.json", dict(schema_version=INDEX_FORMAT,
        schema=dict(path="schema.json", **schema_pin), records=[ref]))
    registry = load(repository / "metadata/catalog.json")
    registry["collections"].append(dict(id="source-followup", kind="source_followups", path="metadata/followup/index.json"))
    write(repository / "metadata/catalog.json", registry)
    before = KnowledgeCatalog(repository)
    assert before.get("M9902")["kind"] == "strategy"
    copytree(folder, repository / "metadata/followup-mirror")
    registry["collections"].append(dict(id="source-followup-mirror", kind="source_followups", path="metadata/followup-mirror/index.json"))
    write(repository / "metadata/catalog.json", registry)
    mirrored = KnowledgeCatalog(repository)
    assert mirrored.stats() == before.stats()
    assert mirrored.get("M9902") == before.get("M9902")

"""Offline integrity of the public-web metadata, never an upstream or replay test.

Only committed metadata is read. Private upstream snapshots are deliberately not
required, so this check also runs in a public clone without those source bytes.
"""
from datetime import datetime
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import unquote, urlsplit

import pytest
from jsonschema import Draft202012Validator

from quantgraph.graph.metadata_catalog import canonical_hash
from quantgraph.graph.metadata_pilot import digest, read_below, validate


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "metadata/public-web/20261004-v1"


@pytest.fixture(scope="module")
def batch():
    records = validate(BATCH)
    return {
        "records": records,
        "index": json.loads(read_below(BATCH, "index.json")),
        "manifest": json.loads(read_below(BATCH, "manifest.json")),
        "lock": json.loads(read_below(BATCH, "source-lock.json")),
    }


def identity(record):
    return tuple(record[key] for key in ("identity_namespace", "entity_type", "record_id"))


def github_source_path(url):
    """Compare the repository and file, without claiming different refs equivalent."""
    parsed = urlsplit(url)
    parts = unquote(parsed.path).strip("/").split("/", 4)
    if parsed.hostname == "github.com" and len(parts) == 5 and parts[2] == "blob":
        return "/".join(parts[:2]), parts[4]
    return None


def test_public_web_index_covers_the_manifest_and_original_schema(batch):
    assert read_below(BATCH, "schema.json") == read_below(ROOT, "metadata/schema.json")
    indexed = {identity(ref): ref["path"] for ref in batch["index"]["records"]}
    declared = {identity(ref): ref["path"] for ref in batch["manifest"]["records"]}
    assert len(indexed) == len(batch["index"]["records"])
    assert len(declared) == len(batch["manifest"]["records"])
    assert indexed == declared
    assert set(indexed) == {identity(record) for record in batch["records"]}
    assert {record["entity_type"] for record in batch["records"]} == {"strategy", "factor"}
    existing = sum(
        any(match["match_type"] == "SAME_SOURCE_PATH" for match in ref["catalog_matches"])
        for ref in batch["manifest"]["records"]
    )
    assert batch["manifest"]["counts"] == {
        "records": len(batch["records"]),
        "strategies": sum(record["entity_type"] == "strategy" for record in batch["records"]),
        "factors": sum(record["entity_type"] == "factor" for record in batch["records"]),
        "source_files": len(batch["lock"]["files"]),
        "existing_source_evidence": existing,
        "new_source_implementations": len(batch["records"]) - existing,
        "new_execution_trials": 0,
        "promoted_native_curated_definitions": 0,
    }
    for record in batch["records"]:
        assert record["record_id"] == record["native_source_id"]
        assert not re.fullmatch(r"M\d{4}", record["record_id"])


def test_every_reviewed_source_resolves_to_an_immutable_lock(batch):
    lock = batch["lock"]
    assert lock["schema_version"] == "quantgraph-public-web-source-lock/v1"
    assert lock["batch_id"] == BATCH.name
    files = {entry["id"]: entry for entry in lock["files"]}
    assert len(files) == len(lock["files"])
    assert files
    for entry in files.values():
        assert re.fullmatch(r"[0-9a-f]{40}", entry["revision"])
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
        assert type(entry["bytes"]) is int and entry["bytes"] > 0
        path = PurePosixPath(entry["path"])
        assert not path.is_absolute() and ".." not in path.parts
        assert entry["repository"] and entry["license_spdx"] and entry["role"]
        assert entry["url"] == (
            f"https://github.com/{entry['repository']}/blob/{entry['revision']}/{entry['path']}"
        )
        assert entry["fetch_url"] == (
            f"https://raw.githubusercontent.com/{entry['repository']}/{entry['revision']}/{entry['path']}"
        )
        assert datetime.fromisoformat(entry["retrieved_at"].replace("Z", "+00:00")).tzinfo

    for record in batch["records"]:
        source_ids = {source["id"] for source in record["sources"]}
        assert source_ids <= files.keys()
        for source in record["sources"]:
            locked = files[source["id"]]
            assert {key: source[key] for key in ("url", "revision", "sha256")} == {
                key: locked[key] for key in ("url", "revision", "sha256")
            }
        fields = record.get("strategy_fields") or record["factor_fields"]
        for field in fields.values():
            assert set(field["evidence"]) <= source_ids
            if field["status"] != "MISSING":
                assert field["evidence"]


def test_source_review_does_not_invent_execution_or_economic_equivalence(batch):
    manifest = batch["manifest"]
    assert manifest["schema_version"] == "quantgraph-public-web-batch/v1"
    assert manifest["batch_id"] == BATCH.name
    records = {identity(record): record for record in batch["records"]}
    for ref in manifest["records"]:
        record = records[identity(ref)]
        assert ref["representation"] == "SOURCE_IMPLEMENTATION"
        assert ref["new_economic_concept_claimed"] is False
        assert ref["admission"] == {
            "metadata": "SOURCE_CODE_REVIEWED",
            "computation_semantics": "NOT_EXECUTED",
            "economic_validity": "NOT_TESTED",
            "commercial_profile": "REVIEW_REQUIRED",
        }
        assert record["lab"] is None
        assert record["relations"] == []
        assert record["economic_basis"]["status"] in {"RESEARCH_HYPOTHESIS_NOT_PROVEN", "MISSING"}
        assert record["rights"]["raw_data_included"] is False
        assert record["rights"]["source_fulltext_included"] is False


def test_catalog_matches_resolve_to_the_current_original_row(batch):
    corpus = json.loads(read_below(ROOT, "metadata/corpus-index.json"))
    source_schema = json.loads(read_below(ROOT, "metadata/source-record.schema.json"))
    validator = Draft202012Validator(source_schema)
    public_directories = {
        f"metadata/{ref['path']}/metadata/source-records" for ref in corpus["batches"]
    }
    records = {identity(record): record for record in batch["records"]}
    for ref in batch["manifest"]["records"]:
        seen = set()
        sources = records[identity(ref)]["sources"]
        source_paths = {github_source_path(source["url"]) for source in sources}
        source_ids = {source["id"] for source in sources}
        has_same_source = any(match["match_type"] == "SAME_SOURCE_PATH" for match in ref["catalog_matches"])
        assert ref["dedup_outcome"] == (
            "EXISTING_SOURCE_EVIDENCE" if has_same_source
            else "NEW_SOURCE_IMPLEMENTATION_NOT_NEW_CONCEPT"
        )
        for match in ref["catalog_matches"]:
            rid = match["record_id"]
            assert re.fullmatch(r"M\d{4}", rid)
            assert rid not in seen
            seen.add(rid)
            relative = PurePosixPath(match["source_record_path"])
            assert str(relative.parent) in public_directories
            assert relative.name == f"{rid}.json"
            original = json.loads(read_below(ROOT, str(relative)))
            validator.validate(original)
            values = {key: field["value"] for key, field in original["reported_fields"].items()}
            assert original["record_id"] == original["native_source_id"] == values["id"] == rid
            assert canonical_hash(values) == original["provenance"]["row_sha256"] == match["row_sha256"]
            assert digest(values["规则"].encode()) == original["provenance"]["rule_sha256"]
            assert match["match_type"] in {"SAME_SOURCE_PATH", "POSSIBLE_CONCEPT_OVERLAP"}
            assert match["reason"]
            assert match["equivalence_claimed"] is False
            assert match["confidence"] in {"HIGH", "MEDIUM", "LOW"}
            catalog_evidence = f"catalog:{rid}:row_sha256"
            assert catalog_evidence in match["evidence"]
            assert set(match["evidence"]) <= source_ids | {catalog_evidence}
            assert source_ids & set(match["evidence"])
            assert values["source_url"] in match["source"]
            assert set(match["source"]) <= {values["source_url"]} | {source["url"] for source in sources}
            if match["match_type"] == "SAME_SOURCE_PATH":
                assert match["role"] == "SOURCE_LOCATOR_MATCH"
                assert github_source_path(values["source_url"]) in source_paths - {None}
            else:
                assert match["role"] == "CONCEPT_COMPARISON_ONLY_NOT_ASSERTED_FACTOR_USE"


def test_private_upstream_snapshots_are_outside_public_records_and_git(batch):
    private_prefix = f"datasets/raw/sources/public-web/{BATCH.name}/"
    indexed_paths = {ref["path"] for ref in batch["index"]["records"]}
    for entry in batch["lock"]["files"]:
        snapshot = entry["private_snapshot_path"]
        assert snapshot.startswith(private_prefix)
        assert ".." not in PurePosixPath(snapshot).parts
        assert snapshot not in indexed_paths
        assert not (BATCH / snapshot).exists()
    assert all(PurePosixPath(path).parts[0] in {"strategies", "factors"} for path in indexed_paths)
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", private_prefix],
        cwd=ROOT, check=True, capture_output=True,
    )
    assert not tracked.stdout, "Private upstream snapshots must not enter the Git index"

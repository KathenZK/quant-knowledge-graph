"""Source follow-ups must preserve identity and earn every reviewed assertion."""
from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
import pytest

from quantgraph.graph import source_review
from quantgraph.graph.metadata_pilot import digest, encoded


INDEX = "metadata/source-review/test/index.json"
COMMIT = "a" * 40
CODE = b"//@version=5\nstrategy('Example')\nif close > open\n    strategy.entry('L', strategy.long)\n"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else encoded(value)
    path.write_bytes(raw)
    return dict(sha256=digest(raw), bytes=len(raw))


def read(path):
    return json.loads(path.read_bytes())


@pytest.fixture
def repository(tmp_path):
    """Trusted CSV rows are tiny and synthetic; no repository raw files are read."""
    root = tmp_path / "repository"
    rows = {}
    for rid, rule in (("M9901", "RSI和EMA参数，交易用途未明确。"), ("M9902", "另一条原始记录。")):
        original = dict(
            record_id=rid, native_source_id=rid, identity_namespace="grokbot",
            entity_type="source_record", reported_fields={
                "id": dict(value=rid), "规则": dict(value=rule),
                "source_url": dict(value="https://github.com/example/signals")},
            provenance=dict(row_sha256=digest(encoded([rid, rule])), rule_sha256=digest(rule.encode())),
        )
        path = f"metadata/corpus/first/source-records/{rid}.json"
        write(root / path, original)
        rows[rid] = dict(path=path, record=original)
    origin = rows["M9901"]
    origin_raw = (root / origin["path"]).read_bytes()
    review = dict(
        schema_version=source_review.FORMAT, record_id="M9901", name="Synthetic source follow-up",
        reviewed_at="2026-10-04T11:00:00+00:00",
        origin=dict(path=origin["path"], sha256=digest(origin_raw), bytes=len(origin_raw),
                    **origin["record"]["provenance"]),
        outcome="SOURCE_CODE_REVIEWED",
        identity_match=dict(status="EXACT_URL", reason="Same explicitly identified source path.", evidence=["code"]),
        classification=dict(kind="strategy", subtype="entry_rule", reason="Code specifies a long entry.", evidence=["code"]),
        sources=[dict(id="code", kind="github_code",
                      url=f"https://github.com/example/signals/blob/{COMMIT}/example.pine",
                      revision=COMMIT, sha256=digest(CODE), bytes=len(CODE), http_status=200,
                      retrieved_at="2026-10-04T10:59:00+00:00",
                      snapshot_path="datasets/raw/sources/source-review/example.pine",
                      locator="example.pine:2-4", attribution="Example author", license="UNKNOWN")],
        fields={name: dict(text="Not supplied by the source.", status="MISSING", evidence=[])
                for name in ("assets", "universe", "signal", "entry", "exit", "position", "risk", "cost", "execution_time", "timeframe")},
        corrections=["Source supplies an entry omitted from the original catalog."],
        missing_information=["Exit and transaction costs are not specified."],
        computation_semantics="NOT_EXECUTED", economic_validity="NOT_TESTED",
        commercial_use="REVIEW_REQUIRED", source_fulltext_included=False,
    )
    review["fields"]["entry"] = dict(text="Enter long when close exceeds open.", status="SOURCE_CODE_REVIEWED", evidence=["code"])
    destination = root / Path(INDEX).parent
    schema_pin = write(destination / "schema.json", source_review.schema())
    record_pin = write(destination / "records/M9901.json", review)
    write(root / INDEX, dict(schema_version=source_review.INDEX_FORMAT,
                            schema=dict(path="schema.json", **schema_pin),
                            records=[dict(path="records/M9901.json", record_id="M9901", **record_pin)]))
    return root, rows


def review_record(repository):
    root, _ = repository
    return read(root / Path(INDEX).parent / "records/M9901.json")


def replace_record(repository, review):
    root, _ = repository
    index = read(root / INDEX)
    ref = index["records"][0]
    ref.update(write(root / Path(INDEX).parent / ref["path"], review))
    write(root / INDEX, index)


def validate(repository, *, verify_snapshots=False):
    root, rows = repository
    return source_review.validate(root, INDEX, rows, verify_snapshots=verify_snapshots)


def unavailable(repository):
    review = review_record(repository)
    review.update(outcome="SOURCE_UNAVAILABLE")
    review["classification"].update(kind="unclassified", subtype="source_unavailable")
    review["identity_match"].update(status="UNRESOLVED")
    review["sources"][0].update(kind="availability_check", http_status=404)
    for field in review["fields"].values():
        field.update(status="MISSING", evidence=[])
    return review


def test_valid_review_keeps_original_identity_and_never_changes_source(repository):
    root, rows = repository
    before = {row["path"]: (root / row["path"]).read_bytes() for row in rows.values()}
    Draft202012Validator.check_schema(source_review.schema())
    index, records = validate(repository)
    assert len(index["records"]) == len(records) == 1
    assert records[0]["record_id"] == "M9901"
    assert records[0]["origin"]["row_sha256"] == rows["M9901"]["record"]["provenance"]["row_sha256"]
    assert records[0]["economic_validity"] == "NOT_TESTED"
    assert records[0]["commercial_use"] == "REVIEW_REQUIRED"
    assert all((root / path).read_bytes() == raw for path, raw in before.items())


def test_default_ci_validation_does_not_require_private_raw_snapshots(repository):
    root, _ = repository
    assert not (root / "datasets").exists()
    assert validate(repository)[1][0]["outcome"] == "SOURCE_CODE_REVIEWED"
    with pytest.raises((ValueError, OSError)):
        validate(repository, verify_snapshots=True)


def test_opt_in_snapshot_validation_checks_actual_bytes(repository):
    root, _ = repository
    source = review_record(repository)["sources"][0]
    path = root / source["snapshot_path"]
    write(path, CODE)
    assert validate(repository, verify_snapshots=True)[1]
    path.write_bytes(CODE.replace(b"close > open", b"close < open"))
    assert validate(repository)[1]  # CI binds the manifest; the local audit binds raw bytes.
    with pytest.raises(ValueError, match="digest mismatch"):
        validate(repository, verify_snapshots=True)


@pytest.mark.parametrize("field,value", [("sha256", "0" * 64), ("bytes", 1),
                                         ("row_sha256", "0" * 64), ("rule_sha256", "0" * 64)])
def test_rehashing_review_cannot_change_origin_pins(repository, field, value):
    review = review_record(repository)
    review["origin"][field] = value
    replace_record(repository, review)
    with pytest.raises(ValueError, match="digest mismatch|origin version mismatch"):
        validate(repository)


def test_origin_cannot_be_redirected_to_another_valid_csv_row(repository):
    root, rows = repository
    review = review_record(repository)
    other = rows["M9902"]
    raw = (root / other["path"]).read_bytes()
    review["origin"] = dict(path=other["path"], sha256=digest(raw), bytes=len(raw), **other["record"]["provenance"])
    replace_record(repository, review)
    with pytest.raises(ValueError, match="origin path mismatch"):
        validate(repository)


def test_rehashed_origin_content_must_still_match_the_trusted_corpus(repository):
    root, _ = repository
    review = review_record(repository)
    original = read(root / review["origin"]["path"])
    original["reported_fields"]["规则"]["value"] = "Replaced original rule."
    review["origin"].update(write(root / review["origin"]["path"], original))
    replace_record(repository, review)
    with pytest.raises(ValueError, match="origin version mismatch"):
        validate(repository)


@pytest.mark.parametrize("mutation", ["record-id", "index-id", "unknown-id", "renamed-path", "duplicate-index"])
def test_identity_membership_and_duplicate_index_are_rejected(repository, mutation):
    root, _ = repository
    index = read(root / INDEX)
    if mutation == "record-id":
        review = review_record(repository)
        review["record_id"] = "M9902"
        replace_record(repository, review)
    elif mutation == "index-id":
        index["records"][0]["record_id"] = "M9902"
        write(root / INDEX, index)
    elif mutation == "unknown-id":
        review = review_record(repository)
        review["record_id"] = "M9999"
        index["records"][0].update(record_id="M9999", path="records/M9999.json",
                                    **write(root / Path(INDEX).parent / "records/M9999.json", review))
        write(root / INDEX, index)
    elif mutation == "renamed-path":
        index["records"][0].update(path="records/renamed.json",
                                    **write(root / Path(INDEX).parent / "records/renamed.json", review_record(repository)))
        write(root / INDEX, index)
    else:
        index["records"].append(deepcopy(index["records"][0]))
        write(root / INDEX, index)
    with pytest.raises(ValueError, match="identity or membership mismatch"):
        validate(repository)


def test_unindexed_record_is_not_silently_ignored(repository):
    root, _ = repository
    write(root / Path(INDEX).parent / "records/orphan.json", review_record(repository))
    with pytest.raises(ValueError, match="directory membership mismatch"):
        validate(repository)


@pytest.mark.parametrize("target", ["classification", "identity_match", "entry"])
def test_all_evidence_references_have_foreign_keys(repository, target):
    review = review_record(repository)
    field = review["fields"][target] if target == "entry" else review[target]
    field["evidence"] = ["nonexistent-source"]
    replace_record(repository, review)
    with pytest.raises(ValueError, match="Unresolved source review evidence"):
        validate(repository)


def test_duplicate_evidence_source_id_is_rejected(repository):
    review = review_record(repository)
    review["sources"].append(deepcopy(review["sources"][0]))
    replace_record(repository, review)
    with pytest.raises(ValueError, match="Duplicate source review evidence ID"):
        validate(repository)


def test_404_is_valid_access_evidence_but_cannot_be_promoted_to_code(repository):
    review = unavailable(repository)
    replace_record(repository, review)
    assert validate(repository)[1][0]["classification"]["kind"] == "unclassified"
    review["sources"][0]["kind"] = "github_code"
    replace_record(repository, review)
    with pytest.raises(ValueError, match="successful fetch"):
        validate(repository)


@pytest.mark.parametrize("mutation", ["classification", "identity", "code-field", "description-field"])
def test_unavailable_source_cannot_resolve_identity_or_review_fields(repository, mutation):
    review = unavailable(repository)
    if mutation == "classification":
        review["classification"]["kind"] = "strategy"
    elif mutation == "identity":
        review["identity_match"]["status"] = "EXACT_URL"
    else:
        review["fields"]["entry"].update(status="SOURCE_CODE_REVIEWED" if mutation == "code-field" else "SOURCE_DESCRIPTION_REVIEWED", evidence=["code"])
    replace_record(repository, review)
    with pytest.raises(ValueError, match="Unavailable source|successful source evidence"):
        validate(repository)


def test_a_source_page_can_support_description_but_not_code_claims(repository):
    review = review_record(repository)
    review["sources"][0]["kind"] = "source_page"
    review["outcome"] = "SOURCE_DESCRIPTION_REVIEWED"
    review["fields"]["entry"]["status"] = "SOURCE_DESCRIPTION_REVIEWED"
    replace_record(repository, review)
    assert validate(repository)[1]
    review["fields"]["entry"]["status"] = "SOURCE_CODE_REVIEWED"
    replace_record(repository, review)
    with pytest.raises(ValueError, match="successful source evidence"):
        validate(repository)


@pytest.mark.parametrize("target", ["entire-review", "identity", "description-field"])
def test_license_attachment_cannot_substitute_for_source_semantics(repository, target):
    review = review_record(repository)
    license_source = deepcopy(review["sources"][0])
    license_bytes = b"MIT License\n"
    license_source.update(id="license", kind="license", locator="LICENSE:1",
                          url=f"https://github.com/example/signals/blob/{COMMIT}/LICENSE",
                          snapshot_path="datasets/raw/sources/source-review/LICENSE",
                          sha256=digest(license_bytes), bytes=len(license_bytes), license="MIT")
    review["sources"].append(license_source)
    if target == "entire-review":
        review["sources"] = [license_source]
        review["outcome"] = "SOURCE_DESCRIPTION_REVIEWED"
        review["classification"]["evidence"] = ["license"]
        review["identity_match"]["evidence"] = ["license"]
        review["fields"]["entry"].update(status="SOURCE_DESCRIPTION_REVIEWED", evidence=["license"])
    elif target == "identity":
        review["identity_match"]["evidence"] = ["license"]
    else:
        review["fields"]["entry"].update(status="SOURCE_DESCRIPTION_REVIEWED", evidence=["license"])
    replace_record(repository, review)
    with pytest.raises(ValueError, match="successful.*evidence"):
        validate(repository)


@pytest.mark.parametrize("target", ["classification", "identity_match", "entry"])
def test_reviewed_assertions_require_positive_evidence_not_just_a_source_list(repository, target):
    review = review_record(repository)
    field = review["fields"][target] if target == "entry" else review[target]
    field["evidence"] = []
    replace_record(repository, review)
    with pytest.raises(ValueError, match="successful.*evidence"):
        validate(repository)


@pytest.mark.parametrize("field,value", [("commercial_use", "ALLOWED"), ("economic_validity", "VALIDATED"),
                                         ("computation_semantics", "EXECUTED"), ("source_fulltext_included", True)])
def test_source_review_cannot_claim_other_admission_gates(repository, field, value):
    review = review_record(repository)
    review[field] = value
    replace_record(repository, review)
    with pytest.raises(ValidationError):
        validate(repository)


@pytest.mark.parametrize("snapshot", ["/tmp/example.pine", "datasets/raw/sources/../example.pine",
                                      "datasets/raw/sources/./example.pine", "datasets/raw/sources//example.pine",
                                      "datasets/raw/sources/example\\file.pine", "datasets/public/example.pine"])
def test_unsafe_snapshot_paths_fail_even_without_private_raw_access(repository, snapshot):
    review = review_record(repository)
    review["sources"][0]["snapshot_path"] = snapshot
    replace_record(repository, review)
    with pytest.raises(ValueError, match="Unsafe source review snapshot path"):
        validate(repository)


def test_snapshot_validation_refuses_symlink_escape(repository, tmp_path):
    root, _ = repository
    source = review_record(repository)["sources"][0]
    outside = tmp_path / "outside.pine"
    outside.write_bytes(CODE)
    target = root / source["snapshot_path"]
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    with pytest.raises(ValueError, match="symlinks"):
        validate(repository, verify_snapshots=True)


@pytest.mark.parametrize("mutation", ["branch-name", "url-version-mismatch"])
def test_github_code_requires_matching_immutable_revision(repository, mutation):
    review = review_record(repository)
    source = review["sources"][0]
    if mutation == "branch-name":
        source.update(revision="main", url="https://github.com/example/signals/blob/main/example.pine")
    else:
        source["url"] = f"https://github.com/example/signals/blob/{'b' * 40}/example.pine"
    replace_record(repository, review)
    with pytest.raises(ValueError, match="pin its commit"):
        validate(repository)


def test_schema_and_record_bytes_are_pinned(repository):
    root, _ = repository
    destination = root / Path(INDEX).parent
    path = destination / "records/M9901.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="digest mismatch"):
        validate(repository)
    replace_record(repository, read(path))
    schema = read(destination / "schema.json")
    schema["additionalProperties"] = True
    index = read(root / INDEX)
    index["schema"].update(write(destination / "schema.json", schema))
    write(root / INDEX, index)
    with pytest.raises(ValueError, match="schema drift"):
        validate(repository)

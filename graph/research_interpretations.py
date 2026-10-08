"""Pin authored research conclusions to original evidence and import revisions."""

import hashlib
import json
import zlib

from quantgraph.graph.corpus_research import _loads, _finite, _identifier, _sha
from quantgraph.graph.research_universe import read_release, read_universe


def _raw_metrics(con, run_id, expected_sha256, cache):
    key = (run_id, expected_sha256)
    if key not in cache:
        row = con.execute(
            "SELECT sha256,content FROM corpus_artifacts WHERE run_id=? AND name='origin__strategy_metrics.json'",
            (run_id,),
        ).fetchone()
        if not row or row["sha256"] != expected_sha256:
            raise ValueError("Interpretation original metric artifact differs")
        decoder = zlib.decompressobj()
        data = decoder.decompress(row["content"], 128 * 1024 * 1024 + 1)
        if len(data) > 128 * 1024 * 1024 or decoder.unconsumed_tail or not decoder.eof:
            raise ValueError("Metric artifact expansion exceeds limit")
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ValueError("Stored original metric bytes differ")
        cache[key] = _loads(data)
    return cache[key]


def _metric_at(metrics, pointer):
    if (
        not isinstance(pointer, str)
        or not pointer.startswith("/")
        or not pointer[1:].isdigit()
    ):
        raise ValueError("Expected a direct original metric array pointer")
    index = int(pointer[1:])
    if not isinstance(metrics, list) or not 0 <= index < len(metrics):
        raise ValueError("Metric pointer does not resolve")
    return metrics[index]


def _numeric_evidence(quant, originals):
    if not isinstance(quant, list):
        raise ValueError("Quantitative evidence must be an array")
    for row in quant:
        reference = row.get("metric_reference") or {}
        key = (
            reference.get("origin_run_id"),
            reference.get("variant_id"),
            reference.get("manifest_sha256"),
        )
        original = originals.get(key)
        if row.get("variant_id") != reference.get("variant_id"):
            raise ValueError("Quantitative variant and origin reference differ")
        if original is None:
            raise ValueError("Quantitative evidence lacks a pinned implementation")
        expected = {
            "periods": original.get("periods"),
            "cost_sensitivity": original.get("cost_sensitivity"),
            "additional_execution_delay": original.get("additional_native_bar_lag")
            or original.get("additional_day_lag"),
            "additional_execution_delay_interpretation": original.get(
                "additional_native_bar_lag_interpretation"
            )
            or original.get("additional_day_lag_interpretation"),
            "primary_window_id": original.get("primary_window_id"),
            "window_selection": original.get("window_selection"),
            "windows_count": len(original.get("windows", [])),
            "capital_state": original.get("capital_state"),
        }
        for key, value in expected.items():
            if key in row and row[key] != value:
                raise ValueError(
                    "Quantitative interpretation differs from original metric: " + key
                )


def import_interpretations(catalog, research, folder, expected_sha256):
    manifest, blobs = read_release(folder, expected_sha256)
    if (
        manifest.get("schema_version") != "quant-research-interpretation-release/v1"
        or manifest.get("new_execution_trials") != 0
    ):
        raise ValueError("Unsupported interpretation release")
    version = manifest.get("id")
    _identifier(version)
    _sha(manifest.get("source_universe_manifest_sha256"))
    rows = _loads(blobs.get("interpretations.json", b"null"))
    _finite(rows)
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError("Expected bounded interpretations")
    with catalog.connect() as con:
        if not con.execute(
            "SELECT 1 FROM sqlite_master WHERE name='research_universes'"
        ).fetchone():
            raise ValueError("Import the verified worklist first")
        versions = con.execute(
            "SELECT version FROM research_universes WHERE manifest_sha256=?",
            (manifest["source_universe_manifest_sha256"],),
        ).fetchall()
        if len(versions) != 1:
            raise ValueError("Interpretation source worklist is not uniquely retained")
    universe = read_universe(catalog, versions[0]["version"])
    by_id = {r["record_id"]: r for r in universe["records"]}
    cache = {}
    prepared = []
    seen = set()
    with research.connect() as con:
        for original_row in rows:
            if not isinstance(original_row, dict):
                raise ValueError("Invalid interpretation")
            row = dict(original_row)
            rid = row.get("record_id")
            _identifier(rid)
            if rid in seen:
                raise ValueError("Duplicate interpretation record")
            seen.add(rid)
            bound = by_id.get(rid)
            if not bound or row.get("definition_sha256") != bound["definition_sha256"]:
                raise ValueError(
                    "Interpretation definition is not the current bound worklist definition"
                )
            if (
                row.get("new_execution_trials") != 0
                or row.get("interpretation_version") != version
            ):
                raise ValueError("Interpretation version/trial declaration differs")
            bindings = row.get("evidence_bindings")
            if not isinstance(bindings, list) or not bindings or len(bindings) > 1000:
                raise ValueError("Interpretation needs bounded evidence bindings")
            mapped = []
            original_metrics = {}
            binding_keys = set()
            for b in bindings:
                run_id = b.get("origin_run_id")
                vid = b.get("variant_id")
                _identifier(run_id)
                _identifier(vid)
                _sha(b.get("manifest_sha256"))
                _sha(b.get("metrics_file_sha256"))
                _sha(b.get("spec_file_sha256"))
                run = con.execute(
                    "SELECT manifest_sha256,lineage FROM corpus_runs WHERE run_id=?",
                    (run_id,),
                ).fetchone()
                impl = con.execute(
                    "SELECT record_id FROM corpus_implementations WHERE run_id=? AND variant_id=?",
                    (run_id, vid),
                ).fetchone()
                if not run or not impl or impl["record_id"] != rid:
                    raise ValueError(
                        "Interpretation execution identity is missing or differs"
                    )
                lineage = _loads(run["lineage"])["declared_lineage"]
                if lineage.get("source_run_manifest_sha256") != b["manifest_sha256"]:
                    raise ValueError(
                        "Origin manifest hash differs; it is not the collection manifest hash"
                    )
                if (
                    lineage.get("source_implementation_specs_sha256")
                    != b["spec_file_sha256"]
                ):
                    raise ValueError(
                        "Interpretation source specification artifact differs"
                    )
                annotation = lineage.get("metadata_enrichment", {}).get(
                    "operator_annotations_sha256"
                )
                if b.get("active_annotation_sha256") != annotation:
                    artifact = con.execute(
                        "SELECT sha256,content FROM corpus_artifacts WHERE run_id=? AND name='operator-annotations.json'",
                        (run_id,),
                    ).fetchone()
                    if (
                        b.get("active_annotation_sha256") is not None
                        or not artifact
                        or artifact["sha256"] != annotation
                    ):
                        raise ValueError(
                            "Interpretation evidence assessment revision differs"
                        )
                    decoder = zlib.decompressobj()
                    body = decoder.decompress(artifact["content"], 16385)
                    if (
                        len(body) > 16384
                        or decoder.unconsumed_tail
                        or not decoder.eof
                        or hashlib.sha256(body).hexdigest() != annotation
                    ):
                        raise ValueError(
                            "Empty annotation placeholder bytes are not verified"
                        )
                    if _loads(body) != {
                        "schema_version": "strategy-screen-annotations/v1",
                        "run_id": run_id,
                        "implementations": {},
                    }:
                        raise ValueError(
                            "Unbound interpretation cannot ignore active annotations"
                        )
                metric = _metric_at(
                    _raw_metrics(con, run_id, b["metrics_file_sha256"], cache),
                    b.get("metric_json_pointer"),
                )
                if (
                    metric.get("id") != rid
                    or metric.get("variant_id", metric.get("id")) != vid
                ):
                    raise ValueError("Original metric pointer identity differs")
                key = (run_id, vid, b["manifest_sha256"])
                if key in binding_keys:
                    raise ValueError("Duplicate interpretation binding")
                binding_keys.add(key)
                original_metrics[key] = metric
                mapped.append(
                    dict(
                        b,
                        origin_manifest_sha256=b["manifest_sha256"],
                        collection_manifest_sha256=run["manifest_sha256"],
                        graph_annotation_artifact_sha256=annotation,
                        source_annotation_sha256=b.get("active_annotation_sha256"),
                    )
                )
            for finding in row.get("observed_findings", []):
                if any(
                    (
                        b.get("origin_run_id"),
                        b.get("variant_id"),
                        b.get("manifest_sha256"),
                    )
                    not in binding_keys
                    for b in finding.get("bindings", [])
                ):
                    raise ValueError(
                        "Finding refers to evidence outside this interpretation"
                    )
            _numeric_evidence(row.get("quantitative_evidence"), original_metrics)
            row.update(
                evidence_bindings=mapped,
                catalog_entity_id=bound["entity_id"],
                catalog_definition_revision=bound["definition_revision"],
                binding_status="SOURCE_DEFINITION_AND_ORIGINAL_EVIDENCE_BOUND",
                source_interpretation_sha256=expected_sha256,
                numeric_reference_check="PERIODS_COST_DELAY_AND_WINDOW_FIELDS_MATCHED_ORIGINAL_NOT_RECOMPUTED",
            )
            prepared.append((rid, json.dumps(row, ensure_ascii=False, sort_keys=True)))
    with catalog.lock, catalog.connect() as con:
        con.executescript("""CREATE TABLE IF NOT EXISTS research_interpretation_releases(
            sequence INTEGER PRIMARY KEY,version TEXT NOT NULL UNIQUE,manifest_sha256 TEXT NOT NULL,manifest_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS research_interpretations(
            version TEXT NOT NULL,record_id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(version,record_id));""")
        for table in ["research_interpretation_releases", "research_interpretations"]:
            for action in ["UPDATE", "DELETE"]:
                con.execute(
                    f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'Interpretation history is immutable'); END"
                )
        con.execute("BEGIN IMMEDIATE")
        old = con.execute(
            "SELECT manifest_sha256 FROM research_interpretation_releases WHERE version=?",
            (version,),
        ).fetchone()
        if old:
            if old[0] != expected_sha256:
                raise ValueError("Interpretation release is immutable")
            return dict(version=version, records=len(rows), replayed=True)
        con.execute(
            "INSERT INTO research_interpretation_releases(version,manifest_sha256,manifest_json) VALUES(?,?,?)",
            (version, expected_sha256, json.dumps(manifest)),
        )
        con.executemany(
            "INSERT INTO research_interpretations VALUES(?,?,?)",
            [(version, rid, payload) for rid, payload in prepared],
        )
    return dict(
        version=version, records=len(rows), replayed=False, new_execution_trials=0
    )


def interpretations(catalog, record_id=None):
    with catalog.connect() as con:
        if not con.execute(
            "SELECT 1 FROM sqlite_master WHERE name='research_interpretations'"
        ).fetchone():
            return []
        sql = "SELECT i.payload FROM research_interpretations i JOIN research_interpretation_releases r ON r.version=i.version"
        args = []
        if record_id:
            sql += " WHERE i.record_id=?"
            args.append(record_id)
        return [
            _loads(r[0])
            for r in con.execute(sql + " ORDER BY r.sequence DESC,i.record_id", args)
        ]

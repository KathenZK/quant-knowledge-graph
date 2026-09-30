"""Append-only restrictive data-quality flags, independent of frozen results."""

import hashlib
import json

from quantgraph.graph.corpus_research import (
    _read_file,
    _loads,
    _finite,
    _identifier,
    _sha,
    safe_research_view,
)


def import_quality_overlay(catalog, research, path, expected_sha256):
    body = _read_file(path, 8 * 1024 * 1024)
    _sha(expected_sha256)
    if hashlib.sha256(body).hexdigest() != expected_sha256:
        raise ValueError("Data overlay digest differs")
    pack = _loads(body)
    _finite(pack)
    version = pack.get("overlay_id")
    _identifier(version)
    if (
        pack.get("schema_version") != "quant-research-data-quality-overlay/v1"
        or pack.get("new_execution_trials") != 0
    ):
        raise ValueError("Unsupported restrictive data overlay")
    rows = pack.get("records")
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError("Invalid data overlay records")
    projected = []
    not_in_snapshot = []
    seen = set()
    with research.connect() as con:
        for row in rows:
            if (
                row.get("strict_comparability_eligible") is not False
                or row.get("original_metrics_unchanged") is not True
            ):
                raise ValueError("This overlay cannot certify data or change returns")
            rid = row.get("record_id")
            run_id = row.get("origin_run_id")
            vid = row.get("variant_id")
            for value in [rid, run_id, vid]:
                _identifier(value)
            key = (run_id, vid)
            if key in seen:
                raise ValueError("Duplicate data-quality binding")
            seen.add(key)
            run = con.execute(
                "SELECT manifest_sha256,lineage FROM corpus_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if not run:
                not_in_snapshot.append(
                    dict(
                        record_id=rid,
                        run_id=run_id,
                        variant_id=vid,
                        reason="ORIGIN_NOT_IN_THIS_SNAPSHOT",
                    )
                )
                continue
            impl = con.execute(
                "SELECT record_id FROM corpus_implementations WHERE run_id=? AND variant_id=?",
                key,
            ).fetchone()
            if not impl or impl["record_id"] != rid:
                raise ValueError("Data overlay execution identity differs")
            lineage = _loads(run["lineage"])["declared_lineage"]
            if lineage.get("source_run_manifest_sha256") != row.get(
                "origin_manifest_sha256"
            ):
                raise ValueError("Data overlay origin manifest differs")
            metric = lineage.get("origin_artifacts", {}).get(
                "origin__strategy_metrics.json", {}
            )
            if metric.get("sha256") != row.get("origin_metrics_file_sha256"):
                raise ValueError("Data overlay original metric artifact differs")
            actual = (row.get("actual_series_ref") or {}).get("sha256")
            _sha(actual)
            pins = [
                lineage.get("normalized_data_sha256", {}).get(name)
                for name in lineage.get("series_data_bindings", {}).get(
                    row.get("asset"), []
                )
            ]
            if actual not in pins:
                raise ValueError(
                    "Data overlay series is not bound to the declared instrument"
                )
            display = {
                k: row.get(k)
                for k in [
                    "record_id",
                    "origin_run_id",
                    "variant_id",
                    "origin_manifest_sha256",
                    "asset",
                    "series_first_observation",
                    "current_vehicle_inception",
                    "historical_scope_requiring_review",
                    "data_quality_status",
                    "strict_comparability_eligible",
                    "priority",
                    "warning_zh",
                    "official_sources",
                ]
            }
            display.update(
                series_sha256=actual,
                collection_manifest_sha256=run["manifest_sha256"],
                overlay_id=version,
                overlay_sha256=expected_sha256,
            )
            projected.append(safe_research_view(display))
    with catalog.lock, catalog.connect() as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS research_data_quality(overlays_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,source_payload TEXT NOT NULL,projection TEXT NOT NULL)"
        )
        con.execute("""CREATE TABLE IF NOT EXISTS research_data_quality_bindings(
            overlay_id TEXT NOT NULL,run_id TEXT NOT NULL,variant_id TEXT NOT NULL,
            collection_manifest_sha256 TEXT NOT NULL,payload TEXT NOT NULL,
            PRIMARY KEY(overlay_id,run_id,variant_id,collection_manifest_sha256))""")
        for table in ["research_data_quality", "research_data_quality_bindings"]:
            for action in ["UPDATE", "DELETE"]:
                con.execute(
                    f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'Data quality history is immutable'); END"
                )
        old = con.execute(
            "SELECT sha256 FROM research_data_quality WHERE overlays_id=?", (version,)
        ).fetchone()
        if old and old[0] != expected_sha256:
            raise ValueError("Data quality overlay is immutable")
        if not old:
            con.execute(
                "INSERT INTO research_data_quality VALUES(?,?,?,?)",
                (
                    version,
                    expected_sha256,
                    body.decode(),
                    json.dumps(projected, ensure_ascii=False),
                ),
            )
        for row in projected:
            key = (
                version,
                row["origin_run_id"],
                row["variant_id"],
                row["collection_manifest_sha256"],
            )
            payload = json.dumps(row, ensure_ascii=False, sort_keys=True)
            old_binding = con.execute(
                "SELECT payload FROM research_data_quality_bindings WHERE overlay_id=? AND run_id=? AND variant_id=? AND collection_manifest_sha256=?",
                key,
            ).fetchone()
            if old_binding and old_binding[0] != payload:
                raise ValueError("Data-quality resolution changed under fixed identity")
            if not old_binding:
                con.execute(
                    "INSERT INTO research_data_quality_bindings VALUES(?,?,?,?,?)",
                    (*key, payload),
                )
    return dict(
        overlay_id=version,
        attached=len(projected),
        not_in_snapshot=not_in_snapshot,
        new_execution_trials=0,
    )


def data_quality_annotations(catalog):
    with catalog.connect() as con:
        if not con.execute(
            "SELECT 1 FROM sqlite_master WHERE name='research_data_quality_bindings'"
        ).fetchone():
            return []
        return [
            _loads(row[0])
            for row in con.execute(
                "SELECT payload FROM research_data_quality_bindings ORDER BY rowid"
            )
        ]

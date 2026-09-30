"""Immutable research worklists bound to actual private Catalog definitions.

An execution count, a source review and an authored interpretation remain
different evidence classes. This module never launches research or trading.
"""

import gzip
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

from quantgraph.graph.corpus_research import (
    _read_file,
    _loads,
    _finite,
    _identifier,
    _sha,
)


def read_release(folder, expected_sha256, *, limit=128 * 1024 * 1024):
    folder = Path(folder)
    if folder.is_symlink():
        raise ValueError("Release directory cannot be a symlink")
    _sha(expected_sha256)
    raw = _read_file(folder / "manifest.json", 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Release manifest digest mismatch")
    manifest = _loads(raw)
    _finite(manifest)
    refs = manifest.get("files")
    if not isinstance(refs, dict) or not 1 <= len(refs) <= 100:
        raise ValueError("Release must pin its bounded file set")
    blobs = {}
    for name, pin in refs.items():
        if not isinstance(name, str) or Path(name).name != name or name in {".", ".."}:
            raise ValueError("Unsafe release file name")
        _sha(pin)
        data = _read_file(folder / name, limit)
        if hashlib.sha256(data).hexdigest() != pin:
            raise ValueError("Release file digest mismatch")
        blobs[name] = data
    return manifest, blobs


def _tables(con):
    con.executescript("""
        CREATE TABLE IF NOT EXISTS research_universes(
            sequence INTEGER PRIMARY KEY, version TEXT NOT NULL UNIQUE,
            manifest_sha256 TEXT NOT NULL, manifest_json TEXT NOT NULL, summary_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS research_universe_records(
            version TEXT NOT NULL, record_id TEXT NOT NULL, entity_id TEXT NOT NULL,
            definition_revision TEXT NOT NULL, definition_sha256 TEXT,
            binding_kind TEXT NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY(version,record_id), UNIQUE(version,entity_id));
    """)
    for table in ["research_universes", "research_universe_records"]:
        for action in ["UPDATE", "DELETE"]:
            con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()}
                BEFORE {action} ON {table} BEGIN
                SELECT RAISE(ABORT,'Research universe history is immutable'); END""")


def import_universe(catalog, folder, expected_sha256):
    manifest, blobs = read_release(folder, expected_sha256)
    if manifest.get("schema_version") != "quant-research-universe-manifest/v1":
        raise ValueError("Unsupported worklist schema")
    version = manifest.get("version")
    _identifier(version)
    if not {"universe.jsonl.gz", "summary.json"} <= blobs.keys():
        raise ValueError("Worklist records and summary are required")
    with gzip.GzipFile(fileobj=io.BytesIO(blobs["universe.jsonl.gz"])) as stream:
        expanded = stream.read(128 * 1024 * 1024 + 1)
    if len(expanded) > 128 * 1024 * 1024:
        raise ValueError("Expanded worklist exceeds limit")
    lines = [line for line in expanded.splitlines() if line.strip()]
    if any(len(line) > 1024 * 1024 for line in lines):
        raise ValueError("One worklist record exceeds limit")
    rows = [_loads(line) for line in lines]
    summary = _loads(blobs["summary.json"])
    _finite(summary)
    if (
        not rows
        or len(rows) > 20000
        or summary.get("total_research_objects_in_scope") != len(rows)
    ):
        raise ValueError("Worklist count differs from declared scope")
    mapped = {}
    prepared = []
    seen = set()
    with catalog.connect() as con:
        for record in con.execute(
            "SELECT entity_id,kind,definition_revision,payload,private_payload FROM catalog_items WHERE active=1"
        ):
            value = _loads(record["payload"])
            raw = _loads(record["private_payload"])
            card = raw.get("intake_card") or {}
            native = card.get("record_id") if card else None
            if not native and record["kind"] == "strategy":
                ids = value.get("source_native_ids") or []
                if len(ids) == 1:
                    native = ids[0]
            if native:
                if native in mapped:
                    raise ValueError("Ambiguous Catalog native identity")
                mapped[native] = (dict(record), value, raw)
        for row in rows:
            _finite(row)
            if not isinstance(row, dict):
                raise ValueError("Invalid worklist row")
            native = row.get("record_id")
            _identifier(native)
            if native in seen:
                raise ValueError("Duplicate worklist native identity")
            seen.add(native)
            if native not in mapped:
                raise ValueError("Worklist has an unindexed Catalog record: " + native)
            record, value, raw = mapped[native]
            declared = row.get("definition_sha256")
            if row.get("identity_namespace") == "grok_final_6973":
                _sha(declared)
                rule = (raw.get("raw_record") or {}).get("规则") or (
                    raw.get("variant") or {}
                ).get("original_rule_text")
                if (
                    not isinstance(rule, str)
                    or hashlib.sha256(rule.encode()).hexdigest() != declared
                    or row.get("definition_text") != rule
                ):
                    raise ValueError(
                        "Worklist rule differs from bound Catalog definition"
                    )
                declared_fields = row.get("raw_record") or {}
                retained = raw.get("raw_record") or {}
                if any(
                    declared_fields.get(k) != retained.get(k)
                    for k in ["规则", "市场", "source_url"]
                    if k in retained
                ):
                    raise ValueError(
                        "Worklist source/market fields differ from Catalog record"
                    )
                row = dict(row)
                row["catalog_projection_metadata_differences"] = {
                    k: dict(catalog_value=v, source_value=declared_fields.get(k))
                    for k, v in retained.items()
                    if declared_fields.get(k) != v
                }
                binding = "EXACT_RETAINED_RULE_MARKET_AND_SOURCE"
            elif row.get("identity_namespace") == "collected_strategy_catalog":
                card = raw.get("intake_card") or {}
                revision = row.get("catalog_revision_sha256")
                _sha(revision)
                if (
                    card.get("record_id") != native
                    or card.get("version_id") != revision
                ):
                    raise ValueError(
                        "Collected candidate revision differs from worklist"
                    )
                binding = "EXACT_COLLECTION_REVISION_NOT_EXECUTION_REUSE"
            else:
                raise ValueError("Unknown research identity namespace")
            prepared.append(
                (
                    version,
                    native,
                    record["entity_id"],
                    record["definition_revision"],
                    declared,
                    binding,
                    json.dumps(row, ensure_ascii=False, sort_keys=True),
                )
            )
    with catalog.lock, catalog.connect() as con:
        _tables(con)
        con.execute("BEGIN IMMEDIATE")
        old = con.execute(
            "SELECT manifest_sha256 FROM research_universes WHERE version=?", (version,)
        ).fetchone()
        if old:
            if old[0] != expected_sha256:
                raise ValueError("Worklist version is immutable")
            return dict(version=version, records=len(rows), replayed=True)
        for values in prepared:
            current = con.execute(
                "SELECT definition_revision FROM catalog_items WHERE entity_id=? AND active=1",
                (values[2],),
            ).fetchone()
            if not current or current[0] != values[3]:
                raise ValueError("Catalog revision changed while importing worklist")
        con.execute(
            "INSERT INTO research_universes(version,manifest_sha256,manifest_json,summary_json) VALUES(?,?,?,?)",
            (
                version,
                expected_sha256,
                json.dumps(manifest, sort_keys=True),
                json.dumps(summary, sort_keys=True),
            ),
        )
        con.executemany(
            "INSERT INTO research_universe_records VALUES(?,?,?,?,?,?,?)", prepared
        )
    return dict(
        version=version,
        records=len(rows),
        replayed=False,
        entity_types=dict(Counter(r["entity_type"] for r in rows)),
        source_definitions_modified=0,
        execution_results_created=0,
    )


def read_universe(catalog, version=None):
    with catalog.connect() as con:
        if not con.execute(
            "SELECT 1 FROM sqlite_master WHERE name='research_universes'"
        ).fetchone():
            return None
        release = (
            con.execute(
                "SELECT * FROM research_universes WHERE version=?", (version,)
            ).fetchone()
            if version
            else con.execute(
                "SELECT * FROM research_universes ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
        )
        if not release:
            return None
        records = [
            dict(r)
            for r in con.execute(
                "SELECT * FROM research_universe_records WHERE version=? ORDER BY record_id",
                (release["version"],),
            )
        ]
    for row in records:
        row["payload"] = _loads(row["payload"])
    return dict(
        version=release["version"],
        manifest_sha256=release["manifest_sha256"],
        summary=_loads(release["summary_json"]),
        records=records,
    )

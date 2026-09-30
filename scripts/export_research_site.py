#!/usr/bin/env python3
"""Export a verified private runtime as bounded immutable Sites data batches.

This is an explicit offline projection, not a collection or research runner.
Existing implementation identities must retain exactly their prior bytes.
"""

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path

from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.corpus_research import CorpusResearch, safe_research_view
from quantgraph.graph.personal_catalog import PersonalCatalogRepository
from quantgraph.graph.research_views import ResearchWorkView
from quantgraph.graph.research_data_quality import data_quality_annotations
from quantgraph.graph.site_feedback import canonical, digest


def sample_curve(curve, meta):
    size = len(curve)
    if size > 280:
        indices = {
            0,
            size - 1,
            min(range(size), key=lambda i: curve[i]["equity"]),
            max(range(size), key=lambda i: curve[i]["equity"]),
            min(range(size), key=lambda i: curve[i]["drawdown"]),
        }
        indices.update(i * (size - 1) // 274 for i in range(275))
        curve = [curve[i] for i in sorted(indices)]
    meta["returned_points"] = len(curve)
    meta["sampling"] = "显示抽样，保留首尾及全局净值/回撤极值；指标基于完整数据"
    return curve


def encode(value, compressed=False):
    data = json.dumps(
        safe_research_view(value),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    if b"/workspace/" in data or b"/tmp/" in data:
        raise ValueError("Private machine path leaked into a display projection")
    return gzip.compress(data, compresslevel=9, mtime=0) if compressed else data


def export(runtime, roots, output, parent):
    runtime, output = Path(runtime), Path(output)
    if output.exists():
        raise ValueError("Use a new immutable export directory")
    output.mkdir(parents=True)
    assets = output / "assets"
    roots = [Path(p) for p in roots]

    def prior(path):
        for root in reversed(roots):
            p = root / path.lstrip("/")
            if p.is_file():
                return p.read_bytes()
        return None

    def read_prior(path):
        data = prior(path)
        if data is None:
            raise ValueError("Required baseline asset missing: " + path)
        return json.loads(
            gzip.decompress(data) if data.startswith(b"\x1f\x8b") else data
        )

    files = {}

    def write(path, value, *, frozen=False):
        body = encode(value, path.endswith(".gz"))
        previous = prior(path)
        if frozen and previous is not None and previous != body:
            raise ValueError("Existing experiment projection bytes changed: " + path)
        if previous == body:
            return False
        if len(body) > 16000000:
            raise ValueError("Object exceeds sync contract: " + path)
        p = assets / path.lstrip("/")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
        files[path] = dict(
            path=path, bytes=len(body), sha256=hashlib.sha256(body).hexdigest()
        )
        return True

    catalog = CatalogRepository(runtime / "catalog.sqlite")
    reader = PersonalCatalogRepository(runtime / "catalog.sqlite")
    research = CorpusResearch(runtime)
    work = ResearchWorkView(catalog, research)
    scope_summary = work.summary()
    if not scope_summary or scope_summary["unbound_execution_versions"]:
        raise ValueError("Research definitions must be bound before export")
    items = reader.all_items()
    by_id = {item["entity_id"]: item for item in items}
    old_manifest = read_prior("/catalog/manifest.json")
    catalog_manifest = dict(old_manifest)
    refs = []
    adjacency = defaultdict(list)
    edges = []
    for original in reader._edges:
        if original["from_id"] not in by_id or original["to_id"] not in by_id:
            continue
        edge = dict(original)
        a, b = by_id[edge["from_id"]], by_id[edge["to_id"]]
        edge.update(
            from_name=a["name"],
            to_name=b["name"],
            from_kind=a["kind"],
            to_kind=b["kind"],
            from_type=a["entity_type"],
            to_type=b["entity_type"],
            explanation=reader.relation_explanation(edge["relation"]),
        )
        edges.append(edge)
        adjacency[edge["from_id"]].append(edge)
        adjacency[edge["to_id"]].append(edge)
    groups = defaultdict(list)
    index_keys = (
        "entity_id entity_type kind definition_revision stable_knowledge_id name aliases family family_label category category_label formula frequency markets required_fields source_name source_type source_url source_native_ids group record_level parameters factor_quality"
    ).split()
    for item in items:
        eid = item["entity_id"]
        if eid not in catalog_manifest:
            catalog_manifest[eid] = dict(
                file=hashlib.sha256(eid.encode()).hexdigest()[:24], kind=item["kind"]
            )
            detail = reader.get(eid)
            rel = sorted(
                adjacency[eid], key=lambda e: (e["relation"], e["relationship_id"])
            )[:40]
            detail["relations"] = rel
            neighbors = list(
                dict.fromkeys(
                    e["to_id"] if e["from_id"] == eid else e["from_id"] for e in rel
                )
            )
            detail["related"] = [
                {
                    k: by_id[v].get(k)
                    for k in [
                        "entity_id",
                        "entity_type",
                        "kind",
                        "name",
                        "definition_revision",
                        "source_url",
                        "family",
                    ]
                }
                for v in neighbors
            ]
            detail["related_strategies"] = [
                dict(strategy_id=v, canonical_name=by_id[v]["name"])
                for v in neighbors
                if by_id[v]["kind"] == "strategy"
            ]
            detail["results"] = reader.results(item["kind"], eid)
            path = "/catalog/details/" + catalog_manifest[eid]["file"] + ".json.gz"
            write(path, detail)
            refs.append(
                dict(
                    kind=item["kind"],
                    entity_id=eid,
                    entity_type=item["entity_type"],
                    definition_revision=item["definition_revision"],
                    name=item["name"],
                    native_ids=item.get("source_native_ids", []),
                    detail_path=path,
                    definition_hash=digest(
                        dict(
                            formula=detail.get("formula"),
                            original_rule=detail["knowledge"].get("original_rule"),
                            definition=detail["knowledge"].get("original_definition"),
                        )
                    ),
                )
            )
        row = {k: item.get(k) for k in index_keys}
        row["knowledge"] = {
            k: item["knowledge"].get(k)
            for k in ["summary", "method_family", "filters", "formula"]
        }
        row["strategy"] = {
            k: item.get("strategy", {}).get(k) for k in ["template_id", "family_id"]
        }
        row["search_fields"] = {
            "来源原文": "\n".join(
                dict.fromkeys(txt for _, _, txt, _ in reader._documents.get(eid, []))
            )
        }
        work.attach(row)
        groups[item["kind"]].append(row)
    indexes = {}
    for kind, rows in groups.items():
        indexes[kind] = []
        for n in range(0, len(rows), 250):
            path = f"/catalog/indexes/universe-{kind}-{n // 250}.json"
            write(path, rows[n : n + 250])
            indexes[kind].append(path)
    factor_sources = [
        row
        for row in groups["source"]
        if row.get("source_type") == "factor_source_record"
    ]
    if factor_sources:
        path = "/catalog/indexes/universe-factor-source.json"
        write(path, factor_sources)
        indexes["factor_source"] = [path]
    write("/catalog/indexes.json", indexes)
    write("/catalog/manifest.json", catalog_manifest)
    edge_paths = []
    for offset in range(0, len(edges), 1000):
        path = f"/catalog/edge-chunks/{offset//1000}.json"
        write(path, edges[offset:offset+1000])
        edge_paths.append(path)
    write("/catalog/edges.json", {"schema_version": "quantgraph-edges/v1", "chunks": edge_paths})
    write(
        "/catalog/nodes.json",
        [
            {k: i[k] for k in ["entity_id", "name", "kind", "entity_type"]}
            for i in items
        ],
    )
    summary = research.summary()
    old_research = read_prior("/data/manifest.json")
    details = dict(old_research["details"])
    results = []
    for run in summary["runs"]:
        rid = run["run_id"]
        with research.connect() as con:
            ids = [
                r[0]
                for r in con.execute(
                    "SELECT variant_id FROM corpus_implementations WHERE run_id=? ORDER BY variant_id",
                    (rid,),
                )
            ]
        for vid in ids:
            detail = research.implementation(vid, run_id=rid)
            detail["curve"] = sample_curve(detail["curve"], detail["curve_meta"])
            for window in detail["metrics"].get("retained_windows", []):
                window["curve"] = sample_curve(window["curve"], window["curve_meta"])
            key = hashlib.sha256((rid + "\n" + vid).encode()).hexdigest()[:24]
            path = "/data/implementations/" + key + ".json.gz"
            details[rid + "|" + vid] = key
            is_old = rid + "|" + vid in old_research["details"]
            changed = write(path, detail, frozen=is_old)
            if changed:
                results.append(
                    dict(
                        origin_run_id=rid,
                        variant_id=vid,
                        manifest_sha256=detail["lineage"]["manifest_sha256"],
                        record_id=detail["id"],
                        detail_path=path,
                        detail_sha256=files[path]["sha256"],
                    )
                )
        if rid not in {r["run_id"] for r in old_research["runs"]}:
            with research.connect() as con:
                rows = []
                for record in con.execute(
                    "SELECT payload,search_text FROM corpus_records WHERE run_id=? ORDER BY id",
                    (rid,),
                ):
                    value = json.loads(record["payload"])
                    rows.append(
                        {
                            **{
                                k: value[k]
                                for k in [
                                    "id",
                                    "name",
                                    "status",
                                    "reason",
                                    "tested_variants",
                                    "implementations",
                                    "families",
                                ]
                            },
                            "audit": {
                                k: value["audit"].get(k)
                                for k in [
                                    "source_verification_status",
                                    "source_rule_attribution_status",
                                ]
                            },
                            "search_text": record["search_text"],
                        }
                    )
            write(f"/data/runs/{rid}/index.json.gz", rows)
            write(f"/data/runs/{rid}/summary.json", research.summary(rid))
        print("EXPORTED RUN", rid, len(ids), flush=True)
    state = work.load()
    native_ids = sorted(state["by_id"])
    work_records, work_entities = {}, {}
    for offset in range(0, len(native_ids), 100):
        chunk = {rid: work.record(rid) for rid in native_ids[offset : offset + 100]}
        path = f"/data/workscope/records-{offset // 100}.json.gz"
        write(path, chunk)
        for rid, row in chunk.items():
            work_records[rid] = path
            work_entities[row["research_scope"]["entity_id"]] = rid
    annotations = data_quality_annotations(catalog)
    write("/data/data-quality.json", annotations)
    manifest = dict(
        old_research,
        schema_version="private-quantgraph-static/v3",
        default_run=summary["run_id"],
        runs=summary["runs"],
        corpus_records=scope_summary["total_work_items"],
        tested_records=scope_summary["execution_records"],
        execution_versions=scope_summary["execution_versions"],
        snapshot_date=scope_summary["as_of_utc"],
        details=details,
        workscope_records=work_records,
        workscope_entities=work_entities,
        data_quality_file="/data/data-quality.json",
        research_scope_summary=scope_summary,
    )
    # Do not misattribute the new view to an old release's validation hash.
    for key in ["release_inventory_sha256", "final_validation_sha256"]:
        if key in manifest:
            manifest["historical_" + key] = manifest.pop(key)
    write("/data/manifest.json", manifest)
    meta = read_prior("/catalog/meta.json")
    fresh = reader.metadata()
    for key in [
        "counts",
        "visible_counts",
        "layer_counts",
        "knowledge_counts",
        "facets",
        "intake_summary",
        "factor_quality_summary",
    ]:
        if key in fresh:
            meta[key] = fresh[key]
    meta["research_scope_summary"] = scope_summary
    meta["historical_initial_batch_progress"] = meta.pop("snapshot_progress", None)
    meta["dataset"] = "最终交接6973条与后续研究对象；因子、组件和来源资料分层显示"
    meta["warnings"] = [
        "执行有结果不等于严格通过；数据质量、PIT、实现忠实度与统计证据分别核验。",
        "641条既有因子已逐ID登记不同核验范围；新增规则产生的4条定义引用仍待核，不能计为通过。",
    ]
    write("/catalog/meta.json", meta)
    # New references/details activate first. The last batch changes all visible indexes
    # together, so incomplete uploads never expose a partially updated catalog.
    pending = set(files)
    batches = []
    for offset in range(0, len(refs), 900):
        part = refs[offset : offset + 900]
        paths = {r["detail_path"] for r in part}
        batch = dict(
            schema_version="quantgraph-site-sync/v1",
            parent_batch_id=parent,
            files=[files[p] for p in sorted(paths)],
            entities=part,
            results=[],
        )
        pin = digest(batch)
        parent = "batch-" + pin
        name = f"batch-{len(batches):02d}.json"
        (output / name).write_text(canonical(batch))
        batches.append(
            dict(
                file=name,
                sha256=pin,
                batch_id=parent,
                files=len(paths),
                entities=len(part),
                results=0,
            )
        )
        pending -= paths
    final = dict(
        schema_version="quantgraph-site-sync/v1",
        parent_batch_id=parent,
        files=[files[p] for p in sorted(pending)],
        entities=[],
        results=results,
    )
    if len(pending) > 4096 or len(results) > 2000:
        raise ValueError("Final batch exceeds deployment contract")
    pin = digest(final)
    name = f"batch-{len(batches):02d}.json"
    (output / name).write_text(canonical(final))
    batches.append(
        dict(
            file=name,
            sha256=pin,
            batch_id="batch-" + pin,
            files=len(pending),
            entities=0,
            results=len(results),
        )
    )
    receipt = dict(
        schema_version="quantgraph-private-export/v1",
        scope=scope_summary,
        batches=batches,
        files=len(files),
        bytes=sum(r["bytes"] for r in files.values()),
        retained_implementation_bytes_checked=len(old_research["details"]),
        new_catalog_entities=len(refs),
        factor_quality_summary=fresh.get("factor_quality_summary"),
        lifecycle_flags=len(annotations),
        new_execution_trials=0,
    )
    (output / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2)
    )
    print(json.dumps(receipt, ensure_ascii=False), flush=True)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--baseline-root", action="append", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--parent-batch", required=True)
    args = parser.parse_args()
    export(args.runtime, args.baseline_root, args.output, args.parent_batch)

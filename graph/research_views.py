"""Private read model joining work scope, retained experiments and conclusions."""

import hashlib
from collections import Counter, defaultdict
from copy import deepcopy

from quantgraph.graph.corpus_research import _loads, fidelity_view, safe_research_view
from quantgraph.graph.research_universe import read_universe
from quantgraph.graph.research_interpretations import interpretations

TYPE_LABELS = {
    "legacy_strategy_record_pending_entity_review": "交接策略条目（实体类型待逐项核验）",
    "development_fixture": "开发样例",
    "strategy_implementation_candidate": "策略实现候选",
    "research_model": "论文研究模型",
    "signal_component": "规则组件",
}
REASONS = {
    "source_completion_and_implementation": "还需补齐来源定义并实现可核对的交易规则",
    "not_assessed_for_added_1160": "已纳入最终交接范围，执行检查正在安排",
    "universe_or_instrument_resolution": "标的池或交易工具尚需精确确认",
    "external_input_acquisition_and_implementation": "需要取得额外输入数据，再落实计算与执行规则",
    "first_run_already_tested": "原始批次已有探索性执行；数据与方法严格验收另列",
    "price_portfolio_programming_candidate": "可按价格与组合规则继续编程核验，尚未完成",
    "price_signal_programming_candidate": "可按价格信号继续编程核验，尚未完成",
    "native_intraday_implementation_and_acquisition": "需要原生盘中数据，并核对信号与成交时序",
    "previously_compiled_unfinished": "已有编译尝试，尚未完成可展示的执行",
    "not_assessed": "已保留工作项，尚未完成执行评估",
}


class ResearchWorkView:
    def __init__(self, catalog, research):
        self.catalog, self.research = catalog, research
        self.stamp = None
        self.state = None

    def _stamp(self):
        paths = [self.catalog.path, self.research.path]
        return tuple(
            (p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None
            for root in paths
            for p in [root, root.with_name(root.name + "-wal")]
        )

    def load(self):
        stamp = self._stamp()
        if stamp == self.stamp:
            return self.state
        universe = read_universe(self.catalog)
        if universe is None:
            self.stamp, self.state = stamp, None
            return None
        by_id = {r["record_id"]: r for r in universe["records"]}
        by_entity = {r["entity_id"]: r for r in universe["records"]}
        results = defaultdict(list)
        audit = {}
        runs = []
        unbound = []
        if self.research.path.exists():
            with self.research.connect() as con:
                runs = [
                    dict(r)
                    for r in con.execute(
                        "SELECT run_id,created_at,manifest_sha256,lineage FROM corpus_runs ORDER BY created_at DESC,run_id DESC"
                    )
                ]
                for run in runs:
                    lineage = _loads(run["lineage"])["declared_lineage"]
                    for row in con.execute(
                        """SELECT i.record_id,i.variant_id,i.metrics,r.payload AS record_payload
                        FROM corpus_implementations i JOIN corpus_records r ON r.run_id=i.run_id AND r.id=i.record_id
                        WHERE i.run_id=? ORDER BY i.variant_id""",
                        (run["run_id"],),
                    ):
                        rid = row["record_id"]
                        work = by_id.get(rid)
                        record = _loads(row["record_payload"])
                        rule = record.get("audit", {}).get("规则")
                        matched = (
                            work
                            and isinstance(rule, str)
                            and work["definition_sha256"]
                            == hashlib.sha256(rule.encode()).hexdigest()
                        )
                        if not matched:
                            unbound.append(
                                dict(
                                    record_id=rid,
                                    origin_run_id=run["run_id"],
                                    variant_id=row["variant_id"],
                                    reason="SOURCE_DEFINITION_BINDING_UNAVAILABLE",
                                )
                            )
                            continue
                        m = _loads(row["metrics"])
                        audit.setdefault(rid, record["audit"])
                        results[rid].append(
                            dict(
                                id=rid,
                                variant_id=row["variant_id"],
                                manifest_sha256=run["manifest_sha256"],
                                origin_manifest_sha256=lineage.get(
                                    "source_run_manifest_sha256"
                                ),
                                protocol_sha256=lineage["protocol_sha256"],
                                **fidelity_view(m, run["run_id"]),
                                evidence_subtype=m.get("evidence_subtype"),
                                original_method_reproduction_status=m.get(
                                    "original_method_reproduction_status"
                                ),
                            )
                        )
        notes = defaultdict(list)
        for row in interpretations(self.catalog):
            work = by_id.get(row["record_id"])
            if (
                work
                and row["definition_sha256"] == work["definition_sha256"]
                and row["catalog_definition_revision"] == work["definition_revision"]
            ):
                notes[row["record_id"]].append(row)
        summary = dict(
            version=universe["version"],
            manifest_sha256=universe["manifest_sha256"],
            total_work_items=len(by_id),
            final_handoff_records=universe["summary"]["final_handoff_records"],
            initial_batch_records=universe["summary"]["initial_batch_records"],
            additional_collected_objects=universe["summary"][
                "collected_additional_research_objects"
            ],
            entity_types=dict(
                Counter(r["payload"]["entity_type"] for r in by_id.values())
            ),
            execution_records=len(results),
            execution_versions=sum(map(len, results.values())),
            no_execution_records=len(by_id) - len(results),
            imported_runs=len(runs),
            interpreted_records=len(notes),
            uninterpreted_execution_records=len(set(results) - set(notes)),
            unbound_execution_versions=len(unbound),
            strict_validation_status="NOT_ESTABLISHED_BY_EXECUTION_COVERAGE",
            as_of_utc=max((r["created_at"] for r in runs), default=None),
            notice="工作项、探索性执行、原方法复现、严格数据/PIT验收与统计证据分别判断；没有结果不等于无效。",
        )
        self.state = dict(
            universe=universe,
            by_id=by_id,
            by_entity=by_entity,
            results=results,
            audit=audit,
            notes=notes,
            runs=runs,
            unbound=unbound,
            summary=summary,
        )
        self.stamp = stamp
        return self.state

    def summary(self):
        state = self.load()
        return deepcopy(state["summary"]) if state else None

    def scope(self, record_id):
        state = self.load()
        bound = state["by_id"][record_id]
        r = bound["payload"]
        results = state["results"].get(record_id, [])
        return dict(
            record_id=record_id,
            entity_id=bound["entity_id"],
            definition_revision=bound["definition_revision"],
            definition_sha256=bound["definition_sha256"],
            binding_kind=bound["binding_kind"],
            universe_version=state["universe"]["version"],
            entity_type=r["entity_type"],
            entity_type_label=TYPE_LABELS.get(r["entity_type"], "待核研究对象"),
            status="EXPLORATORY_EXECUTION_RETAINED" if results else "PENDING_EXECUTION",
            execution_versions=len(results),
            reason=(
                f"已有{len(results)}个探索性实现版本，原方法与数据严格验收另列"
                if results
                else REASONS.get(r.get("data_status"), "执行评估尚未完成")
            ),
            source_title=(r.get("raw_record") or {}).get("标题"),
            source_field_differences=r.get(
                "catalog_projection_metadata_differences", {}
            ),
            strict_validation_status="NOT_ESTABLISHED_BY_EXECUTION_COVERAGE",
            interpreted=bool(state["notes"].get(record_id)),
            in_scope=True,
        )

    def attach(self, item):
        state = self.load()
        if not state:
            return item
        row = state["by_entity"].get(item["entity_id"])
        if row and row["definition_revision"] == item["definition_revision"]:
            item["research_scope"] = safe_research_view(self.scope(row["record_id"]))
        return item

    def record(self, record_id, *, run_id=None):
        if run_id:
            return self.research.record(record_id, run_id=run_id)
        state = self.load()
        if not state:
            return self.research.record(record_id)
        if record_id not in state["by_id"]:
            raise KeyError(record_id)
        work = state["by_id"][record_id]
        row = work["payload"]
        scope = self.scope(record_id)
        audit = state["audit"].get(record_id) or dict(
            row.get("raw_record") or {},
            source_verification_status="NOT_INDIVIDUALLY_VERIFIED",
            source_rule_attribution_status="RETAINED_SOURCE_CLAIM_NOT_VERIFIED",
        )
        results = state["results"].get(record_id, [])
        return dict(
            id=record_id,
            name=row.get("name") or record_id,
            status=scope["status"],
            reason=scope["reason"],
            audit=audit,
            implementations=results,
            related_results=results,
            tested_variants=len(results),
            families=[],
            research_scope=scope,
            interpretations=deepcopy(state["notes"].get(record_id, [])),
            coverage_history=[],
            definition_sha256=work["definition_sha256"],
            definition_revision=work["definition_revision"],
            definition_revision_bound=True,
            limitations=[
                state["summary"]["notice"],
                "定义版本绑定只核对保留的规则/身份；不等于来源作者复现或严格数据验收。",
            ],
        )

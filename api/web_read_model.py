"""Website-only projection over FactorDB. No ingestion, execution or research gate."""

from collections import Counter
from quantgraph.factor_study import definition_identity
import hashlib
import json
import unicodedata
from urllib.parse import urlsplit

CATEGORY_LABELS = {
    "momentum": "动量",
    "price_trend": "价格趋势",
    "technical_price_volume": "技术价量",
    "volatility": "波动率",
}
FIELD_LABELS = {
    "close": "收盘价",
    "open": "开盘价",
    "high": "最高价",
    "low": "最低价",
    "volume": "成交量",
    "vwap": "成交量加权均价",
}
# UI vocabulary only; not persisted aliases, equivalence, or economic evidence.
FAMILY_LABELS = {
    "MA": "移动平均 均线",
    "ROC": "变化率 动量",
    "STD": "标准差 波动率",
    "CORR": "相关系数",
    "CORD": "相关系数变化",
    "BETA": "回归斜率",
    "RSQR": "回归拟合优度",
    "RESI": "回归残差",
    "RANK": "时序排名",
    "MAX": "滚动最大值",
    "MIN": "滚动最小值",
    "IMAX": "最高值位置",
    "IMIN": "最低值位置",
    "IMXD": "极值位置差",
    "VMA": "成交量移动平均",
    "VSTD": "成交量标准差",
    "VWAP": "成交量加权均价",
    "CLOSE": "收盘价",
    "OPEN": "开盘价",
    "HIGH": "最高价",
    "LOW": "最低价",
    "VOLUME": "成交量",
}


def safe_url(value):
    if not isinstance(value, str) or any(ord(c) < 32 for c in value):
        return None
    try:
        parts = urlsplit(value)
        if (
            parts.scheme.lower() in {"https", "http"}
            and parts.hostname
            and not parts.username
            and not parts.password
        ):
            return value
    except ValueError:
        pass
    return None


def normalize(text):
    return unicodedata.normalize("NFKC", str(text)).casefold().strip()


def revision(record):
    """Immutable view identity until the producer supplies definition_revision.

    Hash the actual public definition, not its UI translation or ingestion time.
    This is a local bookmark identity, not certification by a research contract.
    """
    if record.get("factor_variant_id"):
        return definition_identity(record)["definition_revision"]
    if record.get("definition_revision"):
        return record["definition_revision"]
    data = {
        k: v
        for k, v in record.items()
        if k not in {"created_at", "updated_at", "variants"}
    }
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                data, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode()
        ).hexdigest()
    )


def calculation_axis(record):
    if record.get("dialect") != "qlib" or not record.get("formula_ast"):
        return "未补充"
    operators = record.get("parameters", {}).get("operators", [])
    time_ops = {
        "delay",
        "mean",
        "std",
        "sum",
        "ts_rank",
        "ts_max",
        "ts_min",
        "ts_argmax",
        "ts_argmin",
        "quantile",
        "corr",
        "slope",
        "rsquare",
        "resi",
    }
    if any(op.split(":")[-1] in time_ops for op in operators):
        return "时间序列（依据 Qlib 公式算子；未做运行验证）"
    return "逐证券单期表达式（未声明截面排序）"


class WebReadModel:
    def __init__(self, db, studies=None):
        if db.dataset_scope != "public_qlib":
            raise ValueError("The website requires a verified public release")
        self.db = db
        self.studies = studies
        self.mode = "PRIVATE" if studies is not None else "PUBLIC"
        self.records = {}
        offset = 0
        while batch := db.search_factors(limit=1000, offset=offset):
            for row in batch:
                self.records[("variant", row["factor_variant_id"])] = row
            offset += len(batch)
        for cid in sorted({r["canonical_factor_id"] for r in self.records.values()}):
            self.records[("concept", cid)] = db.get_entity("FactorConcept", cid)
        offset = 0
        while batch := db.find_strategies(limit=1000, offset=offset):
            for row in batch:
                self.records[("strategy", row["strategy_id"])] = row
            offset += len(batch)
        self.items = [
            self.project(kind, eid, record)
            for (kind, eid), record in self.records.items()
        ]
        self.by_key = {(item["kind"], item["entity_id"]): item for item in self.items}
        self.entities = {
            r[0]: r[1] for r in db._query("SELECT entity_id, entity_type FROM entities")
        }
        self.legacy_result_count = db.stats()["counts"]["backtest_results"]

    def project(self, kind, eid, row):
        variants = []
        if kind == "concept":
            variants = [
                v
                for (k, _), v in self.records.items()
                if k == "variant" and v["canonical_factor_id"] == eid
            ]
        family = row.get("factor_concept", "").split(":")[-1]
        if kind == "concept":
            family = next(
                (v.get("factor_concept", "").split(":")[-1] for v in variants), ""
            )
        fields = row.get("required_fields") or sorted(
            {f for v in variants for f in v.get("required_fields", [])}
        )
        market = row.get("asset_class") or sorted({v["asset_class"] for v in variants})
        market = [market] if isinstance(market, str) else market
        name = row.get("variant_name") or row.get("canonical_name") or eid
        statuses = {
            "catalog": "已收录",
            "implementation": "概念无独立计算实现"
            if kind == "concept"
            else "来源实现已收录 · 计算语义未验证",
            "readiness": "未完成研究准备",
            "result": "无可展示的研究记录",
            "display": "公开可展示 · 须保留归属声明",
        }
        return {
            "entity_type": {
                "variant": "FactorVariant",
                "concept": "FactorConcept",
                "strategy": "Strategy",
            }[kind],
            "entity_id": eid,
            "definition_revision": revision(row),
            "kind": kind,
            "name": name,
            "aliases": row.get("aliases", []),
            "description": row.get("description"),
            "economic_logic": row.get("economic_logic"),
            "category": row.get("category"),
            "category_label": CATEGORY_LABELS.get(row.get("category"), "未分类"),
            "family": family or None,
            "family_label": FAMILY_LABELS.get(family, family),
            "formula": row.get("raw_formula"),
            "parameters": row.get("parameters", {}),
            "required_fields": fields,
            "markets": market or [],
            "frequency": row.get("frequency"),
            "axis": calculation_axis(row),
            "source_name": row.get("source_name")
            or ("Microsoft Qlib" if variants else None),
            "source_url": safe_url(row.get("source_url")),
            "source_revision": row.get("source_revision"),
            "source_sha256": row.get("source_sha256"),
            "source_native_ids": row.get("source_native_ids", []),
            "statuses": statuses,
            "result_status": "unresearched",
            "variant_count": len(variants),
        }

    def search(
        self,
        *,
        q="",
        kind="variant",
        category="",
        family="",
        field="",
        market="",
        result_status="",
        page=1,
        page_size=20,
    ):
        needle = normalize(q)
        rows = []
        for item in self.items:
            if (
                kind != item["kind"]
                or category
                and category != item["category"]
                or family
                and family != item["family"]
            ):
                continue
            if (
                field
                and field not in item["required_fields"]
                or market
                and market not in item["markets"]
            ):
                continue
            if self.studies is not None:
                studies = self.results(item["kind"], item["entity_id"])["items"]
                if studies:
                    item = {**item, "result_status": "researched",
                            "statuses": {**item["statuses"], "result": "历史探索结果（私有）"}}
            if result_status and result_status != item["result_status"]:
                continue
            haystack = normalize(
                " ".join(
                    str(v or "")
                    for v in [
                        item["name"],
                        *item["aliases"],
                        item["description"],
                        item["category_label"],
                        item["category"],
                        item["family_label"],
                        *item["source_native_ids"],
                        *(FIELD_LABELS.get(f, f) for f in item["required_fields"]),
                    ]
                )
            )
            if needle and needle not in haystack:
                continue
            names = [normalize(n) for n in [item["name"], *item["aliases"]]]
            score = (
                0
                if needle in names
                else 1
                if any(n.startswith(needle) for n in names)
                else 2
            )
            rows.append((score, item))
        rows.sort(key=lambda r: (r[0], r[1]["name"], r[1]["entity_id"]))
        start = (page - 1) * page_size
        return dict(
            items=[r[1] for r in rows[start : start + page_size]],
            total=len(rows),
            page=page,
            page_size=page_size,
            sort="name_alias_relevance_then_name",
            scope=self.mode,
        )

    def metadata(self):
        counts = Counter(i["kind"] for i in self.items)
        return dict(
            mode=self.mode,
            release=self.db.release_path.name,
            graph_api="v1",
            graph_version="0.2.0",
            adapter_version="web-read/v1",
            counts={k: counts[k] for k in ("variant", "concept", "strategy")},
            result_count=self.results()["total"],
            legacy_result_count=self.legacy_result_count,
            facets=dict(
                categories=[
                    {"value": c, "label": CATEGORY_LABELS.get(c, c)}
                    for c in sorted(
                        {i["category"] for i in self.items if i["category"]}
                    )
                ],
                families=[
                    {"value": f, "label": f + " · " + FAMILY_LABELS.get(f, f)}
                    for f in sorted({i["family"] for i in self.items if i["family"]})
                ],
                fields=[
                    {"value": f, "label": FIELD_LABELS.get(f, f) + " / " + f}
                    for f in sorted(
                        {f for i in self.items for f in i["required_fields"]}
                    )
                ],
                markets=[
                    {"value": m, "label": "股票 / equity" if m == "equity" else m}
                    for m in sorted({m for i in self.items for m in i["markets"]})
                ],
            ),
            contracts={
                "request": "research-request/v1",
                "result": "factor-study-result/v1",
                "status": "CONNECTED",
                "export_enabled": True,
            },
        )

    def detail(self, kind, eid):
        item = self.by_key[(kind, eid)]
        row = self.records[(kind, eid)]
        relations = []
        offset = 0
        while batch := self.db.relationships(eid, limit=1000, offset=offset):
            # Defense in depth: only endpoints in this public snapshot may appear.
            relations.extend(
                r
                for r in batch
                if r["from_id"] in self.entities and r["to_id"] in self.entities
            )
            offset += len(batch)
        implementations = []
        for r in relations:
            if r["to_type"] == "Implementation":
                impl = self.db.get_entity("Implementation", r["to_id"])
                implementations.append(
                    {
                        k: impl.get(k)
                        for k in [
                            "implementation_id",
                            "language",
                            "status",
                            "executed",
                            "revision",
                            "sha256",
                            "license",
                            "source_locator",
                        ]
                    }
                    | {"code_url": safe_url(impl.get("code_url"))}
                )
        papers = []
        for pid in row.get("paper_ids", []):
            p = self.db.get_entity("Paper", pid)
            papers.append(
                {
                    k: p.get(k)
                    for k in ["paper_id", "title", "year", "authors", "metadata_status"]
                }
                | {"url": safe_url(p.get("url"))}
            )
        cid = row.get("canonical_factor_id")
        related = [
            i
            for i in self.items
            if i["kind"] == "variant"
            and self.records[("variant", i["entity_id"])].get("canonical_factor_id")
            == cid
            and i["entity_id"] != eid
        ]
        concept = self.by_key.get(("concept", cid)) if kind == "variant" else None
        study_results = self.results(kind, eid)
        if study_results["items"]:
            matching = [r for r in study_results["items"] if r["mapping"]["identity"]["definition_revision"] == item["definition_revision"]]
            item = {**item, "statuses": {**item["statuses"], "result": "历史探索结果（私有）"}}
            if any(r["mapping"]["mapping_status"] == "VERIFIED" for r in matching):
                item["statuses"].update(implementation="已通过所列研究的计算语义核验", readiness="所列研究计划已冻结")
        return item | dict(
            implementations=implementations,
            papers=papers,
            authors=row.get("authors", []),
            concept=concept,
            related=related,
            relations=[
                r
                | {"source_label": r.get("source"), "source": safe_url(r.get("source"))}
                for r in relations
            ],
            related_strategies=self.db.find_strategies(factor=cid) if cid else [],
            source_locator=row.get("source_locator"),
            lookback=row.get("lookback"),
            required_fields_status=row.get("required_fields_status"),
            license=row.get("license", "MIT"),
            terms_url=safe_url(row.get("terms_url")),
            rights={
                "definition": "公开许可定义，保留 Microsoft 归属与 MIT 声明",
                "code": "仅展示公开来源实现的引用，未执行",
                "market_data": "REVIEW_REQUIRED · 不包含底层行情授权",
                "results": "没有已审核可公开展示的研究结果",
            },
            results=study_results,
        )

    def results(self, kind=None, eid=None):
        if kind is not None and (kind, eid) not in self.by_key:
            raise KeyError(eid)
        rows = []
        if self.studies is not None:
            ids = [eid] if eid else [i["entity_id"] for i in self.items if i["kind"] == "variant"]
            for entity_id in ids:
                offset = 0
                while batch := self.studies.query(entity_id, profile="research", limit=1000, offset=offset):
                    rows.extend(r for r in batch if all(p["internal_use"] == "ALLOWED"
                                                       for p in r["permissions"].values()))
                    offset += len(batch)
        # PUBLIC never loads or queries the private journal, including its counts.
        return dict(
            items=rows, total=len(rows),
            status="历史探索结果" if rows else "无可展示结果",
            contract="factor-study-result/v1", contract_status="CONNECTED",
            levels=["computational_test", "exploratory", "retrospective", "confirmatory"],
            reason=("仅供本机私有研究；不代表独立确认或实盘资格。" if rows else
                    "当前没有经许可可展示的研究结果。内部结果受权限限制；公开页面不查询其存在性、数量或指标。"),
        )

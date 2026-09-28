# 研究项目接入契约

研究仓库正式名称为 [quant-research-lab](https://github.com/KathenZK/quant-research-lab)，同级目录为 `../quant-research-lab`。Python package/import 继续使用 `strategy_lab`。架构为 `quant-knowledge-graph → quant-research-lab → quant-runner`。

新 ResearchEvidence、Implementation URI 和 repository identity 使用新仓库名；旧 evidence URI、artifact 字节及 hash 不回写。见 [命名迁移与兼容说明](REPOSITORY_NAME_MIGRATION.md)。

安装本仓库 SDK 后，显式传 root 或环境变量 QUANTGRAPH_ROOT。FactorDB 默认 curated research；商业用途先使用 commercial profile，并独立确认底层市场数据授权。

```python
from quantgraph import FactorDB

db = FactorDB(root="/path/to/quant-knowledge-graph")
candidates = db.search_factors(category="momentum", asset_class="equity")
for v in candidates:
    # 将以下身份写进研究的冻结合约，再在研究项目生成独立计算实现。
    frozen = {
        "release": db.stats()["release"],
        "factor_id": v["canonical_factor_id"],
        "variant_id": v["factor_variant_id"],
        "source_sha256": v["source_sha256"],
        "formula_id": v["formula_id"],
        "rights_status": v["rights_status"],
        "semantic_status": v["semantic_status"],
    }
```

required_fields 可能只做了语法/定义抽取；lookback 仅在能确定 Qlib 输入跨度时填值。上述输出不能替代 PIT 股票池、报告披露时间、价格复权、交易执行时点、成本、funding、OOS 等研究合约。

## 第二阶段允许导入的内容

- Strategy：用户已有策略的原始 namespace/ID、规范名称、规则、持仓、风控、频率、来源和 spec_sha256。
- strategy_factor：明确的 factor/variant 外键、作用角色、置信度、原始规则证据和来源。
- Implementation：指向已有研究代码的 URI/commit/hash，作为引用保存，不复制研究引擎。
- BacktestResult：original reported 与 lab reproduced 分开，保存 artifact URI/hash、合约位置、验证状态。

表和 schema 已实现，当前实际条目为 0。尚未提供自动导入器；策略层稳定接入是下一阶段，不能把因子公式自动包装为完整交易策略。

`find_strategies(factor="momentum")` 当前返回空列表；已经通过数据库测试验证双向查询和外键。策略因子关系的存在不证明收益归因。要声明 EMPIRICALLY_TESTED，必须提供研究结果引用。

知识库无 runner endpoint、API key、订单逻辑或策略发布接口。只有研究项目完成验收后，才由研究项目自身向 runner 交付。

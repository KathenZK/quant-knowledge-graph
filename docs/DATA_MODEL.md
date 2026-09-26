# 实体、关系与 ID

Pydantic 合约在 `models/entities.py`；JSON Schema 在 `models/schemas/`。存储是独立 SQLite 表和独立交换文件，不把策略和因子放在同一张表。

| 实体/表 | 关键标识 | 语义 |
|---|---|---|
| FactorConcept | canonical_factor_id、short_id | 经济概念或当前来源局部族；F 编号是显示别名 |
| FactorVariant | factor_variant_id | 参数、公式、数据域或组合构造的具体版本 |
| Formula | formula_id | 带方言的原式、标准式与 AST |
| Implementation | implementation_id | 固定 revision、文件摘要与源码行范围 |
| Paper | paper_id | 原论文引用或单独标记的汇总平台论文 |
| Author | author_id | 命名空间内的引用姓名；尚未做全球人物消歧 |
| Dataset | dataset_id | 定义集合/配置集合，不等于已收取市场面板 |
| Source | source_id | 采集来源与权限证据入口 |
| License | license_id | 对当前收录内容的权限，不能外推为市场数据授权 |
| Strategy | strategy_id | 规则、仓位、风控、原始 ID 和冻结 spec 摘要 |
| strategy_factor | strategy_id + variant_id + role | 独立关联，必须有证据、来源和置信度 |
| BacktestResult | backtest_result_id | 指向研究项目的结果 artifact，保留原报/复现之别 |

## ID 迁移

- 原因子库 record_id 原样保留在 source_records。
- 原 canonical_factor_id 实际表示具体信号，现在原样作为 factor_variant_id。
- 原 concept_id 成为新的 canonical_factor_id。
- `id_map` 显式保存三个标识的对应关系。
- F000001 等短 ID 来自 `models/id_registry.json`，只增不重排；被隔离概念的编号也不回收。
- UUID5 基于来源原生身份稳定生成；实现与公式另含内容/版本身份。不要按行号重新编号。

## 关系类型

`SAME_AS`, `ALIAS_OF`, `VARIANT_OF`, `DERIVED_FROM`, `RELATED_TO`, `IMPLEMENTATION_OF`, `USES_FACTOR`, `DESCRIBED_BY`, `IMPLEMENTED_BY`, `TESTED_ON`, `SOURCED_FROM`，另有 `AUTHORED_BY`。

每条关系有两端实体类型、证据、来源、confidence 和状态。SQL 外键连接 entity registry，构建校验端点类型。当前只写有证据的关系，声明支持并不代表每种类型已有实例。

- SAME_AS 目前仅用于同方言/频率/域下 Qlib 完全相同的来源表达式，8 条重复来源记录仍保留。
- 参数窗口属于 VARIANT_OF。名字相似只进入 normalized 的 duplicate_candidates。
- 原始源别名带 namespace，裸 Alpha001、SMB 等不作全局唯一键。
- Qlib 的 ROC5 和 CLOSE5 合并为同一具体表达式；ROC60 和 CLOSE59 不合并。
- FF3-SMB 与 FF5-SMB 同族但不同构造，保留不同变体，当前仅在 normalized。
- Momentum 价格排序信号、残差动量、行业动量、盈余动量不能凭关键词合并。收益组合的 Mom/UMD/WML 也不能直接与单股票排序信号 SAME_AS。
- 作者字符串和不完整引用不做全球 SAME_AS；同名同年不能证明是同一论文。

## 计算与收益归因

`USES_FACTOR`/strategy_factor 的 `RULE_LINK_ONLY` 只能证明规则使用了某个信号。要回答“收益由什么驱动”，必须由研究项目提供有合约、数据、成本及检验信息的 BacktestResult，并把 attribution_status 标记为 EMPIRICALLY_TESTED。合约要求这种标记必须绑定结果引用。

GrokBot V1 使用 StrategyConcept/Family、StrategyTemplate、StrategyVariant 最小层次，并投影到兼容的 Strategy。完整候选留在私有 normalized；支持的规则语法进入独立私有 curated。旧筛选结果标为 LEGACY_GROKBOT_SCREEN，不能用于 EMPIRICALLY_TESTED；不执行或复现上游代码。详见根目录 ARCHITECTURE.md。

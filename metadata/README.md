# 知识元数据

统一入口是[知识目录](CATALOG.md)，由[集合登记表](catalog.json)和 `graph/knowledge_catalog.py` 读取仓库中全部已登记元数据，按策略、因子、参考资料、待分类展示。来源、权限与审核状态是条目字段，不是两套知识库。

```bash
uv run quantgraph catalog-stats
uv run quantgraph catalog-search --kind strategy --source QuantConnect
uv run quantgraph catalog-search --kind factor --source qlib --frequency daily
uv run quantgraph catalog-search --kind reference --subtype technical_demo
uv run quantgraph catalog-search --status SOURCE_UNAVAILABLE
uv run quantgraph catalog-show M2904
uv run quantgraph catalog-show 'qlib:Alpha360:VWAP2'
uv run quantgraph catalog-validate
```

当前统一目录为 **8,797 张条目卡：6,522 策略、2,191 因子、83 参考资料、1 待分类**；收录不代表全部准入。每次新增后用 `catalog-stats` 核对最新计数。

原 M 编号、代码原生类名和因子原生 ID 都可查询。同名有歧义时带来源命名空间；稳定 `entity_id` 不随分类或证据版本改变。主 API `/v1/knowledge` 提供同一目录的检索、详情和关系，旧 `FactorDB` 与定义发布接口保持兼容。

| 元数据集合 | 在统一目录中的作用 |
|---|---|
| [CSV来源批次](CORPUS.md) | 保存原始采集字段及 M 编号，未经审核不猜类型 |
| [分类阅读索引](directory-index.json) | 保留前200条阅读页及其历史分类证据 |
| [正文分类批次](classifications/20261004-v1/README.md) | 对6,782条固定CSV正文追加类型、子类、理由、精确引文及质量标记 |
| [来源核查批次](source-reviews/20261004-v1/README.md) | 对4条原记录追加3条源码核查与1条来源不可得证据 |
| [原有审阅索引](index.json) | 给 M0256/M0259 追加已审规则和既有研究引用 |
| [源码采集批次](public-web/README.md) | 追加固定源码版本的策略/因子说明、许可和缺项 |
| [新增来源采集（进行中）](collections/README.md) | 逐条固定规则、来源、旧库比较和独立复核；目标为新增1000策略及1000因子 |
| [因子来源索引](factor-sources/index.json) | 保存1,570条因子变体及来源原生身份、定义准入和记录类型 |

这几类材料是同一目录的来源集合，不能把文件数相加当成策略数。9条源码资料中的4条与 CSV 有精确行摘要和文件定位绑定，在同卡保留不同证据版本，不宣称经济或实现等价。分类阅读页和旧审阅材料也不另算一张新卡。完整计数规则见 [CATALOG.md](CATALOG.md)。

后续同类网络批次放入 `public-web/<batch>/`，经校验后由现有集合适配器自动发现；新格式在 `catalog.json` 登记并增加适配器和测试。原冻结来源、分类裁决、原生 ID 和版本不原地改写。本次只接入仓库、CLI和主API，未修改活动 Site 或运行中的旧 Catalog。

当前CSV共6,971条，其中6,970条已有类型判定，仅[M0176](source-reviews/20261004-v1/README.md#m0176来源不可得)待分类。历史[正文分类批次](classifications/20261004-v1/index.json)冻结时的6,782条决定仍是6,242策略、453因子、83参考资料、4待分类；原批次及其队列不改写，不能将历史队列当作当前待分类集合。当前结果用`catalog-search --kind unclassified`查询。

新的[来源核查索引](source-reviews/20261004-v1/index.json)为M0115、M0196、M2122追加`SOURCE_CODE_REVIEWED`策略证据；M0176的原仓库与main/master README返回404，记录`SOURCE_UNAVAILABLE`而不补猜规则。集合适配器为`source_followups`，版本表示为`SOURCE_FOLLOWUP`，结果在`statuses.source_followup`中保留，可用`--status SOURCE_UNAVAILABLE`筛选。本批共4份核查记录，只增加4个证据版本，不增加条目卡；连同本轮来源采集后，当前共8,807个证据版本；历史已审说明14份，新增采集说明另记251份。未执行源码或回测，原文和源码快照不进入Git。

正文推断、来源源码核查与规则完整性各自保留。策略中的选股提纲与组件、因子中的构造提纲与特征族不具有相同的成熟程度。

## 类型分类与完整性

类型回答“这条记录是什么”，不回答“是否可以直接回测”。策略包括交易规则、资产配置、风险控制和有明确交易用途的组件；因子包括数值信号、特征定义与因子收益构造；参考资料包括研究流程、工具、目录、数据说明和技术测试。只有对象用途仍无法确定的记录才留待分类。

完整公式或执行条件缺失时仍可以判定对象类型，缺项继续保留；分类状态为`CONTENT_INFERRED`，定义状态为`UNVERIFIED`。NLP或教程正文若明确把信号映射为持仓，可以是策略；文件名含Regression也不自动排除。故意拒单、指定历史合约结算断言、NULL买力或订单有效期状态检查等记录，交易动作主要用于测试接口，按参考资料收录。

每条决定绑定原`record_id`、`row_sha256`和`rule_sha256`，证据须是规则正文的精确片段；否定句与“相对已收”的比较对象不能当成本条机制。新的类型证据不会改写原CSV、已有阅读页或来源审核状态。详情的`content_subtypes`和`classification_flags`保留子类与质量提示，`--subtype`可筛选子类。

## 来源核查校验

```bash
uv run python -m quantgraph.graph.source_review --index metadata/source-reviews/20261004-v1/index.json
# 仅在本机拥有被Git忽略的原始快照时使用：
uv run python -m quantgraph.graph.source_review --index metadata/source-reviews/20261004-v1/index.json --verify-snapshots
```

普通校验核对已提交的记录、schema、摘要、原CSV绑定及来源定位；`--verify-snapshots`另核本机原始文件的字节与摘要。源码与网页原文保留在忽略目录，Git只保存自撰规则、定位、版本摘要、许可状态和缺项。

## CSV历史接收与逐编号阅读材料

以下“本次”“本轮”均指此前 CSV 补录及阅读页整理的历史范围，其数量不能作为统一知识目录总数。

原 CSV 的 **6,973 个原 ID** 已完成逐条提取：仓库保存 **6,971 条完整来源 JSON**，
另有 **M2535、M2709 共 2 条**触发现有敏感字段检查，原值仅保存在本地隔离检查点，未公开。
先将旧检查点分支合入 main，再以既有 2,898 条为基线追加 **4,073 条**，保留原 ID 和 46 个编号缺口，不修改既有批次。
每条来源记录完整保留 11 列字符串、CSV 行序号、行与规则 SHA-256。

[按批次查找全部来源记录](CORPUS.md) · [全库覆盖与固定摘要](corpus-index.json)

另已核对 `dot/grok6973-checkpoints-20261003` 的 2,898 条：全部包含在本次 6,971 条内，
对应 3,045 个检查点文件逐字节相同，并沿用该分支的子集路径。该分支已通过
[PR #32](https://github.com/KathenZK/quant-knowledge-graph/pull/32) 合入 main；本次剩余增量为 **4,073 条**。
最初 main 的 500 条仅作历史对账，不与旧分支的 2,898 条相加。

来源记录沿用 `CATALOG_REPORTED_UNVERIFIED`，新增记录的类型仍为 `UNREVIEWED`。
这是供审查的采集元数据，不代表来源核实、经济有效性或商用许可通过。
本次新增已审定义 0、回测 0；未修改原生 loader/API、Lab 结果、个人批注或 Site。

分类Markdown阅读页仍是历史前两批 **M0001–M0200 共 200 条**，与来源记录的覆盖分开统计：

| 目录 | 可读原 ID 数 | 状态 |
|---|---:|---|
| [策略候选](strategies/README.md) | 171 | CONTENT_INFERRED / UNVERIFIED |
| [因子候选](factors/README.md) | 12 | CONTENT_INFERRED / UNVERIFIED |
| [待分类](unclassified/README.md) | 17 | CONTENT_INFERRED / UNVERIFIED |

本轮新增已审原生定义 **0**，新增回测 **0**。既有研究审阅 JSON **2**（M0256/M0259）保持原字节；
它们不在前两批 200 个 ID 内，因此目前两类阅读材料合计 **202 个不同原 ID**，不把同号多层重复计数。
阅读页继续引用原固定快照，不因本次来源补齐改变分类证据。
当前 [checkpoint 目录](corpus-checkpoints/grokbot-6973-20261003/) 覆盖 70 个原批次，
其中第 26、28 批只在 `subsets/` 保存公开安全子集。原逐编号 Markdown 层之外另有 **6,771 条来源记录**，没有在该旧层创建单独的 `<M-ID>.md` 文件；新的正文分类批次使用分组分页，覆盖情况由其批次索引单独记录。
来源记录已保存不等于分类阅读页完成或定义准入；2 条隔离记录也不计入公开完整性。

Markdown 是完整采集字段的目录阅读层；`metadata/index.json` 仍只登记原有审阅 JSON，原生 loader/API、
用户批注和定义均未改变。[目录清单](directory-index.json) 固定每份视图、原始 JSON、行 hash 和分类证据；
[首批分类裁决](directory-classification-batch-0001.json) 与 [第二批分类记录](directory-classification-batch-0002.json) 保留独立复核与最终口径差异。
第二批为 85 策略候选、3 因子候选、12 待分类；其中 4 条分类争议保守留在待分类。首批 100 条原文、分类与视图保持不变。
因子分数和因子收益允许通过多空组合构造，不能仅因存在持仓就一律归为策略。

校验来源全库覆盖，以及现有分类阅读页的完整字段与固定来源：

```bash
uv run pytest -q tests/test_metadata_corpus.py
uv run python -m quantgraph.graph.metadata_directory --metadata metadata
```

历史Markdown阅读层若继续小批扩展，复用 `metadata_directory`：使用绑定 `record_id/row_sha256/rule_sha256` 的明确分类列表，
每项给出 `entity_type`（strategy/factor/unclassified）、理由及原规则的精确证据片段；名称关键词不够。
通过 `--decisions`、`--batch-path`、`--batch-sha256`、`--commit` 和 `--output` 生成新目录供集成审阅；
已有 ID 拒绝覆盖，原冻结批次不改写。所有缺项继续显示原值，分类不升级为来源真实性或经济有效性验证。

`strategies/<原ID>.json` 保存策略；`factors/<原ID>.json` 保存因子。身份是
`identity_namespace + entity_type + record_id`，不重编号，不把参数配置算作新策略。
`native_source_id` 保留原编号，跨类型联系放在 `relations`，同名不自动去重。
`index.json` 精确登记每份记录的路径、字节数和 SHA-256，`schema.json` 定义共同合同。

策略/因子审阅层保存已审查的来源链接、版本和哈希及自撰规则。策略逐项记录标的/选池、信号、
入场、退出、仓位、风险、成本及执行时间；因子记录公式、输入、计算、经济含义、用途和
可用时间。各字段区分 `SOURCE_CODE_REVIEWED`、`RESEARCH_ASSUMPTION`、`MISSING`，
缺项必须保留为缺项。经济解释是研究假设；没有核实的论文不能编成收益支持。
未研究的记录可将 `lab` 设为 `null`，不能生成空想回测。不得加入来源网页全文、原始行情或个人批注。

原 CSV 的独立来源层采用 `source-records/<原ID>.json` 和 `source-record.schema.json`，
完整保存 11 列原值（包括采集规则摘要），各字段标为 `CATALOG_REPORTED_UNVERIFIED`。
类型未知仍保存完整正文，分类单列 `UNREVIEWED`；同 ID 来源层与审阅层只计一个原 ID。
批量工具生成的来源层须逐字段公开审查，敏感条目只在私有检查点 `private-only/` 保存，
不进入公开 metadata 索引。详细合同及不依赖原 CSV 的恢复命令见 [批量准备说明](BATCH_IMPORT.md)。

顶层 `metadata/index.json` 的 Lab 研究审阅记录为 M0256 和 M0259。前者为 HYPOTHESIS 诊断实例（4 配置、1 对照、1 个展示实现）；
后者 DATA_BLOCKED，行情回测 0。它们引用已合并 Lab commit
`8661e31456a44887903327c82cf0f97604fd3b03`，无需依赖某个工作盘路径。

从仓库根目录校验元数据：

```bash
uv run python -m quantgraph.graph.metadata_pilot --metadata metadata
```

已授权恢复该 Lab 提交的公开文件后，在新目录准备轻量导入（不联网、不回测、不改活动库）：

```bash
uv run python -m quantgraph.graph.metadata_pilot --metadata metadata \
  --lab /path/to/quant-research-lab --output /path/to/new-immutable-stage
```

准备器对每个 Lab 文件验证本记录 SHA/字节数、同提交 URL 和 `publication-manifest.json`
公开清单。M0256 的公开日净值 SHA 与冻结完整日账本不同；`public-curve-projection.json`
将两者连接，原 result-manifest 不被改写。指标保留 4h 原账本最大回撤；图中回撤另由
日收盘展示点计算，不能冒充日内回撤。没有公开基准曲线就不生成基准曲线。

## 原站增量导入契约

输出不是可直接同步到 Site 的整站快照，也不是原生 corpus collection：

- `strategy-cards.json`：复用 `graph.private_intake.import_cards` 的
  `source_curation_overlay_for / EXACT_CURRENT_REVISION` 审阅层；必须填入当前实体 ID
  和 definition_revision。未绑定时严格拒绝导入。不会新建同号实体、修改定义或个人批注。
- `records/M0256.json`、`records/M0259.json`：待增量合并研究记录。必须从当前活动批次读取
  原 record 后用 `merge_record` 追加引用；保留旧 status、audit、用户字段、所有既有结果。
  新审阅状态在 `lab_import_candidates` 单独留存，不能覆盖原历史状态。
- `implementations/<key>.json.gz`：只提供 M0256 基准实现；key 与现有 exporter 一致，
  为 SHA-256(`origin_run_id + "\n" + variant_id`) 的前 24 位。现有 detail/compare 数据形状
  保留 HYPOTHESIS、成本敏感性、基准指标和曲线限制；未绑定实体版本、未部署。
- `evidence/` 保存逐个已批准的公开轻量原件；`manifest.json` 列出精确文件哈希和字节数。
  任何已存在输出目录一律拒绝，重建必须选择新目录并对所有文件比较哈希。

若取得**已关闭、无 WAL/SHM 的 active catalog.sqlite 快照及其独立 SHA-256**，可加
`--catalog /path/catalog.sqlite --catalog-sha256 <hash>`。这只对临时复制库试导入两次，
验证定义未改、第二次零新增；不会写原库，也不证明快照仍是活动版本。
没有快照时 `dry-run.json` 的 metadata_import_ready 为 false，绝不能用 bundled 旧库替代。

唯一 Site 写者还需取得当前 active batch ID、完整文件清单、catalog manifest 和两个实体
详情、data manifest 和两个当前 record 及既有 result refs，核对稳定 ID/版本，再做增量
manifest/ref 更新。不得凭两个样本重算全库计数或覆盖旧 bundled 基线；保留原 seed 和
活动祖先链、个人批注及现有 UI。最后 CAS 检查 active parent，验收原策略详情和比较页。
源码提交、静态 hash 相符、临时库试导入均不等于站点已部署。

原 6973 条的完整接收清单、未知分类、小批检查点和断点核验命令见 [批量准备说明](BATCH_IMPORT.md)。

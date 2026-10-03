# 逐编号知识元数据

原目录首批 **M0001–M0100 共 100 条**已经可以直接阅读完整 11 字段：

| 目录 | 可读原 ID 数 | 状态 |
|---|---:|---|
| [策略候选](strategies/README.md) | 86 | CONTENT_INFERRED / UNVERIFIED |
| [因子候选](factors/README.md) | 9 | CONTENT_INFERRED / UNVERIFIED |
| [待分类](unclassified/README.md) | 5 | CONTENT_INFERRED / UNVERIFIED |

本轮新增已审原生定义 **0**，新增回测 **0**。既有研究审阅 JSON **2**（M0256/M0259）保持原字节；
它们不在首批 100 个 ID 内，因此目前两类阅读材料合计 **102 个不同原 ID**，不把同号多层重复计数。
固定来源快照 [`961e59d`](https://github.com/KathenZK/quant-knowledge-graph/tree/961e59d036652b252bf49b54eb56527f308632af/metadata/corpus-checkpoints/grokbot-6973-20261003)
包含 600 条完整 source records，其中 **500 条尚未集成到本目录阅读视图**。checkpoint 已保存不等于目录集成或定义准入。
本次主分支集成基线的 [checkpoint 目录](corpus-checkpoints/grokbot-6973-20261003/batches/) 有前 5 批 500 条；
上面的 600 专指固定来源快照。本轮只集成首批 100 条阅读视图，未声称全部 6973 条已经集成。

Markdown 是完整采集字段的目录阅读层；`metadata/index.json` 仍只登记原有审阅 JSON，原生 loader/API、
用户批注和定义均未改变。[目录清单](directory-index.json) 固定每份视图、原始 JSON、行 hash 和分类证据；
[分类裁决](directory-classification-batch-0001.json) 保留独立复核与最终口径差异。
因子分数和因子收益允许通过多空组合构造，不能仅因存在持仓就一律归为策略。

校验完整 11 字段、分类证据、目录计数和固定来源：

```bash
uv run python -m quantgraph.graph.metadata_directory --metadata metadata
```

后续小批复用 `metadata_directory`：使用绑定 `record_id/row_sha256/rule_sha256` 的明确分类列表，
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

目前已提交的审阅记录仅 M0256 和 M0259。前者为 HYPOTHESIS 诊断实例（4 配置、1 对照、1 个展示实现）；
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

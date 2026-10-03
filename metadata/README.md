# 逐编号知识元数据

`strategies/<原ID>.json` 保存策略；`factors/<原ID>.json` 保存因子。身份是
`identity_namespace + entity_type + record_id`，不重编号，不把参数配置算作新策略。
`native_source_id` 保留原编号，跨类型联系放在 `relations`，同名不自动去重。
`index.json` 精确登记每份记录的路径、字节数和 SHA-256，`schema.json` 定义共同合同。

这里只保存已审查的来源链接、版本和哈希及自撰规则。策略逐项记录标的/选池、信号、
入场、退出、仓位、风险、成本及执行时间；因子记录公式、输入、计算、经济含义、用途和
可用时间。各字段区分 `SOURCE_CODE_REVIEWED`、`RESEARCH_ASSUMPTION`、`MISSING`，
缺项必须保留为缺项。经济解释是研究假设；没有核实的论文不能编成收益支持。
未研究的记录可将 `lab` 设为 `null`，不能生成空想回测。不得加入全文、原始行情或个人批注。

目前仅收录 M0256 和 M0259。前者为 HYPOTHESIS 诊断实例（4 配置、1 对照、1 个展示实现）；
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

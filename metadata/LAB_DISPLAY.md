# 冻结 Lab 结果的显示投影

`graph.lab_display_projection` 是既有详情/比较页的数据适配器，不是回测器、原生corpus导入器或Site上传器。默认 `lab-display-sources.json` 显式固定19个已获准公开的Lab来源，保留16个ADAPTED与3个HYPOTHESIS；M1358的Graph HYPOTHESIS枚举与实际研究ADAPTED单列，不改变研究可信度。只有指定inventory内的ID可进入，不自动扫描Lab、catalog或全库。原M0256/M0259 pilot不变。

源清单包含每个ID的Lab commit、run/variant、publication manifest和实际消费文件的路径、URL、bytes、SHA256。支持publication的repo-relative及逐策略relative文件清单；源角色必须同时通过独立hash与publication allowlist。无原文全文、行情原始文件、完整账本、private Graph detail或批注输入。

离线预览（替换为本执行器已物化、固定commit的本地目录）：

```sh
python -m quantgraph.graph.lab_display_projection \
  --lab-batch009 <Lab-eca7ad8-source-root> \
  --lab-dot004 <Lab-1f0d1e1f-source-root> \
  --lab-root batch011=<Lab-db806c62-source-root> \
  --lab-root dot006=<Lab-3446cfcd-source-root> \
  --lab-root public_display_v2=<Lab-f6d2431b-source-root> \
  --output <new-private-preview-directory>
```

输出`records.json`、`implementations/<key>.json.gz`、`status.json`及独立文件hash清单。状态始终`STAGED_NOT_IMPORTED`，0新试验、0原生corpus导入、0部署。缺真实active-root/entity/revision时`active_merge_status=BLOCKED_CURRENT_ACTIVE_ROOT_ENTITY_REVISION_REQUIRED`，不产生Site envelope；绝不改用bundled seed。

后续批次可添加独立批准的inventory：`--sources <inventory.json> --sources-sha256 <independently-reviewed-sha256> --lab-root <group>=<source-root> --ids <explicit-id...>`。旧v1合同适用已声明的calendar2024/native5m、4策略配置+1新建或复用控制；其他窗口或执行结构应新增明确适配与测试，不静默补默认值。下述v2日频采样profile是显式新增的有限结构。默认清单不随全库增长扩量；batch011新增4条固定于Lab main `db806c62ced6694f13f1250cb132134a83145d22` 的publication revision3，原8条pins保留。

dot006 的 M0253/M0272/M0264/M0266 明确固定于已推送分支提交 `3446cfcd577d3341c862b3bcd84e82701ffa0e2e`，不声称该提交已进入 Lab main 或已部署 Site。它们使用 `PUBLIC_DERIVED_DISPLAY_MANIFEST`，与原12条的运行证据清单区别保存；原12条记录和detail字节保持不变。该派生清单绑定 summary/protocol/C0/曲线及历史publication allowlist，且排除自身与引用它的record，避免循环hash；当前revision3 publication再固定新增显示文件。类型必须由inventory、来源manifest及record引用一致声明，不能静默降为原运行manifest。

M0287/M0289/M1358新增来源固定于已推送的Lab分支提交 `f6d2431bc5c727d6525851a4e6c80b2a2acede33`，分别为publication revision2/2/4；不推断已并入Lab main或Site。原16条inventory对象、记录与压缩detail保持原字节。`graph.lab_display_v2`只接受明确的`quantgraph-public-derived-display-manifest/v2`及两个冻结profile：`NATIVE_5M_RULE_CARD_V2`和`DAILY_SAMPLED_APPROVED_DETAIL_V1`，不把未知结构回退为v1。当前publication验证实际读取的49个角色对象；历史publication验证原`dba8d1d64318f9909cdcfd3bc9c382842a1a742b`来源链。旧README和publication从历史快照取相同哈希字节；M1358私有输出inventory只有已公开的路径/hash引用，正文和其引用的私有NAV均不读取。

原生v2两条各366点，按原USDT权益/100000核对，保留首日损益、估值边界、source_native_drawdown。M0289保持原3.849/3.798幂次、四配置零交易与Sharpe null。M1358直接保留已获准的25个归一化样本对象（首日+24个UTC月末），不再次除100000、不重采样、不由25点推算731日回撤。`curve_meta`区分25显示点与731日指标；原2023、2024、2023-2024期间统计保留，并为现有UI默认期间添加`full`作为2023-2024的等值别名。日频lag2标为`additional_lag_unit=day`，原生两条为`native_5m_bar`；M1358原日频规则、费用另付USDT和研究ADAPTED/Graph HYPOTHESIS区别进入现有spec/assumptions/lineage。未改变UI、默认页面、批注或六字段transport。

派生类型保留在投影record、related_results/implementations、detail及lineage、增量manifest.runs；lineage使用`source_display_manifest_sha256`，不冒称原私有`source_run_manifest_sha256`。含派生类型时，输出文件索引标为`LAB_DISPLAY_ARTIFACT_INDEX`并列出实际来源类型。规则从record.rules进入spec.params.rules，逐字段核对已pin的规则卡与协议；论文/经济假设缺证状态按原record保留。原生source_native_drawdown单列保存，与图上每日净值计算的drawdown区分；净值仍除以冻结初始100000，原UTC日与次日午夜估值边界都校验。

显示转换保留来源不改原件：equity用原nav或冻结初始资金100000归一化，不按首日点重置；annualized_return映射cagr、每日Sharpe映射sharpe、费用键映射协议的0/20bps，原生5m与每日观察数分开。指标保留原生最大回撤，图上回撤由每日NAV计算。M0298保留原估值时间，显示日为其午夜边界前一日；M0304公开没有曲线，输出空curve和明确原因。各执行模型的假设和差异来自公开规则/协议；ADAPTED不改称STANDARDIZED。复用基准不计新控制试验。

可选`--active-root <private-readback> --active-sha256 <receipt-sha> --parent-batch <exact-active>`只生成增量**草稿**。输入`active-snapshot.json`应由sole Site writer从真实current读取并独立固定：

```json
{
  "schema_version": "quantgraph-active-readback/v1",
  "source": "CURRENT_SITE_READBACK",
  "bundled_seed": false,
  "active_batch": "batch-<actual-64-hex>",
  "bindings": {"M0300": {"entity_id": "<actual>", "definition_revision": "<actual>"}},
  "files": {"/data/manifest.json": {"sha256": "<actual>", "bytes": 123}}
}
```

`assets/`保存receipt中逐文件固定的真实assets；必须包含data/catalog manifest、实际catalog details、目标workscope分片及已存在的同run/variant详情。receipt的source字符串不是认证机制，不能自行填写成已核验。合并核对原生ID/实体/定义版本；更新实际workscope入口，保留非目标记录和旧audit/用户字段，以既有merge_record追加结果；同run/variant不同bytes拒绝，精确重放无新增。即使manifest.details遗漏已有实现，receipt.files已固定的路径仍不可覆盖：不同bytes拒绝；相同bytes可原样随草稿登记，以补齐索引和结果引用。已有native定义、用户批注和原8ID的16个结果引用不重写；新4ID当前Site旧引用尚待取得实际snapshot核对。新runs仅供既有详情/比较页实现读取，不冒充完整native collection运行级统计。

目标run_id若已存在，manifest.runs必须只有一条匹配记录，且manifest_kind与source_manifest_sha256均精确一致；字段缺失、类型/hash冲突或重复run_id都拒绝，不推断旧记录身份、不覆盖旧元数据。完全一致时保留其所有额外字段。非目标旧run即使缺少这些字段也按原字节对应的对象保留。

`site-sync-candidate.json`使用既有Sites envelope，`entities=[]`，仅追加获准显示对象与必要data索引/分片。草稿不提供授权、activation或CAS保证，`ready_for_direct_site_sync`始终false；真实权限、完整快照/统计复核及最终串行激活归sole Site writer。站点若为public，不能把既有owner-private service上传前置条件当作成立。

现有Site transport及D1 qg_result_refs只接受六字段：origin_run_id、variant_id、manifest_sha256、record_id、detail_path、detail_sha256。本适配保持该合同，不增加会被Worker拒绝的kind字段；类型通过已hash固定的detail可达。record.related_results中的类型与D1 transport字段不是同一个结构。本次不改Worker、上传协议或访问权限。

测试：`pytest tests/test_lab_display_v2.py tests/test_lab_display_projection.py tests/test_metadata_pilot.py tests/test_site_sync_bulk.py`；前端历史兼容门禁为`npm exec vitest run tests/lab-display.test.ts tests/corpus-research.test.tsx tests/reading-brief.test.tsx tests/research-scope.test.tsx tests/hosted-feedback.test.tsx`及`npm run typecheck`，仅适配Python结构且未改UI时按范围选择复跑。fixture全为合成值，不在CI读取私人Lab数据；实际源预览和逐文件读回回执保持私有，不进Git。

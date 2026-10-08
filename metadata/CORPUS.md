# CSV 来源记录总目录

本次追加 4,073 条，连同合并后 main 已有的 2,898 条，公开仓库共保存 **6,971 条完整来源记录**。
原表共 6,973 条；M2535、M2709 的规则字段触发现有 `CREDENTIAL_OR_SIGNED_URL` 检查，
整条原值保存在本地隔离检查点，不裁字段、不放宽检查器，也不计为已公开。命中检查不代表已经确认存在真实凭证。

每条 JSON 沿用 `quantgraph-catalog-source-record/v1`，包含原 ID、名称、市场、规则、作者或机构、
标题、source_url、页码或文件、可回测、别名来源、提出日期的完整原字符串。
空值、换行、日期和“：高”等原标签均不改写。同名不合并，46 个编号缺口不补号。
所有原字段仍为 `CATALOG_REPORTED_UNVERIFIED`；除已有 M0256/M0259 审阅类型外，来源层保持 `UNREVIEWED`。
自动检查未命中不等于来源、分类、许可或经济有效性通过；商业使用仍为 `REVIEW_REQUIRED`。

现有 200 页分类阅读页和 2 份审阅 JSON 保持原字节。新增已审定义 0、回测 0；
本次只补充 Git 中的来源记录，没有将这些记录导入活动数据库或部署到 Site。

## 已有分支核对

最初 `main` 的 [`103b2dd`](https://github.com/KathenZK/quant-knowledge-graph/commit/103b2dd15d57ddaf78a299a337e1c2ba03b8cb1a) 有 500 条；
`dot/grok6973-checkpoints-20261003` 的 [`ccd868c`](https://github.com/KathenZK/quant-knowledge-graph/commit/ccd868c371fe9761cd018f8d2156e89d98a273b0) 有 2,898 条。
后者覆盖前 29 个原批次，包含第 26、28 批各 99 条的子集。该分支的 2,898 条来源记录和全部
3,045 个检查点文件（包括 schema、index、inventory、manifest 和已有审阅层）与本次对应文件逐字节一致。
没有遗漏、冲突或重复计数；本次沿用该分支原有的 `subsets/batch-0026-public-v1/` 和
`subsets/batch-0028-public-v1/` 路径。固定提交和计数见总索引 `prior_branch_overlap`。

旧分支已通过 [PR #32](https://github.com/KathenZK/quant-knowledge-graph/pull/32) 合入 main，
本次基线为 [`eb7618d`](https://github.com/KathenZK/quant-knowledge-graph/commit/eb7618d72337d264654c75cdb091b2403902be1c)。
新增录入仅为第 30–70 批 4,073 条，已有 2,898 条不重复计入增量。

| 比较基线 | 已有公开来源记录 | 本次增加 | 本次合计 |
|---|---:|---:|---:|
| 合并前 main（历史对账） | 500 | 6,471 | 6,971 |
| 合并后 main（本次基线） | 2,898 | 4,073 | 6,971 |

## 固定输入与复核

- 文件：`quant-master-draft.csv`，6,470,637 字节，6,973 个唯一原 ID。
- SHA-256：`15cc0ecbcb23261e3cd7f2fb0851815daed59951090d9ce3e759ef224ea6f415`。
- ID 范围：M0001–M7019，46 个缺口列在 [corpus-index.json](corpus-index.json)。
- 已合入 main 的前 29 批（含两份子集）保留原 manifest、schema、index、inventory 和来源记录字节；第 30–70 批为本次新增。
- 每批 manifest 固定所有文件的字节数和 SHA-256；总索引再固定每批 manifest SHA-256。

使用现有 `metadata_catalog plan/stage` 从上述固定 CSV 生成，每批按 CSV 记录序号取 100 条，
末批 73 条；第 26、28 批通过现有 `public-subset` 派生各 99 条的独立子集。
原 CSV、完整私有计划和含隔离记录的原批次不进入 Git。复建命令沿用 [BATCH_IMPORT.md](BATCH_IMPORT.md)。
本地生成时，所有 6,973 条均已从来源记录恢复并与原 CSV 的 11 字段逐一比较；
公开部分另外比较来源记录原字节，未重写采集摘要。

无需原 CSV 即可检查仓库内的全量结构、字段、摘要、原 ID 覆盖、编号缺口和隔离边界：

```bash
uv run pytest -q tests/test_metadata_corpus.py tests/test_metadata_directory.py
```

批次内 `metadata/source-records/<原ID>.json` 是完整来源，`inventory.json` 提供逐 ID 的行摘要和文件位置。
CSV 行号是数据记录序号；带引号的字段内换行不增加记录数。历史批次的 `remote_persistence_verified` 等状态保持原值，
本次不会将旧来源清单改写为新的发布或远端持久化证明。

## 批次导航

| 批次 | CSV 记录序号 | 原 ID 首尾 | 公开条数 | 隔离 ID |
|---|---:|---|---:|---|
| [batch-0001](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0001-v2/metadata/source-records/) | 1–100 | M0001–M0100 | 100 | 无 |
| [batch-0002](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0002-v2/metadata/source-records/) | 101–200 | M0101–M0200 | 100 | 无 |
| [batch-0003](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0003-v2/metadata/source-records/) | 201–300 | M0201–M0300 | 100 | 无 |
| [batch-0004](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0004-v2/metadata/source-records/) | 301–400 | M0301–M0400 | 100 | 无 |
| [batch-0005](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0005-v2/metadata/source-records/) | 401–500 | M0401–M0500 | 100 | 无 |
| [batch-0006](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0006-v2/metadata/source-records/) | 501–600 | M0501–M0600 | 100 | 无 |
| [batch-0007](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0007-v2/metadata/source-records/) | 601–700 | M0601–M0700 | 100 | 无 |
| [batch-0008](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0008-v2/metadata/source-records/) | 701–800 | M0701–M0800 | 100 | 无 |
| [batch-0009](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0009-v2/metadata/source-records/) | 801–900 | M0801–M0900 | 100 | 无 |
| [batch-0010](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0010-v2/metadata/source-records/) | 901–1000 | M0901–M1000 | 100 | 无 |
| [batch-0011](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0011-v2/metadata/source-records/) | 1001–1100 | M1001–M1100 | 100 | 无 |
| [batch-0012](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0012-v2/metadata/source-records/) | 1101–1200 | M1101–M1200 | 100 | 无 |
| [batch-0013](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0013-v2/metadata/source-records/) | 1201–1300 | M1201–M1300 | 100 | 无 |
| [batch-0014](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0014-v2/metadata/source-records/) | 1301–1400 | M1301–M1400 | 100 | 无 |
| [batch-0015](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0015-v2/metadata/source-records/) | 1401–1500 | M1401–M1500 | 100 | 无 |
| [batch-0016](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0016-v2/metadata/source-records/) | 1501–1600 | M1501–M1600 | 100 | 无 |
| [batch-0017](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0017-v2/metadata/source-records/) | 1601–1700 | M1601–M1700 | 100 | 无 |
| [batch-0018](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0018-v2/metadata/source-records/) | 1701–1800 | M1701–M1800 | 100 | 无 |
| [batch-0019](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0019-v2/metadata/source-records/) | 1801–1900 | M1801–M1900 | 100 | 无 |
| [batch-0020](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0020-v2/metadata/source-records/) | 1901–2000 | M1901–M2000 | 100 | 无 |
| [batch-0021](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0021-v2/metadata/source-records/) | 2001–2100 | M2001–M2100 | 100 | 无 |
| [batch-0022](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0022-v2/metadata/source-records/) | 2101–2200 | M2101–M2200 | 100 | 无 |
| [batch-0023](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0023-v2/metadata/source-records/) | 2201–2300 | M2201–M2300 | 100 | 无 |
| [batch-0024](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0024-v2/metadata/source-records/) | 2301–2400 | M2301–M2400 | 100 | 无 |
| [batch-0025](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0025-v2/metadata/source-records/) | 2401–2500 | M2401–M2500 | 100 | 无 |
| [batch-0026（子集）](corpus-checkpoints/grokbot-6973-20261003/subsets/batch-0026-public-v1/metadata/source-records/) | 2501–2600 | M2501–M2600 | 99 | M2535 |
| [batch-0027](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0027-v2/metadata/source-records/) | 2601–2700 | M2601–M2700 | 100 | 无 |
| [batch-0028（子集）](corpus-checkpoints/grokbot-6973-20261003/subsets/batch-0028-public-v1/metadata/source-records/) | 2701–2800 | M2701–M2800 | 99 | M2709 |
| [batch-0029](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0029-v2/metadata/source-records/) | 2801–2900 | M2801–M2904 | 100 | 无 |
| [batch-0030](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0030-v2/metadata/source-records/) | 2901–3000 | M2905–M3010 | 100 | 无 |
| [batch-0031](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0031-v2/metadata/source-records/) | 3001–3100 | M3011–M3133 | 100 | 无 |
| [batch-0032](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0032-v2/metadata/source-records/) | 3101–3200 | M3134–M3246 | 100 | 无 |
| [batch-0033](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0033-v2/metadata/source-records/) | 3201–3300 | M3247–M3346 | 100 | 无 |
| [batch-0034](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0034-v2/metadata/source-records/) | 3301–3400 | M3347–M3446 | 100 | 无 |
| [batch-0035](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0035-v2/metadata/source-records/) | 3401–3500 | M3447–M3546 | 100 | 无 |
| [batch-0036](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0036-v2/metadata/source-records/) | 3501–3600 | M3547–M3646 | 100 | 无 |
| [batch-0037](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0037-v2/metadata/source-records/) | 3601–3700 | M3647–M3746 | 100 | 无 |
| [batch-0038](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0038-v2/metadata/source-records/) | 3701–3800 | M3747–M3846 | 100 | 无 |
| [batch-0039](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0039-v2/metadata/source-records/) | 3801–3900 | M3847–M3946 | 100 | 无 |
| [batch-0040](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0040-v2/metadata/source-records/) | 3901–4000 | M3947–M4046 | 100 | 无 |
| [batch-0041](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0041-v2/metadata/source-records/) | 4001–4100 | M4047–M4146 | 100 | 无 |
| [batch-0042](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0042-v2/metadata/source-records/) | 4101–4200 | M4147–M4246 | 100 | 无 |
| [batch-0043](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0043-v2/metadata/source-records/) | 4201–4300 | M4247–M4346 | 100 | 无 |
| [batch-0044](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0044-v2/metadata/source-records/) | 4301–4400 | M4347–M4446 | 100 | 无 |
| [batch-0045](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0045-v2/metadata/source-records/) | 4401–4500 | M4447–M4546 | 100 | 无 |
| [batch-0046](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0046-v2/metadata/source-records/) | 4501–4600 | M4547–M4646 | 100 | 无 |
| [batch-0047](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0047-v2/metadata/source-records/) | 4601–4700 | M4647–M4746 | 100 | 无 |
| [batch-0048](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0048-v2/metadata/source-records/) | 4701–4800 | M4747–M4846 | 100 | 无 |
| [batch-0049](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0049-v2/metadata/source-records/) | 4801–4900 | M4847–M4946 | 100 | 无 |
| [batch-0050](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0050-v2/metadata/source-records/) | 4901–5000 | M4947–M5046 | 100 | 无 |
| [batch-0051](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0051-v2/metadata/source-records/) | 5001–5100 | M5047–M5146 | 100 | 无 |
| [batch-0052](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0052-v2/metadata/source-records/) | 5101–5200 | M5147–M5246 | 100 | 无 |
| [batch-0053](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0053-v2/metadata/source-records/) | 5201–5300 | M5247–M5346 | 100 | 无 |
| [batch-0054](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0054-v2/metadata/source-records/) | 5301–5400 | M5347–M5446 | 100 | 无 |
| [batch-0055](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0055-v2/metadata/source-records/) | 5401–5500 | M5447–M5546 | 100 | 无 |
| [batch-0056](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0056-v2/metadata/source-records/) | 5501–5600 | M5547–M5646 | 100 | 无 |
| [batch-0057](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0057-v2/metadata/source-records/) | 5601–5700 | M5647–M5746 | 100 | 无 |
| [batch-0058](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0058-v2/metadata/source-records/) | 5701–5800 | M5747–M5846 | 100 | 无 |
| [batch-0059](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0059-v2/metadata/source-records/) | 5801–5900 | M5847–M5946 | 100 | 无 |
| [batch-0060](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0060-v2/metadata/source-records/) | 5901–6000 | M5947–M6046 | 100 | 无 |
| [batch-0061](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0061-v2/metadata/source-records/) | 6001–6100 | M6047–M6146 | 100 | 无 |
| [batch-0062](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0062-v2/metadata/source-records/) | 6101–6200 | M6147–M6246 | 100 | 无 |
| [batch-0063](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0063-v2/metadata/source-records/) | 6201–6300 | M6247–M6346 | 100 | 无 |
| [batch-0064](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0064-v2/metadata/source-records/) | 6301–6400 | M6347–M6446 | 100 | 无 |
| [batch-0065](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0065-v2/metadata/source-records/) | 6401–6500 | M6447–M6546 | 100 | 无 |
| [batch-0066](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0066-v2/metadata/source-records/) | 6501–6600 | M6547–M6646 | 100 | 无 |
| [batch-0067](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0067-v2/metadata/source-records/) | 6601–6700 | M6647–M6746 | 100 | 无 |
| [batch-0068](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0068-v2/metadata/source-records/) | 6701–6800 | M6747–M6846 | 100 | 无 |
| [batch-0069](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0069-v2/metadata/source-records/) | 6801–6900 | M6847–M6946 | 100 | 无 |
| [batch-0070](corpus-checkpoints/grokbot-6973-20261003/batches/batch-0070-v2/metadata/source-records/) | 6901–6973 | M6947–M7019 | 73 | 无 |

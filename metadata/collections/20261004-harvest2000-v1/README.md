# 新增策略与因子采集（进行中）

目标是新增 1,000 个策略定义/实现和 1,000 个因子定义/实现。目前为分批采集与逐条复核阶段，尚未完成目标。当前通过本批验收的数量以 [manifest.json](manifest.json) 为准；下载数量和新文件数不计入合格新增。

[质量合同](quality-contract.json)固定基线与计数边界。策略要求入场、退出、仓位和核心信号清楚；因子要求输入、公式和计算步骤清楚。用户已确认因子包括投资因子、技术指标、风险指标和统计特征；链上数值特征单列类别，公式、来源和参数族边界均保留。只改参数、窗口、资产或周期，镜像移植、旧定义新版本和存疑近似均不算新增构造。

[reviews.json](reviews.json)保存逐条审核人、源码行段摘要、旧库近邻比较、定义签名及计数裁决；[source-lock.json](source-lock.json)保存来源版本、文件摘要、取得时间和许可角色。代码、网页原文与本机详细验收记录留在 raw/reports，不进入公开 Git。FMZ 转载版本与原作者确认状态分开说明，代码许可不扩张至原论文或行情。

只有完成来源、定义和去重复核的条目进入本索引；待审、缺项与重复候选保留在采集队列，不进入合格计数。统计特征按原作者计算器算法族计数，不将多个参数组、对称方向或输出分量展开。

本批没有运行上游源码、生成回测或验证收益。`SOURCE_DESCRIPTION_REVIEWED`表示核对原供应商定义文档，不冒称读过其内部计算源码。集合schema只在原字段状态中增加这一选项，历史schema与来源批次保持原样。`SOURCE_CODE_REVIEWED` 表示读过已固定源码，`NOT_EXECUTED`、`NOT_TESTED` 和 `REVIEW_REQUIRED` 分别保留计算、经济和商业权利边界。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261004-harvest2000-v1
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261004-harvest2000-v1 --verify-snapshots
uv run quantgraph catalog-search --status REVIEWED_NEW_DEFINITION --limit 1000
```

各批累计进度见[采集总览](../README.md)。第一条命令检查公开元数据完整性；第二条还核对本机保存的原始字节和每个源码片段。公开克隆没有 raw 时不能声称重新核实了来源正文。自动相似性匹配只产生候选，不自动判定公式等价或新颖。

## 第一批检查点

| 类型 | 合格新增 | 目标 |
|---|---:|---:|
| 策略 | 14 | 1,000 |
| 因子与量化特征 | 44 | 1,000 |

因子按定义类型分开统计：onchain_metric 12、risk_measure 1、statistical_feature 15、technical_indicator 16。不同子类均不代表已证明收益有效。

旧库比较必须绑定原生ID、仓库文件、整文件摘要及CSV行摘要；跨批相同定义签名不能重复计数。签名与自动代码指纹只是审阅辅助，不是形式化经济等价证明。

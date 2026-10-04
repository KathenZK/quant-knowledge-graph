# 第三批来源采集

本批新增 **19 个策略、10 个因子**。前三批累计为 49 个策略、69 个因子；目标仍在进行中，见[采集总览](../README.md)。

策略逐条核对信号、入场、退出、仓位和时序，保留原作者代码的已知边界。因子包括 6 个复杂度或分形统计构造、2 个自适应技术指标、1 个波动冲击恢复风险测度和 1 个尾部区间百分位特征族。一个构造的参数、输出分量或移植版本不拆条计数。

去重比较包含旧目录定义、此前批次和本批近邻。对分形、波动与滤波等易混构造，进一步核对旧条目的原论文、源码或导入库，分别说明相同概念与不同算法的边界。公开比较绑定文件、原生 ID 和摘要；待核、同源和存在未解疑点的候选均未计入。

[source-lock.json](source-lock.json)固定原件版本、取得时间、许可角色和摘要；[reviews.json](reviews.json)保存逐条审核、精确行段证据和旧库比较。本批没有执行来源代码、行情计算或回测；`NOT_EXECUTED`、`NOT_TESTED` 与 `REVIEW_REQUIRED` 分别保留计算、经济验证和商业许可的未完成状态。原件和详细本机报告不进入公开 Git。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261004-harvest2000-v3
# 本机另有保存的原件时：
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261004-harvest2000-v3 --verify-snapshots
```

# 第二批来源采集

本批新增 **16 个策略、15 个因子**。和第一批累计为 30 个策略、59 个因子；目标仍在进行中，见[采集总览](../README.md)。

策略逐条核对信号、入场、退出、仓位、时序与已知边界，包括保存触发状态、计时刷新、组合确认等计算规则。因子分为 9 个金融风险或表现测度、6 个统计特征；输入类型、缺值处理、分组与窗口可用时点均按固定源码说明。

复核排除了已经存在的量价突破和量加权 MACD 策略。Hill 估计在原论文中确认与旧条目组件同族，未计新增；Appraisal 与 Rogers–Satchell 的旧库关系尚有疑问，同样未计入本批。暂缓和拒绝的候选没有混入本索引。

[source-lock.json](source-lock.json)固定原件版本、取得时间、许可角色和摘要；[reviews.json](reviews.json)保存逐条判定、精确行段证据及旧库比较。字段状态分别说明源码审核与文档审核；没有执行、回测或收益验证，商业权利仍独立待核。原件与详细本机报告不在公开 Git 中。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261004-harvest2000-v2
# 本机另有保存的原件时：
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261004-harvest2000-v2 --verify-snapshots
```

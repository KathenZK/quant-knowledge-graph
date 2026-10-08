# 第四批来源采集

本批新增 **11 个策略、9 个因子**。前四批累计 60 个策略、78 个因子；目标仍在进行中，见[采集总览](../README.md)。

策略核对信号、入场、退出、仓位和时序，并逐字段比较基线与新增近邻。有一项布林带衍生策略因旧来源不可得、无法充分排除同核而暂缓，没有计数。

因子包括 6 个技术指标和 3 个统计特征：同窗方差加权回归、衰减极值通道、路径效率剖面、跨资产扫荡广度、Haar 软阈值滤波、Modular 状态滤波，以及 Theil–Sen、Chatterjee xi 和 Jarque–Bera。每个构造的参数、方向、输出分量或附属 p 值均不拆条。

对容易混淆的旧条目，进一步沿原始页面、导入库和函数调用核查。Modular 仅收明确的 Pine v6 零初始化实现；原作者旧版保留为归属与版本差异依据，不混入核心公式。Theil–Sen 与旧 ICU 均线实际调用的重复中位数估计分开；后者未重复新增。

[source-lock.json](source-lock.json)固定原件和版本，[reviews.json](reviews.json)保存逐条审核、字段行段及比较对象摘要。同批候选比较也绑定最终公开文件。原文、源码和详细本机报告不进入 Git；没有执行源码、计算行情、回测或验证盈利，商业权利单独为 `REVIEW_REQUIRED`。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261004-harvest2000-v4
# 本机保存了原件时：
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261004-harvest2000-v4 --verify-snapshots
```

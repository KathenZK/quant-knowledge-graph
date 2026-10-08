# 第五批来源采集

本批新增 **6 个策略、11 个因子**。前五批累计 66 个策略、89 个因子；目标仍在进行中，见[采集总览](../README.md)。

策略核对完整信号、入场、退出、仓位和时序，并回到旧记录的原始源码比较。ATR-RSI 的一项移植因沿用已有主流程而排除。TDI 指标已有的记录不再新增；本批策略保留其交叉事件与旧正号状态条件的具体区别和比较证据。

11 个因子均归为统计特征，包括频谱形状、最低合格谱峰、倒谱、R/S 标度、多尺度样本熵、三种不同的模式复杂度和 0–1 诊断。每个构造的参数、分量、归一结果或附属统计量均不拆条。HCTSA 两个算法仅冻结明确的数值延迟路径，未审的自动延迟选择分支不声称已覆盖。

定义保留源码实际边界：例如多尺度熵删除无效尺度后压缩积分间距，0–1 诊断默认截取最早样本，倒谱中零频谱和奇异自相关的退化。这些边界没有被悄悄改写成更理想的算法。实现文件与框架许可分别登记，不用代码许可代替论文或数据授权。

[source-lock.json](source-lock.json)固定原件和版本，[reviews.json](reviews.json)保存逐条审核、字段行段及比较对象摘要。同批候选比较绑定最终公开文件。原文、源码和详细本机报告不进入 Git；没有执行源码、计算行情、回测或验证盈利，商业权利单独为 `REVIEW_REQUIRED`。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261004-harvest2000-v5
# 本机保存了原件时：
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261004-harvest2000-v5 --verify-snapshots
```

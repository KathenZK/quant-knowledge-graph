# 第九批来源采集

本批新增 **2 个策略、5 个因子**。前九批累计 84 个策略、118 个因子，目标仍在进行中，见[采集总览](../README.md)。

两条策略均来自作者发布的 TradingView 脚本。一条以历史收益路径最近邻及匹配路径后续收益作方向确认；它使用已发生的历史，标签区间可能和查询窗口重叠，尚不能认定为独立样本。另一条以六个特征预测二元涨跌概率，固定了主脚本及实际导入的 XGBoostMini/1 库。库内仍有未固定种子的随机排序；重复入场条件也会刷新退出参考，不能将变量名、绘图或标准 XGBoost 行为替代真实源码。

五个因子分别为指数矩优化的尾风险、幂锥熵约束的尾风险、尾概率网格加权的 Tail Gini、顺序统计量线性组合的 L 矩族，以及超过波动阈值后的 Gerber 同向变化矩阵。阶数、网格、阈值、求解形式和输出坐标均不拆计。求解器回退、非有限值、输入约束与原作者实现边界已保留；没有运行优化器或计算行情。

[source-lock.json](source-lock.json)固定来源版本与字节摘要，[reviews.json](reviews.json)保留字段行段、旧规则比较和补证。Gerber 原作者固定仓库未见许可证或授权，不能套用后来移植库的许可。当前 Polars、CVXPY 与 Pine 官方文档或代码仅支持相关定义说明，不代表已经固定旧来源的历史运行环境。两个同批疑似同族策略仍未计入新增。

公开内容为自撰定义、事实摘要和来源定位；原文、源码及本机验收日志不进入 Git。全部仍为计算 `NOT_EXECUTED`、经济有效性 `NOT_TESTED`、商业使用 `REVIEW_REQUIRED`。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261004-harvest2000-v9
# 本机保存了原件时：
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261004-harvest2000-v9 --verify-snapshots
```

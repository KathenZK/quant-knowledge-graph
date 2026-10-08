# 第二十一批来源采集

本批包含 **2 个策略、3 个统计特征**。每个完整构造只计一族，参数、输出、语言和实现变体不拆数。定义审核、计算验证、经济有效性和商用许可分别记录。

| 原生 ID | 已审构造与边界 |
|---|---|
| `hedging_54.pdf` | Föllmer–Leukert 预算受限的到期看涨负债复制。限定原稿 `m≤σ²` 分支，以预算反求终值阈值，再组合两份看涨期权及数字期权；到期事件不是盘中触障碍，真实费用与执行缺失 |
| `1210.1625` | Cont–Kukanov 静态跨场所订单数量分配。给定买入数量和期限，用 FIFO 队列成交函数与联合出流分布选择市场单、限价单数量，截止不足补市价；超量仅受软惩罚，不默补卖回或提前撤单 |
| `SingularSpectrumAnalysis` | 单序列形成轨迹矩阵，经特征分解、选组和反对角平均重构成分；分组方式与分量不拆新条目，金融输入和样本可得时点另需定义 |
| `pmlr-v48-peyre16` | 两组内部距离在给定边缘概率下求 Gromov–Wasserstein 耦合差异。保留正文平方损失的二分之一系数与后文展开冲突，只审核原始精确目标，未验证数值求解 |
| `procrustes` | 一般预配对点云各自中心化和整体能量归一后，拟合共同正交旋转或反射及非负整体尺度，返回对齐坐标与残差。与子空间主夹角共享交叉奇异值的特例关系保留，不因换聚合方式另计家族 |

[source-lock.json](source-lock.json)固定 22 份原件，含 3 份 PDF；[reviews.json](reviews.json)保留 23 张论文页图摘要、229 个字段行段引用、281 个近邻比较引用（228 个不同文件）和 9 个草稿到正式条目的定义及来源核对映射。Procrustes 新补的三份派发函数源码、固定 Git tree 证据和 M3485 原站源码的派生链均保留。SSA 与 Procrustes 的 M3485 比较只说明本次取得版本，不冒充旧 CSV 当时的实现。

PMLR 原生身份为 `pmlr:pmlr-v48-peyre16`，固定会议卷、论文键与原站 PDF/页面的对应关系。论文、代码、第三方近邻源码及市场数据许可分别判断；原文、源码、页图和本机日志不入 Git。原件路径只用于本机验证，审核正文不暴露本机目录。

所有条目仍为计算 `NOT_EXECUTED`、经济有效性 `NOT_TESTED`、商业使用 `REVIEW_REQUIRED`。本批没有运行来源算法、求解器、行情计算或回测，也不提供交易执行接口。登记与发布验证结果见[主采集目录](../README.md)和审查 PR。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261005-harvest2000-v21
# 本机保留原件及锁定的 pdftotext 版本时：
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261005-harvest2000-v21 --verify-snapshots
```

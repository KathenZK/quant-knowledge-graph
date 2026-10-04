# 第十批来源采集

本批新增 **4 个策略、16 个量化特征**。前十批累计 88 个策略、134 个因子与特征，目标仍在进行中，见[采集总览](../README.md)。

四条策略来自原始方法文档：SPX 期权报价比驱动的方向切换、国家 PV01 约束下的国债套息与滚降组合，以及商品 Nelson–Siegel 曲线变化驱动的斜率价差、曲率蝶式。商品策略各保留一个明确版本，未把截面/时序权重变体再拆计。来源描述已核，但期权现金计息公式疑点、债券桶内分配、商品拟合器及同日结算价成交等缺项仍在各记录中，不能据此直接复现完整指数或回测。

| 特征类别 | 新增 | 内容 |
|---|---:|---|
| 非线性动力学 | 1 | 邻近轨迹发散的 Lyapunov 估计 |
| 样本关系与分布诊断 | 5 | 距离协方差、能量距离、Fligner、Mood、两样本 Cramér–von Mises |
| 信息传递 | 1 | 无背景条件的经验频数转移熵 |
| 图结构与节点权重 | 9 | 循环边、营养层级、Laplacian 能量、模块度、聚类、富节点连接、可通信性、PageRank、HITS |

图特征需要另行定义金融节点、关系与时点，来源函数本身不提供这些数据。重复值、零分母、迭代顺序、收敛条件与原实现选项分别保留；节点、矩阵坐标、归一化、窗口和多个输出均不拆计。Cramér–von Mises 本条只审核统计量，未把其 p 值底层算法纳入已审计算合同。

[source-lock.json](source-lock.json)固定原始版本与字节；PDF 原件和派生文本分开记录，派生文本由指定版本和固定参数的 `pdftotext` 重建。商品论文被文本提取遗漏的公式另按原 PDF 图页核对，在[reviews.json](reviews.json)保留页码、图页摘要和自撰公式转录。字段行段与旧记录比较均绑定具体字节，来源全文、图页和本机日志不进入 Git。

全部仍为计算 `NOT_EXECUTED`、经济有效性 `NOT_TESTED`、商业使用 `REVIEW_REQUIRED`。定义审核与完整计算、市场数据、可成交性及许可分别判断。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261005-harvest2000-v10
# 本机保存了原件及所记录的 pdftotext 版本时：
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261005-harvest2000-v10 --verify-snapshots
```

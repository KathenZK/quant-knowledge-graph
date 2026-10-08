# 第二十二批来源采集

本批包含 **3 个策略、2 个统计特征**。每个完整构造只计一族，参数、输出、不同语言和实现变体不拆数。定义审核、计算验证、经济有效性和商用许可分别记录。

| 原生 ID | 已审构造与边界 |
|---|---|
| `1880728` | Miller–Orr 固定调拨费用下的现金管理。给定零漂移经营现金流和每日方差，触上下界后将现金调回共同内点；不是比例费用下的触边反射。证券余额可能为负，原模型信用假设和长期成本近似保留 |
| `discrete.pdf` | Schweizer 有限非退化事件树上的固定初资均方负债对冲。后向计算条件期望系数，前向按已有财富调整风险证券份额；零目标只表示该期不持有风险证券，不表示安全资产也清空 |
| `NGStorage.pdf` | Lai–Margot–Secomandi 天然气储存 ADP。给定初始期货曲线与风险中性联合模型，在库存容量、月度吞吐和分方向收支约束下求月度注提策略；终值为零不强制清空，未把未来实现值当作条件期望输入 |
| `covariance_mest` | pyRiemann 固定 Tyler 分支的多变量散布形状估计。先用算术均值中心化，迭代按当前逆散布的径向距离加权，末次才归一到 trace=p；50 轮耗尽可警告并返回末值，不等于已经收敛。仅 p≥2 的选定输入域，原始逐观测缩放不变性不成立 |
| `2008-02-PersistentHomology.pdf` | 有限面相容单复形过滤上的普通 F2 持久同调。按列约化边界矩阵形成生灭配对与无穷区间；全部维数、条形码和秩摘要共一族。金融图到复形的映射未定义，不能直接当市场预测 |

[source-lock.json](source-lock.json)固定 17 份正式来源原件，含 4 份 PDF。[reviews.json](reviews.json)保留 45 张主论文页图摘要、204 个字段行段引用、150 个近邻比较引用（135 个不同文件）和 3 个草稿到正式条目的完整定义及来源映射。PH 另保留 2004 原稿的 3 张比较页图、2004/2008 版本差异，以及 M0866 原 API 字符串解码和 M3924 原网页派生链。未使用的 Ripser 导入不等于已定义或运行了持久同调；未冻结依赖的内部行为仍未知。

三条策略的 30 个字段为 27 个 `SOURCE_DESCRIPTION_REVIEWED` 和 3 个 `MISSING`（实际执行时序）。W61 的退出措辞修订链保留。W63 的 Eq47 折现缺项与 RI Eq36 记号疑点单列，不用于修补所选 ADP；W62 存储筛查仍为 HOLD，只保留比较证据，不映射成正式条目或计数。Tyler 与单变量 Huber、逐列 biweight 等旧定义的关系明确记录，代码 BSD 许可不延伸至被引论文或市场数据。

PH 原生身份来自作者出版目录及精确 PDF 文件名，不编造 DOI。2008 综述版权占位文字不是开放许可，2004 个人和课堂使用许可也不授予商业或服务器再分发权。Miller–Orr 的大学托管扫描与 Crossref 书目分别标注，不冒称作者直接托管。原文、源码、页图和本机日志不入 Git。

所有条目仍为计算 `NOT_EXECUTED`、经济有效性 `NOT_TESTED`、商业使用 `REVIEW_REQUIRED`。本批没有运行来源算法、求解器、行情计算或回测，也不提供交易执行接口。登记与发布验证结果见[主采集目录](../README.md)和审查 PR。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261005-harvest2000-v22
# 本机保留原件及锁定的 pdftotext 版本时：
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261005-harvest2000-v22 --verify-snapshots
```

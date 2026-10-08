# 第二十三批来源采集

本批包含 **3 个策略、4 个统计特征**。每个完整构造只计一族，参数、输出坐标、求解器和实现版本不拆数。定义审核、计算验证、经济有效性和商用许可分别记录。

| 原生来源 | 已审构造与边界 |
|---|---|
| `jofi.12032` | 同日期、同到期的 TIPS、通胀互换与 STRIPS 本息复制。实际 TIPS 通缩本金保护形成额外非负残余，未把简化表格当成全状态精确套利；参考指数、日期、融资及成本限制保留 |
| `mktscore.pdf` | 固定流动性参数的 LMSR 运营者构造：以对数成本函数之差收付、更新净事件份额并按最终事件兑付。初始成本函数值不是已收到的现金，最大终值损失界不替代中途资金或信用合同 |
| `271` | 给定风险中性转移模型、有限生产模式和剩余切换次数的 tolling 调度。只采用选定离散递推，终值、截止时点、热耗率/容量单位及源公式疑点保留；未实现回归模拟或实际设备延迟 |
| `shapiro` | 固定 SciPy 路径的 Shapiro–Wilk W 统计量。显式保留 `axis=None`、`nan_policy=propagate`、`keepdims=False`；只审有限一维样本与 W，未把伴随 p 值或参数变体另计 |
| `0912.3599v1` | PCP 完整核范数与逐元素 L1 联合分解，输出满足 L+S=M 的最优解集合。不是唯一数值解；原 Alg1 阈值、符号与目标的冲突明确隔离，没有批准或执行求解器 |
| `1997_KoshevoyM97.pdf` | 给定多维经验样本和查询点的 Zonoid 深度。保留它与全部方向投影 CVaR 支持函数的精确关系，不声称数学独立；完整联合几何查询计一族 |
| `10.1145/335191.335388` | LOF 同样本局部可达密度比。保留第 k 距离并列邻居、以邻居半径定义可达距离、先求距离平均再取倒数及所选欧氏范围。Crossref 只支持来源身份，不能作为公式证据 |

[source-lock.json](source-lock.json)固定 27 份正式来源原件，含 7 份 PDF。[reviews.json](reviews.json)保留 65 张主论文页图摘要、409 个字段行段引用、318 个近邻比较引用（275 个不同文件），以及 8 个草稿到正式条目的完整定义与来源映射。原 PDF、网页、源码、页图和本机日志不入 Git。

三条策略的 30 个字段为 25 个 `SOURCE_DESCRIPTION_REVIEWED` 和 5 个 `MISSING`。W66 的修订只补明定价测度，旧版对照链保留。Shapiro 的四个核心字段为 `SOURCE_CODE_REVIEWED`；三条论文特征的核心字段为 `SOURCE_DESCRIPTION_REVIEWED`，用途说明仍为 `RESEARCH_ASSUMPTION`。

Zonoid 的来源身份取原机构 URL 与原生文件名，不能由本机缓存文件名改写。LOF 按既有约定以 `doi.org/10.1145` 命名空间加 `335191.335388` 安全 ID 编码，完整 DOI 作为别名与来源引用保留；公开 review 保存初始审核建议和 ROOT 的无损编码裁定，这不是另一个来源或新增条目。PCP 的旧许可页面成功快照与本轮 HTTP 406 失败分开记录；arXiv 分发许可不等于读者商业授权。其他论文、源码和市场数据权利分别保留，未从开放代码许可推导论文或数据授权。

所有条目仍为计算 `NOT_EXECUTED`、经济有效性 `NOT_TESTED`、商业使用 `REVIEW_REQUIRED`。没有运行来源算法、优化器、行情计算或回测，也不提供交易执行接口。集合登记与最终发布验证由独立适配审核后另行完成。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261005-harvest2000-v23
# 本机保留原件及锁定的 pdftotext 版本时：
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261005-harvest2000-v23 --verify-snapshots
```

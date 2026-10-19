# v35 来源定义批次

本批新增 4 条策略、7 个投资因子（`investment_factor`）。均来自论文或研究机构公开的 PDF，已完成来源、定义和去重复核；未运行任何算法、未回测、未验证收益，商用状态仍为 `REVIEW_REQUIRED`。用户于 2026-10-08 要求恢复采集，本批即恢复后的第一批，方向为股票横截面因子与论文/机构策略。

| 原生 ID | 类型 | 完整构造 | 来源 |
| --- | --- | --- | --- |
| bmw17b:TK | 因子 | 把过去 60 个月相对市场的月超额收益看作等概率分布，按 Tversky–Kahneman 参数算累积前景理论价值 TK；月度十分位，高 TK 预期低收益。 | Barberis、Mukherjee、Wang，作者主页手稿（2016） |
| w25201:CS_RET | 因子 | 以共同覆盖的分析师人数加权关联股的上月收益；月末五分位，做多高、做空低。 | Ali、Hirshleifer，NBER w25201（2018，2019 修订） |
| CosemansFrehen-2017:ST | 因子 | 用 BGS 显著性函数给当月日收益排名并加权，ST 为权重与日收益的协方差；做多低 ST、做空高 ST。 | Cosemans、Frehen，工作论文（2017-02） |
| 2021w-3:option-momentum | 因子 | 零 Delta 平值跨式的月收益，取滞后 2–12 月的算术平均做五分位排序，持有一个月。 | Heston 等，《Option Momentum》（2021-09） |
| HKS-2010:daily-periodicity | 因子 | 按前 1–5 个交易日同一半小时区间的收益做十分位，只在当前半小时持有赢家减输家组合。 | Heston、Korajczyk、Sadka（2010-05-26） |
| w13249:normalized-inventory | 因子 | 商品实际库存除以 HP 趋势得到“正常库存”比值，月末对半分组，做多低库存、做空高库存。 | Gorton、Hayashi、Rouwenhorst，NBER w13249（2007-07） |
| technological-links:TECHRET | 因子 | 以专利技术类别分布的 Jaffe 非中心化相关为权重，算技术关联公司的上月收益；十分位多空。 | Lee、Sun、Wang、Zhang（2017-10-23） |
| 2304.07619v6:gpt4-headline-ls | 策略 | 用固定提示词让 GPT-4 给新闻标题打分（1/0/−1），隔夜新闻次一开盘等权多空，当日收盘平仓。 | Lopez-Lira、Tang，arXiv v6（2025-10-28） |
| P158:DYN | 策略 | 由 12 月与 1 月收益符号划出四种市场状态；回调态、反弹态的快慢动量混合速度按历史矩的闭式解估计，截断在 [0,1]，月度调仓。 | Goulding、Harvey、Mazzoleni，JFE 149（2023） |
| Shocks-2013:2y-auction-cycle | 策略 | 2 年期国债拍卖前 t 日做空 2 年期、做多久期匹配的 6 月期加 10 年期，拍卖日反手，持有至拍卖后 t 日。 | Lou、Yan、Zhang，作者稿（2013-05） |
| sr917:BtD | 策略 | 前一交易日美东 15:15–16:15 ES 相对签名成交量为负时，01:30 做多 ES、03:30 平仓。 | Boyarchenko、Larsen、Whelan，纽约联储 SR917（2020，2022 修订） |

## 去重

每条都检索了 `coverage-map.csv`，范围包括 6,971 条 M 记录、1,570 个因子变体、v1–v34 的 371 项和 11 条已审记录。最近的旧记录钉在 `reviews.json` 的 `compared_rule_pins` 中，同时锁定文件摘要和行摘要。

本批按“市场相同、核心信号相同即为一条”的规则去重，改窗口、改分组、改样本过滤都不计新。以下候选因此没有收入，原因见 `rejected.csv`：

- 短期动量 STMOM：与 M3915 的动量×换手构造只差窗口参数。
- A 股 PMO（异常换手）：与东吴 PctTurn20（M1756）同属换手相对基准的变化率。
- A 股 VMG（剔壳 EP 价值）：已有 A 股 EP 排序，如 M2757。
- 商品偏度：已有 M0341、M3545。
- Bai–Bali–Wen 债券下行风险因子：原文已撤稿。

## 来源与边界

- 每个来源都锁定了原 PDF 的摘要，以及 `pdftotext -layout -enc UTF-8 - -` 派生文本的摘要。生成器版本为 `pdftotext version 25.03.0`，前几批用的是 24.04.0；用 `--verify-snapshots` 本机复核时须使用同一版本。
- 字段行号指向派生文本，按 Python `splitlines` 计行，换页符也算换行。页码是原 PDF 的物理页。
- 工作论文或作者稿与期刊终版未逐字比对的，都已写在 `missing_information` 里。期刊卷期如来自外部书目，会注明“据外部书目”。
- 已知局限：
  - TK：市场基准指数未写明。
  - 期权动量：组内权重未写明。
  - 库存因子：HP 双边滤波有前视风险。
  - GPT 策略：同日多条标题如何合并未写明，模型版本已停用。
  - 拍卖策略：下单时点未写明。
  - BtD：夏令时不同步时窗口是否平移未定义。
- 公开目录只保存自撰的中文定义和来源证据；论文 PDF 和派生文本留在被忽略的 `datasets/raw/sources/harvest2000-v35/`。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v35
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v35 --verify-snapshots
```

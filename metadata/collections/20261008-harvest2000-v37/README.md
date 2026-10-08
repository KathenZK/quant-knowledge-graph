# v37 来源定义批次

本批新增 4 条策略、7 个投资因子（`investment_factor`）。来源均为 NBER 工作论文、FDIC 金融研究中心工作论文、大学开放仓储（City、Warwick、Wharton Rodney White 中心）、AEA 年会托管稿、Carlo Alberto 学院托管稿或作者主页的论文 PDF，已完成来源、定义和去重复核。本批未运行任何算法，未回测，也未验证收益；商用状态仍为 `REVIEW_REQUIRED`。

本批承接 PR #36 分支并叠加 v36。方向是外汇宏观截面因子、公司债截面、商品期货持仓、事件驱动外汇和另类数据股票组合。本批只收入 11 条，没有凑数：目录在相关方向已高度饱和，多数候选为已有规则或来源无法取得，见下文与 `rejected-v37.csv`。

| 原生 ID | 类型 | 完整构造 | 来源 |
| --- | --- | --- | --- |
| w26299:GAPCS | 因子 | 每月末用实时工业生产（OECD 月度 vintage）按 Hamilton 线性投影求产出缺口，减去美国缺口后分 5 组；等权做多相对缺口最高组、做空最低组。 | Colacito、Riddiough、Sarno，NBER w26299（2019-09） |
| 14851:FX-value-residual | 因子 | 每季度把 5 年对数实际汇率变化对人均实际 GDP、出口质量、净外国资产、产出缺口做横截面回归，取残差 εq；按去均值线性权重（绝对权重和为 1）配置，季末再平衡。 | Menkhoff、Sarno、Schmeling、Schrimpf，City 接受稿（RFS） |
| TaleTwoPremiums-2017:hedger-Q | 因子 | 每周二按 COT 报告计算套保者净多头周变化除以周初持仓量 Q，对 26 种商品升序分 5 组等权；Q 最大组（套保者买入最多）随后跑赢 Q 最小组。 | Kang、Rouwenhorst、Tang，工作论文（2017-01） |
| T265B62E:trade-centrality | 因子 | 每年用双边贸易强度构造邻接矩阵并算 Katz 中心性；每月按上一年中心性把货币分 4 组等权，做多外围、做空中心国家货币。 | Richmond，AEA 2018 托管稿（2017-06） |
| w18057:GDP-share-currency | 因子 | 每季初按发行国占 OECD 总产出的份额把货币分 5 组；以 3 个月远期做多最小国家组、做空最大国家组。 | Hassan，NBER w18057（2012-05） |
| APf13-Verdelhan:dollar-beta-conditional | 因子 | 每月用截至 t−1 的 60 个月滚动回归估计各货币对美元因子的暴露，分 6 组；各组在发达国平均远期贴水为正时做多、为负时做空。 | Verdelhan，NBER 会议稿（2013-10） |
| LTR-2019:LTRBond | 因子 | LTR 为 t−48 至 t−13 的 36 个月累计收益；每月按评级三分、期限三分、LTR 三分（3×3×3 条件排序），市值加权做多低 LTR、做空高 LTR。 | Bali、Subrahmanyam、Wen，作者主页工作论文（2019-03） |
| WRAP94006:FOMC-S2 | 策略 | 预定 FOMC 公告前一日 16:00 ET 做空美元、做多对美利差为正的 G10 货币，持有至公告日 16:00；公告若为紧缩，立即反手做多美元。 | Mueller、Tahbaz-Salehi、Vedolin，Warwick 同行评审稿（JF） |
| 16863:CDS-RX | 策略 | 每月末按 5 年期美元主权 CDS 利差水平做秩权重（美元中性，1 美元多、1 美元空），远期买入高 CDS 货币、卖出低 CDS 货币，持有 1 个月。 | Della Corte、Sarno、Schmeling、Wagner，City 工作论文（日期未知） |
| CFR-WP2010-04:bond-momentum-6-1-6 | 策略 | 每月按 t−6 至 t−1 累计收益把公司债分 10 组，跳过第 t 月；等权做多赢家、做空输家，持有 6 个月，月收益取 6 个重叠组合的均值。 | Jostova、Nikolova、Philipov、Stahel，FDIC CFR WP 2010-04（2010-05） |
| RW0716:best-companies-portfolio-I | 策略 | 每年 2 月 1 日等权买入当年《财富》“100 Best Companies to Work For”中的上市公司，持有到次年 1 月末再按新榜重组。 | Edmans，Rodney White 中心工作论文（2007-05） |

## 去重

每条都检索了 `coverage-map-v37.csv`，同时使用英文和中文关键词，并逐一对照了 v35、v36 集合记录的 ID 清单。检索范围如下：

- 6,971 条 M 记录
- 1,570 个因子变体
- v1–v36 的 396 项
- 11 条已审记录
- v35 的 56 条拒收记录
- v36 的 34 条拒收记录

最近的旧 M 记录钉在 `reviews.json` 的 `compared_rule_pins` 中，同时锁定文件摘要和行摘要。与集合记录的比较只写在去重理由文字中，因为集合记录没有行摘要，例如 v36 的 13287:IMB、Chen_Predict_FX-2013:delta-short-rate 和 13156:FX-VRP。

本批的判重规则是：市场相同且核心信号相同，即视为同一条。以下候选没有收入，原因与匹配 ID 见 `rejected-v37.csv`：

- **已有同规则：**
  - 外汇波动风险溢价：与 v36 的 13156:FX-VRP 同一规则。
  - 期限利差排序：作者自述与套息高度相关。
  - 商品贸易货币：与 M4515 同一规则。
  - 财报前跨式：与 M2729 同一规则。
  - 国债期货协整套利：属于协整配对的资产变体。
- **规则不完整或不可交易：**
  - FOMC 窗口国债：来源没有给出交易规则。
  - IPO 解禁做空：来源报告不盈利，没有完整的盈利规则。
  - 标普纳入：来源只描述效应已消失。
  - CRV：比值方向在派生文本中不可辨认，且依赖估计系数。
- **已撤稿：** Bai–Bali–Wen 的公司债 DRF。
- **来源无法取得：** Houweling–van Zundert、Haesen 等、Gebhardt 等的公司债因子论文，原因是 SSRN 被屏蔽、EFMA 证书错误，或第三方副本返回 405。
- **目录已有：** 并购套利、分拆、波动管理、动量崩溃、隔夜动量、LTG、基差动量、商品偏度、组织资本、协偏度、行业领先滞后、评级下调、借券费等。

## 来源与边界

- **快照锁定：** 每个来源都锁定了原 PDF 的摘要，以及 `pdftotext -layout -enc UTF-8 - -` 派生文本的摘要，生成器版本为 `pdftotext version 25.03.0`。用 `--verify-snapshots` 复核时须使用同一版本。
- **行号与页码：** 字段行号指向派生文本，按 Python `splitlines` 计行；页码是原 PDF 的物理页。
- **版本：** 工作论文、会议稿或接受稿都没有与期刊终版逐字比对，均已写在 `missing_information` 里。Della Corte 等主权 CDS 论文的版本日期标为“未知”：仓储标注为 2013 年，正文却提及 2016 年会议。
- **执行时点：** 四条策略的 `execution_time` 是研究假设，不是来源原文；引用段未写明的成交价格时点均已注明。
- **已知局限：**
  - Hassan 规模因子：“经样本波动调整”的方法正文未给出；高减低 Sharpe 只有约 0.22。
  - 套保者 Q：原文报告了多个持有窗口，没有单列正式持有期。
  - FOMC-S2：紧缩判断依赖公告后约 20–30 分钟的期货数据，实时反手存在时滞。
  - 公司债动量：1973–1990 年不显著（作者自述）；做空公司债的可行性未处理。
  - LTRBond：派生文本中收益公式排版不完整，只转写了文字说明。
  - 最佳雇主组合：工作论文样本只有 1998–2005 年。
  - 交易成本：多数条目的引用段未给出；只有 GAPCS 和 GDP 份额两条含买卖价差。
- **存储位置：** 公开目录只保存自撰的中文定义和来源证据；论文 PDF 和派生文本留在被忽略的 `datasets/raw/sources/harvest2000-v37/`。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v37
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v37 --verify-snapshots
```

# v39 来源定义批次

本批新增 5 条策略、2 个投资因子（`investment_factor`）。来源为纽约联储 Staff Report、NBER 工作论文、加拿大央行网站托管稿、大学开放仓储（宾夕法尼亚大学、LSE、Warwick）和欧洲央行会议托管稿的论文 PDF，已完成来源、定义和去重复核。本批未运行任何算法，未回测，也未验证收益；商用状态仍为 `REVIEW_REQUIRED`。

本批承接 PR #36 分支 c616887（含 v36），并叠加 v37、v38。按要求只检索产出较高的小众来源池，方向是美债曲线内动量与方差风险溢价、外汇套息的增强与期权保护、期权隐含与 CDS 隐含的股票预期收益。本批只收入 7 条，没有凑数：评估的 31 个候选里，24 条因重复、变体、规则不完整、不可交易、前视、证据弱或来源受阻未收，见下文与 `rejected-v39.csv`。

| 原生 ID | 类型 | 完整构造 | 来源 |
| --- | --- | --- | --- |
| 118957:SVIX-expected-stock-return | 因子 | (E R_i − R_f)/R_f = SVIX²_m + ½(SVIX²_i − 市值加权平均 SVIX²_i)，SVIX² 由虚值认沽/认购按行权价等权积分得到，无需估参；作者按预期收益秩^2 加权标普 500 成分股（只做多），每月调仓。 | Martin、Wagner，LSE FMG DP760（2016-11） |
| FWZ2011:CDS-term-structure-credit-risk-premium | 因子 | 逐公司用 1 年 CDS 利差与 1×1/3×1/5×1/7×1 远期利差回归 1/3/5/7 年 CDS 平均超额收益，RP̂ = −γ′F；每月末按 RP̂ 把股票分 5 组，做多最高组、做空最低组。 | Friewald、Wagner、Zechner，ECB 会议托管稿（2011-11-18） |
| SR657:duration-neutral-curve-momentum | 策略 | 美债 6 个期限桶 t−2 至 t−n 月平均收益为信号；线性规划在权重 0–1、组合久期等于指数久期的约束下最大化过去收益，持有 1 个月。 | Durham，纽约联储 SR 657（2013-12） |
| w25420:enhanced-carry-sharpe-exclusion | 策略 | G10 标准套息（多 5 空 5 等权）上，每月用 1984-12 起的扩展窗口逐步剔除能抬高历史夏普的货币，最多剔除 7 种，用剩余货币做等权套息。 | Bekaert、Panayotov，NBER w25420（2019-01） |
| e139a418:crash-neutral-G10-carry | 策略 | 价差加权 G10 套息，按层级配对用交叉汇率一月期 10δ 认沽对冲每个多 J/空 I 敞口，认沽数量按式 (3)，并对冲期权 Delta；月度。 | Jurek，UPenn 托管作者稿（2013-08） |
| returns_currency_speculation:BGT-recursive | 策略 | 递推估计 Backus–Gregory–Telmer 远期贴水回归（首估计用 30 个观测），预测收益 ≥1 则卖出英镑远期，否则买入；含买卖价门槛版；9 种货币等权。 | Burnside、Eichenbaum、Kleshchelski、Rebelo，加拿大央行托管稿（2006-10） |
| 94008:short-generalized-Treasury-variance-swap | 策略 | 每月用 CME 5/10/30 年国债期货期权按式 (6) 计算公允方差执行价，做空一月期广义 Treasury 方差互换，按式 (5)(7) 结算。 | Choi、Mueller、Vedolin，Warwick 作者稿（RoF 2017） |

## 去重

每条都检索了 `coverage-map-v39.csv`，同时使用英文和中文关键词，并逐一对照了 v35、v36、v37、v38 集合记录的 ID 清单。检索范围如下：

- 6,971 条 M 记录
- 1,570 个因子变体
- v1–v38 的 420 项
- 11 条已审记录
- v35 的 56 条、v36 的 34 条、v37 的 41 条、v38 的 37 条拒收记录

最近的旧 M 记录钉在 `reviews.json` 的 `compared_rule_pins` 中，同时锁定文件摘要和行摘要。与集合记录的比较只写在去重理由文字中，例如 v38 的 duarte4:cap-volatility-arbitrage（利率上限波动率，不是国债期货期权方差互换）和 Lee–Naranjo–Sirmans CDS 动量（利差变化动量，不是期限结构隐含风险溢价）。

判重规则：市场相同且核心信号相同，即视为同一条。本批 7 条来源各不相同。以下候选没有收入，原因与匹配 ID 见 `rejected-v39.csv`：

- **已有同规则或变体（8 条）：** Daniel–Hodrick–Lu 美元中性/优化/风险再平衡套息、Hassan–Mano 静态与美元交易、Durham SR708 美债 BAB、Lettau–Maggiori–Weber 货币下行 β、MPRA 商品风格贝叶斯整合（加权叠加）、Fleckenstein–Longstaff–Lustig TIPS 复制、主权 CDS 信用货币理论（与 v37 16863:CDS-RX 同族，未下载）、总统周期汇率（已有 M3790）。
- **规则不完整（1 条）：** 加拿大央行 SAN 2024-16 国债期现基差交易（描述性，无入场阈值）。
- **前视（1 条）：** Jordà–Taylor 基本面增强套息（均衡实际汇率用全样本均值）。
- **证据弱或已撤稿（4 条）：** KNS 偏度互换（以方差互换对冲后利润不显著）、Fernholz–Koch 商品秩效应（可交易样本仅 2010–2015）、Cieslak–Povala 周期因子（复现经济价值很小）、Bai–Bali–Wen 债券因子（2023 年撤稿）。
- **不可交易（4 条）：** 期权非流动性溢价（作者称付价差后无 α）、Driessen–Maenhout–Vilkov 相关性风险（作者称现实摩擦下无法利用）、Cenedese–Della Corte–Wang 货币错价（监管交易库数据，无交易规则）、Constantinides–Jackwerth–Savov 指数期权收益（纯定价检验）。
- **来源受阻（6 条，均未绕过）：** Bali–Murray（UNL 403、SSRN）、Vasquez（EFMA 证书失败、SSRN）、Boyer–Vorkink（仅 SSRN）、Dahlquist–Hasseltoft 经济动量（仅 Quantpedia 转述、SSRN）、Barroso–Santa-Clara 货币组合（Cambridge Core 返回 500）、Coval–Shumway 零 β 跨式（Deep Blue 只返回 HTML、BYU 403、SSRN）。

## 来源池与饱和度

| 来源池 | 结果 |
| --- | --- |
| 纽约联储 SR、达拉斯联储 WP、美联储 FEDS/IFDP | 收 1 条（SR 657）；SR 708 为重复，达拉斯 WP 1607 证据弱。 |
| NBER 工作论文 | 收 1 条（w25420）；Jordà–Taylor 前视，Hassan–Mano 为变体。 |
| 加拿大央行 | 收 1 条（BEKR 托管稿）；SAN 2024-16 为描述性短文。 |
| 大学开放仓储（UPenn、LSE、Warwick、City、Imperial Spiral） | 收 3 条（Jurek、Martin–Wagner、CMV）；City 与 Imperial 的候选为证据弱或不可交易。 |
| 欧洲央行会议托管稿 | 收 1 条（FWZ）。 |
| 作者主页（kentdaniel.net、Goyenko、Savov 等） | 0 收入；均为变体、不可交易或定价检验。 |
| RePEc MPRA | 0 收入；本轮命中多为已有信号的组合或加权叠加。 |
| 挪威央行、瑞典央行、澳洲央行 | 0 收入；未找到含完整交易规则的论文，NBIM 套息短文为已有规则。 |

## 来源与边界

- **快照锁定：** 每个来源都锁定了原 PDF 的摘要，以及 `pdftotext -layout -enc UTF-8 - -` 派生文本的摘要，生成器版本为 `pdftotext version 25.03.0`。用 `--verify-snapshots` 复核时须使用同一版本。
- **行号与页码：** 字段行号指向派生文本，按 Python `splitlines` 计行；页码是原 PDF 的物理页。
- **版本：** 工作论文、会议稿或作者稿都没有与期刊终版逐字比对，均已写在 `missing_information` 里。CMV 作者稿的版本日期标为“未知”。Jurek 稿件 URL 为 UPenn 仓储的 bitstream 内容地址。
- **执行时点：** 各策略的 `execution_time` 中，Bekaert–Panayotov 与 Jurek 依据来源写明的月末报价/采样，其余为研究假设。
- **已知局限：**
  - FWZ：原文主结果用全样本 γ（前视）；本记录按样本外口径（只用 t 时信息的滚动或扩展窗口）描述，但窗口长度与明细在网络附录中，本 PDF 不含。
  - Martin–Wagner：依赖付费 OptionMetrics 数据；作者报告等权组合夏普略高于模型组合。
  - Durham：权重和为 1 未在正文明写；巴克莱期限子指数为商业数据；原文换手单位前后不一致。
  - Bekaert–Panayotov：按样本内夏普选币有选择偏差，作者在附录中做了随机化检验，未转写。
  - Jurek：FX 期权数据来自 J.P. Morgan DataQuery（专有）。
  - BGT：以英镑为基准货币，样本止于 2005 年；推断：b̂ 为正时预测符号多与远期贴水符号一致，交易方向常与普通单币种套息相同。
  - CMV：方差互换需用期权组合加期货动态对冲复制；做空方差有尾部风险。
- **存储位置：** 公开目录只保存自撰的中文定义和来源证据；论文 PDF 和派生文本留在被忽略的 `datasets/raw/sources/harvest2000-v39/`。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v39
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v39 --verify-snapshots
```

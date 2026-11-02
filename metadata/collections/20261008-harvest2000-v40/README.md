# v40 来源定义批次

本批新增 4 条策略、3 个投资因子（`investment_factor`）。来源是 SSRN 候选清单（`ssrn-shortlist.csv`，18 篇）中能在 SSRN 之外找到开放全文的论文，已完成来源、定义和去重复核。本批未运行任何算法，未回测，也未验证收益；商用状态仍为 `REVIEW_REQUIRED`。

本批承接 7702af2，并叠加 v39。只收作者本人的论文本身（工作稿、接收稿或期刊版），不收摘要页、幻灯片、讨论稿或二手转述；所有受阻来源均未绕过。18 篇中有 8 篇找到了开放全文，另 10 篇仍无开放副本，见 `ssrn-still-missing.csv`。评估的 26 个候选中收入 7 条，19 条未收，见下文与 `rejected-v40.csv`。

| 原生 ID | 类型 | 完整构造 | 来源 |
| --- | --- | --- | --- |
| JOIM2018:corporate-bond-value-spread-residual | 因子 | log(OAS) 对 log(久期)、评级与 12 个月超额收益波动的横截面回归残差（经验法），加上 log(OAS) 对 log(违约概率) 的残差（结构法），两项按等风险合成；在 DTS 五分位内去均值后分五组，市值加权做多 Q5、做空 Q1，月度调仓。 | Israel、Palhares、Richardson，JOIM 16(2) 2018，AQR 托管 |
| JOIM2018:corporate-bond-defensive-lev-gp-duration | 因子 | 低市场杠杆、高毛利/总资产与低有效久期三项按等风险合成；分五组，市值加权做多 Q5、做空 Q1，月度调仓。控制价值与动量后不显著。 | 同上 |
| BVV2012:vol-of-vol-implied-volatility | 因子 | 近 20 个交易日 ATM 认购与认沽隐含波动率均值序列的标准差除以其均值；月末（取倒数第二个交易日的期权数据）分五组，市值加权，做多低组、做空高组。 | Baltussen、van Bekkum、van der Grient，2012-07-30 工作稿，Quantpedia 转载 |
| MS2019:equity-pairs-RetDiff | 策略 | 用过去 5 年月收益为每只股票找相关性最高的 50 只股票组成配对组合；RetDiff = β_C·(Cret−Rf) − (Lret−Rf)；按上月 RetDiff 分十组，做多 D10、做空 D1，持有 1 个月。 | Chen、Chen、Chen、Li，MS 65(1) 2019，清华五道口托管 |
| AEA2020:geographic-lead-lag-quintile | 策略 | 按总部所在 BEA 经济区内、不属本公司 FF12 行业的其他公司上月等权收益排序，分五组，市值加权，做多 Q5、做空 Q1，月度调仓。 | Parsons、Sabbatucci、Titman，AEA 2020 工作稿（2019-12-18） |
| SdRNG:basis-sorted-commodity-term-premium-excess-holding | 策略 | 双月按近月对数基差把 21 种商品分四组；超额持有 = 买入 n 期合约持有到交割 − 连续滚动近月合约；做多高基差组、做空低基差组（n=2–4）。 | Szymanowska、de Roon、Nijman、van den Goorbergh，接收稿，第三方内容平台托管 |
| DH2015:economic-momentum-currency-trend-combo | 策略 | 20 种货币，8 项宏观变量在 1–60 个月回看期的变动与时间趋势 t 值，按秩加权构造 799 个美元中性子策略，按过去 3 年波动倒数合成，缩放至 5% 目标波动，月度调仓。 | Dahlquist、Hasseltoft，2015-03-27 工作稿，Quantpedia 转载 |

## 去重

每条都检索了 `coverage-map-v40.csv`，同时使用英文和中文关键词，并逐一对照了 v35–v39 集合记录的 ID 清单。检索范围如下：

- 6,971 条 M 记录
- 1,570 个因子变体
- v1–v39 的 427 项
- 11 条已审记录
- v35 的 56 条、v36 的 34 条、v37 的 41 条、v38 的 37 条、v39 的 24 条拒收记录

最近的旧 M 记录钉在 `reviews.json` 的 `compared_rule_pins` 中，同时锁定文件摘要和行摘要。与集合记录的比较只写在去重理由文字中。

判重规则：市场相同且核心信号相同，即视为同一条。本批两条公司债因子同出 IPR，但核心信号不同（利差残差与杠杆/毛利/久期），不是参数变体。

**公司债风格因子的判断：**

- **IPR 与 Houweling–van Zundert（FAJ 2017）：** HvZ 仍无开放全文。IPR 正文没有描述 HvZ 的因子定义，只在参考文献中列出 HvZ（2014）；IPR 的代表性债券筛选沿用同一 Robeco 团队的 Haesen 等（2013）。因此无法逐条比对 HvZ 的规模、低风险、价值和动量定义，本批只按 IPR 原文收入价值与防御两条，HvZ 未收。
- **IPR 动量与 v37 的重叠：** IPR 动量是两条腿的等风险合成：一条是债券过去 6 个月超额收益，不跳月，持有 1 个月，五分位；另一条是发行人股票过去 6 个月收益。债券腿只在形成期、跳月、持有期和分位上与 v37 的 CFR-WP2010-04:bond-momentum-6-1-6 不同，属参数变体。股票腿属于“股票到债券的动量溢出”族，该族的原始论文（Haesen 等 2017、Gebhardt 等 2005）仍无开放副本，IPR 也没有报告这条腿的单独结果。因此动量未收。
- **IPR 其余部分：** 套息（OAS）的 Fama–MacBeth t=1.0，证据弱，且已有指数级信用套息 M4165、M4191，未收。合成组合与长多优化组合是成分信号的叠加，未收。

**以下候选没有收入**，原因与匹配 ID 见 `rejected-v40.csv`：

- **不可交易（2 条）：** Robinhood 羊群事件（Robintrack 数据 2020-08-13 已停更，原文为事件研究）；Melvin–Prins 伦敦 4 点定盘（只有面板预测回归，没有交易规则）。
- **证据弱（1 条）：** Finta–Ornelas 商品隐含偏度（8 种商品，t 值 1.66 和 1.88，控制展期收益后 α 不显著）。
- **重复、变体或叠加（6 条）：** IPR 套息、IPR 动量、IPR 合成与优化组合、Szymanowska 其他排序的现货溢价、Chen 等的配对动量分解、Dahlquist–Hasseltoft 单变量子策略。
- **来源受阻（10 条，均未绕过）：** 见 `ssrn-still-missing.csv`。

## 版本与转载口径

- **口径变化：** 用户本轮要求以内容为准，只要是作者本人的论文本身即可，因此本批接受了此前未收的两类副本：Quantpedia 转载的作者工作稿（Baltussen 等、Dahlquist–Hasseltoft；v39 曾以“仅 Quantpedia 转载”拒收 R39-015），以及第三方内容平台上的 Szymanowska 等接收稿（v37 曾以“来历不明的第三方副本”拒收 R37-013）。来源锁定的 `revision` 里写明了托管方类型，记录的 `missing_information` 里写明了“未与期刊终版比对”。
- **期刊版：** Chen 等是清华五道口网站托管的 MS 出版社排版版，IPR 是 AQR 网站托管的 JOIM 重印本。
- **工作稿：** Parsons 等是 AEA 2020 年会论文页提供的 2019-12-18 工作稿，未与 RFS 终版比对。

## 来源与边界

- **快照锁定：** 每个来源都锁定了原 PDF 的摘要，以及 `pdftotext -layout -enc UTF-8 - -` 派生文本的摘要，生成器版本为 `pdftotext version 25.03.0`。用 `--verify-snapshots` 复核时须使用同一版本。
- **行号与页码：** 字段行号指向派生文本，按 Python `splitlines` 计行；页码是原 PDF 的物理页。Baltussen 等的派生文本中，“fi”连字处被拆成两行，因此 Python 行号大于文本编辑器显示的行号。
- **执行时点：** 只有 Dahlquist–Hasseltoft 的 `execution_time` 依据原文写明的月末，其余都是研究假设。
- **已知局限：**
  - IPR：结构法违约概率的引用，正文写 Bharath–Shumway (2008)，附表 A.1 写 Shumway (2001)，两处不一致。防御合成中久期分项在 DTS 去均值时如何处理，原文未细写。
  - Szymanowska 等：组合收益是对数收益的平均，不等于可实现的组合收益；n>1 时各批持仓重叠，原文未说明如何合并。
  - Baltussen 等：需要付费的 OptionMetrics 数据，工作稿样本止于 2009 年。
  - Chen 等：全市场两两相关的计算量很大；网络附录未取得。
  - Parsons 等：COMPUSTAT 只有当前总部邮编，迁址公司会被误分。
- **存储位置：** 公开目录只保存自撰的中文定义和来源证据；论文 PDF 和派生文本留在被忽略的 `datasets/raw/sources/harvest2000-v40/`。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v40
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v40 --verify-snapshots
```

# v41 来源定义批次

本批新增 4 条策略、2 个投资因子（`investment_factor`），已完成来源、定义和去重复核。本批未运行任何算法，未回测，也未验证收益；商用状态仍为 `REVIEW_REQUIRED`。

本批承接 cd2f284（v39），并叠加 v40 bundle。来源只取 NBER 官网工作稿、作者个人或教师主页托管的论文，以及出版社开放获取的期刊版；不收摘要页、幻灯片或二手转述，本批没有使用 Quantpedia 或第三方内容平台的转载副本。所有受阻来源都没有绕过。评估的 31 个候选中收入 6 条，25 条未收，见下文与 `rejected-v41.csv`。

| 原生 ID | 类型 | 完整构造 | 来源 |
| --- | --- | --- | --- |
| w27655:corporate-bond-book-to-market-BBM | 因子 | 账面价值取 FISD 发行价按直线法摊销到月末的值，除以月末前至少 8 个日历日的最近一笔 TRACE 成交净价；月末分五组，做多 Q5（BBM 最高）、做空 Q1，持有 1 个月。等权与市值加权都报告。 | Bartram、Grinblatt、Nozawa，NBER WP 27655（2020-08，2023-03 修订），NBER 托管 |
| GHWZ2019:employer-rating-change-quarterly | 因子 | Glassdoor 员工总体星级的季度均值变化（当季减上季，每季至少 15 条评价）；季末按最低五分位、中间三个五分位、最高五分位分三组，做多最高组、做空最低组，持有 3 个月。 | Green、Huang、Wen、Zhou，2018-07 接收稿（JFE 2019），作者 Georgetown 主页托管 |
| ACP2021:best-ideas-active-fund-max-IR-holding | 策略 | 每只主动股票基金的持仓超配（基金权重减市值权重）乘以预测的 CAPM 特质波动率，取最大者为该基金的“最佳想法”；只用最大值处于前 25% 的基金，把最佳想法等权合成多头组合（多只基金同选则按次数加重），每季度第一天重组，持有到季末，股价不低于 5 美元。 | Antón、Cohen、Polk，2021-04 工作稿，作者 LSE 主页托管 |
| w24676:mood-beta-mood-month-decile-flip | 策略 | 情绪月（1、3、9、10 月及每年等权市场收益最高与最低的各两个月）中个股超额收益对等权市场超额收益的 10 年滚动回归斜率，取 t−2 至 t−5 年平均；1 月和 3 月做多最高十分位、做空最低十分位，9 月和 10 月反向，十分位等权，其余月份空仓。 | Hirshleifer、Jiang、Meng，NBER WP 24676（2018-06，2019-02 修订；JFE 2020），NBER 托管 |
| JS2018:earnings-calendar-revision-weekly-long-short | 策略 | REV = Wall Street Horizon 的未确认预期财报日减去公司首次公布的预约财报日（交易日）；在预约财报日所在的周做多 REV>3、做空 REV<−3，周度调仓；多空两侧持仓数达不到最低要求的周不交易。 | Johnson、So，作者接收稿（未印日期，PDF 元数据 2017-06-22；JFQA 2018），作者 MIT 站点托管 |
| KPPZ2025:satellite-parking-fill-rate-earnings-window | 策略 | 卫星图像测得的零售商同店停车场占用率（车辆数/车位数）同比增长；用过去 3 个月内结束财季的零售商滚动计算四分位界限，在财报日前后 3 个交易日（−1 至 +1）做多最高四分位、做空最低四分位。 | Katona、Painter、Patatoukas、Zeng，JFQA 60(2) 2025，Cambridge 开放获取版（CC BY 4.0） |

## 去重

每条都检索了 `coverage-map-v41.csv`，同时使用英文和中文关键词，并逐一对照了 v35–v40 集合记录的 ID 清单。检索范围如下：

- 6,971 条 M 记录
- 1,570 个因子变体
- v1–v40 的 434 项
- 11 条已审记录
- v35 的 56 条、v36 的 34 条、v37 的 41 条、v38 的 37 条、v39 的 24 条、v40 的 19 条拒收记录

最近的旧 M 记录钉在 `reviews.json` 的 `compared_rule_pins` 中，同时锁定文件摘要和行摘要。与集合记录的比较只写在去重理由文字中。

判重规则：市场相同且核心信号相同，即视为同一条。

**需要复核的三条：**

- **公司债 BBM 与 v40 公司债价值：** 两者同属公司债价值族。v40 的 JOIM2018:corporate-bond-value-spread-residual 用 log(OAS) 对久期、评级、波动或违约概率回归取残差；本条只用摊销发行价与成交净价之比，不用利差、评级或违约模型，核心信号不同，因此收入。同文的 BG 债券误定价信号是 v36 已收的“不可知基本面误定价”（同一作者）在公司债上的映射，未收。
- **情绪β与日历季节性：** 已有的 MomSeason（M0429/M0430）、MomOffSeason（M0424）与一年前同月收益（M0874）都按历史同月收益排序，方向不翻转。本条估计个股对情绪月市场收益的敏感度，并在低情绪月反向；作者显示情绪β吸收了同月收益的大部分预测力。同文直接按历史情绪月收益排序的四个策略属于已有季节性族，未收。
- **卫星停车场：** 样本只有 44 家零售商、650 个公司季度（2011Q1–2017Q4），数据来自付费供应商 RS Metrics，组内权重原文未写明。

**以下候选没有收入**，原因与匹配 ID 见 `rejected-v41.csv`：

- **规则不完整或没有交易规则（2 条）：** Bolton–Kacperczyk 碳风险（只有面板回归）；Lee–Ma–Wang 搜索同伴（只有收益联动检验，v41 未取全文快照）。
- **证据弱（1 条）：** Bennett–Cucuringu–Reinert 领先滞后聚类（统计学预印本 v1，毛收益约 2.4bp/日，未扣成本，2012 年后衰减）。
- **重复、变体或子策略（11 条）：** van Binsbergen 等的分析师条件偏差（PredictedFE 的机器学习估计）、BG 债券误定价、BBM 年度调仓版本、深度动量网络（TSMOM 的 LSTM 映射）、学习排序截面动量、Hartley–Schwarz 国债月末效应，以及已收各条的子策略：最佳想法的“最佳减其余”、前 3/前 5 与组合α口径；情绪月历史收益排序；周内与复合情绪β；Glassdoor 子评分、文字评分、业务前景与样本拆分；Johnson–So 的 REV 三分位版本。
- **来源受阻（1 条，未绕过）：** In–Park–Monk 碳排放强度 EMI，sustainablefinance.ch 上的 SSRN 副本两次 TLS 连接错误。
- **仍无开放全文（10 条）：** `ssrn-still-missing.csv` 中的 10 篇本批重新检查（OpenAlex 再查，eScholarship 上的 Unusual News Flow 副本仍为 HTTP 403），没有新的开放副本。原文件未改，更新后的检查记录写在 `ssrn-still-missing-v41.csv`。

## 版本口径

- **NBER 工作稿：** w24676、w27655 为 NBER 官网托管的修订稿，均未与期刊终版比对。w24676 页脚另印 SSRN 电子副本说明，文件本身取自 NBER。
- **作者托管的接收稿或工作稿：** Green 等（Georgetown 教师主页）、Johnson–So（MIT 个人站点）、Antón 等（LSE 个人主页），均未与期刊终版比对，写入了各记录的 `missing_information`。
- **期刊开放获取版：** Katona 等为 Cambridge 出版社托管的 JFQA 开放获取版，页首声明 CC BY 4.0，记录 `sources[].license` 单独标注（只指论文文本，卫星数据仍是商业数据）。其余来源未见明确的再使用许可，沿用 `UNKNOWN_NO_EXPLICIT_REUSE_LICENSE`。

## 来源与边界

- **快照锁定：** 每个来源都锁定了原 PDF 的摘要，以及 `pdftotext -layout -enc UTF-8 - -` 派生文本的摘要，生成器版本为 `pdftotext version 25.03.0`。用 `--verify-snapshots` 复核时须使用同一版本。
- **行号与页码：** 字段行号指向派生文本，按 Python `splitlines` 计行；页码是原 PDF 的物理页。
- **执行时点：** Antón 等的 `execution_time` 依据原文脚注（按公开披露日建仓仍有显著收益，见原文图 4）；其余各条的执行时点都是研究假设。
- **已知局限：**
  - Antón 等：主结果按基金的真实持有日识别最佳想法，相对 13F/N-PORT 公开日有前视；按公开日建仓的结果只有图示与脚注，没有表格。特质波动率预测回归的系数在附录表 A.V，未取得。
  - Hirshleifer 等：所有收益未扣成本；十分位等权含大量小盘股。
  - Green 等：样本偏大盘股，Glassdoor 数据的当前可得性和历史回填方式需另行确认。
  - Johnson–So：周度策略的组内权重未写明；Table 9 的 REV>3/REV<−3 与 R-Score 第二档从 ±3 起算的边界不同。
  - Bartram 等：月度调仓扣除全部客户交易成本后净 α 不显著，只有年度调仓版本在机构交易规模下净 α 显著。
  - Katona 等：样本小，数据贵（作者估计每年数十万美元），收益可能随数据普及而衰减。
- **存储位置：** 公开目录只保存自撰的中文定义和来源证据；论文 PDF 和派生文本留在被忽略的 `datasets/raw/sources/harvest2000-v41/`。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v41
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v41 --verify-snapshots
```

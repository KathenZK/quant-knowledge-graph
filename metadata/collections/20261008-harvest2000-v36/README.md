# v36 来源定义批次

本批新增 6 条策略、8 个投资因子（`investment_factor`）。均来自 NBER 工作论文、央行/监管机构工作论文、大学开放仓储或作者页托管的论文 PDF，已完成来源、定义和去重复核；未运行任何算法、未回测、未验证收益，商用状态仍为 `REVIEW_REQUIRED`。本批承接 v35（PR #36 分支），方向为 2015 年后未被 OSAP/JKP 覆盖的股票横截面构造，以及外汇、商品、利率、期权的完整规则策略。

| 原生 ID | 类型 | 完整构造 | 来源 |
| --- | --- | --- | --- |
| BEf14-CHSS:EarnRank | 因子 | 用前 20 个季度的拆股调整 EPS 排名，取往年同财季平均排名；在“12 个月前有公告”的股票中月度五分位，多高空低。 | Chang、Hartzmark、Solomon、Soltes，NBER 会议稿（2014-10） |
| 13287:IMB | 因子 | 先按净外国资产/GDP 分两篮，再按外债本币计价占比重排为 5 组；IMB=P5−P1，等权。 | Della Corte、Riddiough、Sarno，接受稿（RFS 2016） |
| 86183:agnostic-mispricing-M | 因子 | 每月市值对 28 个 Compustat 时点科目做横截面回归，M=(拟合值−市值)/市值；五分位多低估空高估。 | Bartram、Grinblatt，Warwick 接受稿（JFE） |
| NAT-RFS2019:NAT | 因子 | 对冲基金持股与空头比例各减过去四季均值，NAT=AHF−ASI；季末五分位，剔除 NYSE 20% 分位以下，等权持有下一季。 | Chen、Da、Huang，RFS 在线版（2018） |
| ConnectedStocks-JF2014:connected-reversal | 因子 | 以共同主动基金持股（正交化秩权）构造关联组合收益；大盘股按自身与关联组合 3 个月收益 5×5 独立分组，多双低空双高。 | Antón、Polk，JF 69(3)（2014） |
| 13156:FX-VRP | 因子 | 货币过去一年已实现波动减一年期无模型波动率互换利率；月末五分位，多 VRP 最高空最低。 | Della Corte、Ramadorai、Sarno，接受稿（JFE 2016） |
| w23432:InnOrig | 因子 | 专利原创性=所引专利的唯一技术类别数，公司取过去 5 年均值；6 月末 30/70 三分组，市值加权持有 12 个月，多高空低。 | Hirshleifer、Hsu、Li，NBER w23432（2017-05） |
| Chen_Predict_FX-2013:delta-short-rate | 因子 | 一个月同业利率的月度一阶差分排序，等权多最高三分之一、空最低三分之一货币，月度再平衡。 | Ang、Chen，工作论文（2013-05-20） |
| swp2021-48:fix-reversal | 策略 | 美东 17:00–20:55 多美元、20:55–02:00 空美元（东京定盘）；02:00–08:15 多美元、11:00–17:00 空美元（欧洲定盘）。 | Krohn、Mueller、Whelan，加拿大央行 SWP 2021-48 |
| w30688:dividend-payment-timing | 策略 | 当日或前一日全市场股息支付额高于过去 252 日中位数时持有市值加权大盘，否则空仓。 | Hartzmark、Solomon，NBER w30688（2022-11） |
| plstudy_33:goldman-roll-frontrun-S1 | 策略 | 对当月 S&P-GSCI 将展期的商品，首个展期日前第 10–6 个营业日每日建 20% 空近月/多远月价差，展期期内每日平 20%。 | Mou，CFTC 托管工作论文（2011-07-15） |
| JFE66-2002:bond-oldbond-convergence | 策略 | 30 年美债拍卖日卖空新券、买入老券（回购融资），久期中性且 y·DP 恒定，持有至下次拍卖。 | Krishnamurthy，JFE 66（2002） |
| JFE108-2013:ivol-delta-hedged-call-ls | 策略 | 月末按上月 FF3 残差特异波动五分位，买最低组、卖最高组的 Delta 对冲平值认购，每日调对冲，持有至下月末。 | Cao、Han，JFE 108（2013） |
| goyal_041808:HV-IV-straddle-ls | 策略 | 到期后首个交易日按 log(12 月历史波动/平值隐含波动) 十分位，次日等权买 D10、卖 D1 的近月平值跨式，持有至到期。 | Goyal、Saretto，工作论文（2008-03） |

## 去重

每条都检索了 `coverage-map-v36.csv`，范围包括 6,971 条 M 记录、1,570 个因子变体、v1–v35 的 382 项、11 条已审记录和 v35 的 56 条拒收记录，并同时用英文与中文关键词检索。最近的旧 M 记录钉在 `reviews.json` 的 `compared_rule_pins` 中，同时锁定文件摘要和行摘要；与 v35 集合记录的比较（如 CS_RET、TECHRET、2 年期拍卖周期）因集合记录无行摘要，只写在去重理由文字中。

本批按“市场相同、核心信号相同即为一条”的规则去重。以下候选没有收入，原因与匹配 ID 见 `rejected-v36.csv`：

- 美元套息（Lustig–Roussanov–Verdelhan 2014）：与 M0348“美元套息”同一规则。
- 股债再平衡抢跑（Harvey 等 2025）：与 M3755 同一来源规则。
- 预期增长、保守公式、残差动量、空头回补天数、派息月溢价、FOMC 周期、创新效率、PEAD、中介β、下行β、货币动量/价值等：目录已有。
- 电话会议“casting”：正文与表注多空方向冲突，规则不确定。
- 若干来源因 SSRN 屏蔽、TLS 证书错误或 403 无法取得原文。

## 来源与边界

- 每个来源都锁定了原 PDF 的摘要，以及 `pdftotext -layout -enc UTF-8 - -` 派生文本的摘要，生成器版本 `pdftotext version 25.03.0`；用 `--verify-snapshots` 复核时须使用同一版本。
- 字段行号指向派生文本，按 Python `splitlines` 计行；页码是原 PDF 的物理页。双栏期刊 PDF（Cao–Han）在派生文本中左右栏同行混排，行段仍覆盖所引原文。
- 工作论文或接受稿与期刊终版未逐字比对的，都已写在 `missing_information` 里；Krishnamurthy 期刊 PDF 的托管方未核实是否为作者主页。
- 已知局限：
  - 定盘反转：按全额报价价差计成本时多数时窗净收益为负；夏令时窗口调整需自定。
  - 新老券收敛：原文结论为扣除回购成本后平均利润接近零。
  - NAT：图注“百分比变化”与正文“差值”定义冲突，采用正文；13F 披露滞后未处理。
  - 关联股反转：原文为事件时买入持有，实施持有期未固定。
  - IMB：表注“月度再平衡”与脚注“实务年末再平衡”并存。
  - Cao–Han：五分位内期权加权未写明。
  - 股息支付择时、商品展期抢跑：引用段未给交易成本。
- 公开目录只保存自撰的中文定义和来源证据；论文 PDF 和派生文本留在被忽略的 `datasets/raw/sources/harvest2000-v36/`。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v36
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v36 --verify-snapshots
```

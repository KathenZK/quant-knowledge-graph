# v38 来源定义批次

本批新增 7 条策略、6 个投资因子（`investment_factor`）。来源为纽约联储 Staff Report、美联储 IFDP、加拿大央行网站托管稿与 Staff Working Paper、大学开放仓储（City、Warwick）、RePEc MPRA、AEA 年会托管稿和奥克兰理工大学（AUT）托管稿的论文 PDF，已完成来源、定义和去重复核。本批未运行任何算法，未回测，也未验证收益；商用状态仍为 `REVIEW_REQUIRED`。

本批承接 PR #36 分支 c616887（含 v36）并叠加 v37。方向是固定收益与信用相对价值、外汇期权与风险因子、商品期货另类数据与持仓、美股收益分解反转。本批只收入 13 条，没有凑数：评估的 50 个候选里，37 条因重复、规则不完整、不可交易、前视或来源受阻未收，见下文与 `rejected-v38.csv`。

| 原生 ID | 类型 | 完整构造 | 来源 |
| --- | --- | --- | --- |
| SR513:DR-reversal | 因子 | 上月收益分解为 FF3 预期收益、分析师三阶段增长模型现金流冲击和残差折现率冲击 DR；每月在 I/B/E/S 11 个行业内按 DR 分 10 组，做多 DR 最负组、做空最正组。 | Da、Liu、Schaumburg，纽约联储 SR 513（2011-09） |
| IFDP1253:US-tail-beta-FX | 因子 | Tail = PPUT 对数收益 − 标普 500 对数收益；60 个月滚动回归估计各货币的 Tail β，分 5 组等权；低 β 组收益高于高 β 组。 | Fan、Londono、Xiao，美联储 IFDP 1253（2019-07） |
| 6418:commodity-IVol-GSCI | 因子 | 过去 R 个月日收益对 S&P-GSCI 回归的残差标准差；做多 IVol 最低五分位、做空最高五分位，等权，持有 1 个月。 | Fuertes、Miffre、Fernandez-Perez，City 接受稿（JFM 2015） |
| 94014:FX-correlation-risk-beta | 因子 | G10 货币对 3 个月已实现相关性的顶/底十分位差为 FXC；36 个月滚动 ΔFXC β 把 9 种货币分 3 组，做多低 β、做空高 β。 | Mueller、Stathopoulos、Vedolin，Warwick 作者稿（JFE 2017） |
| 100528:CFEAR | 因子 | 149 个危害关键词 Google 搜索周对数变化标准化后，对各商品周收益逐词回归，斜率之和为 CFEAR；做空最高五分位、做多最低五分位，持有 1 周。 | Fernandez-Perez 等，MPRA 100528（2019-09） |
| AUT-HP-2017:hedging-pressure-4-classes | 因子 | 12 个月平均商业交易者 (空−多)/(空+多)；在商品、外汇、股指、利率期货各类内做多最高三分位、做空最低三分位，等权，持有 1 个月。 | Fan、Fernandez-Perez、Fuertes、Miffre，AUT 托管初步稿（2017-06） |
| 6418:triple-screen-Mom-TS-IVol | 策略 | 动量、平均展期收益、低 IVol 三项各赋 1..N 分求和；做多总分最高五分位、做空最低五分位，等权，持有 1 个月。 | 同上 JFM 2015 接受稿 |
| 24178:FX-vol-carry-VCA | 策略 | 按 (24 月 − 3 月隐含波动率)/3 月隐含波动率的斜率把远期波动率协议分 5 组；买入斜率最低组、卖出最高组，等权，月度再平衡。 | Della Corte、Kozhan、Neuberger，City 接受稿（JFE 2021） |
| duarte4:swap-spread-arbitrage | 策略 | 互换利差减 Libor−GC 回购利差 >10bp 时收固定互换、做空同期国债（<−10bp 反向），持有至收敛或到期；资本按 10% 年化波动缩放。 | Duarte、Longstaff、Yu，加拿大央行托管稿（2006-03） |
| duarte4:cap-volatility-arbitrage | 策略 | 每月卖出平值美元利率上限并以欧洲美元期货 Delta 对冲（等价 1 个月 caplet 波动率互换），卖出价按中间价减 1 个波动率点计成本。 | 同上 |
| duarte4:capital-structure-arbitrage | 策略 | CreditGrades 模型由股价与负债算理论 CDS 利差；市场利差 >(1+α)× 模型利差时卖出 CDS 保护并做空股票对冲，收敛或满 180 天平仓。 | 同上 |
| AEA2015-957:CDS-momentum-3-1 | 策略 | 按过去 3 个月单名 CDS 盯市收益分 5 组；卖出赢家保护、买入输家保护，等权，持有 1 个月，不跳月，每月 19 日进出。 | Lee、Naranjo、Sirmans，AEA 2015 托管稿（2014-12） |
| SWP2017-44:butterfly-relative-value | 策略 | 同发行人 3 只相邻债券匹配久期、凸性与面值构造复制组合；可交易收益率差超过 ±5bp 做蝶式，收敛到 0 或满一年平仓。 | Fontaine、Nolin，加拿大央行 SWP 2017-44 |

## 去重

每条都检索了 `coverage-map-v38.csv`，同时使用英文和中文关键词，并逐一对照了 v35、v36、v37 集合记录的 ID 清单。检索范围如下：

- 6,971 条 M 记录
- 1,570 个因子变体
- v1–v37 的 407 项
- 11 条已审记录
- v35 的 56 条、v36 的 34 条、v37 的 41 条拒收记录

最近的旧 M 记录钉在 `reviews.json` 的 `compared_rule_pins` 中，同时锁定文件摘要和行摘要。与集合记录的比较只写在去重理由文字中，例如 v36 的 13156:FX-VRP、v37 的 TaleTwoPremiums-2017:hedger-Q、16863:CDS-RX 和 CFR-WP2010-04:bond-momentum-6-1-6。

判重规则：市场相同且核心信号相同，即视为同一条。同源多条（JFM 2015 两条、Duarte 等三条）彼此资产或核心交易规则不同，不是参数变体。以下候选没有收入，原因与匹配 ID 见 `rejected-v38.csv`：

- **已有同规则、变体或通用规则（12 条）：** 主权 CDS 动量（本批单名 CDS 动量的资产变体）、投机压力（套保压力的输入变体，来源稿报告与套保压力相关 0.84）、商品偏度、IRFA 商品 IVol、货币政策条件套息、Filippou–Taylor 宏观因子、行业趋势、五十日（Gotobi）外汇效应（近 v36 定盘反转）、商品多空加权方案、现金对冲因子组合、噪声测度债券交易（同源蝶式的变体）、St. Louis Fed 通用技术交易规则。
- **规则不完整或含义不明（3 条）：** CDS→股票联合动量（股票动量窗口与持有期未写明）、商品流动性变化因子、CDS-债券基差残差模型。
- **前视（2 条）：** 两因子 Vasicek 收益率曲线套利（全样本校准参数）、GNMA 美元滚动套利（全样本对冲比率、提前使用提前还款数据）。
- **证据弱、来源弱或过于通用（6 条）：** 国别股市期限利差排序（后段 Sharpe 约为 0，股息率与动量版本已有国别股指 carry/动量记录）、公司债短期反转、欧洲高收益债隔夜反转学生报告、现金生产率、印度物理动量、15 分钟加密反转。
- **不可交易（11 条）：** 监管或私有数据（BoE SWP 964、871、客户订单流、交易商库存、ICRG 政治风险 β）、纯定价检验（ECB WP 2452、Mayordomo 等 CDS–债券基差、Dallas Fed IPCA 期权）、杠杆 ETF 再平衡、刻钟级加密可预测性、网络风险文本指标。
- **来源受阻（3 条）：** 货币偏度（仅 SSRN）、商品期权隐含偏度（SMU InK 屏蔽）、Basu–Miffre 套保压力（仅 SSRN，已改用 AUT 公开稿收入套保压力信号）。

## 来源池与饱和度

| 来源池 | 结果 |
| --- | --- |
| arXiv q-fin.TR/PM 2023–2026 | 按列表标题与摘要筛选并细看可疑候选，0 收入；以机器学习、微观结构、加密和学生论文为主，判定为饱和。 |
| 美联储 FEDS/IFDP、纽约联储 SR、地区联储 | 收 2 条（SR 513、IFDP 1253）；其余多为定价检验或已有规则。 |
| ECB 工作论文 | 0 收入；以定价检验为主，产出低。 |
| BoE Staff Working Paper | 0 收入（SWP 537 因证据弱拒收，其余为监管数据）。 |
| 加拿大央行（新池） | 收 4 条（Duarte 等三条、SWP 2017-44）；固定收益相对价值是本批主要新增方向。 |
| 大学开放仓储（City、Warwick） | 收 4 条；外汇与商品学术因子仍有零星增量，White Rose、Lancaster 几乎无产出，SMU InK 被屏蔽。 |
| RePEc MPRA 与作者或学院托管稿（含 AEA 年会） | 收 3 条（CFEAR、套保压力、CDS 动量）。 |
| A 股公开 PDF | 目录已有 800 余条 A 股 M 记录，CNKI 不开放，判定为饱和或不可达。 |
| 加密学术 arXiv | 目录已有一千余条加密相关 M 记录，判定为饱和。 |

## 来源与边界

- **快照锁定：** 每个来源都锁定了原 PDF 的摘要，以及 `pdftotext -layout -enc UTF-8 - -` 派生文本的摘要，生成器版本为 `pdftotext version 25.03.0`。用 `--verify-snapshots` 复核时须使用同一版本。
- **行号与页码：** 字段行号指向派生文本，按 Python `splitlines` 计行；页码是原 PDF 的物理页。
- **版本：** 工作论文、会议稿或接受稿都没有与期刊终版逐字比对，均已写在 `missing_information` 里。MSV 作者稿的版本日期标为“未知”。套保压力来源是 2017-06-08 的初步稿，封面注明“not for quotation”：本记录只自撰转述规则，不引原文，结论可能与正式版不同。
- **执行时点：** 除 CDS 动量（来源写明每月 19 日进出）外，各策略的 `execution_time` 都是研究假设。
- **已知局限：**
  - DR 反转：因子风险溢价取全样本均值，有前视，实盘应改为递推均值；十分位组内的加权方式未写明。
  - 商品 IVol 与三重筛选：S&P-GSCI 基准是作者在 8 个候选中按样本内表现事后选定的；R 有 1/3/6/12 月四种。
  - CFEAR：Google Trends 是抽样数据，复现结果会有偏差。
  - 互换利差套利与利率上限波动率套利：依赖 Libor 和欧洲美元期货，两者已停用，实盘需改用 SOFR 体系。
  - 资本结构套利：CreditGrades 定价公式未印在本文中；Markit CDS 是商业数据。
  - 蝶式交易：回购特殊利率未计，融资成本用政策利率近似。
- **存储位置：** 公开目录只保存自撰的中文定义和来源证据；论文 PDF 和派生文本留在被忽略的 `datasets/raw/sources/harvest2000-v38/`。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v38
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v38 --verify-snapshots
```

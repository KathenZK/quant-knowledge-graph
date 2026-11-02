# v45 来源定义批次

本批新增 4 条策略，0 个因子，已完成来源、定义和去重复核。本批未运行任何算法，未回测，也未验证收益；商用状态仍为 `REVIEW_REQUIRED`。

本批承接 cd2f284（v39），叠加 v40–v44 bundle，`prior_checkpoint` 指向 v44 批次（manifest sha256 `db71fcef…087e6d`，与 v44 bundle 内 manifest 一致）。本批只看用户指定的三类来源：

- **池 B 五条线索：** README-v44 列为“未取全文”的 KIT、Aston、KCL、City、兰卡斯特五篇。
- **池 B 余量：** 尚未访问的大学机构仓储，重点是美国（Harvard DASH、MIT DSpace、Columbia Academic Commons、Duke、NYU、UChicago Knowledge、Stanford）和亚洲（HKUST、NUS ScholarBank、SMU InK（仍受阻则跳过）、PolyU）。
- **NBER：** 2024–2026 年尚未入目录、带完整交易规则的资产定价工作论文。

评估的 21 个候选中收入 4 条（池 B 五线索 1 条、NBER 3 条、池 B 余量 0 条）；17 条未收，见下文与 `rejected-v45.csv`。所有受阻来源都没有绕过。

前视规则沿用 v42 起的严格口径：论文主结果若依赖当时无法获得的信息（如真实持仓日期、事后确定的样本、回溯或修订数据、同一时点既算信号又按该价成交），且表格中没有按可交易日期给出的结果，即以“前视”拒收。本批 1 条因此拒收（Aston OST），另 1 条因前视无法核实拒收（NBER w35513）。

| 原生 ID | 类型 | 完整构造 | 来源 |
| --- | --- | --- | --- |
| VX2024:default-risk-delta-hedged-equity-option-returns | 策略 | 美国非金融个股期权，每月末取最接近平值、到期超过一个月的最短期期权，算 Delta 对冲看涨收益（按 \|Δ·S−O\| 缩放）。按标普信用评级数值（1=AAA 至 22=D；替代口径为 Bharath–Shumway 违约概率）分五组，做多违约风险最低组、做空最高组（等权/持仓量加权/市值加权），月末建仓、下月末平仓。 | Vasquez、Xiao，Management Science 2024 作者接受稿，City St George's Research Online 机构仓储托管 |
| BGX2025:central-bank-restrictiveness-currency-forwards | 策略 | 每月末用前 60 个月面板，以当时公开的实时 GDP、出口、进口（OECD 实时库当期版本，换成美元）解释最新公开 M1（经济体与月份固定效应，斜率用季度一阶差分估计）；信号=−第 T 月残差/M1。16 个 OECD 经济体货币按信号分五组，月末等权做多最紧缩组、做空最宽松组的一个月远期，持有一个月。 | Bartram、Grinblatt、Xu，NBER WP 33423（2025-01），NBER 官网原发 |
| GWW2024:procyclical-stocks-Livingston-expected-GDP-beta | 策略 | 用 Livingston 调查名义 GDP 与 CPI 中位预测构造两期前视的半年预期实际 GDP 增长，取二阶滞后 LEGDP。每年 6 月与 12 月对每只美股用过去 20 个半年超额收益回归市场与 LEGDP，按 LEGDP 系数分十组，市值加权多最高组（顺周期）、空最低组（逆周期），持有六个月。 | Goetzmann、Watanabe、Watanabe，NBER WP 32509（2024-05），NBER 官网原发 |
| BKM2026:volatility-disagreement-VDIS-delta-hedged-straddles | 策略 | 模拟 100 名“投资者”，各随机取一半公开股票特征与期权隐含特征、随机取随机森林超参数，5 年滚动面板（每 12 个月重估）预测下一持有期实现方差；VDIS=100 个预测的横截面标准差。每月第三个周五后的周一按 VDIS 把平值跨式分十组等权，做多最低组、做空最高组，日度 Delta 对冲，持有至下月到期。 | Bali、Kelly、Mörke，NBER WP 35500（2026-07，含网络附录），NBER 官网原发 |

## 去重

每条都检索了 `coverage-map-v45.csv`，同时使用英文和中文关键词，并逐一对照了 v35–v44 集合记录的 ID 清单。检索范围如下：

- 6,971 条 M 记录
- 1,570 个因子变体
- v1–v44 的 451 项
- 11 条已审记录
- v35 的 56 条、v36 的 34 条、v37 的 41 条、v38 的 37 条、v39 的 24 条、v40 的 19 条、v41 的 25 条、v42 的 15 条、v43 的 17 条、v44 的 29 条拒收记录

最近的旧 M 记录钉在 `reviews.json` 的 `compared_rule_pins` 中，同时锁定文件摘要和行摘要。与集合记录的比较只写在去重理由文字中。

判重规则：市场相同且核心信号相同，即视为同一条。

**需要复核的四条：**

- **违约风险期权（VX2024）：**
  - 违约信号（默顿 DLI M4543、CHS 失败概率 M4225、O 分 M4436）目录里已有，但都交易股票本身；本条交易个股 Delta 对冲期权，按“市场不同即另起一行”收入。目录内已有的期权截面记录（v36 特质波动 Delta 对冲看涨、HV−IV 跨式，v35 期权动量）信号不同。
  - 主结果按买卖中间价、未扣成本。作者 4.8 节与表 10：有效价差设为报价价差的 25% 时三种加权仍显著为正，50% 时转负；2003 年起 OPRA 实际有效价差约为报价价差的 52%，计入后只有持仓量加权显著，再计保证金与融券费后不再盈利。这一点已写入记录。
  - 实证部分的对冲调整频率正文未明说；信用评级取自 Compustat，不来自期权价格，月末建仓不构成“同价既算信号又成交”。
- **央行紧缩度（BGX2025）：**
  - 信号全部用作者自建的实时数据（OECD ORDR 当期版本与 MEI 月度存档），作者另报告当月同期收益（不可交易）与下一月收益（可交易，0.42%/月，t=2.29），记录只按下一月口径写。
  - 正文写样本 2001-07 至 2020-04，表 1 标题写 2006-07 至 2020-05，原文未解释；货币只有 16 种，五分位每组约 3 种。原文未扣交易成本。
  - 与套息（M4161、M0345）、PPP 价值（M0346、M4146）、货币动量（M3573）不同；作者明确与套息赛马且本信号胜出。
- **顺周期股票（GWW2024）：**
  - β 回归窗口的最后一个半年收益以建仓日收盘计，原文没有跳过一期再建仓的结果；但表 10 持有 12–36 个月的重叠组合 10−1 仍显著（0.42%/0.36%/0.30%），说明价差不是建仓日价格造成的，故不按前视处理。
  - 四因子 α 只在 10% 水平显著（0.36%，t=1.86），多空组合动量 β 为 0.15。原文未扣交易成本。
  - 同作者 NBER w34402（2025-10）改用现金流 β 对特征组合排序，属同一核心信号，已拒收为变体。
- **波动率分歧（BKM2026）：**
  - 信号的股票特征截至建仓前一个月末，期权隐含特征截至第三个周五，周一建仓；随机森林只用过去 5 年数据训练。时点清楚。
  - 收益按中间价计，**原文没有任何交易成本分析**；价差主要来自做空高分歧组跨式（需保证金），个股跨式买卖价差通常很大，实际可得收益未知。
  - 信号依赖随机抽取的特征子集与超参数（随机种子未给出）以及 Jensen–Kelly–Pedersen 全部特征与 30 个期权隐含特征，复现成本高。
  - 与分析师分歧（M4426、M7010，股票市场）、按分析师分歧买个股认沽卖指数认沽的离散度交易（M0168）、HV−IV 跨式（v36 集合）不同。

**以下候选没有收入**，原因与匹配 ID 见 `rejected-v45.csv`：

- **前视（1 条）：** Aston“Salience theory and option returns”（So、Zhang，EJF 2026，CC BY）。OST 用到月末为止的日度 Delta 对冲期权中间价收益计算（派生文本 L345–L430），又按同一月末中间价建仓，OST 与上月期权收益相关 0.31（L448），表格中没有隔日建仓的结果。
- **前视无法核实（1 条）：** NBER w35513“Industry Distress Anomaly”。行业困境=SIC4 内按销售额加权的 CHS 失败概率（L337–L345），原文没有说明 logit 系数是否只用过去数据估计，无法确认可交易口径；核心输入就是目录已有的 CHS 信号（M4225）。
- **叠加层（1 条）：** 兰卡斯特“Integrated Approach to Currency Factor Investing”，参数化组合在套息、动量、价值上倾斜并加因子择时（摘要 L59–L70），不是新信号。
- **不可交易（1 条）：** KIT“Anomalies and optionability”，研究已有异象在可期权与不可期权股票上的差异（摘要 L17–L27），没有独立交易规则。
- **变体（2 条）：**
  - PolyU 托管的 Ang、Lam、Wei“Mispricing Firm-level Productivity”：PROD 是 ln(ME) 对 ln(BE)、D/A、CAPX/SALES、RD/SALES、AD/SALES、PPE/TA、EBITDA/TA 与行业虚拟变量的随机前沿效率（L385–L435），与目录已有的 Nguyen–Swanson 有效前沿 Frontier（M0407，同一回归变量、6 月排序、等权十分位、持 12 个月）同核心信号，SFA 与 OLS 残差只是估计方法不同；
  - NBER w34402：同 GWW2024 的现金流 β 版本。
- **来源受阻或不可得（11 条，均未绕过）：**
  - KCL Pure 外汇期权截面因子（Cloudflare 403）；
  - Harvard DASH 两篇（Peso Perspective、Passive Drift；AWS WAF “Human Verification”，HTTP 405）；
  - eScholarship 两篇（Unusual News Flow 仍 403，此前已在 R36-009/R40-019/R41-024/R43-004 拒收；Purchase Obligations 403）；
  - MIT DSpace 的 So 等财报公告波动风险溢价（AWS WAF，HTTP 405）；
  - DukeSpace 的 Multiples Valuation 论文（Anubis 工作量证明校验页）；
  - UChicago Knowledge 的 Company Announcements and Stock Returns（请求挂起超过 150 秒后终止）；
  - SMU InK 的 Center of Volume Mass（仍是 212 字节 Incapsula 页面，按指示跳过）；
  - HKUST 两篇（Leased Capital Premium、Asset Durability Premium；验证码重定向循环）。

## 产出评估（按池）

本批 4 条过线（多于 3 条），未凑数。

| 池 | 评估 | 收入 | 未收 | 收入率 |
| --- | ---: | ---: | ---: | ---: |
| 池 B 五条线索 | 5 | 1（City） | 4 | 20% |
| 池 B 余量（美国与亚洲仓储） | 11 | 0 | 11 | 0% |
| NBER 2024–2026 | 5 | 3（w33423、w32509、w35500） | 2 | 60% |
| 合计 | 21 | 4 | 17 | 19% |

- **池 B 五条线索：** 五条全部处理完。City 收入；兰卡斯特为叠加层，KIT 无独立规则，Aston 前视，KCL 受阻。**这五条线索已用尽。**
- **池 B 余量：**
  - **发现方式：** OpenAlex 按仓储来源 ID（DASH、MIT、Columbia、Duke、UChicago、Stanford、NYU FDA、eScholarship、HKUST、NUS、SMU、PolyU）检索资产定价相关作品，共 2,829 条，按标题筛选后再对目录去重。
  - **结论：** 美国仓储大多有机器人防护：DASH 与 MIT DSpace 为 AWS WAF 人机验证，Duke 为 Anubis，eScholarship 403，UChicago 请求挂起；均未绕过。Columbia、NYU、Stanford、NUS 在 OpenAlex 中没有找到带开放全文、且有交易规则的资产定价候选（Columbia 与 NUS 的相关条目没有 PDF 链接）。HKUST 仍为验证码，SMU InK 仍为 Incapsula。PolyU 唯一可取的候选与 M0407 同信号。许多 HKUST/SMU/PolyU 标题已被目录覆盖（好坏套息、frog-in-the-pan、days-to-cover、技术关联、客户资本等）。
  - **判断：池 B 对可访问内容已枯竭。** 剩余价值都在受阻来源后面，不绕过就拿不到。
- **NBER 2024–2026：**
  - **发现方式：** 用 NBER 官网的工作论文列表接口做 37 组关键词检索，得到 2024–2026 年工作论文 1,963 篇；按标题与摘要前 300 字筛出 229 篇金融相关，再按“有截面或时序交易规则、目录未覆盖”取 5 篇全文。
  - **筛掉未取全文的（只看标题与摘要，未写入拒收表）：** w33037 Trading Volume Alpha（组合优化中的交易量预测，非独立信号）、w33320 公司债玻璃盒机器学习（多特征机器学习组合）、w34086 散户逆向与动量（动量条件化，属变体）、w32422 自动生成异象（方法论）、w35186 AlphaGlass、w35195 AlphaPortfolio、w34861 ML meets Markowitz（机器学习或强化学习组合选择）、w35158 Mosaics of Predictability（面板树预测）、w32900/w34009（定价检验）、w35572 与 w34443（货币溢价模型）、w35498（最优货币对冲配置）、w35041（国会议员交易，作者结论为无信息）、w35095（沪深港通政策事件）、w35451 AI Premium（依赖专有 OpenRouter 数据）。
  - **判断：NBER 池未枯竭。** 关键词列表接口的覆盖不完整（是否按日期排序未核实，每词最多取 300 条），摘要只看了前 300 字。更细的逐月浏览可能每批再找到 1–3 条，但多数会是机器学习组合或期权截面，需逐篇核前视与成本。

## 版本口径

- **NBER 官网原发（非镜像）：** w33423（封面 2025-01）、w32509（封面 2024-05，作者 2013 年工作论文的大幅修订版）、w35500（封面 2026-07，PDF 内含网络附录 IA1–IA5）。均未见期刊版，未比对。
- **大学机构仓储托管：** Vasquez、Xiao 为 City St George's Research Online 托管的作者接受稿（文件名 VX_Jan2022，含网络附录），未与 Management Science 2024 终版比对。
- **镜像：** 本批收入的记录没有使用第三方镜像。
- **许可：**
  - City Research Online 条款：可用于个人研究、学习、教育或非营利目的，须注明出处并链接元数据页，**不得改动内容**。该 PDF 只放在 bundle 的 raw/ 和被忽略的快照目录中，不应改动后再分发。
  - NBER 三篇版权页均为“All rights reserved”，只允许引用不超过两段，沿用 `UNKNOWN_NO_EXPLICIT_REUSE_LICENSE`。PDF 不应提交到公开仓库。

## 抓取日志说明

- v45 的全部 24 行（23 次文档抓取，含失败，外加 1 行补记说明）在 `fetch-log-v45.jsonl`，即原日志第 210–233 行，时间为 2026-10-08 19:49–20:02（UTC+8）。日志只追加，本批没有删除任何行。
- OpenAlex API 与 NBER 列表接口的发现性查询没有写入该日志，只写入候选文档抓取。
- **补记行（如实披露的失误）：** 我曾用不经过 `fetch.py` 的手工 `curl` 请求 `http://hdl.handle.net/10161/9589` 与 `http://knowledge.uchicago.edu/record/2849`，两次都挂起超过 150 秒后被终止，未保存内容，当时也没有写日志。事后补写第 228 行（键 `note_manual_attempts_v45`，`type: note`），所以这一行的时间戳晚于它所记录的请求，且排在 `duke_multiples` 之后。
- **状态码与内容不符：** 第 227 行 `duke_multiples` 记为 HTTP 200，但内容是 5,017 字节的 Anubis 工作量证明校验页，不是论文。保留原样未改，按“来源受阻”拒收。
- **城市大学两行辅助页：** 第 214 行 `city_xiao_list`（作者列表页）与第 216 行 `city_defopt_page`（条目页）只用于定位 PDF。

## 来源与边界

- **快照锁定：** 每个来源都锁定了原 PDF 的摘要，以及 `pdftotext -layout -enc UTF-8 - -` 派生文本的摘要，生成器版本为 `pdftotext version 25.03.0`。用 `--verify-snapshots` 复核时须使用同一版本。
- **行号与页码：** 字段行号指向派生文本，按 Python `splitlines` 计行；页码是原 PDF 的物理页。
- **执行时点：**
  - VX2024 月末按已有信用评级排序、按月末期权中间价建仓。
  - BGX2025 只用第 T 月末已知的实时宏观数据，T 月末建仓，按 T+1 月收益评价。
  - GWW2024 每年 6 月、12 月用已公布的调查预测估计 β 后建仓。
  - BKM2026 信号数据早于周一建仓，模型滚动样本外。
- **已知局限：** BGX2025、GWW2024、BKM2026 原文未扣交易成本；VX2024 作者的成本分析显示实际有效价差加保证金与融券费后不再盈利。
- **存储位置：** 公开目录只保存自撰的中文定义和来源证据；论文 PDF 和派生文本留在被忽略的 `datasets/raw/sources/harvest2000-v45/`。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v45
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v45 --verify-snapshots
```

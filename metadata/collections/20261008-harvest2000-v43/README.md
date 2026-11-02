# v43 来源定义批次

本批新增 1 条策略、3 个投资因子（`investment_factor`），已完成来源、定义和去重复核。本批未运行任何算法，未回测，也未验证收益；商用状态仍为 `REVIEW_REQUIRED`。

本批承接 cd2f284（v39），叠加 v40、v41 与 v42 bundle。本批只看此前未扫过的四类来源：SSRN 受阻论文在 RePEc/IDEAS、CORE、大学机构仓储与央行/国际机构工作论文系列中的开放副本；国际与新兴市场股票异象；期权/波动率与商品期货策略；开放获取期刊（JFDS、Critical Finance Review、FAJ、JPM、MDPI JRFM/IJFS）。收入的 4 条全部来自大学机构仓储（剑桥 Apollo、雷丁 CentAUR、兰卡斯特 EPrints），没有使用第三方镜像。所有受阻来源都没有绕过。评估的 21 个候选中收入 4 条，17 条未收，见下文与 `rejected-v43.csv`。

本批沿用 v42 更严的前视规则：论文主结果若依赖当时无法获得的信息（如事后确定的样本、回溯数据、同一时点既算信号又按该价成交），且表格中没有按可交易日期给出的结果，即以“前视”拒收。

| 原生 ID | 类型 | 完整构造 | 来源 |
| --- | --- | --- | --- |
| LSZ2025:currency-skewness-risk-premium-SRP | 因子 | 28 种兑美元货币；每月末用过去 3 个月去均值日收益算上行/下行已实现半方差，RSK=(RV^U−RV^D)/RV；用 3 个月期场外期权（ATM、10δ/25δ 风险逆转与蝶式插值）算隐含半方差，ISK=(IV^U−IV^D)/IV；SRP=RSK−ISK。按 SRP 分五组等权，做多最高组、做空最低组，用 1 个月远期持有 1 个月。 | Li、Sarno、Zinna，作者接收稿（2025-08-22 修订，JFQA），剑桥大学 Apollo 机构仓储托管，稿件声明 CC BY |
| HPT2021:commodity-aggregate-jump-beta-AggJump | 因子 | 每月末对每种商品期货用过去 12 个月日超额收益回归股票市场超额收益与 Cremers–Halling–Weinbaum（2015）总体跳跃因子 JUMP，取 JUMP 的β；分三组等权，全额抵押下做多β最低组、做空β最高组（各半仓），逐月再平衡。 | Hollstein、Prokopczuk、Tharann，作者接收稿（QJF 2021），雷丁大学 CentAUR 机构仓储托管 |
| HPW2020:beta-uncertainty-UncBeta | 因子 | 每月末对每只美国普通股用九种贝塔估计（12/6 个月历史、两种 EWMA、Dimson 滞后 1–4 期、Scholes–Williams）的 95% 置信区间，贝塔不确定性=区间上端最大值−下端最小值；分五组市值加权，做多最低组、做空最高组，持有 1 个月。 | Hollstein、Prokopczuk、Wese Simen，作者接收稿（2020-03-16，JBF 2020），雷丁大学 CentAUR 机构仓储托管，CC BY-NC-ND 4.0 |
| AKMP2021:option-volume-moneyness-dispersion-DISP-market-timing | 策略 | 个股期权（5–60 天、剔除 0.95–1.05 近平值）按各行权价成交量占比算成交量加权价位 K/S 的离散度，月内日均后按市值加权得全市场 DISP；月末用此前全部数据（初始 5 年）递推回归下月 CRSP 价值加权超额收益，样本外预测按风险厌恶 3 的均值方差规则配置美股指数，权重限 0–1.5，其余持无风险资产，逐月调整。 | Andreou、Kagkadis、Maio、Philip，2019-08 作者终稿（Critical Finance Review 2021），兰卡斯特大学 EPrints 机构仓储托管 |

## 去重

每条都检索了 `coverage-map-v43.csv`，同时使用英文和中文关键词，并逐一对照了 v35–v42 集合记录的 ID 清单。检索范围如下：

- 6,971 条 M 记录
- 1,570 个因子变体
- v1–v42 的 443 项
- 11 条已审记录
- v35 的 56 条、v36 的 34 条、v37 的 41 条、v38 的 37 条、v39 的 24 条、v40 的 19 条、v41 的 25 条、v42 的 15 条拒收记录

最近的旧 M 记录钉在 `reviews.json` 的 `compared_rule_pins` 中，同时锁定文件摘要和行摘要。与集合记录的比较只写在去重理由文字中。

判重规则：市场相同且核心信号相同，即视为同一条。

**需要复核的四条：**

- **货币 SRP 与套息：** 作者显示 SRP 多空收益主要来自利率差（远期贴水年化 8.06%），即期部分为负（−2.59%），与套息因子高度相关；作者称 SRP 的定价能力强于套息。核心信号是“已实现偏度−隐含偏度”，与 M0345/M4161 套息（利率差）、M0829（4 个货币对的历史偏度阈值）、v36 的 13156:FX-VRP（方差而非偏度风险溢价）、v38 的 24178:FX-vol-carry-VCA（隐含波动率期限斜率）不同，所以判为不同核心信号。期权数据来自未具名投行，非公开；原文未扣交易成本。
- **商品 AggJump：** JUMP 因子的构造（标普 500 指数期权的市场中性、vega 中性、gamma 为正的跨式组合）本文未重印，复现须查 Cremers 等（2015）；JUMP 依赖 OptionMetrics，实际可用样本应自 1996 年起，本文未单列该排序的起止期。分子样本期结果方向相同但统计上更弱。
- **贝塔不确定性：** 溢价在卖空成本低的两组不显著、在卖空成本高的三组显著，空头腿实现难度大；置信区间是否用稳健标准误等估计细节未写明。
- **DISP 择时：** 均值方差权重的公式与方差估计窗口原文只写“基于历史数据”，未印明，已写入缺失信息；样本外期只有 2001–2017 年，原文未扣交易成本。

**以下候选没有收入**，原因与匹配 ID 见 `rejected-v43.csv`：

- **前视（2 条）：**
  - Duan–Li–Wen 碳排放强度与公司债：每年 6 月用 Trucost 上一财年排放排序，未核对 Trucost 实际发布时点；Trucost 对未披露公司用模型估算并回溯修订历史，表格中没有按发布时滞调整的结果。SMU INK 仓储两次 TLS 错误，未绕过，改读 SMU SKBI 研究院托管的 2022-02 稿。
  - Bianchi–Fan–Miffre–Zhang 商品期货曲线 Nelson–Siegel 斜率策略（arXiv）：用 t 日结算价算信号，又按同一结算价建仓，没有次日执行的结果表。
- **不可交易（2 条）：** Jones–Shemesh 非交易日期权定价（作者明言扣成本后单独策略不可行）；Prokopczuk 等商品方差风险（合成方差互换收益的度量，无交易规则）。
- **重复（1 条）：** Kang–Rouwenhorst–Tang 商业交易者净交易，与集合 TaleTwoPremiums-2017:hedger-Q 同市场同信号。附注（未改动旧记录）：旧记录按周二持仓排序，早于周五 COT 发布，可能含前视；原文表 4 有发布后第 5–20 天的可交易版本。
- **证据偏弱（1 条）：** 同一 CentAUR 稿中的商品波动率之波动，原始多空均值只在 10% 水平显著，不另起一行。
- **叠加层（1 条）：** 商品期货波动率管理组合（波动率缩放叠加，CORE 全文未取）。
- **来源受阻或无开放全文（10 条，均未绕过）：**
  - Muravyev–Ni 期权日夜收益（作者站点机器人校验页）；
  - Unusual News Flow（CORE 下载 Cloudflare 403）；
  - Bianchi–Drew–Fan 商品 52 周高点（只找到二手摘要）；
  - Curve Momentum（CentAUR HTTP 401 受限，http 地址超时）；
  - 股票波动率长记忆（汉诺威大学讨论稿服务器超时，EconStor 机器人校验）；
  - Convenience Yield Risk（埃塞克斯大学仓储 TLS 错误）；
  - FAJ 三篇混合开放获取文章（tandfonline HTTP 403）：气候脆弱性与货币收益、货币股权差异因子、规避指数调仓拥挤；
  - 韩国股息月溢价（Emerald HTTP 403）。

## 产出评估

本批 4 条过线（多于 3 条），但几乎全部来自同一个子池。按池说明如下：

- **池 1（开放副本）：** 是本批唯一有实质产出的池。剑桥 Apollo、雷丁 CentAUR、兰卡斯特 EPrints 各出 1 条（另 1 条来自 CentAUR）。CORE API 能找到仓储地址，但 core.ac.uk 下载一律是 Cloudflare 校验；EconStor 有机器人校验；SMU INK、埃塞克斯仓储 TLS 错误；汉诺威讨论稿服务器超时；CentAUR 部分条目受限（401）。IDEAS 站内检索没有可解析结果。Prokopczuk 团队在 CentAUR 的开放稿已基本看完，其余多为波动率预测、beta 估计方法等非策略论文。美联储、欧央行、英格兰银行、IMF、BIS 等央行和国际机构工作论文系列，本批没有系统重扫（v36–v38 已收过 IFDP 等），**这一子池仍未穷尽**。
- **池 2（国际与新兴市场）：** 用 OpenAlex 按中国 A 股、日本、韩国、印度、台湾检索开放获取论文。结果多是对美国异象的简单复制，或发在低质量刊物上；少数相关文章（Emerald、Taylor & Francis）返回 403。**本池零产出，从本机可达的高质量开放来源看已枯竭。**
- **池 3（期权与商品）：** 收入 1 条（商品 AggJump）。其余候选或不可交易，或触发前视，或来源受阻。**本池接近枯竭。**
- **池 4（开放获取期刊）：**
  - cfr.pub 域名已不再是 Critical Finance Review 网站（现为无关站点）；CFR 文章只能找仓储副本，本批由此收入 DISP 一条。
  - FAJ 的混合开放获取 PDF 在 tandfonline 一律返回 403。
  - JPM、JFDS 的开放文章多为机器学习方法、社论或资产配置，没有完整的可交易规则。
  - MDPI 没有找到证据扎实的候选，未收。
  - **本池基本枯竭或受阻。**

继续采集时，只有池 1 的大学仓储和央行工作论文系列还有少量余量，预计每批过线不超过 2–4 条；池 2、池 3、池 4 不建议再投入。

## 版本口径

- **大学机构仓储托管的稿件：**
  - Li–Sarno–Zinna 为剑桥 Apollo 托管的作者接收稿（2025-08-22 修订），未与 JFQA 终版比对。同仓储另一条目是网络附录，已抓取（`fxsrp_cam`）但未作为证据。
  - Hollstein–Prokopczuk–Tharann 为雷丁 CentAUR 托管的接收稿（正文为 SSRN 3567629 稿），未印日期。
  - Hollstein–Prokopczuk–Wese Simen 为 CentAUR 托管的接收稿（2020-03-16）。
  - Andreou 等为兰卡斯特 EPrints 托管的 2019-08 作者终稿。
  - 以上都未与期刊终版比对，已写入各记录的 `missing_information`。
- **镜像：** 本批收入的记录没有使用第三方镜像。
- **许可：**
  - Li–Sarno–Zinna 稿件脚注声明作者对接收稿适用 CC BY，未印版本号。
  - Beta Uncertainty 的 CentAUR 封面标注 CC BY-NC-ND 4.0。
  - 其余两条未见明确的再使用许可，沿用 `UNKNOWN_NO_EXPLICIT_REUSE_LICENSE`。

## 来源与边界

- **快照锁定：** 每个来源都锁定了原 PDF 的摘要，以及 `pdftotext -layout -enc UTF-8 - -` 派生文本的摘要，生成器版本为 `pdftotext version 25.03.0`。用 `--verify-snapshots` 复核时须使用同一版本。
- **行号与页码：** 字段行号指向派生文本，按 Python `splitlines` 计行；页码是原 PDF 的物理页。
- **执行时点：** 四条都只用信号时点已可得的数据：
  - SRP 的物理偏度用滞后已实现值（随机游走代理），t 时可观测。
  - AggJump 与贝塔不确定性用 t 之前 12 个月（或更长）的日数据。
  - DISP 以当月倒数第二个交易日为月末，预测只用当时可得的数据。
- **已知局限：** 三个因子与一个策略的原文都没有扣交易成本。SRP 与套息高度相关，AggJump 依赖未重印的 JUMP 因子，贝塔不确定性溢价集中在难卖空的股票，DISP 的权重细节未印明。
- **存储位置：** 公开目录只保存自撰的中文定义和来源证据；论文 PDF 和派生文本留在被忽略的 `datasets/raw/sources/harvest2000-v43/`。

```sh
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v43
uv run python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v43 --verify-snapshots
```

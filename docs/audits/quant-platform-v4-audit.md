# Quant Platform V4 Audit Report

日期：2026-09-28。结论：三个可信链路缺陷已修复并增加反例测试；研究数量目标未实现：**ELIGIBLE=0，Formal Real-Market Backtest=0**。没有降低许可、完整历史或原生字段门槛。没有任何实盘授权或部署。

## 基线与范围

[开发前 main 基线](quant-platform-v4-baseline.md)：Graph `dd983d7a`，Lab `cef6207c`。前轮 PR #4/#9 仍 OPEN，未被当成已合并事实。新分支从 main 建立并包含这两个未合并提交作为依赖；本 PR 包含相应功能，旧 PR 保持原状，均不自行合并。

Graph 分支 `feat/evidence-chain-v4`；Lab 分支 `feat/formal-market-research-v4`。Lab 主目录的 160 项既有改动未修改。本轮没有读取、修改或运行 quant-runner 代码，也没有读取私钥。

## 本轮修复

1. ResearchContract 明确身份、实验族、完整参数网格与次数、固定资产、频率、请求历史、IS/OOS、成交时序、持有/再平衡、费用、滑点和数据依赖。行情 manifest 固定合同**原始 UTF-8 字节 SHA256**；回放前后复核，连空白变化也不能绕过。Graph 保存合同原文及摘要，写回再核验网格、family 与 config。
2. MarketCoverageValidator 对完整 `[start,end)` 范围验证：左右边界、内部缺口、实际/预期数量、顺序、重复和额外时间点。加密市场按 UTC 24/7；股票按 exchange-calendars 的交易日，保存版本，日线时间戳为 session label。actual_end 表示最后一根开盘标签，不是窗口右端。
3. 下载器仅引用 reviewed-rights-v4。research、commercial、redistribution、derivative、attribution 相互独立；`rights_sha256` 为规范化 JSON 对象摘要，`evidence_sha256` 为支持材料原始字节摘要。Lab 检查文件存在、两个摘要、provider/source/scope、用途、审核状态及权限。旧 V3 下载入口已关闭，旧许可断言不能成为当前权限。
4. 每项研究假设增加 assumption_reason / assumption_version；来源定义保留各自出处。来源可追溯与实际支持的规则部分分开判断，指标作者不自动成为策略作者。
5. 数据需求由 AST 与 ExecutionContract 推导：SMA/ZScore 下一开盘需要 close/open；EMA 加成交量与括号退出需要 OHLCV；CLOSE 执行不强加 open。未知节点阻断，基本面保留可得性滞后与辅助数据；未验证辅助数据仍阻断。**信号依赖不豁免 Lab 全仓库 OHLCV 质量合同**。
6. Gate V4 独立输出来源、支持范围、许可、规则、执行、数据需求、实际数据、去重、本体。准备分数不表示盈利概率。旧 V3 审核仍可读，但无法自动入场。队列按缺口、准备程度、来源质量和家族多样性排序。
7. 市场内核新增不可变 v2，保留 v1；开盘即平仓 exposure=0。exposure 是开盘操作后的持仓代理；盘中退出只给时长上下界，不冒充实际持续时间。回归测试要求 PnL、成交、费用逐项不变。
8. 正式写回升级 schema 3.0；API/SDK 保留查询、认证、不可变 run ID、重试幂等。`/v1/research/chain/{variant_id}` 返回 Source/Support/Provenance/Factor/Execution/Data/Dataset/Run/结果。BacktestResult 是同一不可变研究记录的确定性投影，避免两份结果漂移。此轮实际正式写回为 0。

## 实际漏斗

| 指标 | main 基线 | V4 最终 |
|---|---:|---:|
| observations / semantic records / revision rows | 5813 / 5813 / 5813 | 5816 / 5816 / 5816 |
| additional revisions / duplicates | 0 / 0 | 0 / 0 |
| strict parsed / rule review | 202 / 5611 | 263 / 5553 |
| concepts / templates / variants | 28 / 41 / 5813 | 35 / 75 / 5816 |
| strategy-factor links | 221 | 296 |
| 完整 SourceEvidence（含历史审核） | 0 | 6 |
| 当前 V4 rights research-approved | 0 | 3 |
| 完整 ExecutionContract | 0 | 3 |
| 完整 AST-derived DataRequirement | 0 | 3 |
| VERIFIED datasets（质量和覆盖同时通过） | 0 | 0 |
| ELIGIBLE / CONDITIONALLY_ELIGIBLE | 0 / 0 | 0 / 0 |
| REVIEW_REQUIRED / BLOCKED | 5813 / 0 | 5815 / 1 |
| 正式候选 / 正式回测 | 0 / 0 | 0 / 0 |
| 正式 IS / OOS / Walk-forward complete | 0 / 0 / 0 | 0 / 0 / 0 |
| 正式 DSR / PBO evaluated | 0 / 0 | 0 / 0 |
| 正式 passed / failed / inconclusive | 0 / 0 / 0 | 0 / 0 / 0 |
| 正式 ResearchEvidence / BacktestResult 新写入 | 0 / 0 | 0 / 0 |

相对未合并 V3：同样的原始 5813 条语料 strict parsed **260 → 260**；三条手工来源派生规则另列，总量 **263 → 263**。本轮没有新写 parser，也没有猜 AST。主分支到本 PR 的解析增长来自显式包含的 V3 依赖。规则 review=5553；准入 review queue=5816，二者不同。

## 最近的三个模板与真实数据审计

三个显式来源改编模板分别为 price>SMA、stateless ZScore reversion、EMA crossover+volume+bracket；共三个实验族、13 个网格配置（3/5/5），不是 13 个独立发现。三者准备分数均 90，仅剩数据可用性这一大项，但该项包含多个独立硬缺口。

| 模板 | 数据源 / 市场 | 预期 / 实际 bars | 缺口 | 覆盖 | 正式入场 |
|---|---|---:|---:|---|---|
| SMA 日线 | Bit2Me public REST / BTC/EUR spot | 1549 / 719 | 830 | PARTIAL | 拒绝 |
| ZScore 日线 | Bit2Me public REST / BTC/EUR spot | 1549 / 719 | 830 | PARTIAL | 拒绝 |
| EMA 4h | Bit2Me public REST / BTC/EUR spot | 9294 / 714 | 8580 | PARTIAL | 拒绝 |

固定请求 2022-07-01 至 2026-09-27（右开）；日线实际 2024-10-08 至 2026-09-26，4h 实际 2026-05-31 至 2026-09-26 20:00 UTC。均无重复、无乱序；主要是左侧历史不足，不能称 FULLY_COVERED。下载后未缩短合同窗口。

此外，接口缺原生 trade_count、quote_volume、vwap、is_closed；未建立可信闭合和独立场所身份交叉核验。没有造列、补零、把 missing funding 当零，亦未把这些数据写成 trusted/normalized。spot 的 funding 是机制上不适用。

Bit2Me 官方[行情条款](https://legal.bit2me.com/en/support/solutions/articles/35000293283-market-data)允许受限制的内部分析，并限制向第三方分发行情与派生研究。结构化审核保留 research=true、commercial=null、redistribution=false。本轮没有使用社区代码许可充当行情许可。Kraken 等替代来源的非个人商业用途仍需单独授权；未收到用户用途确认或新授权前不作推定。

## 私有诊断与统计边界

三组真实市场 PRIVATE_DIAGNOSTIC_PROBE 已运行，均 formal_count=0，均没有写入正式证据库。三组数据质量阻断日志和逐栏账户/成交/交易路径保留在对应家族 artifacts。相同冻结合同的验收重放单列修订，不重复计算模板或独立发现。当前 journal 还保留一个旧 PIPELINE_DIAGNOSTIC（synthetic），与此次真实行情私有诊断分开。

DSR 使用每 bar Sharpe、总体标准化 skew、Pearson kurtosis、名义网格次数和 expected-max Sharpe；明确年化转换与既往试验暴露，不冒充全项目多重检验校正。PBO 使用 CSCV、并列 IS 优胜者等权、OOS midrank；不满足样本或方差要求为 NOT_APPLICABLE。没有 purge/embargo，跨块持仓是 LIMITATION。参数面、基线邻域敏感度、平台范围、成本压力和最近窗口均保留；不选择最高 OOS 参数。

完整收益数字和可复核哈希仅保存在本机《Quant Platform V4 Research Report.md》，不随公开 PR 分发。私有诊断中的 IS/OOS 不计入上表正式 complete；EMA 样本全部晚于原 OOS 起点，IS 不足，不能偷偷重新切分。

## Top blockers

- DATA_AVAILABILITY_UNCONFIRMED: 5816。
- DATA_REQUIREMENT_UNVERIFIED: 5813。
- DEDUP_UNRESOLVED: 5813。
- EXECUTION_CONTRACT_INCOMPLETE: 5813。
- RIGHTS_REVIEW_REQUIRED: 5813。
- RULE_NOT_VERIFIED: 5813。
- SOURCE_EVIDENCE_UNVERIFIED: 5813。
- V4_REVIEW_REQUIRED: 5813。
- SOURCE_SUPPORT_UNVERIFIED: 5810。
- ONTOLOGY_INCOMPLETE: 5553。

## 验收与剩余工作

本机完整检查见下方最终验收；精确 commit 与 CI URL 见对应 PR 与交付消息。契约变更、缺尾/中间缺 bar/重复/乱序、股票交易日、权限未知/错 scope/篡改、正式入口拒绝、schema/API/SDK/读回、暴露不改账均有测试。没有配置 typecheck，不能把它报告为通过。

未完成的是业务目标，不是以诊断冒充正式研究：仍需覆盖冻结历史、满足原生 schema、闭合和来源身份要求且权限适用的数据。在这些事实改变前保持 ELIGIBLE=0，不自动进入任何执行层。

## 当前 parser review archetypes

共 5553 条规则待审；重新按现有语义分类统计，未新增猜测解析。

| 类别 | 待审数 |
|---|---:|
| other_or_ambiguous | 821 |
| cross_sectional_rank_top_n | 720 |
| fundamental_value_quality | 483 |
| rsi | 431 |
| price_vs_ma | 359 |
| volatility_filter | 298 |
| threshold_allocation | 259 |
| event_calendar | 243 |
| source_factor_portfolio | 184 |
| trend_volatility_combination | 169 |
| macd | 153 |
| source_code_fragment | 151 |
| momentum_other | 145 |
| ema_crossover | 137 |
| breakout_donchian_rolling_extreme | 118 |
| options_volatility | 100 |
| sma_crossover | 85 |
| bollinger | 77 |
| funding_carry | 75 |
| volatility_targeting | 72 |
| etf_rotation | 68 |
| oscillator | 64 |
| pairs_spread_zscore | 61 |
| roc | 54 |
| absolute_momentum | 47 |
| mean_reversion | 44 |
| risk_on_off | 39 |
| relative_momentum | 34 |
| dual_momentum | 31 |
| machine_learning | 27 |
| zscore | 4 |

## 最终本机验收

Graph：143 passed / 1 skipped；lint、validate-release（离线重建指纹一致）、verify-public、build-public 全部 PASS。首轮代码迭代期间的 release 指纹变化失败日志完整保留，最终按 build → validate-release 顺序核验同一代码快照通过。Lab：900 passed / 98 skipped，governance preflight 与 lint PASS。两仓库均未配置独立 typecheck。CI 与最终提交见 PR 和交付消息；未将尚未完成的 CI 写为成功。

真实 HTTP/SDK 读取 5816 条候选并按模板筛选；三个目标模板的完整证据链读回通过，实际正式 writeback=0。临时服务已关闭，认证 token 仅存在于运行内存。

私有诊断 DSR 3 组 COMPUTED；PBO 3 组 NOT_APPLICABLE（零方差/样本不足），正式统计计数仍全部为 0。日线诊断 IS 85 / OOS 634 bars，4h IS 0 / OOS 714 bars。账户路径在原 IS/OOS 切点连续；闭合交易按退出时间归区间，不强制在切点平仓。最近窗口用于审计，不用于选择。

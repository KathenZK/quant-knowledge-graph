# Quant Platform Evidence & Research V3 Report

本轮总目标尚未达到：`ELIGIBLE = 0`、正式 `REAL_MARKET_BACKTEST = 0`。不能把私有行情诊断改名计入正式研究。阻断是来源/执行覆盖不足与行情准入，不能据此断言这些经济机制无效。

## 当前计数

| 口径 | 实际值 |
|---|---:|
| 原 GrokBot observations / records | 5813 / 5813 |
| 新增显式来源派生记录 | 3，单列，不充当语法覆盖增长 |
| 当前 observations / semantic records / revision rows | 5816 / 5816 / 5816 |
| additional revisions / duplicates | 0 / 0 |
| 原始语料 strict parsed | 202 → 260，4.47% |
| 原始规则 REVIEW | 5611 → 5553 |
| 含显式派生记录 parsed | 263 |
| concepts / templates / variants | 35 / 75 / 5816 |
| 真实参数变体组 / 资产变体组 | 34 / 11 |
| SOURCE evidence / research rights 已审核 | 6 / 6 |
| 完整执行约定 / 已记录 DataRequirement / 已验证数据 | 3 / 6 / 0 |
| ELIGIBLE / CONDITIONALLY_ELIGIBLE | 0 / 0 |
| REVIEW_REQUIRED / BLOCKED | 5815 / 1 |
| 只缺数据的高优先级模板 | 3 |
| 因子来源记录 / canonical concepts | 1578 / 13 |
| cross-source mapped / unresolved | 204 / 1374 |
| 有因子链接策略 / strategy-factor links | 263 / 296，均不代表收益归因 |

Lab 通过真实本机 HTTP + QuantGraph SDK 消费全部 5816 行，显式检查 READY/V3/ELIGIBLE。按概念/模板取最多 20 个的结果是 0，保留全部阻断原因。

## 研究执行与停止原因

看行情结果前固定了三个独立家族的研究约定：PRICE_SMA 1d、ZSCORE_REVERSION 1d、EMA_CROSSOVER 4h，分别 3、5、5 组参数；固定基准而非挑 OOS 最优值。现货 BTC/EUR，EUR 账户，每边 60 bps 手续费和 10 bps 滑点属于显式研究假设。源码短仓转现金、下一栏开盘也属于改编，未冒充原始引擎精确复现。

原摘要中的 M0234“均线交叉”与锁定 momentum.py 的价格/SMA 条件冲突；M0256 摘要缺少源码的成交量、ROI 与止损条款；M0233 摘要未完整说明实际 stateless 头寸行为。原记录未覆盖；新版本保留 parent ID、代码版本与授权来源。

Bit2Me 官方条款第 2 条明确允许内部分析；第 3 条限制对第三方分发行情及衍生分析。这是内部研究用途判断，不是商业产品或行情再分发授权。因此价格、净值、收益指标和诊断结果仅保留本机私有 artifacts；公共 PR 只放代码、冻结约定及准入/完成状态。参考 [官方 Market Data Terms](https://legal.bit2me.com/en/support/solutions/articles/35000293283-market-data)。

接口原生缺少 trade_count、quote_volume、vwap；没有把它们补成 0 或假装 native。最初日线分页缺口由同一接口补回，重复观察一致；但所需完整历史和可信字段仍不足。4h 下载遇到限流，保留部分字节，未绕过限制。所有数据保持 raw_unaccepted，不写 normalized，不进入 trusted loader。

| 执行口径 | 完成数 |
|---|---:|
| 正式研究 candidates / backtests / IS / OOS / walk-forward | 0 / 0 / 0 / 0 / 0 |
| 正式 research passed / failed / inconclusive | 0 / 0 / 0；没有可判定正式 ResearchRun |
| 私有真实行情诊断家族 / 参数试验 | 2 / 8 |
| 私有诊断 IS / OOS | 2 / 2；历史覆盖不足，不能当正式 OOS 证据 |
| 私有诊断 DSR computed / PBO computed | 2 / 0 |
| PBO attempted but not computable | 2：CSCV 分块零方差；未换样本或参数绕开 |
| 4h 家族完成诊断 | 0 |
| 正式 ResearchEvidence 回写 | 0 |

私有诊断输出完整账户、逐笔费用、净值、IS/OOS、成本压力、全网格稳健性、最近 1d/7d/1m/3m/6m/1y 切片。DSR 用每观察期 Sharpe、Pearson kurtosis、全部 nominal trials；PBO 保留 tie policy，明确无 purge/embargo。未产生 prospective、promotion 或 Runner 证据。

## 代码与验收

- Lab 缺失/未知/非 READY 上游状态 fail closed，只有显式 ELIGIBLE V3 自动准入；多样性覆盖六个维度。
- 新账户内核 v1 逐栏时序、费用守恒、未来价格不影响既往行为、止损跳空和双触碰顺序均有测试；原诊断内核 v1/v2 未改写。
- schema 2.0 编码/SDK 写入与回读已实现；QuantGraph 同事务重查准入和完整 DataRequirement。正式写回的成功/拒绝、幂等、来源失配均只在隔离测试库验证，未污染真实 journal。
- Lab 完整本地：865 passed / 98 skipped；preflight、lint PASS。跳过是原有本机制品/资料依赖，不是研究通过。
- Graph 完整本地：137 passed；lint、build-public、verify-public、rights verify、validate-release 全部 PASS。两仓库没有单独配置静态 typecheck。CI 状态见 PR。

下一项实质工作是为三个高优先级模板提供获准使用、原生字段完整、历史足够且闭合语义明确的行情，再冻结数据哈希并重跑正式账户。当前证据不支持把 eligible 或正式回测计数改成非零。

## 基线与变更入口

- [最新 main 基线](quant-platform-evidence-phase-baseline.md)：Graph `dd983d7a2b4025a796fc7130934bf56b7f26973a`；Lab `cef6207c502bb05e22b438321a8f29c7703ba8ba`。
- [V3 契约与使用方法](../evidence-research-v3.md)。
- [Top30 规则类型汇总](rule-archetypes-v3-summary.md)。完整含代表规则、来源和失败分类的报告仅在私有 reports 中。
- 原始 parser REVIEW 5611，当前 5553；unsupported 与 ambiguous 仍是合并码，独立计数 UNKNOWN，处理异常 0。
- Graph 分支 `feat/evidence-enrichment-and-research-gate-v3`；Lab 分支 `feat/first-real-quantgraph-research-v3`。两个 PR 均不自动合并。

## 阻断原因（允许重叠）

| 原因 | 记录数 |
|---|---:|
| DATA_AVAILABILITY_UNCONFIRMED | 5816 |
| SOURCE_SUPPORT_UNVERIFIED | 5810 |
| RIGHTS_REVIEW_REQUIRED | 5810 |
| RULE_NOT_VERIFIED | 5813 |
| EXECUTION_CONTRACT_INCOMPLETE | 5813 |
| DEDUP_UNRESOLVED | 5813 |
| ONTOLOGY_INCOMPLETE | 5553 |

只有三个显式派生记录已完成来源、研究权限和执行约定且只缺数据；其余并非仅增加行情就能放行。SOURCE evidence 完成意味着来源支持范围已核实，不表示原摘要完全正确。BLOCKED 的来源冲突仍保留。

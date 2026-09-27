# 真实数据质量报告 v2（2026-09-27）

统计基于同一 5813 条 GrokBot 来源记录；没有补造策略或行情。原 archive SHA256：`c9d6e7de6e876fcd75678085aebe5c88e94a4d8932a39565a5cad96fa0418954`。原始字节、旧 ID、来源原生 ID、原版本 projection 均保留；本报告只发布已审核聚合数字。

| 验收项 | 实际值 |
|---|---:|
| GrokBot observations / semantic records | 5813 / 5813 |
| revision rows（含首版）/ 后续 revisions / duplicates | 5813 / 0 / 0 |
| 批次 | 39 |
| parser before → after | 170 → 202 |
| 规则 review before → after | 5643 → 5611 |
| 全部准入 review before → after | 5813 → 5813 |
| Strategy Concepts / Templates / Variants | 28 / 41 / 5813 |
| factor-linked strategies / links | 202 / 221 |
| source factor records / canonical economic concepts | 1578 / 13 |
| factor mapped / unresolved | 204 / 1374 |
| conflicts / alias groups / variant review groups | 1 / 0 / 8 |
| eligible research variants / templates | 0 / 0 |
| real backtests / OOS completed | 0 / 0 |
| passed / failed research validation | 0 / 0（未启动） |
| failed candidate admission | 5813 |
| real promotion artifacts / paper approved / live approved | 0 / 0 / 0 |

Concept/Template 仅从可明确解析的规则计算；未分类的 5611 条保留来源变体，不虚构独立思想。curated=202 仅指规则定义通过语法门槛，不代表许可获准、可执行、经济有效或可晋级。

当前 parser grok-rule-v3.1 全量 projection 为 READY，current=5813，stale=0。每条记录缺来源核验、研究许可、执行契约与数据可用性证据，其中 5611 条另缺完整 AST。许可待审不等于已证实禁止使用；数据可用性未证实不等于市场不存在历史数据。Lab 通过认证 HTTP 重新读取全量，按模板去重后合格数为 0。

下面是本机报告生成器的聚合输出；它没有发布任何私有来源正文或回测制品。

## Parser coverage v2

输入 5813 条；grok-rule-v2.0 parsed=170 → grok-rule-v3.1 parsed=202，覆盖率 3.47%。
规则 review: 5643 → 5611。全部许可/执行待审。

1000 目标未达成，新增 32 条。缺口既包括未实现语法，也包括缺失规则/额外条款；不能声称所有剩余规则均无法解析。
下面 25 类加 residual 只用于审核路由，不据关键词生成 AST。

| RuleArchetype | 全部 | 严格解析 |
|---|---:|---:|
| other_or_ambiguous | 961 | 0 |
| cross_sectional_ranking | 920 | 0 |
| price_ma | 627 | 17 |
| rsi | 568 | 8 |
| trend_volatility_filter | 345 | 1 |
| source_code_fragment | 297 | 0 |
| volatility_filter | 274 | 6 |
| threshold_allocation | 259 | 10 |
| momentum_other | 198 | 1 |
| source_factor_portfolio | 184 | 0 |
| breakout_donchian | 122 | 1 |
| pairs_trading | 109 | 4 |
| macd | 103 | 1 |
| relative_momentum | 102 | 67 |
| ema_crossover | 95 | 0 |
| sma_crossover | 87 | 0 |
| oscillator | 85 | 36 |
| etf_rotation | 84 | 0 |
| absolute_momentum | 82 | 35 |
| volatility_targeting | 80 | 11 |
| bollinger | 62 | 0 |
| roc | 49 | 2 |
| mean_reversion | 44 | 0 |
| risk_on_off | 39 | 0 |
| dual_momentum | 34 | 2 |
| zscore | 3 | 0 |

## Error taxonomy

- UNSUPPORTED_GRAMMAR_COMPLETENESS_UNVERIFIED: 4545
- EXPLICIT_MISSING_OR_CROSS_RECORD_DEFINITION: 100
- ENVELOPE_OR_ADDITIONAL_CLAUSES_REQUIRE_REVIEW: 815
- SOURCE_CODE_REQUIRES_REPRODUCTION: 151

现金工具、成交时序、价格复权、指标计算和缺失数据政策未写明时保持空值，AST 不等于可执行。

## Factor ontology v2

source factor records=1578；canonical economic concepts=13；mapped=204；unresolved=1374。
conflicts=1；alias groups=0；variant review groups=8；SAME_AS merges=0。

使用已冻结分类、JKP 原始 theme 列及来源摘要；经济分类 RELATED_TO 不代表公式等价。新增 Size/Growth/Low Risk。

| Source | Records | Mapped | Unresolved |
|---|---:|---:|---:|
| aqr | 6 | 6 | 0 |
| french | 9 | 8 | 1 |
| gtja191 | 191 | 0 | 191 |
| jkp | 422 | 105 | 317 |
| osap | 331 | 10 | 321 |
| qlib | 518 | 75 | 443 |
| wq101 | 101 | 0 | 101 |

source-scoped variant groups 为待审聚类，未合并跨源定义。Alpha101/191 复合公式保留未解决；12-1、6-1、残差、行业、盈余动量不能合并为同一实现。许可不随本体映射变化。

## Strategy Factor Coverage Report

5813 Source Records → 28 Concepts → 41 Templates → 5813 Variants。

202 条策略有规则关联，221 条 USES_FACTOR links；全部 RULE_LINK_ONLY，EMPIRICALLY_TESTED=0。

RSI 阈值/资产变更共享 RSI 参数因子；显式多指标分别保存引用。link_id、strategy_id、factor_id、factor_variant_id、reason、AST evidence、confidence、source、parser_version、validation_status 均有存储。来源未验证实现仍 REVIEW_REQUIRED；未分类记录不臆造 Concept。

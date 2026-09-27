# V3 Rule Archetype 汇总（公开精简版）

分析顺序：先对冻结 grok-rule-v3.1 的全部 5611 条 REVIEW 做路由，再写新语法。原始全量报告的时间戳/快照哈希保留于本机。以下关键词路由不证明策略机制，原文、URL 和逐条代表示例不公开。

| 类型 | REVIEW 数 | 比例 | 所需字段 | 难度 |
|---|---:|---:|---|---|
| other_or_ambiguous | 821 | 14.63% | 待逐条确认完整定义 | HIGH |
| cross_sectional_rank_top_n | 721 | 12.85% | PIT池、打分公式、排序方向、N、权重、换仓 | HIGH |
| fundamental_value_quality | 483 | 8.61% | PIT财务数据、发布日期、股票池、打分和换仓 | HIGH |
| rsi | 434 | 7.73% | 周期、平滑方法、阈值、比较/穿越、资产、退出 | LOW |
| price_vs_ma | 376 | 6.70% | 价格字段、MA类型和窗口、比较、分配、退出 | LOW |
| volatility_filter | 298 | 5.31% | 波动字段/公式、窗口、阈值、仓位与退出 | MEDIUM |
| threshold_allocation | 269 | 4.79% | 完整条件、双方分配、资产与再平衡 | MEDIUM |
| event_calendar | 244 | 4.35% | 事件时点、日历、持仓窗口、退出和资产 | HIGH |
| source_factor_portfolio | 184 | 3.28% | 完整信号公式、PIT股票池、分组和持仓规则 | HIGH |
| trend_volatility_combination | 170 | 3.03% | 趋势条件、波动公式、AND/OR、仓位、退出 | MEDIUM |
| macd | 153 | 2.73% | 快慢信号周期、柱/线定义、条件、退出 | MEDIUM |
| source_code_fragment | 151 | 2.69% | 完整源码、依赖版本、配置、回测语义 | HIGH |
| momentum_other | 147 | 2.62% | 收益定义、窗口、门槛、资产、退出 | MEDIUM |
| ema_crossover | 137 | 2.44% | 快慢窗口、穿越方向、仓位、反向/平仓 | LOW |
| breakout_donchian_rolling_extreme | 131 | 2.33% | 回看窗口、排除当前栏、比较、入场和退出 | MEDIUM |
| options_volatility | 100 | 1.78% | 期权链、到期日、行权价、希腊值、报价与成交 | HIGH |
| sma_crossover | 90 | 1.60% | 快慢窗口、穿越方向、仓位、反向/平仓 | LOW |
| bollinger | 79 | 1.41% | 窗口、标准差定义、倍数、上下轨、退出 | MEDIUM |
| funding_carry | 75 | 1.34% | 合约、两腿价格、资金费率、展期和保证金 | HIGH |
| volatility_targeting | 72 | 1.28% | 波动估计、目标、杠杆上下界、再平衡 | MEDIUM |
| etf_rotation | 68 | 1.21% | 完整资产池、相对排名、阈值、分配、平手政策 | MEDIUM |
| oscillator | 65 | 1.16% | 指标完整参数、阈值、比较、资产与退出 | MEDIUM |
| pairs_spread_zscore | 61 | 1.09% | 配对池、形成期、价差定义、入场退出、两腿权重 | HIGH |
| roc | 56 | 1.00% | 窗口、收益口径、阈值、分配、退出 | LOW |
| absolute_momentum | 47 | 0.84% | 资产、收益口径、窗口、阈值、避险资产 | LOW |
| mean_reversion | 44 | 0.78% | 锚点、偏离度量、阈值、持仓和退出 | MEDIUM |
| risk_on_off | 39 | 0.70% | 状态信号、阈值、风险与避险分配、退出 | MEDIUM |
| relative_momentum | 34 | 0.61% | 比较资产、窗口、收益口径、平手政策 | LOW |
| dual_momentum | 31 | 0.55% | 绝对与相对动量窗口、资产池、现金门槛、换仓 | MEDIUM |
| machine_learning | 27 | 0.48% | 特征、标签、训练窗口、泄漏控制、模型及执行 | HIGH |

## 规则覆盖对照

原始 5813 条的 parsed 从 202 到 260；三条显式手工转录单列。没有为达到 1000 放松未知参数、资产、公式或尾部条件。

| 类型 | 全部 | Before | After |
|---|---:|---:|---:|
| other_or_ambiguous | 821 | 0 | 0 |
| cross_sectional_rank_top_n | 721 | 0 | 1 |
| fundamental_value_quality | 483 | 0 | 0 |
| rsi | 442 | 8 | 11 |
| price_vs_ma | 382 | 6 | 23 |
| volatility_filter | 304 | 6 | 6 |
| threshold_allocation | 284 | 15 | 25 |
| event_calendar | 245 | 1 | 2 |
| source_factor_portfolio | 184 | 0 | 0 |
| trend_volatility_combination | 171 | 1 | 2 |
| macd | 154 | 1 | 1 |
| momentum_other | 153 | 6 | 8 |
| source_code_fragment | 151 | 0 | 0 |
| ema_crossover | 137 | 0 | 0 |
| breakout_donchian_rolling_extreme | 132 | 1 | 14 |
| oscillator | 101 | 36 | 37 |
| options_volatility | 100 | 0 | 0 |
| relative_momentum | 100 | 66 | 66 |
| sma_crossover | 90 | 0 | 5 |
| volatility_targeting | 83 | 11 | 11 |
| absolute_momentum | 82 | 35 | 35 |
| bollinger | 79 | 0 | 2 |
| funding_carry | 75 | 0 | 0 |
| etf_rotation | 68 | 0 | 0 |
| pairs_spread_zscore | 65 | 4 | 4 |
| roc | 58 | 2 | 4 |
| mean_reversion | 45 | 1 | 1 |
| risk_on_off | 39 | 0 | 0 |
| dual_momentum | 33 | 2 | 2 |
| machine_learning | 27 | 0 | 0 |
| zscore | 4 | 0 | 0 |

大类中仍有大量摘要缺少 PIT 资产池、完整退出、执行时点、公式或数据。MACD 缺信号周期、模糊突破回看、未知多腿构造不会由名字补齐。已有相对/双/绝对动量、排名、ETF 切换、配对、ROC、MA 等完整 grammar 保留；新增算式和复合条件都要求全串匹配。

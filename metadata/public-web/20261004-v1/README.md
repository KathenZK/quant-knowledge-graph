# 2026-10-04：首批公开来源实现

本批新增 **5 条策略实现元数据、4 条因子实现元数据**，实际获取并固定 **22 份代码、
许可及归属文件**。其中 4 条策略与原 CSV 的上游文件路径相同，属于补充版本和规则证据；
QSTrader 及 4 个 Zipline 因子是本次核对目录中未发现同源文件的实现。**不宣称新增 9 个经济概念**。

| 类型 | 实现与记录 | 范围 | 与原目录的关系 |
|---|---|---|---|
| 策略 | [MovingAverageCrossAlgorithm](strategies/MovingAverageCrossAlgorithm.json) | SPY，日线 EMA15/30 | M2904 同源路径补证 |
| 策略 | [EmaCrossFuturesFrontMonthAlgorithm](strategies/EmaCrossFuturesFrontMonthAlgorithm.json) | 黄金近月期货，分钟 EMA100/300 | M2914 同源路径补证 |
| 策略 | [EquityRsiOverboughtOversoldAlgorithm](strategies/EquityRsiOverboughtOversoldAlgorithm.json) | QQQ，小时 RSI14 多空 | M2598 同源路径补证 |
| 策略 | [EquityDonchianBreakoutTurtleAlgorithm](strategies/EquityDonchianBreakoutTurtleAlgorithm.json) | 五只股票 ETF，日线通道与开盘调仓 | M2599 同源路径补证 |
| 策略 | [sixty_forty.py](strategies/sixty_forty.py.json) | SPY/AGG，月末股债配置 | 新实现来源；60/40 概念已有近邻 |
| 因子 | [AnnualizedVolatility](factors/AnnualizedVolatility.json) | 简单收益的年化历史波动 | 与低波选股条目只做概念比较 |
| 因子 | [AverageDollarVolume](factors/AverageDollarVolume.json) | 收盘价乘成交量的窗口统计 | 与流动性条目只做概念比较 |
| 因子 | [Aroon](factors/Aroon.json) | 窗口高低点位置，两个输出 | 与同名指标参数不能直接画等号 |
| 因子 | [TrueRange](factors/TrueRange.json) | 包含跳空距离的单期波幅 | 不是 ATR 或完整交易策略 |

[索引和记录哈希](index.json) · [来源锁与采集时间](source-lock.json) · [准入状态和旧 ID 关联](manifest.json)

核对的是源码行为，不是名称或注释承诺。例如：

- SPY 示例检查两条 EMA 的当前大小，并未要求前一根发生交叉；订阅默认频率和实际成交时点仍需核验。
- QQQ 的 RSI 使用互斥分支：持多时 RSI 高于 70，本事件先清仓；持空时 RSI 低于 30，可在第一分支直接转多。
- 唐奇安模板将 ATR 用于仓位计算，未实现独立 ATR 止损；黄金期货的 `set_holdings(0.1)` 不能直接写成 10% 保证金。
- QSTrader 先预留 1% 现金再按 60/40 取整数股；调度尝试使用 `BME` 和固定 21:00 UTC；日期字符串拼接兼容性、交易所节假日与夏令时尚未核验。
- Zipline 的成交金额统计按全部行数作分母；Aroon 按 `W-1` 归一化；TrueRange 未做 ATR 平滑。数值库边界行为尚未执行验证。

三个来源组织、四个仓库的固定版本为：

| 上游 | 固定版本 | 代码许可 |
|---|---|---|
| [QuantConnect/Lean](https://github.com/QuantConnect/Lean/tree/705b9551be1aaa821c7f77896a7eb8fcd07b92ee) | `705b9551be1aaa821c7f77896a7eb8fcd07b92ee` | Apache-2.0 |
| [QuantConnect/Documentation](https://github.com/QuantConnect/Documentation/tree/fc50f126f5c47748e0667b898c9af4c7583da5e3) | `fc50f126f5c47748e0667b898c9af4c7583da5e3` | Apache-2.0 |
| [mhallsmoore/qstrader](https://github.com/mhallsmoore/qstrader/tree/4c59e1584e83fcc2be644b820f827c0dd1b45c02) | `4c59e1584e83fcc2be644b820f827c0dd1b45c02` | MIT |
| [quantopian/zipline](https://github.com/quantopian/zipline/tree/014f1fc339dc8b7671d29be2d85ce57d3daec343) | `014f1fc339dc8b7671d29be2d85ce57d3daec343` | Apache-2.0 |

保留 QuantConnect、Michael Halls-Moore/QSTrader、Quantopian/Zipline 及相应贡献者归属；
锁文件保存每份许可、归属文件的原件哈希。本批公开内容为自行编写的中文事实摘要，不包含来源全文或行情。
代码再分发时仍需履行各自许可义务；这些许可不扩张至原始论文或市场数据。

全部记录的计算执行状态为 `NOT_EXECUTED`、经济有效性为 `NOT_TESTED`、
整体商业状态为 `REVIEW_REQUIRED`，`lab=null`。回测 **0**，原生 curated 晋级 **0**。
旧 ID 关联保存原行哈希、匹配依据、角色、置信度和来源，不声明版本等价或收益驱动。
源路径比较覆盖 6,971 条公开 CSV 记录；它不证明全库语义去重已完成。

离线检查（不下载或执行上游代码）：

```bash
uv run python -m quantgraph.graph.metadata_pilot --metadata metadata/public-web/20261004-v1
uv run pytest -q tests/test_public_web_metadata.py tests/test_metadata_corpus.py tests/test_metadata_pilot.py tests/test_public.py
```

原始代码仅作为来源快照保存在私有 raw 路径；后续研究与回测按 Graph → quant-research-lab 流转。

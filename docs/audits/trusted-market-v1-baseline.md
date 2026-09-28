# 可信行情首条闭环：重新测量的基线

核验日期：2026-09-28。主目录的未提交工作没有纳入本分支。研究仓库改名由另一个任务负责。

## Git 与测试

- QuantGraph main：`f2beb91`；公开环境 120 passed / 24 skipped；补齐本机私有输入和校验清单后 143 passed / 1 skipped。唯一未执行项需显式提供原始 GrokBot archive，最终验收补跑。
- Research Lab main：`cef6207`。补齐 ML extras 并用全新 main 导出排除工作树缓存干扰后，848 passed / 98 skipped。
- 既有 V4 依赖：PR #9/#10 未合并；本分支从 main 建立，快进纳入既有提交 `8431293`、`4c02229`，没有合并 GitHub PR。V4 全量测试 900 passed / 98 skipped。

## 私有追加日志实测

| 项目 | 数量 |
|---|---:|
| GrokBot 原始记录 | 5813 |
| 显式改编研究记录 | 3 |
| strict parsed | 263 |
| Strategy Concepts | 35 |
| Templates | 75 |
| Factor links | 296 |
| SourceEvidence 已审记录 | 6 |
| V4 RightsEvidence / ExecutionContract / DerivedDataRequirement 完整记录 | 3 / 3 / 3 |
| VERIFIED Dataset / TRUSTED Dataset | 0 / 0 |
| ELIGIBLE / Formal Real-Market Backtest | 0 / 0 |
| ResearchEvidence 日志（含旧工程演示） | 1 |

使用 `scripts/report_evidence_v4.py` 对当前 journal 快照重算，未照抄旧报告。完整机器基线及候选快照留在被 Git 排除的 `reports/trusted-market-v1/`。

## 候选选择冻结

三个高优先候选都为 90 分，仅 `DATA_AVAILABILITY_UNCONFIRMED`：

| 顺序 | 原生 ID | 机制 / 周期 | 处理原则 |
|---|---|---|---|
| 1 | EV3-M0234-BTC-EUR | PRICE_SMA / 1d | 先完成唯一首条闭环；固定 SMA50、网格 40/50/60 |
| 2 | EV3-M0233-BTC-EUR | ZSCORE_REVERSION / 1d | 首条闭环成功后才考虑 |
| 3 | EV3-M0256-BTC-EUR | EMA_CROSSOVER / 4h | 首条闭环成功后才考虑 |

首条完整请求保留 `[2022-07-01, 2026-09-27)` UTC，IS 为 2023–2024，OOS 为 2025–截止日。市场来源变更需要新冻结合同，不更改旧 raw、旧合同或旧 ID。不根据收益选择 provider 或参数。

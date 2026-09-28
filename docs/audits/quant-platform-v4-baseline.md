# Quant Platform V4 开发前基线

核验日期：2026-09-28。事实来源为已同步的 GitHub main；先完成下列检查，再开发 V4。

| 项目 | QuantGraph | Strategy Lab |
|---|---|---|
| main commit | `dd983d7a2b4025a796fc7130934bf56b7f26973a` | `cef6207c502bb05e22b438321a8f29c7703ba8ba` |
| 上轮 PR | [#4](https://github.com/KathenZK/quant-knowledge-graph/pull/4)，OPEN、未合并 | [#9](https://github.com/KathenZK/quant-strategy-lab/pull/9)，OPEN、未合并 |
| main CI | [SUCCESS](https://github.com/KathenZK/quant-knowledge-graph/actions/runs/36311956129) | [SUCCESS](https://github.com/KathenZK/quant-strategy-lab/actions/runs/36311968727) |
| 上轮 PR CI | SUCCESS | SUCCESS |
| 工作区 | tracked clean | 独立目录 tracked clean；原主目录 160 项已有改动完整保留 |
| 完整测试 | 103 passed / 1 skipped | 848 passed / 98 skipped |
| lint | PASS | PASS |
| typecheck | 未配置，不记为已运行 | 未配置，不记为已运行 |
| 其他 | verify-public、build-public、validate-release PASS，包含 rights/profile 隔离 | governance preflight PASS；完整测试包含 knowledge integration |

Lab 主分支正在用户有改动的主目录使用，故不在那里切换或更新文件。对干净独立目录 fetch 最新 main，并以 main 的纯文件归档执行基线，等价核验提交内容。新分支均从以上 main 创建，未合并任何 PR。

首次本地运行的失败也保留：Graph 102 passed / 1 failed / 1 skipped，原因是私有 curated 的 V3 source-lock 与 main 不同；依照 main 离线重建后，第二次 validate-release 的确定性重建通过。Lab 初次 841 passed / 5 failed / 100 skipped，原因是未跟踪 V3 artifacts/cache 残留造成无 README 的家族目录；纯 main 归档复核通过。没有改测试来隐藏失败。原始日志位于本机私有 `platform-v4-work/audit/`，不发布日志或私有语料。

## main 实际漏斗

以 `datasets/ingestion/platform-v2.sqlite` 当前投影统计，parser=`grok-rule-v3.1`，投影完整 5813/5813。

| 指标 | 数量 |
|---|---:|
| observations / semantic records / revision rows | 5813 / 5813 / 5813 |
| additional revisions / duplicate observations | 0 / 0 |
| strict parsed / rule review | 202 / 5611 |
| concepts / templates / variants | 28 / 41 / 5813 |
| strategy-factor links / linked strategies | 221 / 202 |
| reviewed SourceEvidence / RightsEvidence / ExecutionContract | 0 / 0 / 0 |
| verified DataRequirement / verified datasets | 0 / 0 |
| ELIGIBLE / REVIEW_REQUIRED | 0 / 5813 |
| CONDITIONALLY_ELIGIBLE / BLOCKED | 0 / 0（V2 未细分此状态，按全部证据待审归类） |
| formal real-market backtests | 0 |
| journal pipeline diagnostics | 1（明确 synthetic，非正式证据） |
| main 可执行的真实市场 diagnostic | 0 |

未合并 V3 单独保留：5816 条记录、263 严格解析、75 模板、6 条来源审核、3 个完整执行约定、0 个 ELIGIBLE、0 次正式回测、2 个私有真实行情诊断家族。不得把这些当成 main 已有功能。V4 将明确包含这两个未合并提交作为实现依赖，保留原 PR，不自行合并。

当前 main 阻断：来源未核验 5813、许可待审 5813、规则不完整 5611、执行约定待补 5813、数据可得性未确认 5813。准备程度不代表盈利概率。

本轮范围仅 Graph 与 Lab；不读取或运行 quant-runner 代码，不读取私钥，不创建任何实盘授权。

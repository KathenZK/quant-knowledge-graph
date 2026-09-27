# 三仓库 main 审计（2026-09-26）

本报告基于本轮实际从 GitHub 获取的 main，不以历史 PR 对话作为状态依据。三个仓库保持独立，唯一数据流为 QuantGraph → Lab → Runner；本轮未运行交易进程或改变任何运行实例。

| 仓库 | main commit | 本地基线结果 |
|---|---|---|
| quant-knowledge-graph | 45c1989 | lint、verify-public、build-public 通过；私有 release 离线重建后 80 passed / 1 skipped，validate-release PASS |
| quant-strategy-lab | c69708e | 治理与数据契约 preflight、lint 通过；完整测试 824 passed / 98 skipped |
| quant-runner | 789c051 | fmt、clippy、cargo check、四项治理检查通过；切换已安装的 Command Line Tools 后 264 tests passed |

测试数量包括本地集成测试；Python 仓库无独立静态 typecheck 配置。Lab 的 98 个跳过项是未保留在该 main 隔离工作区的本地数据或历史制品测试，不代表这些研究已通过验证。Runner 测试为 254 单元测试及 10 集成测试，未启动交易程序。

## 基线阻断与环境修复

- Runner cargo audit 发现 rustls 0.23.43 的 RUSTSEC-2026-0285，修复版本为 >=0.23.45；另有 chacha20 0.10.1 yanked 警告。供应链门禁尚未通过。
- QuantGraph 首次测试为 78 passed / 2 failed / 1 skipped，原因是私有 release 的代码摘要落后于 main。离线重建后重新 validate-release PASS；不是删除或忽略失败测试。
- Runner 默认 Xcode 工具链链接时报许可未接受。使用机器上已安装的 /Library/Developer/CommandLineTools 完整测试通过；未代用户接受许可。
- 命令行旧代理 7897 不可用，使用系统已配置的 7890 代理完成同步；未改全局网络设置。

## 工作区保护

Lab 原本地 main 超前旧远端 13 个提交，且有大量未提交研究。Runner 有未提交 AGENTS/规则修改。本轮保留它们，在独立 Git worktree 从最新 origin/main 建立功能分支。QuantGraph 干净 main 已快进至远端 main 后建立功能分支。不 reset、stash 或覆盖原研究现场。

## 版本与跨仓库契约

- QuantGraph package 0.2.0；ingestion SQLite user_version 1；parser grok-rule-v2.0；私有 research/evidence schema 1.0。
- Lab package 0.1.0；candidate summary、ResearchEvidence、StrategyArtifact schema 1.0。候选输入只接受 TRIAGE_ONLY；执行/许可/来源/数据门禁由研究层独立检查。
- Runner package 0.1.0；当前 main 尚未接入 QuantGraph promotion artifact。现有 runner-owned lock 仍是运行授权来源。
- ResearchEvidence 为 SUBMITTED_NOT_INDEPENDENTLY_VERIFIED，既有证据不能产生 live approval。
- commercial/public profile 与私有 corpus 隔离；未知许可保持 REVIEW_REQUIRED。

## main 功能审计与计划

QuantGraph main 已合并原始语料导入和 ingestion/research API；Lab main 已合并 candidate/evidence bridge 与初版统计诊断；Runner main 尚无该新契约。

P0 阻断：record_hash 包含 collected_at；parser 升级后 API 可静默少数据。先修这两项并完成迁移、原始字节保护和集成测试，再继续 P1–P9。

P1–P9 保持用户路线：增量统计 → 严格 parser / RuleArchetype → 稳定策略与因子本体 → readiness/diversity 候选 → 独立 DSR/PBO 基准 → 合格候选真实回测与证据回写 → 仅离线 Runner 晋级契约。若许可、规则或数据门禁阻断，不以合成回测或参数枚举补数量。

本机完整日志与私有数据不加入公开 Git；公开报告只记录已审核的聚合结果。最终 CI/PR 状态在工程交付报告中更新，本节不是最终验收。

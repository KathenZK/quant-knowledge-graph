# Quant Platform Evidence Phase 基线（2026-09-27）

本轮核对 GitHub：上轮 QuantGraph #3 与 Lab #8 均已合并。最新 main 分别为 dd983d7a2b4025a796fc7130934bf56b7f26973a、cef6207c502bb05e22b438321a8f29c7703ba8ba。功能分支从这些提交建立；Lab 使用已有干净隔离工作区，原 main 上未提交研究原样保留。本轮不修改或运行 Runner。

基线完整检查：QuantGraph lint、verify-public、build-public、rights verify、validate-release PASS，私有 archive 完整测试104 passed；Lab preflight、lint和完整测试848 passed / 98 skipped。Python仓库无单独静态typecheck。跳过项依赖未携带的本地研究数据/制品；不解释为研究通过。

统计来自最新main代码实际读取私有journal和冻结因子快照，未把上轮聊天数字直接作为事实。工作副本使用SQLite backup创建，原journal不改写。

| 指标 | 重新计算值 |
|---|---:|
| observations / semantic records | 5813 / 5813 |
| revision rows（含首版）/ additional revisions / duplicates | 5813 / 0 / 0 |
| strict parsed / rule review | 202 / 5611 |
| 全部准入 review | 5813 |
| concepts / templates / variants | 28 / 41 / 5813 |
| factor-linked strategies / links | 202 / 221 |
| factor source records / canonical concepts | 1578 / 13 |
| factor mapped / unresolved | 204 / 1374 |
| eligible research variants / templates | 0 / 0 |
| real research runs | 0 |
| 既有PIPELINE_DIAGNOSTIC证据 | 1，不计真实研究 |

P0已复核：semantic hash仍含backtestability；ingestion投影为所有模板静态填入参数/资产轴；Lab缺projection_status时默认READY，candidate_gate缺失可走旧兼容路径。先修这三项并测迁移/反例。解析前先对完整review队列生成30类模式分析。来源支持范围、策略许可、行情许可、执行假设和数据完整性必须分别举证；可下载不等于允许使用。

# 增量导入、重投影与研究审核

原始提交字节保留在私有 journal，raw_payload_hash 记录单条规范化审计 payload，wire_payload_hash 记录请求原始字节。semantic_record_hash 只覆盖来源 URL、名称、作者、发布日期、原规则/市场/参数、source_metadata 等语义字段。collected_at、请求/导入时间和运行批次元数据不改变策略 revision；未知扩展仍可审计但不能授予许可或改变准入。

数据库迁移为增量 user_version=3，不改历史 revisions、submissions、observations 或旧 projection。第二天再次采集形成 duplicate observation；规则变化产生 revision。幂等重放相同 batch 不重复写观察。parser grok-rule-v3.1 为每个 revision 保留独立版本投影，不覆盖 v2.0。

```bash
quantgraph projection-status --db datasets/ingestion/platform-v2.sqlite
quantgraph reproject --db datasets/ingestion/platform-v2.sqlite
quantgraph ingest-stats --db datasets/ingestion/platform-v2.sqlite
```

状态为 READY/STALE/REPROJECTING/FAILED。候选读取在非 READY 状态返回 503 和完整状态，禁止静默导出部分 universe。重投影提交运行标记，再原子追加 projection；失败或进程中断后保持阻断，显式重试。相同 parser version 的结果漂移会报错，修改解释规则必须升级版本。

研究审核通过本机管理入口 `quantgraph review-record --db ... decision.json`，不暴露给采集 API。审核必须携带当前 semantic hash、审核人、分别对应来源/研究许可/执行/数据的证据 URI 和 SHA256。证据确认 PRIVATE_RESEARCH 并不产生商业使用许可。规则变更自动使旧审核失效；重新采集但语义未变保留审核。仓库没有替本轮语料生成任何批准。

ResearchCandidateGate 的评分只表示证据完备程度。规则解析、数据资产完整、指标语义、闭合 bar、成本和执行契约均须满足；未定义现金工具继续阻断。API 任意字段 research_allowed/live_ready 不能替代本机审核。未经归因/消融核验的因子关系维持 RULE_LINK_ONLY；提交收益结果不能将其升级。

已有 research:write 提交不可变 ResearchEvidence；新增 research:read 查询 `/v1/research/evidence/{variant_id}`。提交的结果始终为 SUBMITTED_NOT_INDEPENDENTLY_VERIFIED，不触发晋级。完整私有数据、审核材料和本机验收日志不公开。聚合诊断用 `uv run python scripts/report_platform_v2.py --db ...` 重算；1000 parser 和候选/回测目标未达到时必须报告真实缺口。

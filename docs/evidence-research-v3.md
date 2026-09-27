# Evidence Enrichment 与 Research Gate V3

V3 把来源支持、许可、规则、执行、数据、去重和本体映射分开判断。分数只表示研究准备度，不代表盈利概率。正式真实市场研究仍须独立研究验证；本轮没有实盘接口或自动晋级。

## 兼容与审计

- 数据库 schema 4 是增量迁移。旧 raw、wire bytes、observation 和 revision 哈希保留；新语义哈希放在 `revision_semantics_v2`，observation 记录实际使用的哈希版本。
- 新语义身份包含来源 URL、名称、作者、发布日期、市场、规则及明确来源元数据/参数；采集时间、backtestability、bot/parser/rights/readiness assessment 不构成策略修订。
- 新观察仍有完整 raw hash。只改 assessment 增加 observation，不增加 strategy revision。
- 同一模板在全部当前 sibling 范围内计算真实差异，再分页；未知值不作为资产/市场变体证据。可能差异放 `possible_variation_axes`。
- 本轮需求称 Parser V3，但既有正式解析器已经是 `grok-rule-v3.1`，新实现版本固定为 `grok-rule-v4.0`；旧投影不覆写。只做全串解析，未消费的条件/退出条款一律 REVIEW。
- `QG-DSL/1` 是完整显式研究规则的输入格式。它不能自动证明来源或权限；手工派生记录单列，不计入原 GrokBot 语法覆盖增长。

## 正式证据

[models/evidence.py](../models/evidence.py) 与 [JSON schemas](../models/schemas/) 定义：

- SourceEvidence：固定 URL/commit/文件哈希、来源等级、支持与不支持的规则组件、真实代码作者；指标作者不会自动变成派生策略作者。
- RightsEvidence：SOURCE_TEXT、IMPLEMENTATION_CODE、MARKET_DATA 三个范围独立；research/commercial/redistribution/derivative/attribution 分别记录。个人非商业授权不能放行商业内部用途，研究许可不改变 commercial export。
- ExecutionContract：全部执行项带 SOURCE_DEFINED / RESEARCH_ASSUMPTION / UNKNOWN；明确研究约定不伪装成来源原文。
- DataRequirement：来源、真实场所、symbol、频率、字段、版本、时区、日历、范围及字节哈希。真实价格不等于数据质量通过。
- EvidenceEnrichment：绑定当前 semantic hash 的本机行政审核，append-only；规则变更后旧审核不会继续放行。

## Gate 与队列

只有 `research-candidate-gate-v3` 的 `ELIGIBLE` 可进入自动研究。唯一缺口为尚未接受的研究假设时为 CONDITIONALLY_ELIGIBLE；明确禁用、来源冲突、质量失败为 BLOCKED；其他缺口为 REVIEW_REQUIRED。旧 V2 review 需重新审核，不能继承准入。

分值：source 20、rights 20、rule 20、execution 15、data 15、dedup 5、ontology 5。每项有独立阻断原因。模板与概念评估选择明确代表，保留合格 sibling 数量，不声称整个组已通过。队列优先准备度高、只缺 1–2 项、少重复的模板；重复/参数枚举有单列扣分。Lab 先按概念覆盖，再按六个维度的多样性选择，最多 20 个，不能把参数变体当独立发现。

## API 与操作

- `GET /v1/research/assessments`：概念/模板评估、审核队列、阻断汇总。
- `GET /v1/research/candidates`：显式 READY 投影及 V3 gate；Lab 缺字段、过期或未知版本时拒绝。
- `POST /v1/research/evidence`：旧 schema 1.0 仅保留兼容；真实市场结果必须 schema 2.0 + REAL_MARKET_BACKTEST，含 IS/OOS、成本、稳健性、DSR/PBO、全部参数试验、数据/代码/config/候选快照哈希。
- 正式写入在同一事务检查当前 ELIGIBLE、概念/模板和整个 admitted DataRequirement；不可变 run ID；无自动晋级。
- `GET /v1/research/evidence/{variant_id}` 与 SDK `research_evidence()` 回读完整证据。
- 标注 synthetic/fixture 的结果或不完整 IS/OOS 不可通过真实研究入口。该检查不替代独立验证，已提交证据仍为 SUBMITTED_NOT_INDEPENDENTLY_VERIFIED。

本机 `quantgraph reproject --db <private-journal>` 更新新版本投影；`scripts/enrich_research_v3.py` 只消费显式审核 manifest 并核验 artifact 字节哈希；`scripts/report_evidence_v3.py` 导出私有报告。先运行 `scripts/analyze_rule_archetypes_v3.py` 对冻结旧投影做覆盖分析，再增加语法。本机完整原文、审核 manifest、候选快照及行情结果不加入公开 Git。

本轮实测结果见 [统一验收报告](audits/quant-platform-evidence-research-v3.md)。

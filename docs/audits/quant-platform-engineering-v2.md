# 三仓库工程交付报告 v2（2026-09-27）

工程门禁与离线契约已落地；研究目标仍有明确缺口，不能宣布整个 roadmap 完成。三个仓库保持独立，固定单向数据流 QuantGraph → Lab → Runner。本轮没有合并 PR、启动交易实例、变更 live 配置或批准真实策略。

基线依据：[最新 main 审计](quant-platform-audit-2026-09-26.md)；当前数据依据：[数据质量报告](quant-platform-data-quality-v2.md)。Lab 与 Runner 在最新远端 main 的独立 worktree 上开发，原本地未提交研究和规则修改保留。

## 交付范围与剩余工作

| 阶段 | 本轮结果 | 未完成与边界 |
|---|---|---|
| P0 | semantic/raw/wire hashes 分离；增量迁移；原表保留；投影状态、原子重建与 503 阻断 | 后续 parser 变更必须继续显式重投影 |
| P1 | 幂等、历史、scope/限流/体积限制延续；ingest-stats 与审核后统计 | 完整私有数据不进入公开 Git |
| P2 | 25 类+residual review 路由；完整匹配语法与反例；170→202 | 1000 未达到；4545 条尚不支持的语法不能都归咎于源数据，继续按类开发 |
| P3 | 稳定 concept/template/variant/implementation 与关系；参数、资产变体同族 | 未分类来源不补造 Concept；实现引用未做源码复现 |
| P4 | 202 条策略、221 条规则因子关联，保存证据/版本/角色/置信度 | 0 个收益驱动或归因验证；全部 RULE_LINK_ONLY |
| P5 | 13 个经济概念；1578 条来源中 204 映射；源码分类及摘要可追溯 | 1374 未解决，1 组冲突；没有跨源公式等价合并 |
| P6 | hash-bound 本机审核、readiness 和 family diversity；最低与目标缺口分开 | 0 合格，最低缺100、目标缺200；缺许可/来源/执行/数据证据 |
| P7 | 全量候选筛选真实运行，阻断结果落档 | 0 真实回测/OOS；不存在可提交的前20项收益摘要 |
| P7.1 | DSR 原文3例+SciPy冻结向量+vectorbt对拍；PBO原文+独立冻结CSCV逐split、tie测试 | 未运行外部 R PBO 包；数学通过不能替代真实研究和门禁 |
| P8 | 保留不可变 research:write，新增按variant读取证据；回写不能升级因子归因或批准 | 没有真实研究结果可回写；历史 PIPELINE_DIAGNOSTIC 不计真实研究 |
| P9 | Lab/Runner v2 Schema及字节样例一致；内容摘要、配置、人审声明、环境离线校验 | 不接入 run/live；批准字段非签名验证，Runner自有授权仍必需 |

研究启动必须先补齐已有门槛，不能借用其他研究家族的成本/数据/入场规则，更不能用参数变体或合成基准填满20个策略。

## 本地最终验证

| 仓库 | 验证结果 |
|---|---|
| QuantGraph | lint、verify-public、build-public、完整 pytest 104 passed / 0 skipped、私有 rights verify、validate-release PASS（确定性离线重建） |
| Lab | 完整 preflight、lint、pytest 848 passed / 98 skipped；独立拒绝空费用、负费用、非闭合bar，不能被上游合格标记覆盖 |
| Runner | fmt、clippy -D warnings、cargo check --all-targets、267 tests、四项治理检查、cargo audit 全部成功 |

Graph 显式提供本机原始 archive 后，私有语料回归测试也通过；公开 CI 不携带私有数据，因此会跳过相应检查。另使用真实认证 HTTP 从 Lab 读完5813条并复算候选。Lab 跳过项依赖隔离 main 未携带的本地研究数据/历史制品，不能声称这些研究已验收。Python 仓库没有单独静态 typecheck 配置。

Runner 原基线 rustls RUSTSEC-2026-0285 已通过0.23.45解决；chacha20 0.10.1 yanked 已更新至兼容的0.10.2。首次 push 的 audit 无漏洞但因缺少 checks:write 无法发布状态；仅给 audit job 和对应复用调用补足该权限。Graph 测试还有 Starlette/httpx 弃用警告。GitHub CI 必须以各 PR 最新提交的实际状态为准，本表不是远端 CI 结果。

## 版本与复现

- ingestion user_version=3；semantic hash strategy-record-semantics-v1；parser grok-rule-v3.1；strategy ontology v2；factor taxonomy v2；candidate gate v2。
- Lab candidate schema2.0；ResearchEvidence schema1.0（提交不等于独立验证）；冻结统计内核v1保留，v2单独新增。
- StrategyArtifact schema2.0，Lab/Runner SHA256 `7d41067c52d8404c20237e2c6046221ffd4939fe23d04fadc28931718a01f726`。contracts/fixtures-v2 是不可交易样例，不算真实制品。
- DSR固定基准：Lab=0.7196294320273795，vectorbt=0.7196294320273796，绝对误差1.11e-16。PBO固定8×3矩阵为2/3，全部6个split逐值对照。
- QuantGraph 操作与迁移见 [ingestion-v2](../ingestion-v2.md)，聚合报告由 scripts/report_platform_v2.py 生成；对应私有数据库、原文、标准输出与验收日志均保留在本机忽略目录。

后续继续原 roadmap：先补 P2 语法与 P5/P6 证据，重新获取合格候选，冻结真实试验后再做 P7/P8；只在真实研究和人审均完成后考虑 Runner 实际接入。

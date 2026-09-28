# Factor research contracts v1

本目录是网页与 Lab 共用契约的唯一正式来源。JSON Schema 从
`models/factor_study.py` 生成，测试逐字段比对生成结果。Lab 读取本目录并冻结
schema SHA256，不复制一套 schema。现有 Strategy / ResearchEvidence API 不变。

## Research request

`research-request.schema.json` 的 `schema_version=research-request/v1`。
`entity_refs` 保留原 ID、实体类型和定义版本。`status` 只能是 `DRAFT`；它只是
研究意向，不是准入、运行授权、持仓执行或晋级。Lab 必须另行校验并冻结计划。
`STRATEGY_REPLICATION` 是兼容网页的意向类型，本次因子引擎明确拒绝执行它。

## Factor study result

`factor-study-result.schema.json` 的 `schema_version=factor-study-result/v1`。
一个 run 对应一个定义/参数变体，可含多个预先冻结的标签期限。完整实验清单由
Lab 导出为 definition × horizon，分段统计不能冒充独立因子。

`definition_revision` 是规范化身份、来源版本/快照、公式 AST 摘要、参数和依赖字段
的 SHA256，算法见 `quantgraph.factor_study.definition_identity`。它不替换旧 ID
或来源原生 ID。`implementation.version` 与计算源码全文件 SHA256 分开保存。

研究类型的要求分别是：

| 类型 | 要求/本次边界 |
|---|---|
| COMPUTATION_CHECK | 定义与实现核对；合成数据仅用于此层 |
| FACTOR_DIAGNOSTIC | 定义、两层语义检验、合法可信数据、标签、时序、冻结计划；无须止损/仓位 |
| PORTFOLIO_BACKTEST | 须走现有完整执行、成本、持仓准入；v1 因子提交器拒绝 |
| CONFIRMATORY_VALIDATION | 须由任务 C 提供相应登记、holdout 和统计证据；v1 因子提交器拒绝 |

Pydantic 的业务验证还检查成功研究的真实数据声明、VERIFIED 映射的三个必需测试，
以及合法研究类型；服务端不能仅用静态 schema 代替准入。提交人提供的 hash 和
INTERNAL_CHECKED 不是服务端独立重算，也不是经济有效性认证。

## 权限与查询

定义、代码、行情、衍生结果分别有 internal_use / public_display / evidence。
每个 artifact 也有独立权限。未知授权为 REVIEW_REQUIRED；v1 不提供公开结果许可
审批，拒绝生产者直接提交公开行情/衍生结果或公开 artifact。

私有 journal 与所有 curated/public release 分离，默认不启用 HTTP 写入。
设置 `QUANTGRAPH_FACTOR_STUDY_DB` 后，以现有 `QUANTGRAPH_API_KEYS` 配置
`research:read` / `research:write` scope。这不是任何交易凭据。

- POST `/v1/research/factor-studies`：幂等提交；同 run_id 改内容返回冲突。
- GET `/v1/research/factor-studies/{entity_id}`：认证后的私有查询；支持 concept 或 variant ID。
- GET `/v1/factors/{factor_id}/studies`：商业/公开详情入口；v1 始终为空，不泄露私有数量。
- SDK `FactorDB.factor_studies(..., journal=..., profile="research")`：显式本机私有读取。
- SDK `QuantGraphClient.submit_factor_study` / `factor_studies`：对应 HTTP 接口。

失败和无效结果也保留；写回不更改原定义的 semantic_status/backtest_ready，
不生成策略 BacktestResult，也不触发晋级。后续版本可扩展审批能力，不能通过
解释 v1 的 DRAFT 或 EXPLORATORY_RETROSPECTIVE 获得授权。

`fixtures/` 仅有公开来源身份和人工构造的失败计算样例，没有真实市场数据、
个人路径、凭据、统计结果。兼容性测试覆盖额外字段拒绝、旧接口不变和私有隔离。

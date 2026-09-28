# OHLCV 核心契约与独立 Dataset Trust

此次增加显式的 `TRUSTED_OHLCV_CORE_V1` 数据 profile 和 `MarketDatasetTrustAssessment`。
旧 `LAB_OHLCV_V1` 的规则不变；没有信任审核的旧记录不会自动升级。新 profile 将可选原生
质量列与 AST/ExecutionContract 推导的策略必需列分开，但仍需要完整 OHLCV、来源与身份、
UTC 日历、全历史覆盖、原始字节、收盘证据和许可。

九项维度独立取 PASS / FAIL / UNKNOWN；任何 FAIL 只能 REJECTED，存在 UNKNOWN 只能
DIAGNOSTIC_ONLY，全部 PASS 才能 TRUSTED。数据摘要、合同摘要、权利摘要、原始页摘要、
审核代码摘要和审核时间均保存。新 profile 没有 assessment 即产生 DATASET_TRUST_UNVERIFIED，
不因 coverage 为 VERIFIED 而放行。

Evidence review 绑定完整合同、manifest、dataset 和独立 rights 原文证据。写回仍走已有
追加式 review/evidence 接口；不写 status=ELIGIBLE。Gate 计算结果、BacktestResult 和
ResearchEvidence 以本机私有日志为准，不能从单元测试成功推断实际研究已成功。

发布 schema 的入口为 [generate_v4_schemas.py](../../scripts/generate_v4_schemas.py)。Lab 使用
此处导出的 schema，自己重新检查原始页、重建 normalized bytes 和许可，Graph 负责记录
定义与关联、审查和导出；没有反向研究依赖或执行接口。完整行情及衍生研究不进入公开 Git。

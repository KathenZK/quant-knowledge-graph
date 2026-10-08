# 归一化覆盖层 v1 架构说明

## 文件结构

| 文件 | 说明 |
|------|------|
| `normalized-records.jsonl` | 主覆盖记录（每行一个 M-ID），**哈希钉扎**到源记录 |
| `families.json` | 家族映射（临时键） |
| `variants.json` | 变体链接（参数/窗口/ticker 变体） |
| `schema.json` | JSON Schema |
| `manifest.json` | 文件清单及 SHA-256 |
| `discrepancies.json` | 差异报告 |
| `summary.json` | 统计摘要 |

## 覆盖记录架构

```json
{
  "id": "M####",
  "pinned_to": {
    "row_sha256": "...",
    "rule_sha256": "...",
    "csv_row_ordinal": 123
  },
  "family_id": "F####",
  "provisional_family_key": "loose::author::mechanism",
  "implementation_id": "...",
  "variant_id": "...",
  "parent_id": "M####",
  "origin_type": "original_rule | indicator_definition | adaptation | hypothesis | secondary_citation | unknown",
  "source_rule": "源规则文本（原文实际陈述）",
  "implementation_rule": "实现规则文本（回测执行）",
  "attribution": {
    "universe": "原文明确 | 编纂者决定 | 尚未知",
    "thresholds": "...",
    "lookbacks": "...",
    "frequency": "...",
    "entry": "...",
    "exit": "...",
    "sizing": "...",
    "cash_asset": "...",
    "stop": "...",
    "displacement": "...",
    "fill_timing": "..."
  },
  "dates": {
    "indicator_origin_year": "1978",
    "source_published_at": "2013-02-28",
    "source_updated_at": null,
    "implementation_first_documented_at": null,
    "retrieved_at": null,
    "date_precision": "year | month | day | unknown"
  },
  "statuses": {
    "source_verified": "verified | partial | unverified",
    "spec_status": "complete | partial | incomplete | ambiguous | unknown",
    "data_status": "ready | needs_PIT_panel | data_insufficient | pending | unknown",
    "implementation_status": "runnable | blocked | unknown",
    "result_status": "executed | proxy | not_executed | unknown",
    "access_status": "ok | access_blocked | access_pending | unknown"
  },
  "disposition": "keep_as_source_strategy | merge_as_family_variant | keep_as_labeled_adaptation | await_evidence | ...",
  "confidence": "high | heuristic",
  "lab_coverage": {
    "lab_commit": "...",
    "run_id": "...",
    "variant_id": "...",
    "fidelity_class": "ADAPTED | FAITHFUL | ...",
    "group": "batch###"
  },
  "coverage_note": "2026-09-30: not_executed; refreshed from Lab registry 2026-10-08",
  "backtest_coverage_status_20260930": "faithful_source_reproduction | labeled_proxy_or_adaptation_trial | not_executed",
  "known_issues": [
    {
      "family": "RSI14_threshold_SPY_BIL",
      "disposition": "merge_as_threshold_variant",
      "verified_at": "2026-09-30T12:35:00+08:00"
    }
  ]
}
```

## 关键约束

### 哈希钉扎

每个覆盖条目通过 `pinned_to.row_sha256` 和 `pinned_to.rule_sha256` 绑定到 `metadata/corpus-checkpoints/grokbot-6973-20261003/` 的源记录。若源记录修订，覆盖条目的哈希不匹配将被验证器检出，须人工审核后更新覆盖。

### 类型分类

**覆盖层不含类型分类**（strategy/factor/reference/unclassified）。类型由 `metadata/classifications/20261004-v1/` 提供，覆盖层只追加：
- 家族映射
- 源规则 vs 实现规则拆分
- 归因旗标（原文明确/编纂者决定/尚未知）
- origin_type
- 日期修正
- 拆分状态
- 已知问题修正
- 回测覆盖（从 Lab 注册表刷新）

### 来源核验

`source_verified=partial` 的行表示有 URL/线索但未完成原文核验。200 行样本队列（`source-verification-sample-v1.csv`）**仅设计未实际抓取**，不能当作已核验。

### 回测覆盖刷新

- 2026-09-30 矩阵：`faithful_source_reproduction=0`, `labeled_proxy_or_adaptation_trial=1691`, `not_executed=5282`。
- 2026-10-08 从 `metadata/lab-display-sources.json` 刷新：27 个 Lab 运行记录（全部标记 `ADAPTED`）。
- 历史「仍有效/已衰减」标签为描述性，不代表最新回测结果。

## 置信度

- `high`：`known-issues-verification-v1` 清单内的 15 个强制补丁（RSI 家族、M5851/M5853/M5854/M5855、M5015、M5659/M5848/M5651 等）。
- `heuristic`：其余行继承 `row-audit-v1.csv` 的家族/处置/状态；chartschool+SPY/BIL 宽旗标亦为启发式（但 origin 强制 adaptation）。

## 枚举值完整列表

见 `00-schema.md`（上游提供）。

## 差异与未解决项

见 `discrepancies.json` 和 `BLOCKERS-v0.md`（上游提供）。

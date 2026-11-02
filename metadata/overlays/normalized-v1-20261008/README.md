# 归一化覆盖层 v1

**版本**: normalized-v1-20261008  
**生成时间**: 2026-10-08 03:40 UTC  
**来源**: 2026-09-30 离线审计工作（`quant-master-draft.csv` md5 `f3c60e61bedfd0434c339cb4c16a7e4a`）

## 概述

本覆盖层将 2026-09-30 完成的目录修复工作（归一化、家族映射、源规则拆分、日期修正、已知问题修复）以**附加层**形式加入仓库，**不改写**既有源记录文件（`metadata/corpus-checkpoints/grokbot-6973-20261003/`）。

每个覆盖条目通过 `row_sha256` 和 `rule_sha256` **哈希钉扎**到源记录当前版本；若源记录改变，验证器将检出哈希不匹配，须人工审核后更新覆盖。

## 边界（重要）

- **不含类型分类**：strategy/factor/reference/unclassified 由 `metadata/classifications/20261004-v1/` 提供（main 权威），覆盖层不重复或覆盖。
- **不修改 M 编号**：保留全部既有 `M####` id 及 46 个历史编号缺口。
- **不修改源记录文件**：覆盖层为独立追加层，不原地改写 `metadata/corpus-checkpoints/` 或 `metadata/index.json`。
- **不公开私有资料**：M2535/M2709 若触发现有敏感字段检查，其原值不进入此公开覆盖层。

## 内容类型

### 1. 家族与变体映射（6,265 家族 + 695 变体）

- `family_id`：稳定家族编号（当前使用临时 `provisional_family_key`）
- `parent_id`：对 `merge_as_family_variant` 处置，指向家族内最早条目
- `what_changed`：参数/窗口/ticker 变体说明（`threshold:50` / `param_or_ticker_or_window_variant`）

### 2. 源规则 vs 实现规则拆分

- `source_rule`：原始来源实际陈述的规则（指标公式、论文组合等）
- `implementation_rule`：回测执行规则（可能叠加 SPY/BIL、频率、成交）
- 当两者不同时，`origin_type` 通常为 `adaptation`，处置为 `keep_as_labeled_adaptation`

### 3. 归因旗标（per-field）

每个字段标注为：`原文明确` / `编纂者决定` / `尚未知`

字段：`universe`, `thresholds`, `lookbacks`, `frequency`, `entry`, `exit`, `sizing`, `cash_asset`, `stop`, `displacement`, `fill_timing`

### 4. origin_type

- `original_rule` — 源规则本身即可交易/可研究
- `indicator_definition` — 仅指标定义，无完整组合规则
- `adaptation` — 在指标/论文核上由编纂者叠加入场资产、现金腿等
- `hypothesis` — 明确标注为假设/未验证构想
- `secondary_citation` — 二手转引，需追一级来源
- `unknown` — 尚未判定

### 5. 日期修正

- `indicator_origin_year`：指标起源年（如 Wilder RSI 1978）— **非**适配日期
- `source_published_at`：来源发表日
- `date_precision`：`year` / `month` / `day` / `unknown`

master 列「提出日期」常混淆指标起源与实现日期 — 审计须拆分这些。**绝不编造**；使用 `未知`。

### 6. 拆分状态

- `source_verified`: `verified` / `partial` / `unverified`
- `spec_status`: `complete` / `partial` / `incomplete` / `ambiguous` / `unknown`
- `data_status`: `ready` / `needs_PIT_panel` / `data_insufficient` / `pending` / `unknown`
- `implementation_status`: `runnable` / `blocked` / `unknown`
- `result_status`: `executed` / `proxy` / `not_executed` / `unknown`
- `access_status`: `ok` / `access_blocked` / `access_pending` / `unknown`

### 7. 已知问题修正（15 个 high 置信度）

清单：M5603（RSI 家族父节点）+ M5673/M5681/M5760/M5822/M5823/M5850（阈值变体）、M5851（ADX 不完整）、M5853（Antonacci PDBC 时序）、M5015（非完整 GEM）、M5854（Ichimoku Span B 位移）、M5659/M5848（门控适配）、M5651（Force Index 缺 22EMA）、M5855（KVO 来源标签修正，access_blocked）。

每个已知问题条目附带证据摘录（`known-issues-verification-v1.json` / `.md`）。

### 8. 回测覆盖（从 Lab 注册表刷新）

- **2026-09-30 矩阵**：
  - `faithful_source_reproduction`: 0
  - `labeled_proxy_or_adaptation_trial`: 1,691（历史，弱溯源，无日 NAV/交易日志，BIL 腿常 `cash_zero`，单向 5bps）
  - `not_executed`: 5,282
  
- **2026-10-08 刷新**（从 `metadata/lab-display-sources.json`）：
  - 27 个 Lab 运行记录
  - 全部标记 `fidelity_class=ADAPTED`
  - 未发现新的 `faithful_source_reproduction`
  - 所有 27 个在 09-30 矩阵中已标记为某种状态（非 not_executed）
  
- **历史「仍有效/已衰减」标签**：为描述性，不代表最新回测结果或准入决定。

### 9. 来源核验队列

- `source-verification-full-queue-v1.csv`（3,128 行）：人工核验队列
- `source-verification-access-pending-v1.csv`（1,186 行）：需访问权限的子集
- `source-verification-sample-v1.csv`（200 行）：**仅设计，未实际抓取** — 不能当作已核验

`source_verified=partial` 表示有 URL/线索但未完成原文核验。

## 统计

| 项目 | 计数 |
|------|-----:|
| 覆盖条目 | 6,773 |
| 家族 | 6,265 |
| 变体 | 695 |
| Lab 覆盖刷新 | 27 |
| 已知问题标注 | 15 |
| 缺失哈希（未在 corpus 找到）| 200 |

缺失哈希的前 10 个：M2501–M2510（可能在隔离检查点或后续批次）。

## 置信度

- **high**：15 个已知问题强制补丁（附证据摘录）
- **heuristic**：其余行继承 `row-audit-v1.csv` 的家族/处置/状态；chartschool+SPY/BIL 宽旗标亦为启发式（但 origin 强制 adaptation）

## 文件清单

| 文件 | 大小 | 说明 |
|------|-----:|------|
| `normalized-records.jsonl` | 15M | 主覆盖记录（6,773 行） |
| `families.json` | 2.6M | 家族映射（6,265 个） |
| `variants.json` | 410K | 变体链接（695 个） |
| `schema.md` | — | 架构说明（本文件） |
| `manifest.json` | — | 文件清单及 SHA-256 |
| `discrepancies.json` | 2.8K | 差异报告 |
| `summary.json` | 617 | 统计摘要 |
| `build_overlay.py` | 12K | 可复跑构建脚本 |

## 使用

1. **读取覆盖条目**：

```python
import json
from pathlib import Path

overlay_dir = Path("metadata/overlays/normalized-v1-20261008")
records = []
with open(overlay_dir / "normalized-records.jsonl") as f:
    for line in f:
        records.append(json.loads(line))
```

2. **验证哈希钉扎**：

```bash
python3 metadata/overlays/normalized-v1-20261008/validate_overlay.py
```

3. **统一目录集成**（待实现）：

```python
# 伪代码
catalog_entry = load_source_record(mid)
overlay_entry = load_overlay(mid)
if overlay_entry and overlay_entry["pinned_to"]["row_sha256"] == catalog_entry["provenance"]["row_sha256"]:
    catalog_entry.update(overlay_entry)  # 叠加覆盖字段
```

## 已知限制

见 `discrepancies.json` 和上游 `BLOCKERS-v0.md`：

- 200 个 M-ID 未在 corpus 找到哈希（可能在隔离检查点或后续批次）
- `source_rule` vs `implementation_rule` 拆分：已知问题与 chartschool 旗标行已拆分；其余暂两者相同（待人工）
- 家族 ID 当前使用临时 `provisional_family_key`；待固化
- 来源核验：大部分为 `partial`（有 URL 但未完整人工核验）

## 下一步

1. 消化上游 `BLOCKERS-v0.md` 人工项
2. 将 `family_id` 从 provisional 固化；补充引用 `evidence_snippet` / `content_hash`
3. 对仍 `source_rule == implementation_rule` 的行做拆分抽检
4. 挂接回测时只读本归一化覆盖，不改活主库 id

## 许可与溯源

本覆盖层依据 2026-09-30 离线审计工作生成（输入 md5 `f3c60e61bedfd0434c339cb4c16a7e4a`）。

源记录保留在 `metadata/corpus-checkpoints/grokbot-6973-20261003/`，遵循原仓库许可。覆盖层为**判断与修正的附加层**，可由仓库所有者审核后合并或弃用。

---

**生成者**: build_overlay.py  
**验证**: validate_overlay.py  
**测试**: tests/test_overlay_normalized_v1.py

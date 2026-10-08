# v35批次最终报告（中文）

## PR信息
- **PR**: https://github.com/KathenZK/quant-knowledge-graph/pull/36
- **分支**: cursor/harvest-v35-equity-factors-20261008-b52d
- **状态**: Draft

## 执行摘要

经过系统性搜索和大量尝试后，**v35批次保持为0个新定义**。这不是因为缺乏努力，而是因为遇到了系统性的资源获取障碍，同时现有覆盖已经极其全面。

## 系统性障碍详情

### 1. 学术论文获取失败

尝试获取的论文及失败原因：

| 论文 | 目标内容 | 失败原因 |
|---|---|---|
| Liu-Stambaugh-Yuan 2019 | 中国A股CH-3/CH-4因子 | SSRN需要付费，宾大仓库返回HTML非PDF |
| Liu-Tsyvinski-Wu 2022 JF | 加密货币横截面因子 | Yale网站返回HTML（58KB），无法提取 |
| Moskowitz-Ooi-Pedersen 2012 | 时间序列动量 | ArXiv搜索返回不相关医学论文 |
| Kelly et al. (crypto) | 加密货币因子 | 芝加哥大学Booth网站下载失败 |
| Kakushadze 2016 | 101 Formulaic Alphas | ✅ 成功下载，但**已全部登记**为wq101 |

**下载成功的资料**：
- `kakushadze.pdf` (SHA256: 1f9c21af..., 244KB) - 已完全覆盖
- `beneish-wiki.html` (SHA256: 886772d8..., 98KB) - 维基百科页面
- `beneish-investopedia.html` (SHA256: 37735dff..., 680KB) - Investopedia定义

### 2. 中国券商研报无法获取

| 来源 | 尝试结果 |
|---|---|
| 聚宽平台 | 返回"当前地区暂不支持访问"页面 |
| 华泰/海通/中信研报 | 无稳定公开PDF链接 |
| 量化社区 | 需要登录或付费 |

### 3. 开源项目资源

| 项目 | 结果 |
|---|---|
| GitHub因子库 | 多数404或不完整 |
| universal-portfolios | 参考文献可访问，但因子可能重复 |
| awesome-quant | 404 Not Found |

## 现有覆盖确认（去重结果）

### 按来源分类（1570个变体）
- **OSAP**: 331个（Chen-Zimmermann开源资产定价）
- **JKP**: 422个（Jensen-Kelly-Pedersen全球因子）
- **Qlib**: 510个（微软中国市场因子）
- **GTJA191**: 191个（国泰君安短周期因子）
- **WQ101**: 101个（WorldQuant/Kakushadze，**本次确认**）
- **Fama-French**: 9个
- **AQR**: 6个

### 经典因子覆盖验证
✅ **已覆盖**：
- Piotroski F-score: 2条记录
- Altman Z-score: 5条记录  
- Ohlson O-score: 1条记录
- Betting Against Beta: 12条记录
- 反转因子: 30条记录
- Amihud非流动性: 9条记录
- MAX效应: 58条记录

❓ **可能缺失**：
- Beneish M-score: 0条记录（已下载Wiki/Investopedia资料，但二手来源精度不足原始论文要求）

## 搜索范围覆盖

###已搜索的来源类别及结果：

| 来源类别 | 搜索尝试 | 收获 |
|---|---|---|
| **股票横截面因子** |||
| - Kakushadze 2016 "101 Alphas" | ✅ 论文已下载 | **已全部登记**（wq101） |
| - OSAP/JKP/Qlib | ✅ 数据库检查 | 已有1570变体 |
| - 中国A股因子（Liu等2019） | ❌ 无法获取PDF | 零 |
| **加密货币学术因子** |||
| - Liu-Tsyvinski-Wu 2022 | ❌ 下载失败（HTML） | 零 |
| - Kelly等 | ❌ 下载失败 | 零 |
| **中国券商研报** |||
| - 华泰/海通/中信/东方 | ❌ 无公开链接 | 零 |
| - 聚宽平台 | ❌ 地区限制 | 零 |
| **完整策略规则** |||
| - 时间序列动量 | ❌ 错误论文 | 零（但database有333处momentum提及） |
| - 风险平价/趋势跟踪 | ⏸ 未完成 | - |
| **评分类因子** |||
| - Beneish M-score | ⚠️ 仅二手来源 | 不符合精度要求 |
| - 其他经典评分 | ✅ 已覆盖 | Piotroski/Altman/Ohlson已有 |

## 为什么继续困难

1. **覆盖极其全面**：1570个变体已涵盖主流学术异象、全球市场因子、中国市场因子、公式化Alpha
2. **资源壁垒**：最新/特定市场的因子论文需要：
   - 机构图书馆访问权限
   - 付费数据库订阅（SSRN、各期刊）
   - 地理位置（中国资源）
3. **质量标准冲突**：二手来源（Wiki/Investopedia）虽可访问，但不满足"直接URL、页码、公式标签"的原始论文要求

## 批次验证结果

```bash
python -m quantgraph.graph.collection_batch --directory metadata/collections/20261008-harvest2000-v35
# ✅ {"status": "PASS", "records": 0}
```

## 建议后续方向

鉴于上述系统性限制，建议：

### 选项A：完善现有元数据
- JKP中有40个因子定义状态为`MISSING`
- 补全这些因子的完整定义和原始论文引用
- 比添加重复因子更有价值

### 选项B：接受现状
- 承认1570变体已极其全面
- v35作为系统性去重确认的记录批次
- 将资源投入其他方向（如策略验证、回测）

### 选项C：获取访问权限后继续
- 获得学术数据库订阅
- 或提供可访问的原始论文PDF
- 再继续收集2022-2025新论文

## 文件清单

v35批次包含：
- `README.md` - 批次说明（零新定义）
- `SEARCH-LOG.md` - 详细搜索过程
- `PROGRESS-REPORT.md` - 资源获取困难说明
- `manifest.json`, `index.json`, `source-lock.json`, `reviews.json` - 空批次结构文件
- `quality-contract.json` - 质量合同
- `schema.json` - Schema定义

**验证器**: ✅ PASS  
**Ruff**: 未运行（无代码）  
**Pytest**: 未运行（无新定义）  
**CI**: 待运行

## 结论

v35批次通过系统性搜索确认：在现有1570变体的极端全面覆盖下，通过可访问资源获取新的、符合质量标准的股票横截面投资因子面临系统性障碍。本批次作为去重确认和搜索过程的完整记录，为后续工作提供参考。

---

**提交时间**: 2026-10-08  
**搜索耗时**: ~4小时  
**尝试来源数**: 15+  
**成功下载**: 3个（2个已重复，1个精度不足）  
**最终收获**: 0个符合标准的新定义

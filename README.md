# Quant Knowledge Graph

面向量化研究的因子、策略、论文、公式、实现和研究结果关系库。

本公开仓库包含可运行的采集/标准化程序、Python SDK、只读 API，以及 **508 个通过定义准入的 Qlib 信号变体**。每条记录保留原始公式、AST、来源版本、文件摘要和许可信息。它们归入 43 个特征族，不代表 508 个独立盈利因子。

> 完整本地研究目录曾接入 1,578 条来源记录、形成 1,085 个 curated 定义变体。该混合许可研究包没有上传到此公开仓库；这里发布的是经过筛选的 Qlib 数据及其关联实体。

## 快速运行

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。

```sh
git clone https://github.com/KathenZK/quant-knowledge-graph.git
cd quant-knowledge-graph
uv sync --frozen --extra test
uv run quantgraph verify-public
uv run quantgraph build-public
uv run pytest tests/test_formula.py tests/test_public.py -q
uv run quantgraph serve
```

API 默认监听 `127.0.0.1:8000`，交互文档位于 `/docs`。无须市场数据账号，公开批次可以完全离线重建。它不执行上游交易代码，不连接券商或交易所。

## Python SDK

```python
from quantgraph import FactorDB

db = FactorDB()  # 干净 clone 自动读取公开 Qlib 发布；stats 标明 public_qlib
rows = db.search_factors(category="momentum", asset_class="equity")
variant = rows[0]
factor = db.get_factor(variant["canonical_factor_id"])
related = db.find_related_factors(variant["factor_variant_id"])
print(db.stats())
print(db.find_strategies(factor="momentum"))  # 策略层尚未导入，返回 []
```

在其他项目使用时安装本包，并设置 `QUANTGRAPH_ROOT` 指向克隆目录，或传入 `FactorDB(root="/path/to/quant-knowledge-graph")`。wheel 不捆绑数据。

## 已交付

| 内容 | 公开批次 |
|---|---:|
| Qlib Alpha158/Alpha360 原始输入列 | 518 |
| 完全相同表达式的重复来源记录 | 8 |
| 排除的常数/近常数特征 | 2 |
| curated 信号变体 / 唯一公式 | 508 |
| 当前特征族 | 43 |
| Strategy / BacktestResult 实际记录 | 0 / 0 |

覆盖原始文件与 SHA-256、带方言的公式解析、名称和别名、概念与参数变体区分、Paper/Author/Implementation 等独立实体，以及带证据的关系。SQLite、JSONL、CSV、Parquet 均可使用。

`backtest_ready` 全部为 false。定义准入不代表计算语义已认证，更不代表收益或 OOS 验证通过。当前是股票特征来源，不会自动把记录标记为适用于 crypto。

## 三项目分工

```text
quant-knowledge-graph → quant-research-lab → quant-runner
    知识与来源             研究与验证           交易与风控
```

知识库不包含既有研究项目的研究引擎，也没有向 runner 发布策略的接口。策略层和 BacktestResult 已有独立 schema，后续仅接入标准化描述、来源及研究结果引用。

## 仓库结构

```text
collectors/          # OSAP / JKP / French / AQR / WorldQuant / GTJA / Qlib 等采集器
models/              # 独立实体、JSON Schema、稳定 ID 注册表
normalize/           # aliases / formula / dedup / taxonomy / rights
graph/               # 本体、关系、存储、准入和校验
api/                 # 只读 HTTP API
sdk/quantgraph/      # Python SDK 和 CLI
datasets/
  raw/source_lock.json    # 来源 URL、版本及摘要索引
  raw/sources/qlib/       # 公开分发的固定版本 MIT 源文件
  public/CURRENT         # 公开发布版本指针
  public/releases/       # 可校验的 Qlib 数据与关系图
tests/ docs/ reports/
```

本地的 `datasets/normalized`、`datasets/curated` 和其他来源原文由 `.gitignore` 排除，不能直接提交。`build-public` 只读取三个锁定的 Qlib 文件，写新的公开发布并原子切换 CURRENT，不修改完整研究发布。

## 数据许可与代码许可

Qlib 源文件和衍生表达式保留微软 MIT 声明；这不包含底层市场数据授权。公开包附有 `THIRD_PARTY_LICENSE.txt` 和修改说明。

项目公开可见不代表整库拥有统一的开放许可。自写采集组件的原 MIT 声明继续保留；其余新代码尚未选定统一开源许可证，见 [LICENSE](LICENSE)。受限来源的许可不会因为标准化而改变。

OSAP、JKP、French、AQR、WorldQuant/GTJA 的采集逻辑和来源索引可供审阅；它们的原始材料及衍生研究数据未随本公开发布分发。不能用社区代码的许可证推定原论文、研报或数据的再分发权。

## 文档

- [公开发布范围与验证](reports/PUBLIC_RELEASE.md)
- [实体、关系与 ID](docs/DATA_MODEL.md)
- [公式 DSL](docs/FORMULA_DSL.md)
- [来源许可](docs/RIGHTS.md)
- [研究项目接入契约](docs/RESEARCH_INTEGRATION.md)
- [长期维护](docs/MAINTENANCE.md)

下一阶段优先补齐论文和公式语义、审核重复候选，再接入策略描述与研究结果引用。

# Quant Knowledge Graph

面向量化研究的因子、策略、论文、公式、实现和研究结果关系库。

本公开仓库包含可运行的采集/标准化程序、Python SDK、只读 API，以及 **508 个通过定义准入的 Qlib 信号变体**。每条记录保留原始公式、AST、来源版本、文件摘要和许可信息。它们归入 43 个特征族，不代表 508 个独立盈利因子。

> 完整本地研究目录曾接入 1,578 条来源记录、形成 1,085 个 curated 定义变体。该混合许可研究包没有上传到此公开仓库；这里发布的是经过筛选的 Qlib 数据及其关联实体。

## 原目录阅读入口

原目录前两批 200 条完整 11 字段已整理到 [171 条策略候选](metadata/strategies/README.md)、
[12 条因子候选](metadata/factors/README.md) 与 [17 条待分类](metadata/unclassified/README.md)。
它们是 CONTENT_INFERRED / UNVERIFIED 的目录阅读层，不增加下文 Qlib 已审定义或回测数量。
[完整计数、固定来源与分类证据](metadata/README.md)。

## 个人知识工作台

个人模式使用显式选择的本机完整 Catalog，提供策略/因子阅读、中文检索、方法族、关系、2–4 项比较，以及服务端持久笔记和研究清单。未解析规则和未准入公式仍可阅读；来源事实、整理解释与个人判断分开保存。它不运行研究，不连接交易执行系统，也不改变公开 API 的可见性或许可边界。

已初始化 `.artifacts/personal` 后，日常只需这一条命令；页面缺失或源码变化时自动重建，失败时停止启动：

```sh
bash scripts/start_personal.sh
```

访问 `http://127.0.0.1:8791`。没有完整 Catalog 时页面明确提示初始化，绝不静默退回 Qlib-only。[首次初始化、增量更新、备份恢复与验收](docs/product/personal-workbench.md)。

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

## 本地知识工作台

需要 Node.js 22+；`bash web/start.sh` 会优先启动本机已导入的持久化 Catalog，
提供真实策略/因子目录、2–4 项比较、可点击关系图、研究清单与鉴权管理后台。
没有挂载业务语料时仍可显式运行 Qlib-only 分发场景；Git 附带的公开快照不是整个产品数据库。

完整本机配置用 `bash scripts/start_platform.sh /absolute/operator/config.json` 同时启动 API
和已登记的 Lab worker。策略、因子和演化请求复用 `research-request/v1`，在原条目读回对应结果。
业务条目默认 PUBLIC，第三方全文、代码、行情与研究数值仍按字段分别执行许可规则。
匿名访客不能修改资料或无限启动计算，DRAFT 导出不代表研究已执行。

详见[当前产品范围](docs/product/platform-delivery.md)、[启动与运维](docs/product/platform-operations.md)、
[真实数据验收与截图](docs/product/platform-acceptance.md)。

## Python SDK

公开因子研究桥接的正式契约见 [factor-study/v1](contracts/factor-study/v1/README.md)。
Lab 计算与研究完成后可写入独立私有 FactorStudy journal，并从因子详情的 studies
入口查询。DRAFT 不是运行/晋级授权；公开默认不展示私有研究结果，不改变已有定义准入。

```python
from quantgraph import FactorDB

db = FactorDB()  # 干净 clone 自动读取公开 Qlib 发布；stats 标明 public_qlib
rows = db.search_factors(category="momentum", asset_class="equity")
variant = rows[0]
factor = db.get_factor(variant["canonical_factor_id"])
related = db.find_related_factors(variant["factor_variant_id"])
print(db.stats())
print(db.find_strategies(factor="momentum"))  # 公开 Qlib 批次不含私有策略，返回 []
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

研究层仓库为 [quant-research-lab](https://github.com/KathenZK/quant-research-lab)，Python 包 `strategy_lab` 兼容保留；参见 [命名迁移](docs/REPOSITORY_NAME_MIGRATION.md)。

知识库不包含既有研究项目的研究引擎，也没有向 runner 发布策略的接口。GrokBot 策略候选和旧筛选结果通过独立私有发布接入；研究验证和实盘执行仍分别属于下游两个项目。

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

下一阶段优先审核规则语义、来源与许可，再由研究项目完成独立复现。


## GrokBot Strategy Corpus V1

GrokBot 数据按 **raw → normalized → curated** 导入。5,813 行是来源候选记录，不是 5,813 个独立策略。公开仓库不分发这批完整语料；真实导入统计见 [汇总报告](reports/grok_strategy_import_v1.md) 和 [机器可读统计](reports/grok_strategy_import_v1.json)。

```sh
uv run quantgraph import-grokbot /private/path/quant-handoff-minimal-2026-09-24.tar.gz
uv run quantgraph verify-grokbot
```

导入器保留原始压缩包字节、原生 ID、规则全文、市场原文和历史日期字段。来源支持的指标/方法与 GrokBot 生成的阈值、ETF 配置分开标注；RSI 指标定义不会被冒充为原作者发布的 ETF 切换策略。解析失败的规则保留为 REVIEW，不生成猜测的 AST。日期没有独立证据时保持为空。

策略族、模板、变体和引用关系进入独立的私有图谱；现有 `Strategy` 查询保持兼容：

```python
from pathlib import Path
from quantgraph import FactorDB

corpus = Path("datasets/curated/grokbot")
release = (corpus / "CURRENT").read_text().strip()
db = FactorDB(database=corpus / "releases" / release / "quantgraph.sqlite")
strategies = db.find_strategies()
links = db.get_strategy_factors(strategies[0]["strategy_id"])
# 所有关联均为 RULE_LINK_ONLY；信号定义不代表收益归因。
```

私有定义准入、可执行性和许可是三个独立检查。所有记录目前均需许可和执行合约复核；`PARSED` 不等于可交易，`executable` 全为 false。已有回测仅作为 `LEGACY_GROKBOT_SCREEN`，不算研究复现或有效性证明。默认公开 API 和商业导出不包含这些私有规则。详见 [ARCHITECTURE](ARCHITECTURE.md)。

新增测试使用人工构造的样例；维护者可用 `GROKBOT_TEST_ARCHIVE=/private/path/input.tar.gz uv run pytest -q` 额外验证真实 5,813 条批次。公开 CI 没有私有语料时会明确跳过这一条测试。

## 增量 GrokBot 与研究联通

[Ingestion API / Python SDK / CLI / 部署](docs/INGESTION.md) ·
[规则和本体进度](docs/ONTOLOGY_PROGRESS.md) · [实际联通验证](docs/ingestion-validation.json)。
私有原始记录只追加；公开商业接口继续使用许可安全 release。知识层不直接对接 runner。

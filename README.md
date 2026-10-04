# Quant Knowledge Graph

量化研究的知识目录，收集策略、因子、公式、实现和来源关系。统一按**策略、因子、参考资料、待分类**查找；来源、版本、许可和审核状态保留在每条记录中。

统一入口是 [知识目录说明](metadata/CATALOG.md) 与 [集合登记表](metadata/catalog.json)。它将 CSV 来源记录、分类阅读页、已审源码说明和因子定义汇集到同一张条目卡；原 ID、文件和证据版本均保留。收录不代表准入、可回测、盈利或可商用。

当前目录有 **8,797 张条目卡：6,522 策略、2,191 因子、83 参考资料、1 待分类**。同卡的来源版本不重复计数；策略包含组成部分与选股提纲，因子包含构造提纲、特征族、安慰剂、撤回记录和参数模板，各条目的成熟程度不同。使用 `catalog-stats` 查询当前值。

## 常用查询

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。在仓库根目录运行：

```sh
git clone https://github.com/KathenZK/quant-knowledge-graph.git
cd quant-knowledge-graph
uv sync --frozen --extra test
uv run quantgraph catalog-validate
uv run quantgraph catalog-stats
uv run quantgraph catalog-search --kind strategy --source QuantConnect --limit 10
uv run quantgraph catalog-search --kind factor --source qlib --frequency daily --limit 10
uv run quantgraph catalog-search --kind reference --subtype technical_demo --limit 10
uv run quantgraph catalog-search --kind unclassified --limit 10
uv run quantgraph catalog-search --status SOURCE_UNAVAILABLE --limit 10
uv run quantgraph catalog-show M2904
uv run quantgraph catalog-show 'QuantConnect/Lean:MovingAverageCrossAlgorithm'
uv run quantgraph catalog-show 'qlib:Alpha360:VWAP2'
```

`catalog-search` 支持关键词以及 `--kind`、`--source`、`--market`、`--frequency`、`--status`、`--record-kind`、`--subtype` 筛选。状态筛选匹配各状态字段；例如 `SOURCE_CODE_REVIEWED` 只说明审过对应源码，不代表运行或经济有效性通过。同名原生 ID 有歧义时必须带来源命名空间，不能任取一条。

目录详情包含原始身份、分类证据、所有证据版本、缺项和许可。没有隐式“最新版”；重复版本不重复计数，同一源码路径也不会自动被认定为同一经济策略。[字段、准确计数及添加来源的方法](metadata/CATALOG.md)。

## 只读 API

```sh
uv run quantgraph serve
curl 'http://127.0.0.1:8000/v1/knowledge/stats'
curl 'http://127.0.0.1:8000/v1/knowledge?kind=strategy&source=QuantConnect&limit=10'
curl --get 'http://127.0.0.1:8000/v1/knowledge/lookup'   --data-urlencode 'identity=QuantConnect/Lean:MovingAverageCrossAlgorithm'
```

主 API 默认监听 `127.0.0.1:8000`，交互文档位于 `/docs`。`/v1/knowledge` 检索，`/v1/knowledge/stats` 统计，`/v1/knowledge/lookup?identity=...` 按原 ID 查找；详情返回的 `entity_id` 可用于 `/v1/knowledge/{entity_id}` 与 `/v1/knowledge/{entity_id}/relations`。

目录读取仓库中登记的元数据，不执行上游代码，不运行回测，也不连接交易系统。服务首次访问时建立只读快照；接受新批次后重启服务以加载更新。本次集成完成的是仓库、CLI 和主 API，未更新活动 Site 或旧的运行中 Catalog。

## 收录和审核

[因子来源索引](metadata/factor-sources/index.json) 保存 1,570 条变体及原生编号，包含信号、安慰剂、撤回记录、参数模板和因子组合；不能全称为已准入因子。CSV 的“可回测”和历史日期是来源原标签，未经独立核实。已有阅读分类也不改变原来源记录的审核状态。

新网络批次按固定版本审源码，保存哈希、许可、规则和缺项。首批9条中，4条与旧 M 记录有明确文件定位及行摘要绑定，聚合到同卡的不同证据版本；这不证明参数、执行语义或经济概念等价。其余概念近邻只保留关系。[批次记录](metadata/public-web/README.md)。

[历史正文分类批次](metadata/classifications/20261004-v1/README.md)冻结时覆盖6,782条：6,242策略、453因子、83参考资料、4待分类，状态为`CONTENT_INFERRED / UNVERIFIED`。这一历史批次不原地改写。

随后对4条待分类记录追加[来源核查](metadata/source-reviews/20261004-v1/README.md)：M0115、M0196、M2122取得原来源关联的源码，补为策略；M0176原仓库及README返回404，保留`SOURCE_UNAVAILABLE`。当前CSV已分类6,970/6,971条。新增证据与原CSV在同卡保留，本次未执行源码或回测。

类型分类与规则完整性分开判断：已明确用于开平仓、风险控制或组合配置的记录可归为策略组件，即使还缺公式、参数或成交条件；工具流程、文档目录和订单回归测试归为参考资料。分类依据正文用途与证据片段，不凭标题中的“策略”、NLP、教程或 Demo 字样一刀切。来源原标签和原文继续保留。

目录保存来源核验、定义准入、计算语义、经济有效性和商业许可等不同状态。未审核的信息保留未知；不存在的回测不补写成结果。数据访问权限和分发范围是字段及接口边界，不作为两套知识库的主分类。

## Python 查询

```python
from quantgraph.graph.knowledge_catalog import KnowledgeCatalog

catalog = KnowledgeCatalog("/path/to/quant-knowledge-graph")
print(catalog.stats())
print(catalog.search("RSI", kind="strategy", source="QuantConnect"))
record = catalog.get("grokbot:M2904")
print(record["versions"])
print(catalog.relations(record["entity_id"]))
```

原 `FactorDB`、`search`、`stats` 及 `/v1/factors` 等接口继续服务既有定义发布，保持数据形状和许可筛选兼容；其计数不是统一知识目录总数。需要完整收录视图时使用 `catalog-*` 或 `/v1/knowledge`。

```python
from quantgraph import FactorDB

db = FactorDB(root="/path/to/quant-knowledge-graph")
rows = db.search_factors(category="momentum", asset_class="equity")
variant = rows[0]
factor = db.get_factor(variant["canonical_factor_id"])
related = db.find_related_factors(variant["factor_variant_id"])
```

在其他项目使用时安装本包，并设置 `QUANTGRAPH_ROOT` 或传入仓库路径；wheel 不捆绑数据。API 的 commercial profile 默认值保持不变。research profile 是显式参考模式，不代表取得商业内部研究许可。

## 原有界面与研究接口

已初始化工作台后可继续使用：

```sh
bash scripts/start_personal.sh
bash web/start.sh
# 已有平台运维配置时：
bash scripts/start_platform.sh /absolute/operator/config.json
```

这些命令保留原有运行时配置与 Catalog 导入约定，本次不会替换其活动数据或宣称已部署。个人工作台默认地址为 `http://127.0.0.1:8791`；Node.js 22+ 用于网页构建。参见[个人工作台](docs/product/personal-workbench.md)、[产品范围](docs/product/platform-delivery.md)、[启动与运维](docs/product/platform-operations.md)。

研究请求沿用 [factor-study/v1](contracts/factor-study/v1/README.md) 和 [研究接入契约](docs/RESEARCH_INTEGRATION.md)。Lab 结果、个人笔记和研究状态保留各自证据与权限，DRAFT 不代表研究已运行或策略已晋级。

## 三项目分工

```text
quant-knowledge-graph → quant-research-lab → quant-runner
    知识与来源             研究与验证           交易与风控
```

研究仓库为 [quant-research-lab](https://github.com/KathenZK/quant-research-lab)，Python 包 `strategy_lab` 兼容保留；参见[命名迁移](docs/REPOSITORY_NAME_MIGRATION.md)。本项目不迁入回测引擎，不添加向 runner 发布策略或下单的接口。

## 仓库结构

```text
metadata/catalog.json       # 统一知识目录的集合登记表
metadata/CATALOG.md         # 目录计数、查询和版本规则
metadata/corpus-checkpoints # 原 CSV 固定批次，保留 M 编号
metadata/classifications   # 冻结的正文类型决定、精确证据与分页阅读层
metadata/source-reviews    # 追索原来源的补证版本与不可得原因
metadata/public-web         # 固定源码版本的采集批次；存储名不决定知识分类
metadata/factor-sources     # 因子变体元数据，保留来源原生 ID
graph/knowledge_catalog.py  # 只读聚合、版本核对和检索
collectors/                 # 来源采集器
models/ normalize/ graph/   # 定义、公式、关系、准入和校验
api/ sdk/quantgraph/        # 主 API、Python SDK 和 CLI
datasets/                  # 原始来源锁及定义发布产物
tests/ docs/ reports/
```

只读聚合保留既有目录和文件。不同来源的同名记录靠命名空间区分；同一原生身份的新版本追加证据，不用覆盖旧快照。后续同类网络批次放入已登记集合，校验通过后由适配器自动发现；新的集合格式需新增适配器和测试。

## 定义发布兼容与验证

现有 Qlib 定义发布保留：518 个原始输入列，经8条重复表达式合并、2条常数/近常数排除后，形成508个准入信号变体、43个特征族。这个历史发布范围不是知识目录总量，也不表示508个独立盈利因子。其 Strategy/BacktestResult 表为0/0，不能据此推断全目录没有策略或既有研究记录。

```sh
uv run quantgraph verify-public
uv run quantgraph build-public
uv run pytest tests/test_formula.py tests/test_public.py -q
uv run quantgraph catalog-validate
```

`build-public` 保留原行为：只读取锁定的 Qlib 原文件并生成分发产物，不会把全部收录记录提升为可分发定义。完整私有数据的发布继续执行 `quantgraph validate-release`；源码提交、定义准入和经济有效性是不同验收。

## 历史导入兼容

原 GrokBot V1 的5,813行是独立历史接收批次，不能与当前 CSV 数量直接相加。原导入命令和接口仍保留：

```sh
uv run quantgraph import-grokbot /private/path/quant-handoff-minimal-2026-09-24.tar.gz
uv run quantgraph verify-grokbot
```

导入器保留来源字节、原生 ID、历史字段和版本，解析失败不补猜 AST。历史筛选结果 `LEGACY_GROKBOT_SCREEN` 不算独立复现或有效性证明。详见[历史导入报告](reports/grok_strategy_import_v1.md)、[增量接入](docs/INGESTION.md)、[架构说明](ARCHITECTURE.md)。

## 许可和文档

软件许可证不自动覆盖原论文、研报、底层行情及其他第三方材料。公开可见也不代表整库拥有统一的商用许可；不确定的商业使用保留 `REVIEW_REQUIRED`。记录的已收录、定义准入和商业许可分开判断。

完整 normalized/curated、非 Qlib 来源原文及本机验收日志仍由 `.gitignore` 隔离，不直接加入 Git。元数据保存定义、注明来源的摘录、自撰说明及定位；许可范围按字段保留，不确定的授权不因收录而视为通过。原始材料和数据的范围按来源单独审核。

- [知识目录与准确计数](metadata/CATALOG.md)
- [元数据格式与历史接收](metadata/README.md)
- [实体、关系与 ID](docs/DATA_MODEL.md)
- [公式 DSL](docs/FORMULA_DSL.md)
- [来源许可](docs/RIGHTS.md)与[项目许可](LICENSE)
- [定义分发范围与验证](reports/PUBLIC_RELEASE.md)
- [长期维护](docs/MAINTENANCE.md)

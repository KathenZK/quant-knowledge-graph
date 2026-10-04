# 知识目录

这是仓库中策略、因子和待分类资料的统一阅读与查询入口。来源、版本、许可、定义准入和研究状态分别保留；不会因为资料出现在目录中就获得执行或商业使用许可。

[集合登记表](catalog.json)指定要读取的集合，`graph/knowledge_catalog.py`校验后生成只读视图。主 API 和 CLI 使用同一视图，保留原目录、原 ID、固定快照和全部证据版本。本次没有改写活动 Site 或运行中的旧 Catalog。

## 当前数量

2026-10-04，统一目录包含 **8,546 张知识条目卡**：

| 分类 | 条目卡数 | 数量含义 |
|---|---:|---|
| 策略 | 178 | 包括内容推断的候选及已审源码说明，不都具备回测条件 |
| 因子 | 1,586 | 包括因子候选、实现和1,570条来源变体，不都通过定义准入 |
| 待分类 | 6,782 | 保留来源记录，尚无足够的明确分类决定 |
| 合计 | 8,546 | 来源证据聚合后的条目数，不是经济独立策略或因子的数量 |

用 `uv run quantgraph catalog-stats` 读取当前值；后续批次可能增加条目、版本和证据，不能仅沿用本页历史数字。

计数按下面的规则核对：

- 原 CSV 保存6,971个原ID，分70批读取；M2535、M2709仍隔离，不计入仓库目录。不能把历史5,813行导入批次或旧2,898条检查点再相加。
- 200张分类阅读页在对应 CSV 卡中追加分类证据，其中171策略候选、12因子候选、17待分类；不新增200张卡。
- M0256、M0259两份原有审阅 JSON 通过行摘要和元数据摘要绑定原 M 卡，不新增2张卡。
- 首批网络资料有5条策略实现、4条因子实现。4条明确源码定位匹配 M2904、M2914、M2598、M2599，计入原卡的不同证据版本；另5条增加5张卡。
- 因子来源集合有1,570条变体，保留原 `factor_variant_id`；其中包含此前508条 Qlib 分发成员，这508条不另相加。

因此当前总数为 `6,971 + (9 − 4) + 1,570 = 8,546`。底层有8,552个证据版本、200张分类阅读页、11份已审说明、14条来源定位或概念比较关系；这些数字不再加到条目卡总数上。来源行数另记为 CSV 6,971行、因子来源1,578行，同一变体可有多条来源。

1,570条因子变体的记录类型如下，分类时不能把安慰剂或撤回记录当作有效信号：

| 记录类型 | 数量 |
|---|---:|
| signal：信号定义或候选 | 1,415 |
| placebo：安慰剂对照 | 114 |
| withdrawn：撤回记录 | 5 |
| parameter_template：参数模板 | 21 |
| factor_portfolio：因子组合 | 15 |

这些变体中1,085条属于既有 curated 定义成员。准入只证明相应定义门槛，不能代替计算语义、经济有效性、数据许可或回测准备度审核。详细原状态以 [factor-sources/index.json](factor-sources/index.json) 和逐条记录为准。

## 查找与查看

```bash
uv run quantgraph catalog-stats
uv run quantgraph catalog-search --kind strategy --source QuantConnect --limit 10
uv run quantgraph catalog-search --kind factor --source qlib --frequency daily --limit 10
uv run quantgraph catalog-search --kind factor --record-kind placebo --limit 10
uv run quantgraph catalog-search --kind unclassified --limit 10
uv run quantgraph catalog-search 'RSI' --status SOURCE_CODE_REVIEWED
uv run quantgraph catalog-show M2904
uv run quantgraph catalog-show 'QuantConnect/Lean:MovingAverageCrossAlgorithm'
uv run quantgraph catalog-show 'quantopian/zipline:AnnualizedVolatility'
uv run quantgraph catalog-show 'qlib:Alpha360:VWAP2'
```

`catalog-search` 的位置参数为关键词，空格分隔的词需全部匹配。`--kind`只接受 `strategy`、`factor`、`unclassified`；`--source`、`--market`、`--frequency`和`--record-kind`按文本包含关系筛选，忽略大小写；`--status`须匹配完整状态值，也忽略大小写，不按子串匹配。`--limit`为1–1000，`--offset`用于分页。

市场取来源的市场或资产字段；频率取已有定义及已审说明，不从策略名称猜执行周期。方法名称可用关键词搜索，例如`EMA`或`RSI`；目前没有独立方法分类或缺项过滤参数，缺项保留在详情的`missing_information`及原证据字段中。尚未审阅不能解读为已证明缺失。

原 M 编号、源码原生类名、因子原生 ID 和稳定`entity_id`均可定位。裸 ID 同时指向多张卡时拒绝选择，应改用`来源命名空间:原生ID`。例如上面的 M2904 和`QuantConnect/Lean:MovingAverageCrossAlgorithm`返回同一张卡，但详情中的两个版本仍分别保留原始身份。

## 主 API

启动：

```bash
uv run quantgraph serve
```

| 路径 | 内容 |
|---|---|
| `GET /v1/knowledge` | 检索和分页，参数为q、kind、source、status、market、frequency、record_kind、limit、offset |
| `GET /v1/knowledge/stats` | 统一目录计数 |
| `GET /v1/knowledge/lookup?identity=...` | 用原ID或带来源的ID查看详情 |
| `GET /v1/knowledge/{entity_id}` | 用稳定目录ID查看详情 |
| `GET /v1/knowledge/{entity_id}/relations` | 查看带role、confidence、evidence、source的关系 |

来源命名空间含斜杠时使用`lookup`查询参数：

```bash
curl --get 'http://127.0.0.1:8000/v1/knowledge/lookup' \
  --data-urlencode 'identity=QuantConnect/Lean:MovingAverageCrossAlgorithm'
```

找不到身份返回404，原生ID有歧义返回409，非法筛选参数返回422。详情中的`entity_id`可继续用于关系接口。服务实例在首次访问时加载并校验一个快照，不轮询磁盘；接受新批次后重启API加载新快照。只读取仓库元数据，无需下载行情或运行上游源码。

旧`/v1/stats`、`/v1/factors`、`FactorDB`及其许可筛选继续服务原定义发布；它们的数字不是统一目录总数。用于既有站点的专用分发API也不因本次变更自动获得新目录。

## 身份、分类和版本

稳定目录ID由来源命名空间和原生身份生成，不将分类或修订号放进ID。待分类资料后续得到分类决定时不会生出一张新卡。原生身份、版本摘要和表示类型共同区分证据版本；重复的完全相同版本只保留一次。

CSV分类决定必须匹配`record_id`、`row_sha256`和`rule_sha256`。原有审阅覆盖同时核对CSV行摘要及审阅JSON摘要。网络补证只有在批次明确声明`SAME_SOURCE_PATH`、绑定精确CSV行和源文件路径后才进入同卡；不能只凭URL、名称或指标相同自动合并。

`SOURCE_EVIDENCE_AGGREGATION_NOT_EQUIVALENCE`表示同卡汇集来源证据，不声明规则参数、源码版本或经济概念等价。`POSSIBLE_CONCEPT_OVERLAP`仅建立比较关系，不合卡、不减少计数，也不冒充策略使用该因子的证据。

详情保留所有`versions`，`current_version`默认为空，策略为`NO_IMPLICIT_LATEST_SELECTION`。跨批次的新版本不隐式覆盖旧版本；同一来源身份被重新绑定到另一张卡会拒绝加载。非空分类决定相互冲突时，目录返回待分类并标记`classification_conflict`，不任取一个结论。

## 状态的读法

| 状态维度 | 示例及含义 |
|---|---|
| 分类 | `UNREVIEWED`尚未判断；`CONTENT_INFERRED`依据原摘要推断；`REVIEWED_TYPE`已审对象类型 |
| 来源核验 | `CATALOG_REPORTED_UNVERIFIED`只是采集原值；`SOURCE_CODE_REVIEWED`审查过所列源码 |
| 定义准入 | 保留因子原有`ADMITTED`及其他准入状态，不能由收录动作自动升级 |
| 计算语义 | 未运行或未完成核验时保留`NOT_VERIFIED`等限制 |
| 经济有效性 | `NOT_ESTABLISHED_BY_COLLECTION`表示此次收录没有建立经济有效性 |
| 商业许可 | 保留各来源的`ALLOWED`、`REVIEW_REQUIRED`及权利范围，不能外推到行情或论文 |

状态筛选跨上述字段匹配。同一卡同时出现未核CSV和已审源码状态是有意保留的历史证据，不表示整个卡的全部内容均已验证。逐字段的`MISSING`、研究假说与原始空白仍能在对应版本中查看。

## 添加来源与验证

`metadata/catalog.json`只登记集合，当前包含CSV来源、分类决定、原有审阅、网络批次、因子定义五种适配器。所有集合都投影为同一目录结构，存储路径或访问权限不决定用户看到的主分类。

新增同类网络批次使用`metadata/public-web/<batch>/index.json`、`manifest.json`、`source-lock.json`及`schema.json`约定。现有`reviewed_batches`适配器自动发现其子目录，无需为每批新增API或CLI路径；发布前仍须校验整个新批次。新来源格式则在登记表增加集合和适配器，并补充读取、版本和边界测试。

同一批次可能存在同名实现，文件按命名空间摘要再分目录：`strategies/<namespace-hash>/<native-id>.json`，其中`namespace-hash`是命名空间UTF-8字节的SHA-256前24位。例如`QuantConnect/Lean`对应`712c3a6dee2a42e7bcd6fa81`，路径可为`strategies/712c3a6dee2a42e7bcd6fa81/MovingAverageCrossAlgorithm.json`。索引登记完整路径，不能直接把含斜杠的命名空间作为目录名。旧批次的固定路径仍兼容。代码身份始终用命名空间加原生ID区分，不依赖文件名碰巧唯一。已有冻结文件、M编号、来源原生ID和许可记录不原地改写。

验证命令：

```bash
uv run quantgraph catalog-validate
uv run pytest -q tests/test_metadata_corpus.py tests/test_public_web_metadata.py
```

目录加载会检查集合身份、索引文件摘要、精确来源绑定、版本归属和关系引用。新批次自动发现、跨来源同名、跨批次版本和只读API需要保持测试覆盖；这一验证不代替`quantgraph validate-release`的完整定义发布门槛，也不代表网站已部署或经济验证通过。

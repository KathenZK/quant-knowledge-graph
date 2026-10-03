# 原 6973 条的完整知识记录准备（v2）

`graph.metadata_catalog` 只整理给定原 CSV 的已验字节，不下载、不回测、不写 Site/活动数据库，
也不自动提交 Git。默认输入契约为：6470637 B；SHA-256
`15cc0ecbcb23261e3cd7f2fb0851815daed59951090d9ce3e759ef224ea6f415`；
6973 个唯一原 ID，M0001–M7019，保留 46 个缺口。发现重复 ID/列、缺列、错 hash、错数量或
错缺口即拒绝，不重编号、不自动合并。CSV 行号是数据记录序号，引号内换行不算新记录。

## 每个原 ID 的保存合同

每个 ID 都有独立 `source_record`，完整保留以下 11 列的原字符串，包括空字符串、换行和
完整采集规则摘要，不截成 240 字标签：id、名称、市场、规则、作者或机构、标题、source_url、
页码或文件、可回测、别名来源、提出日期。`reported_fields` 每个字段均有原 `value` 和
`status: CATALOG_REPORTED_UNVERIFIED`。日期、可回测标签及作者归属不是新核验结果、许可
或执行授权。来源网页只保留链接，不抓取网页全文或行情。

- `metadata/source-records/<原ID>.json`：未命中敏感检查的完整来源层，仍须逐字段公开审查。
- `private-only/source-records/<原ID>.json`：命中凭证、签名链接、私有 Library 引用、本机
  路径或私密批注等检查的完整来源层。整条记录保留原值，只能私有保存，不生成公开投影。
- `inventory.json`：每个原 ID 对应完整来源记录的路径、字节数和 SHA-256，以及 CSV 行
  hash、规则 hash、分类和公开审查状态。标签仅供摘要显示；恢复以完整来源记录为准。
- `metadata/source-record.schema.json` 定义来源层；`metadata/index.json` 精确登记公开
  审查候选中的来源层与策略/因子审阅层。`private-only` 从不加入该索引。

CSV 没有权威类型列。未知类型保持 `classification.entity_type: null`、
`type_status: UNREVIEWED`，不靠关键词猜类型，不因未分类而省略知识字段。
来源层的 `entity_type: source_record` 是记录层身份，不是新增策略/因子。原 ID 计数使用
`inventory_ids` / `knowledge_records`；`metadata_records` 是层数，同 ID 的来源层与审阅层
可能各有一份，不能相加后声称新增 ID。未分类存在时 `classified_folders_complete` 为 false。

已有 M0256/M0259 审阅文件保持原字节。其他条目只有绑定原行 hash 的明确类型审阅结论才
生成 strategies/factors 投影；投影缺项仍为 MISSING。支持的三类封闭语法可生成待核的规则
释义，其他语法和因子公式待人工补证；完整原规则始终留在来源层。

## 创建新 v2 计划和首 100 条检查点

在持有已核 CSV 的执行器上 checkout 本工具提交并安装环境。路径必须在该执行器上实际
存在；输出父目录需已存在，工具强制保留至少 5 GiB。旧 v1 计划只有 hash 清单，无法恢复
完整知识字段，只作审计，v2 工具拒绝读取；必须从已核 CSV 创建新目录，不覆盖旧证据。

```bash
qg_source_csv=/absolute/path/to/quant-master-draft.csv
qg_stage_root=/absolute/path/to/private-checkpoints
uv run python -m quantgraph.graph.metadata_catalog plan \
  --csv "$qg_source_csv" --metadata metadata \
  --batch-size 100 --output "$qg_stage_root/plan-v2"
qg_plan_sha=$(python -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$qg_stage_root/plan-v2/manifest.json")
uv run python -m quantgraph.graph.metadata_catalog stage \
  --plan "$qg_stage_root/plan-v2" --plan-sha256 "$qg_plan_sha" \
  --csv "$qg_source_csv" --batch-id batch-0001 \
  --output "$qg_stage_root/batch-0001-v2"
```

默认契约不符即停止核对，不改 hash 或数量绕过。验收该原表后计划为 70 批（69×100＋73）；
未执行批次不算完成。首次 `stage --csv` 会把逐条恢复值与已核 CSV 再比较。计划已保存完整
值，后续可省略 `--csv`，仅依赖经过清单/文件/行 hash 校验的 v2 计划继续准备或重建：

```bash
uv run python -m quantgraph.graph.metadata_catalog stage \
  --plan "$qg_stage_root/plan-v2" --plan-sha256 "$qg_plan_sha" \
  --batch-id batch-0001 --output "$qg_stage_root/batch-0001-v2-rebuild"
```

重建的所有文件 hash 应一致。已有输出目录拒绝覆盖；manifest 最后写入，中断后没有
manifest 的目录不计完成。inventory 读取上限为 64 MiB，普通单文件仍限 8 MiB。

## 不依赖 CSV 的完整字段恢复验收

首批检查点自身包含恢复需要的 schema、inventory 和逐 ID 来源记录。原 CSV 与计划均
不需要出现在恢复命令中；远端备份读回后使用独立保存的清单 hash 执行同一命令：

```bash
qg_batch_sha=$(python -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$qg_stage_root/batch-0001-v2/manifest.json")
uv run python -m quantgraph.graph.metadata_catalog restore \
  --checkpoint "$qg_stage_root/batch-0001-v2" --sha256 "$qg_batch_sha" \
  --kind batch --output "$qg_stage_root/restored-first100-v2"
```

输出 `private-only/restored-records.jsonl` 每行是一条原记录的 11 列原值；
`restore-receipt.json` 给出真实恢复数量、字节数和 hash。可以逐字段重建知识文本，不能
据此声称恢复原 CSV 的列顺序、引号或 BOM 等字节格式；原 CSV 私有备份仍应单独保存。
`--kind plan` 可从完整 v2 计划恢复全部行。恢复输出始终标为私有，不向终端打印知识正文。

```bash
uv run python -m quantgraph.graph.metadata_catalog resume \
  --plan "$qg_stage_root/plan-v2" --plan-sha256 "$qg_plan_sha" \
  --checkpoint "$qg_stage_root/batch-0001-v2" "$qg_batch_sha"
```

`resume` 拒绝跨计划、错批次、重复计算、错 hash/计数，分别报告 inventory、完整知识、
分类目录和公开审查候选的覆盖率。`public_publication_complete` 与
`remote_persistence_verified` 始终为 false；本机生成或恢复不证明远端持久化成功。

## 公开审查与后续分类

自动敏感检查只作保守拦截，未命中不等于获准公开；所有原字段和分类依据仍须审查。
不要整包提交或上传 Site。协调者先私有保存完整检查点与独立清单、读回并恢复验证，再把
获准元数据按原 ID 追加到仓库并合并统一索引。敏感记录不得计作公开完整验收；原值保持
在私有备份中，不默默删字段伪造完整性。工具不读取本次新候选，不写全局进度。

人工类型决定必须提供原 ID、完整 CSV 行 hash、strategy/factor、理由和来源证据。例如
以下只是合成格式，不是真实分类：

```json
{"schema_version":"quantgraph-csv-type-decisions/v1","records":[
  {"record_id":"M0001","row_sha256":"<actual 64-hex row hash>",
   "entity_type":"strategy","reason":"人工核对买卖规则的具体理由",
   "evidence":["https://example.org/exact-source#section"]}
]}
```

用 `plan --decisions reviewed.json --decisions-sha256 <actual-file-hash>` 创建新计划，
不改冻结证据。决定不在原 CSV 内、错行 hash、与既有类型冲突时拒绝；类型迁移另行审查。
行 hash 是 UTF-8、按键排序、无多余空白的完整 11 字段 JSON 的 SHA-256。
测试可用 `--contract` 指定明确的合成契约，不能将其当生产默认输入的替代。

通用 validate 支持来源层及增长后的元数据；Lab `metadata_pilot prepare` 仍只选
M0256/M0259，不因目录增长增加回测、曲线或策略配置。

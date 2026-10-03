# 原 6973 条的可恢复元数据准备

`graph.metadata_catalog` 只整理给定原 CSV 的已验字节，不下载、不回测、不写 Site/活动数据库，
也不自动提交 Git。默认输入契约为：6470637 B；SHA-256
`15cc0ecbcb23261e3cd7f2fb0851815daed59951090d9ce3e759ef224ea6f415`；
6973 个唯一原 ID，M0001–M7019，保留 46 个缺口。CSV 行号是**数据记录序号**，
引号内换行不算新记录；行 hash 为 UTF-8、按键排序、无多余空白的完整行 JSON 的 SHA-256。
不重编号，不截掉重复 ID；发现重复 ID/列、缺列、错 hash、错数量或错缺口即拒绝。

这 11 列没有权威策略/因子类型列：id、名称、市场、规则、作者或机构、标题、source_url、
页码或文件、可回测、别名来源、提出日期。因此：

- `inventory.json` 完整保留每个原 ID、CSV 行 hash、规则 hash、来源链接及链接原值 hash、
  `original_classification: null` 和分类理由。未知类型为 `type_status: UNREVIEWED`、
  `entity_type: null`，持久化不以先分类为条件。
- 已有审阅元数据可作为当前类型依据，但不能宣称原 CSV 已有该分类。M0256/M0259 原文件
  字节保持不变。其他条目必须有绑定本行 hash 的明确审阅结论才写 strategies/factors；
  禁止靠关键词、目录名或旧 importer 的统一 strategy 模型分类。
- 相同规则/市场/来源的 hash 只形成重复候选组，所有不同原 ID 保留，不自动合并。
- 原“可回测”和“提出日期”仅为原标签，不是回测许可、收益验证或已核实日期。
- 新记录不复制原规则全文。三个现有封闭语法类型（threshold_switch、absolute_momentum、
  relative_momentum_rotation）可生成自撰事实释义，状态是 `CATALOG_REPORTED_UNVERIFIED`。
  成交、费用、风险等未给条件仍为 MISSING；其他语法、因子公式和经济假设均待人工复查。
  来源网页未下载，内容 hash/revision 为 null，不能用 CSV hash 冒充网页 hash。

## 在持有已核 CSV 的执行器上运行

先 checkout 含本工具的 Graph 提交并安装项目环境。以下路径应在该执行器上实际存在；
不能假定另一机器的目录可读。输出父目录需已存在，工具强制保留至少 5 GiB。

```bash
qg_source_csv=/absolute/path/to/quant-master-draft.csv
qg_stage_root=/absolute/path/to/private-checkpoints
uv run python -m quantgraph.graph.metadata_catalog plan \
  --csv "$qg_source_csv" --metadata metadata \
  --batch-size 100 --output "$qg_stage_root/plan-v1"
```

默认契约不能通过时停止核对输入，不改 hash、改数量或换数据绕过。工具输出真实 plan_sha256；
计划含 70 个确定批次（69×100＋73），具体取决于实际验收字节，未执行的批次不算完成。

```bash
qg_plan_sha=$(python -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$qg_stage_root/plan-v1/manifest.json")
uv run python -m quantgraph.graph.metadata_catalog stage \
  --plan "$qg_stage_root/plan-v1" --plan-sha256 "$qg_plan_sha" \
  --csv "$qg_source_csv" --batch-id batch-0001 \
  --output "$qg_stage_root/batch-0001-v1"
```

每个检查点包含自己的逐 ID inventory、已分类 metadata 子集/schema/index 和最后写入的
manifest。已有目录拒绝覆盖；中断目录没有 manifest，不得计入进度。重跑同批选新目录，
全部文件 hash 应一致。清单读取显式限定 64 MiB，普通单文件仍限 8 MiB。

协调者审查每个小批，按现有授权保存远端并读回 hash，然后登记远端 checkpoint/commit。
工具不会把本机文件标为远端备份。持久保存 inventory 能证明收到原 ID 和字段指纹，
但不能恢复原 CSV 全文；原 CSV 的获准私有备份仍需单独保留。

```bash
qg_batch_sha=$(python -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$qg_stage_root/batch-0001-v1/manifest.json")
uv run python -m quantgraph.graph.metadata_catalog resume \
  --plan "$qg_stage_root/plan-v1" --plan-sha256 "$qg_plan_sha" \
  --checkpoint "$qg_stage_root/batch-0001-v1" "$qg_batch_sha"
```

`resume` 只读校验各检查点，拒绝跨计划、错批次、重复计算同批、错清单/计数。报告分别给出
`inventory_complete` 与 `classified_folders_complete`；有未分类条目时后者为 false。
最终由唯一协调者把经审核元数据追加到仓库并更新统一索引，不自动替换现有记录或提交
未经字段审查的整包。此工具不读取或纳入本次新候选。

## 后续人工分类

每条审阅决定必须提供原 ID、完整 CSV 行 hash、strategy/factor、理由和来源证据。例如
以下内容仅展示合成格式，不能用于真实分类：

```json
{"schema_version":"quantgraph-csv-type-decisions/v1","records":[
  {"record_id":"M0001","row_sha256":"<actual 64-hex row hash>",
   "entity_type":"strategy","reason":"人工核对买卖规则的具体理由",
   "evidence":["https://example.org/exact-source#section"]}
]}
```

用 `plan --decisions reviewed.json --decisions-sha256 <actual-file-hash>` 创建**新计划**，
不得改旧计划和冻结批次。决定不在原 CSV 内、错行 hash、或与既有实体类型冲突时拒绝；
类型迁移另行审查。测试可用 `--contract` 指定明确的合成契约；它不是生产默认输入的替代。

通用 schema/validate 支持增长后的全部记录；Lab `metadata_pilot prepare` 仍明确只选
M0256/M0259，不因知识目录增长增加回测、曲线或策略配置。

# QuantGraph Personal Workbench

面向自己使用的本地知识工作台。工作流为搜索 → 阅读规则或定义 → 沿来源与方法关系核对 → 比较差异 → 保存个人判断 → 导出研究说明。没有登录、账户、云同步、研究调度或交易接口。

## 安装与启动

使用 Python 3.11+、Node.js 22+、uv。所有可写目录放在本工作区，不能把其他正在使用的数据库直接挂为可写数据库。

```sh
uv sync --frozen --extra test
# 只读取操作者明确指定的 Graph 数据目录，SQLite backup 创建独立副本。
uv run python -m scripts.personal_runtime \
  --source-runtime /absolute/authorized/graph-runtime \
  --destination .artifacts/personal
bash scripts/start_personal.sh
```

打开 `http://127.0.0.1:8791`。可传新的运行目录：`bash scripts/start_personal.sh .artifacts/my-workbench`；端口可用 `--port 8793` 或 `QUANTGRAPH_PERSONAL_PORT` 指定；占用时只提示，不终止其他进程。服务始终绑定 `127.0.0.1`，拒绝非回环来源、不可信 Host 和跨站请求，不信任转发头。不要把个人端口反向代理到公网。

日常更新后仍只运行 `bash scripts/start_personal.sh`。它会核对源码、静态资源、生成文件、package/lockfile、构建脚本、配置及生产环境文件的内容指纹，检测未提交修改和新增/删除文件；同时核对已构建文件摘要。有效构建直接复用；依赖签名未变化时不重装依赖。缺失、过期或损坏时先在临时目录构建，成功后替换，失败则不启动服务。`--rebuild` 可强制构建。不要绕过入口直接调用 API 模块来更新页面。

需要使用指定 Node 时，可设置 `QUANTGRAPH_NODE_BIN=/path/to/node/bin`，或在本机忽略目录 `.artifacts/personal-launch.json` 保存 `{"node_bin":"/path/to/node/bin"}`。这些配置不进入 Git。页脚“运行信息”显示页面嵌入的构建编号、服务构建编号、应用版本、Catalog 快照和数量；源码变化或旧标签页与服务不一致时会提示先保存笔记再刷新，不自动刷新未保存内容。服务启动后再次修改源码，也应重新运行日常命令。

公开仓库不分发完整个人资料。缺少已建 Catalog 时，先复用 [现有导入入口](platform-operations.md) 在自己的运行目录导入明确授权的 ingestion journal、factor database、normalized records；然后使用个人入口。原始材料没有找到时仍必须列明缺失，不能用公开 Qlib 或临时样例冒充完整资料。

个人启动不使用 platform 配置，不启动 Lab worker。原有公开服务入口保持原边界；个人模式不会把隐藏条目标记成 PUBLIC。

## 阅读与比较

- 策略：完整来源规则、可读摘录、参数、说明例子、来源和未知项独立于执行 AST。摘录是检索辅助，复杂条件的完整上下文仍保留。明确缺失与尚未成功提取分别标注。
- 因子：原始及标准化公式、变量、口径、参数、来源和已知语义。没有准入的来源记录也从因子入口可达；原始记录、定义变体与规则引用分层计数。
- 分类：方法类型、市场、频率、数据、结构、内容完整度和个人状态分别筛选。阅读分类显示根据什么字段整理；不会用同名代替等价证据。
- 关系：方法/来源分开，列表和图形、一/两跳、类型/置信度、分页。RULE_LINK_ONLY 是规则引用，没有收益归因结论。
- 比较：2–4 项，按实际字段解释窗口、资产、排名范围、数据和来源差异。未知字段不会因同时缺失而被认定相同。
- 外链：保留文档 ID、必要查询参数和章节锚点，只去掉敏感凭证与已知跟踪参数。点击检查才发出有限 HEAD 请求，一天缓存、超时和限速；连接失败、权限限制与明确 404 分开，不删除资料。

## 中文组合检索

不需要刻意插入空格：“均线动量”按均线和动量两个条件一起查；同一概念的中英文别名任选其一匹配。未知词保留，不会被悄悄丢掉。RSI14、MA200、12-1 Momentum 等保留参数；名称、完整别名和完整公式优先。结果解释命中的字段和词，不能把相近方法当作等价定义。“只用日线”严格要求已确认日频且只需 OHLCV；资料未说明时不会猜测，有可能真实返回空结果。

## 个人判断、版本与重复

收藏、五种阅读状态、标签、分组、理由、疑问、备注、自己的整理、别名和来源问题存在 `personal.sqlite`。同一服务的浏览器共享数据，刷新和服务重启后仍在。原文与许可字段不会因个人编辑而修改。

页面检测原浏览器的 PUBLIC/PRIVATE 清单后提供一次性迁移。迁移保留来源记录和版本，不覆盖服务端更新的笔记，重复提交幂等；原浏览器记录不会静默删除。

同一来源记录修订形成新定义，旧 ID 与定义版本保持可查。新版会提示原笔记固定的旧版本，可并排比较；导出不会把旧版本 ID 与当前规则拼接。找不到旧定义时明确标记缺失，不生成看似有效的对应研究请求。

完全相同原记录以来源、原生 ID、字节摘要与定义共同识别。相同内容、同名不同定义、同模板变体只生成有依据的候选。详情可确认、否决或撤销；归并只改变个人浏览身份，原笔记、ID、来源与研究引用各自保留，不改历史研究 artifact。

## 导出与备份

“我的清单”可按主题和状态筛选，选择条目导出 Markdown 或 JSON。导出含固定版本、规则/公式、参数、数据需求、来源、个人疑问、相关方法和已有研究引用；兼容的 `research-request/v1` 始终是 DRAFT，没有运行研究。

“完整备份”下载个人层及重复关系、重定向、迁移和审核记录，包含笔记、收藏、状态、标签、分组、个人整理和定义引用。备份格式为 `quantgraph-personal-backup/v2`，兼容 v1（缺少的个人记录版本记为 0），不支持的未来格式明确拒绝。个人备份不包含第三方原始语料，不能替代来源数据库的备份。

恢复必须先上传预览：显示新增、相同、冲突、无效的数量。计数单位是稳定身份记录组；关联的重复关系与重定向共同处理，避免悬空引用。相同个人内容即使时间不同也不会重复创建；内容或定义引用不同则显示双方全文、定义版本、个人记录版本与带时区时间。时间只供核对，不自动决定新旧，也不自动拼接笔记。

逐项选择“保留本机（KEEP_LOCAL）”或“采用备份（USE_BACKUP）”后才可执行；任何未处理冲突或无效记录都阻止整批写入。冲突报告及双方原件保存在本机，可刷新查看。预览后本机记录变化会拒绝执行，要求重新预览。执行前写入可下载的恢复点，使用事务校验后整体写入；失败保留原个人资料。同一预览重复提交返回原结果，再次上传同一备份不会重复创建记录。文件上限 8 MiB，重复主键、损坏摘要、结构或引用错误均明确报告。

身份含义各自独立：数据库主键 `entity_id` 定位记录；`stable_id`/`stable_knowledge_id` 关联稳定知识身份；`definition_revision` 固定当时定义；`record_revision` 是个人编辑计数；`schema_version` 是备份格式。采用备份也不会自动把旧笔记改挂到新定义上。恢复报告与执行前副本保存在本机运行目录；完整目录备份包含这些文件，普通个人 JSON 备份不递归包含历次上传的恢复计划。

整套工作台备份请在新的目录再次运行 `scripts.personal_runtime`，源目录为当前运行目录。SQLite backup 不会漏掉已提交的 WAL 数据。原始资料快照应按已有 source lock 独立保留。恢复先在新的隔离目录启动并核对数量、版本和笔记，再选择使用；不要覆盖正式数据。

## 增量更新

复用既有 ingestion journal/导入器，在本工作区副本写入新批次。个人 API 只读该 journal 的投影变化，按已有 checkpoint 增量同步；语料未变时复用阅读缓存。个人数据库与 Catalog 来源层分开，已有人工确认的 Catalog 关系 patch 及个人合并不会被自动投影覆盖。失败见 `/v1/web/reconciliation`，修复输入后通过已有 `catalog.sync_ingestion(retry=True)` 重试。

离线重建因子来源时使用固定 raw/source_lock，复用 `catalog_runtime` 更新同一个 Catalog，而不是删除 Catalog 重建；不要删除 `personal.sqlite`。固定版本需要在原来源变化之前保留。

## 可复现验收

```sh
uv run pytest tests/test_personal_catalog.py tests/test_personal_store.py \
  tests/test_factor_reading.py tests/test_personal_research.py \
  tests/test_personal_app.py tests/test_source_links.py \
  tests/test_personal_build.py tests/test_personal_search.py -q
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web test
npm --prefix web run build
# 个人端到端验收必须有真实 Catalog；自动复制到隔离验收目录，缺失则失败。
npm --prefix web run e2e:personal
# 既有公开浏览流程回归。
npm --prefix web run e2e
uv run python -m scripts.accept_personal_content \
  --runtime .artifacts/personal --output .artifacts/acceptance
uv run quantgraph build-public
uv run quantgraph verify-public
uv run pytest tests/test_public.py -q
# 挂载已校验的完整私有来源后；在隔离工作区运行。
uv run quantgraph build
uv run quantgraph validate-release
```

内容验收固定种子、分层选择至少 50 条策略和 30 条因子，并把 ID 冻结到输出目录，修复后仍检查同一批。全量核对已有规则和公式保留情况；自动字段检查不能替代人工式逐条忠实度审查和浏览器实际操作。真实内容、完整报告、截图、数据库和日志只留在忽略目录，不进入公开 Git。

本工作台不会从不完整来源推测缺失参数、收益、作者、适用市场、计算语义或商用授权。来源不完整的条目仍有阅读价值，页面明确显示目前知道与不知道的内容。

## 私有研究证据页

新增 `/results` 研究证据页，用于查看已保存策略筛查的全库覆盖、逐条来源审计、
独立实现假设、分段指标、成本敏感性和净值回撤。通过固定摘要的操作者导入命令
接入，不启动研究任务，也不把结果改标为来源精确复现或公开可分发。
详见[私有筛查导入与展示](private-corpus-research.md)。

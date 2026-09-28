# 启动、导入和运维

## 当前本机产品

在产品 Graph worktree、依赖及构建已准备好的情况下，一条命令启动前台、后台、API 和受控 Lab worker：

```sh
bash scripts/start_platform.sh .artifacts/product-research/config.json
```

默认验收配置监听 `127.0.0.1:8785`。配置属于操作者的本机运行目录，不进 Git。Ctrl-C 同时停止 API 和 worker；worker 意外退出会有限重启，租约恢复复用原任务和实验身份。`GET /healthz` 检查 Catalog，`GET /v1/research/capabilities` 检查 worker 是否在线。

完整安装与启动也可用 `QUANTGRAPH_PLATFORM_CONFIG=/absolute/operator/config.json bash web/start.sh`。没有研究配置时，`web/start.sh` 优先读取 `.artifacts/platform` 的持久化 Catalog；显式 `QUANTGRAPH_QLIB_ONLY=1` 保留仅 Qlib 的分发验证场景，不代表整个产品数据库。

## 新的独立环境

需要 Node.js 22+、Python 3.11+、uv。Graph 与正式命名的 `quant-research-lab` 各用自己的虚拟环境，部署应固定已验收提交。不要共享可写数据库、研究 registry、输出目录或服务端口。

```sh
# Graph 根目录
uv sync --frozen --extra test
npm --prefix web ci
npm --prefix web run build
# 独立 Lab 根目录，按固定版本锁文件安装
uv sync --frozen --extra dev --extra ml
uv pip install --python .venv/bin/python -e /absolute/own/quant-knowledge-graph
```

公开 Git 只附带许可已审查的 Qlib 快照。完整业务语料需要显式挂载；程序不扫描用户主目录，也不从其他执行系统取数据。用已授权路径初始化运行时 Catalog：

```sh
.venv/bin/python -m scripts.catalog_runtime \
  --runtime .artifacts/platform \
  --source-journal /absolute/authorized/ingestion.sqlite \
  --factor-database /absolute/authorized/quantgraph.sqlite \
  --normalized-records /absolute/authorized/records.jsonl
```

`--source-journal` 在目标不存在时通过 SQLite backup 读取源库并创建本任务副本，不共用可写库。也可显式提供 `--archive /absolute/authorized/grokbot.tar.gz` 走既有采集流程。来源不齐时只导入已挂载输入，管理后台对账列出实际去向；禁止把缺少输入解释为零条真实资料。

## 配置和管理

`deploy/platform-config.example.json` 提供结构示例，`profiles:{}` 表示没有注册研究能力；它不会产生演示结果。研究 profile 由 B/C 审核注册，固定 capability、市场 manifest/acquisition contract、定义集合、许可策略、预算与本地路径，不从网页接受任意执行配置。独立运行时包含 Catalog、采集、任务、因子研究 journal、TrialRegistry 和输出文件。

管理员密码由部署者在服务端文件生成，至少 16 个字符，文件仅操作者可读（`chmod 600`），配置用 `admin_password_file` 引用。网页只收取登录会话，Cookie 为 HttpOnly/SameSite，密码不会进入构建或本地清单。不要把凭证、数据库、原始资料、完整报告和运行日志加入 Git。

新 GrokBot 批次可在后台“导入与错误”提交既有 IngestBatch，或通过已有鉴权 `POST /v1/ingest/grokbot/batches`。自动化采集端的 `QUANTGRAPH_API_KEYS` 只在服务端配置 `ingest:write`；不放到前端。成功 ingestion 后和公开查询前会同步增量 Catalog。相同批次/内容幂等；同原生 ID 新内容形成新版本并停用旧索引；失败有记录，可在后台重试。

隐藏通过服务端视图同时约束列表、搜索、数量、详情、关系两端、导出、研究结果；查询没有客户端可切换的私有 profile，也没有可绕过的旧查询 API。对应来源资料随隐藏策略不可见。重新公开不会改写历史结果。已被他人下载的历史数据无法撤回。

## 备份、恢复与迁移

1. 停止本部署命令，确认没有仍运行的 worker。用 SQLite backup（`sqlite3.Connection.backup` 或 sqlite3 `.backup`）备份 Catalog、ingestion、jobs 和 FactorStudy journal；不要只复制正在写入的主 `.sqlite` 文件而遗漏 WAL。
2. 一起备份 operator config、固定输入摘要、原始来源快照、市场 manifest/contract、结果 artifacts 与 TrialRegistry 原文件。TrialRegistry 是 Lab 的追加登记格式，不能按 SQLite 打开或修改状态。
3. 管理密码单独加密保管，恢复时可轮换凭证并清除管理会话。浏览器私有清单需要用户导出 JSON，不在服务端备份中。
4. 恢复到新的独立目录，先用相同代码提交验证健康、输入摘要与引用。索引可再次运行 `catalog_runtime` 重建；元信息修正、可见性与审核 overlay 保留。不能删除 Catalog 后声称管理审计仍在。
5. Catalog 当前数据库版本为 1，建表、索引及 `is_test` 增量列幂等初始化；未来更高版本拒绝旧程序直接打开。升级前保留整套备份，发生未知 schema 时停止升级，不能 reset 用户数据。

## 部署包

仓库包含锁文件、`web/dist` 的可重建源、受控启动脚本和 `deploy/quantgraph-local.service.example`。示例服务继续绑定回环地址，可用受控 SSH 隧道访问；没有修改 DNS、购买服务或公开管理员凭证。生产公网域名、TLS、代理可信主机和访问控制需部署者另行配置审核，本轮只声明本地版本可用。

## 重跑验收

```sh
npm --prefix web run lint && npm --prefix web run typecheck && npm --prefix web test
npm --prefix web run build
PLAYWRIGHT_BROWSERS_PATH="$PWD/web/.artifacts/browsers" npm --prefix web run e2e
QUANTGRAPH_ACCEPTANCE_RUNTIME="$PWD/.artifacts/platform" \
QUANTGRAPH_ACCEPTANCE_OUTPUT="$PWD/.artifacts/acceptance-new" \
PLAYWRIGHT_BROWSERS_PATH="$PWD/web/.artifacts/browsers" \
npm --prefix web run e2e -- --config=catalog.playwright.config.ts
# 已启动自己的完整平台时：真实执行，会新增带独立ID的研究请求与实验
QUANTGRAPH_PRODUCT_CONFIG="$PWD/.artifacts/product-research/config.json" \
PLAYWRIGHT_BROWSERS_PATH="$PWD/web/.artifacts/browsers" \
npm --prefix web run e2e -- --config=product.playwright.config.ts
uv run ruff check .
uv run quantgraph build-public
uv run quantgraph verify-public
uv run pytest tests/test_runtime_catalog.py tests/test_research_jobs.py tests/test_web.py tests/test_public.py -q
# 全量授权来源挂载并按source_lock校验后
uv run quantgraph build
uv run quantgraph validate-release
```

Catalog E2E 每次使用新的输出目录与 SQLite 副本，端口 8787；Qlib E2E 用 8777。完整研究 E2E 需要配置中已冻结的真实 `acceptance_cases`，缺失即失败，不退回 mock。截图仅保存公开字段，内部研究指标与报告不截图、不提交。

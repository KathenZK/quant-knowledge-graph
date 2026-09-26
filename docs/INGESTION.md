# GrokBot 增量入口与研究接口

数据流：QuantGraph → quant-strategy-lab（研究层）→ quant-runner。
本服务不提供下单、实盘策略发布或 runner 控制接口。

## 启动

```bash
uv sync --frozen --extra test --python 3.12
export QUANTGRAPH_INGEST_DB="$PWD/datasets/ingestion/grokbot.sqlite"
# 在环境变量/secret manager 配置真实随机 token（至少 32 字符）：
# QUANTGRAPH_API_KEYS={"collector-v1":{"token":"<random-secret>","scopes":["ingest:write","ingest:read"],"requests_per_minute":60,"plan":"private"}}
uv run quantgraph serve --profile commercial --port 8000
```

未设置 `QUANTGRAPH_INGEST_DB` 时，原有只读服务行为不变。未配置 key 时私有接口不可访问。
研究调用方独立配置 `research:read`；证据提交方使用 `research:write`。商业公开 API
继续来自现有许可安全 release；私有 ingestion journal 不会并入公开库。

## 接口与输入

- `POST /v1/ingest/grokbot/batches`
- `GET /v1/ingest/jobs/{job_id}`
- `GET /v1/ingest/batches/{batch_id}`
- `GET /v1/research/strategies/{concepts|templates|variants}`
- `GET /v1/research/lineage/{variant_id}`
- `GET /v1/research/factors/{factor_id}/strategies`
- `GET /v1/research/candidates`：仅返回待筛选候选及阻断原因。
- `POST /v1/research/evidence`：证据只追加，重复 run 幂等，修改须用新 run。
- `GET /v1/usage`：当前 key 的请求计数，不返回密钥或规则内容。
- `GET /v1/ontology/factor-concepts`：自有经济分类概念，非公式等价声明。

[OpenAPI](ingestion-openapi.json) 由真实服务生成，运行服务也可访问 `/docs`。

```json
{
  "batch_id": "grokbot-demo-001",
  "collector_version": "v1",
  "records": [{
    "record_id": "SYNTHETIC-1",
    "source_url": "https://example.org/own-rule",
    "name": "Synthetic integration example",
    "author": "Fixture author",
    "source_publication_date": null,
    "raw_market": "美股 ETF",
    "raw_rule": "日频：若 RSI(7)>53 → 满仓 QQQ，否则 SHV。",
    "backtestability": "REVIEW",
    "collected_at": "2026-09-26T00:00:00Z",
    "metadata": {"fixture": true}
  }]
}
```

`external_id/title/org` 分别兼容 `record_id/name/author`；冲突别名拒绝。
未知字段原样保留，并进入 `auditable_unknown_fields`；许可、批准、live_ready 等
额外声明仅是采集方陈述，不能改变审核结论。source publication date 也是未核验的报告日期，
不自动成为策略起源日期。时间必须带时区。单次最多 1000 条，默认压缩前后均不超过 2 MiB。

```bash
curl --fail-with-body -H "Authorization: Bearer $QUANTGRAPH_TOKEN" \
  -H 'Content-Type: application/json' --data-binary @batch.json \
  http://127.0.0.1:8000/v1/ingest/grokbot/batches
uv run quantgraph ingest-batch batch.json --url http://127.0.0.1:8000 --gzip
uv run quantgraph ingest-batch batch.ndjson.gz --batch-id demo-002 \
  --collector-version v1 --url http://127.0.0.1:8000
```

```python
from quantgraph.client import QuantGraphClient
client = QuantGraphClient("http://127.0.0.1:8000")  # QUANTGRAPH_TOKEN
result = client.ingest_batch(batch, compress=True)
status = client.get_job(result["job_id"])
candidates = client.export_research_candidates(limit=1000, offset=0)
```

SDK 不跟随重定向，远端地址必须 HTTPS。客户端失败后可原样重试。

## 幂等、版本与统计

- 一个 HTTP 请求事务性完成；返回时 job 为 `COMPLETED`。本版不假装有后台任务队列。
  中途失败整批回滚并返回错误；重试安全。后台 worker 可在保持接口语义下扩展。
- 同 batch_id + 相同完整 payload 重放返回原 job_id 和全量 duplicate。
- 同 record_id + 相同记录 hash 跨批次引用原 revision；变化增加 revision，旧 raw 永不覆盖。
  退回历史内容也建立新 revision，从而保留变更顺序。
- record_id 是 GrokBot 全局命名空间，采集器须保持稳定；本版为一个可信组织使用，非多租户 SaaS。
- 请求元数据变化保留新的 submission；每个 observation 连接 batch、record、revision、projection。
- `accepted/duplicate/revision` 互斥且相加等于输入条数；`curated` 表示新增/修订中严格规则语法通过数。
  `review_required` 包含许可或执行审核，因此可与 curated 重叠。整批无部分成功，成功响应 errors=0。
- `curated` 不等于可执行。所有导入记录默认许可待审、executable=false；因子关联只有 RULE_LINK_ONLY。
- `reproject()` 为解析版本升级追加投影；相同 parser version 内容漂移报错。旧原始数据和旧投影不改。
  canonical IDs 使用原始身份/规则 hash 与结构槽位，插入无关记录不会改旧 ID。

## 本地与生产

SQLite adapter 使用 WAL、外键、写事务与防 UPDATE/DELETE 触发器。数据库及其目录应由服务专用用户持有；
备份使用 SQLite backup API 或停写后的完整快照，不只拷贝正在写入的主文件。
`IngestionRepository` 定义适配边界；Postgres 版本需实现相同事务、唯一性、幂等、配额与追加约束，
当前没有声称已交付 Postgres adapter。

生产部署使用单台持久存储服务 + HTTPS 反向代理（建议先单 worker）。设置反向代理 body limit、
连接数/超时和 IP 防护；应用限流按 key/分钟保存在数据库中，多 worker 共用同一 SQLite 配额。
不将 SQLite 放在不支持其锁语义的共享网络盘。多机服务须先实现 Postgres/共享限流 adapter。
API key 轮换：先同时加载旧/新 key，滚动重启，迁移采集器，最后删除旧 key 并重启。
环境配置在进程启动时读取；key ID 和 plan 可公开，token 不进入 Git、日志、URL 或报告。
当前 plan 仅是计数标签，无收费、租户隔离或账单功能。

原始语料、SQLite、完整候选和映射仅留在被忽略的私有目录。
公开变更只含代码、合成测试、接口定义、自有聚合统计。受限许可内容不通过 public/commercial profile 分发。

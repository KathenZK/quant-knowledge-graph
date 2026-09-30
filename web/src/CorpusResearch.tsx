import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, FileCheck2, Search } from "lucide-react";
import { useApi } from "./api";
import { Empty, ErrorState, ExternalLink, Loading } from "./components";
import { readable } from "./personal-data";
import "./corpus-research.css";

type Metrics = {
  start?: string;
  end?: string;
  observations?: number;
  cagr?: number | null;
  sharpe?: number | null;
  max_drawdown?: number | null;
  annual_volatility?: number | null;
  annual_turnover?: number | null;
};
type Periods = Record<string, Metrics>;
export type CurvePoint = { date: string; equity: number; drawdown: number };
type Audit = {
  source_verification_status?: string;
  source_rule_attribution_status?: string;
  [key: string]: unknown;
};
export type CorpusSummary = {
  available: boolean;
  run_id?: string;
  runs: { run_id: string; created_at?: string }[];
  counts: {
    corpus_records: number;
    tested_records: number;
    tested_variants: number;
    data_files: number;
    used_data_series: number;
    standardized_implementations?: number;
    supplemental_defaults_implementations?: number;
  };
  coverage_counts: Record<string, number>;
  families: { value: string; count: number }[];
  limitations: string[];
  manifest_sha256?: string;
};
type CorpusRecord = {
  id: string;
  name: string;
  status: string;
  reason: string;
  tested_variants: number;
  families: string[];
  audit: Audit;
  implementations: { variant_id: string; family: string }[];
  catalog_refs?: { entity_id: string; definition_revision: string }[];
};
export type CorpusDetail = {
  run_id: string;
  id: string;
  variant_id: string;
  name: string;
  family: string;
  metrics: {
    periods?: Periods;
    cost_sensitivity?: Record<string, Periods>;
    spy_benchmark?: Periods;
    risk_matched_benchmark?: Periods;
    equal_weight_universe_benchmark?: Periods;
    risk_match_note?: string;
    implementation_fidelity?: string;
    [key: string]: unknown;
  };
  spec: {
    source_url?: string;
    assumptions?: string[];
    rule_excerpt?: string;
    params?: Record<string, unknown>;
    [key: string]: unknown;
  };
  audit: Audit;
  deep_validation?: Record<string, unknown>;
  curve: CurvePoint[];
  lineage: Record<string, unknown>;
  limitations: string[];
  curve_meta?: {
    total_observations: number;
    returned_points: number;
    sampling: string;
    benchmark_curve_available: boolean;
  };
};
const base = "/v1/personal/corpus-research";
export const statusLabel = (status: string) =>
  ({
    tested: "本次已回测",
    not_implemented_or_data_scope_unresolved: "未实现 / 数据范围待定",
    screened_not_implemented: "已筛查 · 尚未实现",
    screened_data: "额外数据待补",
    market_data_unavailable: "行情不可用",
    screened_out_of_monthly_scope: "超出月频实现范围",
    screened_ambiguous: "规则歧义待核对",
    screened_ambiguous_or_data_required: "规则 / 数据待核对",
    cross_market_clock_unresolved: "跨市场时钟待核对",
    not_individually_checked: "尚未逐条核验来源",
    unverified: "来源归属未核验",
    readable: "来源页面已读取",
    inaccessible_via_web_tool: "来源访问未决",
    readable_text_but_decision_tree_image_not_verified: "文本已读 · 图示未核验",
  })[status] || status;
const periodLabels: Record<string, string> = {
  full: "历史全段",
  development: "开发段",
  validation: "验证段",
  holdout: "留出段（回顾性）",
  latest_2026: "2026 观察段",
};
export function metricValue(value: number | null | undefined, percent = false) {
  return typeof value === "number" && Number.isFinite(value)
    ? percent
      ? `${(value * 100).toFixed(2)}%`
      : value.toFixed(2)
    : "未提供";
}
function MetricTable({
  rows,
}: {
  rows: { label: string; metrics?: Metrics }[];
}) {
  return (
    <div className="cr-table-scroll">
      <table className="cr-metrics">
        <caption className="sr-only">
          同区间指标比较；未知数据不会按零计
        </caption>
        <thead>
          <tr>
            <th>对象 / 成本</th>
            <th>区间</th>
            <th>年化收益</th>
            <th>Sharpe</th>
            <th>最大回撤</th>
            <th>年化换手</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ label, metrics: m }) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              <td>{m?.start && m?.end ? `${m.start} → ${m.end}` : "未提供"}</td>
              <td>{metricValue(m?.cagr, true)}</td>
              <td>{metricValue(m?.sharpe)}</td>
              <td>{metricValue(m?.max_drawdown, true)}</td>
              <td>{metricValue(m?.annual_turnover)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function EquityChart({
  points,
  drawdown = false,
}: {
  points: CurvePoint[];
  drawdown?: boolean;
}) {
  const valid = points.filter(
    (p) =>
      Number.isFinite(p.equity) &&
      Number.isFinite(p.drawdown) &&
      Number.isFinite(Date.parse(p.date)),
  );
  if (valid.length < 2)
    return <p className="pw-muted">没有足够的逐日数据绘图；不补造曲线。</p>;
  const values = valid.map((p) => (drawdown ? p.drawdown : p.equity));
  const lo = Math.min(drawdown ? 0 : 1, ...values),
    hi = Math.max(drawdown ? 0 : 1, ...values);
  const span = hi - lo || 1,
    start = Date.parse(valid[0].date),
    end = Date.parse(valid[valid.length - 1].date);
  const xy = valid
    .map(
      (p, i) =>
        `${52 + ((Date.parse(p.date) - start) / (end - start || 1)) * 698},${16 + ((hi - values[i]) / span) * 170}`,
    )
    .join(" ");
  const title = drawdown ? "逐日净收益对应的回撤" : "净值曲线（初始净值 1）";
  return (
    <figure className="cr-chart">
      <figcaption>{title}</figcaption>
      <svg
        viewBox="0 0 780 225"
        role="img"
        aria-label={`${title}，${valid[0].date} 至 ${valid[valid.length - 1].date}`}
      >
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line
              x1="52"
              y1={16 + t * 170}
              x2="750"
              y2={16 + t * 170}
              stroke="#dfe6df"
            />
            <text x="45" y={20 + t * 170} textAnchor="end">
              {metricValue(hi - t * span, drawdown)}
            </text>
          </g>
        ))}
        <polyline
          points={xy}
          fill="none"
          stroke={drawdown ? "#a65539" : "#2b6652"}
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
        <text x="52" y="213">
          {valid[0].date}
        </text>
        <text x="750" y="213" textAnchor="end">
          {valid[valid.length - 1].date}
        </text>
      </svg>
    </figure>
  );
}
export function ResearchDetail({ detail }: { detail: CorpusDetail }) {
  const [period, setPeriod] = useState("full");
  const m = detail.metrics;
  return (
    <article className="cr-detail">
      <header>
        <span className="pw-kicker">IMPLEMENTATION / 独立实现</span>
        <h2>{detail.name}</h2>
        <p>
          <code>{detail.variant_id}</code> · {detail.family} · 原记录{" "}
          {detail.id}
        </p>
      </header>
      <div className="cr-warning">
        探索性回顾筛查。来源忠实度、实现假设与经济有效性分别判断；留出段标签本身不证明独立样本外验证。
      </div>
      <p>
        <strong>独立标准化实现</strong> ·{" "}
        {m.supplemental_defaults_flag === true ||
        detail.spec.supplemental_defaults_flag === true
          ? "包含额外补充默认假设，请逐项核对"
          : "仍使用统一执行与成本约定；未标记额外默认假设不代表来源精确复现"}
      </p>
      <div className="cr-audit">
        <span>
          {statusLabel(
            detail.audit.source_verification_status ||
              "not_individually_checked",
          )}
        </span>
        <span>
          {statusLabel(
            detail.audit.source_rule_attribution_status || "unverified",
          )}
        </span>
      </div>
      <section>
        <h3>1. 来源规则与实现假设</h3>
        <p>{detail.spec.rule_excerpt || "没有附带规则摘录"}</p>
        <ExternalLink url={detail.spec.source_url}>核对原始来源</ExternalLink>
        <p className="pw-muted">
          {m.implementation_fidelity || "本次独立实现；不能据此宣称原作者复现"}
        </p>
        <details>
          <summary>查看参数及全部补充假设</summary>
          <p>{readable(detail.spec.params)}</p>
          <ul>
            {detail.spec.assumptions?.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </details>
      </section>
      <section>
        <div className="cr-section-head">
          <h3>2. 分段结果与基准</h3>
          <label>
            比较区间{" "}
            <select value={period} onChange={(e) => setPeriod(e.target.value)}>
              {Object.entries(periodLabels).map(([v, label]) => (
                <option value={v} key={v}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <MetricTable
          rows={[
            { label: "策略（基础成本）", metrics: m.periods?.[period] },
            { label: "SPY 买入持有", metrics: m.spy_benchmark?.[period] },
            {
              label: "开发段定权风险匹配",
              metrics: m.risk_matched_benchmark?.[period],
            },
            {
              label: "原资产池等权",
              metrics: m.equal_weight_universe_benchmark?.[period],
            },
          ]}
        />
        <p className="pw-muted">
          基准按原研究记录展示，请逐行核对区间与风险暴露；超额收益不是 alpha
          证明。{m.risk_match_note}
        </p>
      </section>
      <section>
        <h3>3. 成本敏感性</h3>
        <MetricTable
          rows={Object.entries(m.cost_sensitivity || {})
            .sort(([a], [b]) => Number(a) - Number(b))
            .map(([bps, periods]) => ({
              label: `${bps} bps / 成交金额`,
              metrics: periods[period],
            }))}
        />
        {!Object.keys(m.cost_sensitivity || {}).length && (
          <p>未附带成本情景。</p>
        )}
      </section>
      <section>
        <h3>4. 保留的净值与回撤</h3>
        <p className="pw-muted">
          以下曲线来自保存的基础成本逐日净收益，覆盖其全部日期，不随上方区间切换。仅作显示抽样，指标来自原完整结果。未附带基准逐日序列时不绘制基准曲线。
        </p>
        {detail.curve_meta && (
          <p className="pw-muted">
            完整 {detail.curve_meta.total_observations.toLocaleString()}{" "}
            个观察值，显示 {detail.curve_meta.returned_points.toLocaleString()}{" "}
            点；{detail.curve_meta.sampling}
          </p>
        )}
        <EquityChart points={detail.curve} />
        <EquityChart points={detail.curve} drawdown />
      </section>
      <section>
        <h3>5. 审计、敏感性与证据链</h3>
        <details>
          <summary>逐条来源核验（未核验不会记为通过）</summary>
          <p>{readable(detail.audit)}</p>
        </details>
        <details>
          <summary>额外延迟 / 现金收益敏感性</summary>
          <p>
            {detail.deep_validation
              ? readable(detail.deep_validation)
              : "未纳入深化验证；不推断通过"}
          </p>
        </details>
        <details>
          <summary>原记录 → 实现 → 实验的固定摘要</summary>
          <dl className="pw-definition-list">
            {Object.entries(detail.lineage).map(([key, val]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>
                  <code>{readable(val)}</code>
                </dd>
              </div>
            ))}
          </dl>
        </details>
        <ul>
          {detail.limitations.map((v, i) => (
            <li key={i}>{v}</li>
          ))}
        </ul>
      </section>
    </article>
  );
}
export function SourceRecordDetail({
  record,
}: {
  record: CorpusRecord & { source_url?: string; run_id?: string };
}) {
  return (
    <article className="cr-detail">
      <header>
        <span className="pw-kicker">SOURCE RECORD / 原始记录</span>
        <h2>
          {record.id} · {record.name}
        </h2>
        <p>
          {statusLabel(record.status)} · {record.tested_variants} 个本次回测实现
        </p>
      </header>
      <div className="cr-warning">
        {record.reason || "本次已保存独立实现结果，来源核验状态另列。"}{" "}
        未回测不代表规则失效；原始采集声明不自动成为验证结论。
      </div>
      <div className="cr-audit">
        <span>
          {statusLabel(
            record.audit.source_verification_status ||
              "not_individually_checked",
          )}
        </span>
        <span>
          {statusLabel(
            record.audit.source_rule_attribution_status || "unverified",
          )}
        </span>
      </div>
      <section>
        <h3>原始规则与引用</h3>
        <p>{readable(record.audit["规则"])}</p>
        <ExternalLink url={record.source_url}>核对原始来源</ExternalLink>
        <dl className="pw-definition-list">
          {[
            "市场",
            "作者或机构",
            "标题",
            "页码或文件",
            "提出日期",
            "可回测",
          ].map((key) => (
            <div key={key}>
              <dt>{key}（采集方原声明）</dt>
              <dd>{readable(record.audit[key])}</dd>
            </div>
          ))}
        </dl>
      </section>
      <section>
        <h3>逐条来源核验</h3>
        {record.audit.source_verification ? (
          <p>{readable(record.audit.source_verification)}</p>
        ) : (
          <p>本条没有附带逐条来源检查，不从抽样记录推断它已通过。</p>
        )}
      </section>
      <section>
        <h3>机械筛查与数据缺口</h3>
        <p>这些标记是机械筛查线索，不是人工完整度或可执行性结论。</p>
        <dl className="pw-definition-list">
          {[
            "data_screen_primary",
            "mechanical_flags",
            "data_requirements_flags",
            "date_precision_shape",
            "github_commit_pinned",
          ].map((key) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{readable(record.audit[key])}</dd>
            </div>
          ))}
        </dl>
      </section>
    </article>
  );
}
function RecordDetailLoader({ id, run }: { id: string; run: string }) {
  const request = useApi<CorpusRecord & { source_url?: string }>(
    `${base}/records/${encodeURIComponent(id)}?run_id=${encodeURIComponent(run)}`,
  );
  if (request.loading) return <Loading />;
  if (request.error || !request.data)
    return (
      <ErrorState
        error={request.error || "原记录不可用"}
        retry={request.retry}
      />
    );
  return <SourceRecordDetail record={request.data} />;
}
function DetailLoader({ variant, run }: { variant: string; run: string }) {
  const request = useApi<CorpusDetail>(
    `${base}/implementations/${encodeURIComponent(variant)}?run_id=${encodeURIComponent(run)}`,
  );
  if (request.loading) return <Loading />;
  if (request.error || !request.data)
    return (
      <ErrorState
        error={request.error || "实现结果不可用"}
        retry={request.retry}
      />
    );
  return <ResearchDetail key={`${run}/${variant}`} detail={request.data} />;
}
function RecordList({
  run,
  params,
  update,
}: {
  run: string;
  params: URLSearchParams;
  update: (key: string, value: string) => void;
}) {
  const query = new URLSearchParams({
    run_id: run,
    q: params.get("q") || "",
    status: params.get("status") || "",
    family: params.get("family") || "",
    page: params.get("page") || "1",
    page_size: "20",
  });
  const rows = useApi<{
    items: CorpusRecord[];
    total: number;
    page: number;
    page_size: number;
  }>(`${base}/records?${query}`);
  if (rows.loading) return <Loading />;
  if (rows.error || !rows.data)
    return (
      <ErrorState error={rows.error || "覆盖记录不可用"} retry={rows.retry} />
    );
  return (
    <section className="cr-records">
      <div className="cr-section-head">
        <h2>记录覆盖与实现</h2>
        <span>{rows.data.total.toLocaleString()} 条原记录</span>
      </div>
      {!rows.data.items.length && (
        <p>没有匹配记录。可清除筛选；未回测不等于原规则不可执行。</p>
      )}
      {rows.data.items.map((row) => (
        <article key={row.id} className="cr-record">
          <div className="cr-section-head">
            <h3>
              {row.id} · {row.name}
            </h3>
            <span
              className={`cr-tag ${row.status === "tested" ? "tested" : ""}`}
            >
              {statusLabel(row.status)}
            </span>
          </div>
          <p>{row.reason}</p>
          <p className="pw-muted">
            {statusLabel(
              row.audit.source_verification_status ||
                "not_individually_checked",
            )}{" "}
            ·{" "}
            {statusLabel(
              row.audit.source_rule_attribution_status || "unverified",
            )}
          </p>
          <div className="cr-variants">
            <button
              onClick={() => update("record", row.id)}
              aria-pressed={params.get("record") === row.id}
            >
              查看原始规则与逐条审计
            </button>
            {row.implementations.map((v) => (
              <button
                key={v.variant_id}
                onClick={() => update("variant", v.variant_id)}
                aria-pressed={params.get("variant") === v.variant_id}
              >
                {v.variant_id}
                <span>{v.family}</span>
                <ArrowRight size={14} />
              </button>
            ))}
          </div>
          {row.catalog_refs?.map((ref) => (
            <Link
              key={ref.entity_id}
              to={`/entity/strategy/${encodeURIComponent(ref.entity_id)}`}
            >
              阅读 Catalog 来源条目（原生 ID 引用，非定义等价认定）
            </Link>
          ))}
        </article>
      ))}
      <div className="cr-pagination">
        <button
          disabled={rows.data.page <= 1}
          onClick={() => update("page", String(rows.data!.page - 1))}
        >
          <ArrowLeft size={14} />
          上一页
        </button>
        <span>
          第 {rows.data.page} /{" "}
          {Math.max(1, Math.ceil(rows.data.total / rows.data.page_size))} 页
        </span>
        <button
          disabled={rows.data.page * rows.data.page_size >= rows.data.total}
          onClick={() => update("page", String(rows.data!.page + 1))}
        >
          下一页
          <ArrowRight size={14} />
        </button>
      </div>
    </section>
  );
}
export default function CorpusResearch() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") || "");
  const queryText = params.get("q") || "";
  useEffect(() => setSearch(queryText), [queryText]);
  const run = params.get("run_id") || "";
  const summary = useApi<CorpusSummary>(
    `${base}${run ? `?run_id=${encodeURIComponent(run)}` : ""}`,
  );
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page" && key !== "variant") next.delete("page");
    if (key !== "variant") next.delete("variant");
    if (key !== "record") next.delete("record");
    if (key === "run_id") {
      next.delete("status");
      next.delete("family");
    } else if (summary.data?.run_id) next.set("run_id", summary.data.run_id);
    setParams(next);
  };
  return (
    <div className="cr-workbench">
      <header className="pw-title">
        <div>
          <span className="pw-kicker">RESEARCH EVIDENCE / 私有研究</span>
          <h1>从来源记录，看到可核对的实验。</h1>
          <p>
            逐条查看覆盖、实现差异与结果。原记录数、实现数和方法分组分别计数。
          </p>
        </div>
        <FileCheck2 size={32} />
      </header>
      {summary.loading ? (
        <Loading />
      ) : summary.error || !summary.data ? (
        <ErrorState
          error={summary.error || "研究集合不可用"}
          retry={summary.retry}
        />
      ) : !summary.data.available ? (
        <Empty title="尚未导入这批研究结果">
          <p>
            使用已固定摘要的 strategy-screen
            私有导入命令接入保留结果。此页不会运行研究或改变公开资料。
          </p>
          <p>原有条目详情中的研究 journal 引用仍保留。</p>
        </Empty>
      ) : (
        <>
          <label className="cr-run">
            研究快照{" "}
            <select
              value={summary.data.run_id}
              onChange={(e) => update("run_id", e.target.value)}
            >
              {summary.data.runs.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {r.run_id}
                </option>
              ))}
            </select>
          </label>
          <p className="pw-muted">
            本页显示已导入的历史快照；后续回测须作为新批次导入，旧结果不会覆盖。记录时间：
            {summary.data.runs.find((r) => r.run_id === summary.data?.run_id)
              ?.created_at || "未登记"}
          </p>
          <div className="cr-coverage">
            <label htmlFor="cr-coverage">
              本次已回测覆盖 {summary.data.counts.tested_records} /{" "}
              {summary.data.counts.corpus_records} 条原记录
            </label>
            <progress
              id="cr-coverage"
              max={summary.data.counts.corpus_records || 1}
              value={summary.data.counts.tested_records}
            />
          </div>
          <div className="cr-stats">
            {[
              ["原始记录", summary.data.counts.corpus_records],
              ["已回测记录", summary.data.counts.tested_records],
              ["标准化实现配置", summary.data.counts.tested_variants],
              [
                "使用 / 已取行情",
                `${summary.data.counts.used_data_series} / ${summary.data.counts.data_files}`,
              ],
            ].map(([label, value]) => (
              <div key={label}>
                <span>{label}</span>
                <strong>
                  {typeof value === "number" ? value.toLocaleString() : value}
                </strong>
              </div>
            ))}
          </div>
          <div className="cr-warning">
            <strong>本地只读 · 探索性研究</strong>
            {summary.data.counts.standardized_implementations !== undefined && (
              <p>
                全部 {summary.data.counts.standardized_implementations}{" "}
                个回测实现采用标准化约定；其中{" "}
                {summary.data.counts.supplemental_defaults_implementations ??
                  "未统计"}{" "}
                个标记额外补充默认假设。
              </p>
            )}
            <p>
              实现配置不等于独立策略；来源核验、规则实现和收益验证是不同状态。未测试、失败和受限记录都保留。
            </p>
            <details>
              <summary>本次限制与固定摘要</summary>
              <ul>
                {summary.data.limitations.map((v, i) => (
                  <li key={i}>{v}</li>
                ))}
              </ul>
              <code>{summary.data.manifest_sha256}</code>
            </details>
          </div>
          <div className="cr-filters">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                update("q", search);
              }}
            >
              <label htmlFor="cr-search">原记录 / 名称</label>
              <div>
                <input
                  id="cr-search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="输入 M 编号或名称"
                />
                <button type="submit">
                  <Search size={15} />
                  查找
                </button>
              </div>
            </form>
            <label>
              覆盖状态
              <select
                value={params.get("status") || ""}
                onChange={(e) => update("status", e.target.value)}
              >
                <option value="">全部状态</option>
                {Object.entries(summary.data.coverage_counts).map(
                  ([v, count]) => (
                    <option key={v} value={v}>
                      {statusLabel(v)} · {count}
                    </option>
                  ),
                )}
              </select>
            </label>
            <label>
              实现方法分组
              <select
                value={params.get("family") || ""}
                onChange={(e) => update("family", e.target.value)}
              >
                <option value="">全部分组</option>
                {summary.data.families.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.value} · {f.count}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {params.get("record") && (
            <div className="cr-selected">
              <button onClick={() => update("record", "")}>
                <ArrowLeft size={14} />
                关闭原记录详情
              </button>
              <RecordDetailLoader
                id={params.get("record")!}
                run={summary.data.run_id!}
              />
            </div>
          )}
          {params.get("variant") && (
            <div className="cr-selected">
              <button onClick={() => update("variant", "")}>
                <ArrowLeft size={14} />
                关闭实现详情
              </button>
              <DetailLoader
                variant={params.get("variant")!}
                run={summary.data.run_id!}
              />
            </div>
          )}
          <RecordList
            run={summary.data.run_id!}
            params={params}
            update={update}
          />
        </>
      )}
    </div>
  );
}

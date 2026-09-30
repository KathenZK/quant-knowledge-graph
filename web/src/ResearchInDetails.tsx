import { useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { useApi } from "./api";
import { ErrorState, ExternalLink, Loading } from "./components";
import {
  DetailLoader,
  EquityChart,
  MetricTable,
  fidelityLabel,
  type CorpusDetail,
  type CorpusRecord,
} from "./CorpusResearch";
import type { PersonalDetail, PersonalItem } from "./personal-data";
import { personalPath } from "./personal-data";

const base = "/v1/personal/corpus-research";
export function nativeResearchId(item: PersonalItem) {
  if (item.kind !== "strategy" || item.source_type === "COLLECTION_CANDIDATE")
    return undefined;
  return (
    item.knowledge?.source.native_ids ||
    item.source_native_ids ||
    []
  ).find((id) => /^M\d{4}$/.test(id));
}
export default function ResearchInDetails({
  item,
  compact = false,
}: {
  item: PersonalDetail;
  compact?: boolean;
}) {
  const id = nativeResearchId(item);
  if (!id)
    return (
      <p>
        {item.kind === "strategy"
          ? "尚无与这条来源记录关联的已导入回测。候选收录不代表已经执行。"
          : "因子研究按因子定义版本单独关联。包含这个因子的策略收益不能作为它的独立检验。"}
      </p>
    );
  return (
    <RecordResearch
      key={item.entity_id}
      item={item}
      id={id}
      compact={compact}
    />
  );
}
function RecordResearch({
  item,
  id,
  compact,
}: {
  item: PersonalDetail;
  id: string;
  compact: boolean;
}) {
  const request = useApi<CorpusRecord>(
    `${base}/records/${encodeURIComponent(id)}`,
  );
  const [params, setParams] = useSearchParams();
  const initial =
    params.get("research_run") && params.get("research_variant")
      ? JSON.stringify([
          params.get("research_run"),
          params.get("research_variant"),
        ])
      : "";
  const [selection, setSelection] = useState(initial);
  if (request.loading) return <Loading />;
  if (request.error || !request.data)
    return (
      <ErrorState
        error={request.error || "研究记录暂不可读"}
        retry={request.retry}
      />
    );
  const record = request.data;
  const results = record.related_results || [];
  const selected = results.find(
    (r) => JSON.stringify([r.origin_run_id, r.variant_id]) === selection,
  );
  const sameText = record.audit["规则"] === item.knowledge?.original_rule;
  return (
    <div className="pw-inline-research">
      <PublishedPortfolio id={id} />
      <p>
        {results.length
          ? `已导入 ${results.length} 个实现版本，可在这里查看结果。`
          : record.reason || "尚未保留可展示回测；没有结果不等于规则无效。"}
      </p>
      <p className="pw-reading-basis">
        {sameText
          ? "与当前原始规则文本一致；成交、成本和补充假设仍需核对。"
          : "按原生来源 ID 关联历史实验，尚未证明与当前定义版本完全一致。"}
      </p>
      {record.coverage_history?.length ? (
        <details>
          <summary>各批次的执行状态与未完成原因</summary>
          {record.coverage_history.map((entry) => (
            <p key={entry.run_id}>
              {entry.run_id}：{entry.reason || entry.status}
            </p>
          ))}
        </details>
      ) : null}
      {results.length > 0 && (
        <label className="pw-research-select">
          选择历史实现
          <select
            aria-label={`${item.name}的历史实现`}
            value={selected ? selection : ""}
            onChange={(e) => {
              setSelection(e.target.value);
              const result = results.find(
                (r) =>
                  JSON.stringify([r.origin_run_id, r.variant_id]) ===
                  e.target.value,
              );
              const next = new URLSearchParams(params);
              if (result) {
                next.set("research_run", result.origin_run_id);
                next.set("research_variant", result.variant_id);
                next.set("research_manifest", result.manifest_sha256);
              } else {
                next.delete("research_run");
                next.delete("research_variant");
                next.delete("research_manifest");
              }
              setParams(next, { replace: true });
            }}
          >
            <option value="">请选择要读的实现与批次</option>
            {results.map((r) => (
              <option
                key={`${r.origin_run_id}|${r.variant_id}`}
                value={JSON.stringify([r.origin_run_id, r.variant_id])}
              >
                {fidelityLabel(r.fidelity_class)} · {r.variant_id} ·{" "}
                {r.origin_run_id}
              </option>
            ))}
          </select>
        </label>
      )}
      {selected && (
        <>
          <p className="pw-reading-basis">
            {fidelityLabel(selected.fidelity_class)}。
            {selected.fidelity_reason || "统一执行约定和原作者版本分开判断。"}
          </p>
          {compact ? (
            <CompactResult
              run={selected.origin_run_id}
              variant={selected.variant_id}
            />
          ) : (
            <DetailLoader
              run={selected.origin_run_id}
              variant={selected.variant_id}
            />
          )}
        </>
      )}
    </div>
  );
}
type PublishedMetric = {
  source_url?: string;
  source_vintage?: string;
  scope?: string;
  periods: Record<
    string,
    {
      observations?: number;
      start?: string;
      end?: string;
      annualized_compound_factor_return?: number;
      sharpe_zero_cash?: number;
      monthly_max_drawdown?: number;
    }
  >;
};
type PublishedSeries = {
  evaluation_id: string;
  records: {
    id: string;
    name: string;
    metrics: PublishedMetric;
    curve: { date: string; equity: number; drawdown: number }[];
  }[];
};
function PublishedPortfolio({ id }: { id: string }) {
  const request = useApi<PublishedSeries[]>(
    `/v1/personal/source-portfolios?record_id=${encodeURIComponent(id)}`,
  );
  if (request.loading) return null;
  if (request.error)
    return (
      <p className="pw-reading-basis">
        作者公布组合的评估资料暂不可读；不据此判定没有来源数据。
      </p>
    );
  if (!Array.isArray(request.data) || !request.data.length) return null;
  return (
    <section className="pw-published-evidence">
      <h3>作者公布组合收益的评价</h3>
      <p>
        这是对来源已发布收益序列的计算，没有独立重建持仓，也不计入策略执行覆盖。以下为月度组合统计，不是我们实现的净收益。
      </p>
      {request.data.flatMap((group) =>
        group.records.map((row) => (
          <div key={group.evaluation_id + "/" + row.id}>
            <h4>{row.name}</h4>
            <MetricTable
              rows={Object.entries(row.metrics.periods).map(([label, p]) => ({
                label,
                metrics: {
                  ...p,
                  cagr: p.annualized_compound_factor_return,
                  sharpe: p.sharpe_zero_cash,
                  max_drawdown: p.monthly_max_drawdown,
                },
              }))}
            />
            <p className="pw-reading-basis">
              数据版本：{row.metrics.source_vintage}
              。当前版本可能修订历史；没有建立当时可见的数据版本。
            </p>
            <details>
              <summary>来源组合的归一化收益路径（月频）</summary>
              <p>
                按公布的月收益归一化为1；这不是独立重建交易的净值，月度回撤不包含月内最低点。
              </p>
              <EquityChart points={row.curve} />
            </details>
            <ExternalLink url={row.metrics.source_url}>
              核对作者数据来源
            </ExternalLink>
          </div>
        )),
      )}
    </section>
  );
}
function CompactResult({ run, variant }: { run: string; variant: string }) {
  const request = useApi<CorpusDetail>(
    `${base}/implementations/${encodeURIComponent(variant)}?run_id=${encodeURIComponent(run)}`,
  );
  if (request.loading) return <Loading />;
  if (request.error || !request.data)
    return (
      <ErrorState
        error={request.error || "结果暂不可读"}
        retry={request.retry}
      />
    );
  const d = request.data;
  return (
    <div>
      <p>{fidelityLabel(d.fidelity_class)} · 基础成本，历史全段</p>
      <MetricTable
        rows={[
          {
            label: d.name,
            metrics: (d.metrics.presentation_periods || d.metrics.periods)
              ?.full,
          },
        ]}
      />
      <p className="pw-reading-basis">
        批次 {run}。不同区间、资产和费用不能直接按收益排名。
      </p>
    </div>
  );
}
export function LegacyResearchEntry() {
  const [params] = useSearchParams();
  const variant = params.get("variant"),
    run = params.get("run_id") || "";
  if (variant) return <LegacyImplementation variant={variant} run={run} />;
  const id = params.get("record") || params.get("q") || "";
  return /^M\d{4}$/.test(id) ? (
    <LegacyRecord id={id} run={run} />
  ) : (
    <Navigate
      replace
      to={`/strategies${id ? "?q=" + encodeURIComponent(id) : ""}`}
    />
  );
}
function LegacyImplementation({
  variant,
  run,
}: {
  variant: string;
  run: string;
}) {
  const request = useApi<CorpusDetail>(
    `${base}/implementations/${encodeURIComponent(variant)}?run_id=${encodeURIComponent(run)}`,
  );
  if (request.loading) return <Loading />;
  if (request.error || !request.data)
    return (
      <ErrorState
        error={request.error || "历史实现不可用"}
        retry={request.retry}
      />
    );
  return (
    <LegacyRecord
      id={request.data.id}
      variant={variant}
      run={request.data.run_id}
    />
  );
}
function LegacyRecord({
  id,
  run,
  variant,
}: {
  id: string;
  run: string;
  variant?: string;
}) {
  const request = useApi<{ items: PersonalItem[] }>(
    `/v1/web/search?kind=strategy&q=${encodeURIComponent(id)}&collapse_templates=false&page_size=100`,
  );
  if (request.loading) return <Loading />;
  if (request.error || !request.data)
    return (
      <ErrorState
        error={request.error || "关联条目暂不可用"}
        retry={request.retry}
      />
    );
  const item = request.data.items.find((item) => nativeResearchId(item) === id);
  if (!item)
    return (
      <div>
        <p>该历史实验仍被保留，但当前 Catalog 未找到相同原生 ID 的条目。</p>
        {variant && <DetailLoader run={run} variant={variant} />}
        <Link to="/strategies">返回策略目录</Link>
      </div>
    );
  const params = new URLSearchParams();
  if (run) params.set("research_run", run);
  if (variant) params.set("research_variant", variant);
  return (
    <Navigate
      replace
      to={`${personalPath(item)}${params.size ? "?" + params : ""}#research`}
    />
  );
}

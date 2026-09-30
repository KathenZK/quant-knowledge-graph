import { useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { useApi } from "./api";
import { ErrorState, Loading } from "./components";
import {
  DetailLoader,
  MetricTable,
  fidelityLabel,
  type CorpusDetail,
  type CorpusRecord,
} from "./CorpusResearch";
import type { PersonalDetail, PersonalItem } from "./personal-data";
import { personalPath } from "./personal-data";

const base = "/v1/personal/corpus-research";
export function nativeResearchId(item: PersonalItem) {
  if (item.kind !== "strategy") return undefined;
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
  const [params] = useSearchParams();
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
      {results.length > 0 && (
        <label className="pw-research-select">
          选择历史实现
          <select
            aria-label={`${item.name}的历史实现`}
            value={selected ? selection : ""}
            onChange={(e) => setSelection(e.target.value)}
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
        rows={[{ label: d.name, metrics: d.metrics.periods?.full }]}
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

import { useApi } from "./api";
import type { CorpusDetail } from "./CorpusResearch";

type QualityFlag = {
  overlay_id: string;
  asset: string;
  warning_zh: string;
  data_quality_status: string;
  strict_comparability_eligible: false;
  official_sources?: (string | { url?: string; title?: string })[];
};

export default function ResearchAssurance({
  detail,
}: {
  detail: CorpusDetail;
}) {
  const lineage = detail.lineage.declared_lineage as
    Record<string, unknown> | undefined;
  const origin = String(
    lineage?.source_run_manifest_sha256 ||
      detail.lineage.source_run_manifest_sha256 ||
      "",
  );
  const request = useApi<QualityFlag[]>(
    `/v1/personal/corpus-research/data-quality?run_id=${encodeURIComponent(detail.origin_run_id || detail.run_id)}&variant_id=${encodeURIComponent(detail.variant_id)}&origin_manifest_sha256=${encodeURIComponent(origin)}`,
  );
  const flags = Array.isArray(request.data) ? request.data : [];
  const unavailable =
    request.error || (request.data && !Array.isArray(request.data));
  const vehicle =
    detail.metrics.evidence_subtype === "FUND_VEHICLE_BUY_HOLD_PROXY" ||
    detail.spec.evidence_subtype === "FUND_VEHICLE_BUY_HOLD_PROXY";
  const pitUnresolved =
    vehicle ||
    detail.metrics.original_method_reproduction_status ===
      "PIT_CONSTITUENT_METHOD_UNRESOLVED";
  return (
    <section className="pw-research-assurance" aria-label="研究可信度边界">
      <h3>这份结果能证明到哪一步</h3>
      {unavailable && (
        <p className="cr-warning">
          最新数据质量注解暂不可读；不能据此判断数据已严格通过。
          <button onClick={request.retry}>重试</button>
        </p>
      )}
      {request.loading && <p className="pw-muted">正在读取数据质量补充核验…</p>}
      {flags.map((flag) => (
        <div className="cr-warning" key={`${flag.overlay_id}|${flag.asset}`}>
          <strong>数据生命周期待核验 · 暂不具备严格可比性</strong>
          <p>{flag.warning_zh}</p>
          {flag.official_sources?.map((sourceRef, index) => {
            const source =
              typeof sourceRef === "string" ? { url: sourceRef } : sourceRef;
            return source.url && /^https:\/\//.test(source.url) ? (
              <p key={index}>
                <a href={source.url} target="_blank" rel="noreferrer">
                  {source.title || "官方来源"}
                </a>
              </p>
            ) : null;
          })}
        </div>
      ))}
      {vehicle && (
        <p className="cr-warning">
          本项测试的是基金载体买入持有代理。原方法的历史成分、当时可得信息和调仓逻辑尚未复现，不能把代理收益称为原策略收益。
        </p>
      )}
      <dl className="pw-definition-grid">
        <dt>数据质量</dt>
        <dd>
          {flags.length
            ? "存在版本绑定的待核验事项，详见上方警示"
            : "保留输入与来源哈希；逐项数据完整性、公司行动和证券生命周期仍需核验"}
        </dd>
        <dt>当时可得信息（PIT）</dt>
        <dd>
          {pitUnresolved
            ? "原方法的历史成分／可得时点未解决"
            : "本页未给出完整 PIT 通过认证，请核对该版本的信号时钟、发布日期与补充假设"}
        </dd>
        <dt>实现忠实度</dt>
        <dd>
          {(detail.fidelity_class === "HYPOTHESIS"
            ? "假设性实现，需要单独验证补充假设"
            : detail.fidelity_class === "PROXY"
              ? "代理实现，原方法尚待复现"
              : undefined) ||
            "执行版本的标准化规则、代理和补充假设单独记录；已执行不代表忠实复现原作"}
        </dd>
        <dt>统计证据</dt>
        <dd>
          历史筛查与成本敏感性属于探索证据；未证明排除多重检验、选择偏差或未来失效
        </dd>
      </dl>
    </section>
  );
}

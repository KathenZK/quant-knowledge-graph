import { ExternalLink } from "./components";

export type Interpretation = {
  interpretation_version: string;
  record_id: string;
  actual_tested_rule: string;
  source_and_implementation_differences: string;
  observed_findings: { text: string; evidence_kind: string }[];
  mechanism_hypothesis: { text: string; verification_status: string };
  failure_or_applicability_conditions: string;
  robustness_scope: string;
  unverified_claims: string[];
  research_priority: { category: string; reason: string };
  next_falsification_test: string;
  source_url?: string;
  evidence_bindings: {
    origin_run_id: string;
    variant_id: string;
    origin_manifest_sha256: string;
    collection_manifest_sha256: string;
  }[];
};

export default function ResearchInterpretation({
  rows,
  selected,
}: {
  rows: Interpretation[];
  selected?: {
    origin_run_id: string;
    variant_id: string;
    manifest_sha256: string;
  };
}) {
  const visible = selected
    ? rows.filter((row) =>
        row.evidence_bindings.some(
          (b) =>
            b.origin_run_id === selected.origin_run_id &&
            b.variant_id === selected.variant_id &&
            b.collection_manifest_sha256 === selected.manifest_sha256,
        ),
      )
    : rows;
  return (
    <section className="pw-reading-section">
      <h3>这次研究说明了什么</h3>
      {!visible.length ? (
        <p>
          这个版本尚无人工研究总结。已有执行指标和对结果的理解分别计数；未补造“有效”或“无效”的结论。
        </p>
      ) : (
        visible.map((row) => (
          <div key={row.interpretation_version}>
            <p className="pw-reading-basis">
              研究整理，不是原作者背书；仅对应下面明确绑定的实现与样本。
            </p>
            <dl className="pw-reader-facts">
              <div>
                <dt>实际测了什么</dt>
                <dd>{row.actual_tested_rule}</dd>
              </div>
              <div>
                <dt>与来源有哪些差别</dt>
                <dd>{row.source_and_implementation_differences}</dd>
              </div>
              <div>
                <dt>观察到的结果</dt>
                <dd>
                  {row.observed_findings.map((finding, i) => (
                    <p key={i}>{finding.text}</p>
                  ))}
                </dd>
              </div>
              <div>
                <dt>什么情况下可能失效</dt>
                <dd>{row.failure_or_applicability_conditions}</dd>
              </div>
              <div>
                <dt>费用与敏感性检查</dt>
                <dd>{row.robustness_scope}</dd>
              </div>
              <div>
                <dt>可能赚的是什么钱</dt>
                <dd>
                  {row.mechanism_hypothesis.text}
                  <small className="pw-reading-basis">
                    机制假说，尚未证明因果关系或未来盈利。
                  </small>
                </dd>
              </div>
              <div>
                <dt>是否值得继续深研</dt>
                <dd>{row.research_priority.reason}</dd>
              </div>
              <div>
                <dt>下一步怎样验证</dt>
                <dd>{row.next_falsification_test}</dd>
              </div>
            </dl>
            <details>
              <summary>仍未验证的内容与版本依据</summary>
              <ul>
                {row.unverified_claims.map((claim, i) => (
                  <li key={i}>{claim}</li>
                ))}
              </ul>
              <p>
                整理版本：{row.interpretation_version}
                。新的回测版本不会自动继承这些结论。
              </p>
              {row.evidence_bindings.map((b) => (
                <p
                  key={`${b.origin_run_id}|${b.variant_id}|${b.collection_manifest_sha256}`}
                >
                  {b.origin_run_id} · {b.variant_id}
                  <br />
                  原实验清单：{b.origin_manifest_sha256}
                  <br />
                  Graph导入清单：{b.collection_manifest_sha256}
                </p>
              ))}
              <ExternalLink url={row.source_url}>原始来源入口</ExternalLink>
            </details>
          </div>
        ))
      )}
    </section>
  );
}

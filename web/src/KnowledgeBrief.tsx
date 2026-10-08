import { readable } from "./personal-data";
import type { PersonalDetail } from "./personal-data";
import { ExternalLink } from "./components";

export default function KnowledgeBrief({ item }: { item: PersonalDetail }) {
  const brief = item.knowledge?.reader_brief;
  const strategy = item.kind === "strategy";
  if (!brief)
    return (
      <section className="pw-reading-section" id="overview">
        <h2>这项方法做什么</h2>
        <p>{item.knowledge?.summary || "现有资料尚未生成可核对的用途说明。"}</p>
        <p>完整规则与来源保留在下方；没有补写缺失的盈利解释。</p>
      </section>
    );
  return (
    <div className="pw-reader-brief">
      <section className="pw-reading-section" id="overview">
        <h2>{strategy ? "1. 这项策略做什么" : "1. 这个因子测什么"}</h2>
        <p className="pw-reader-purpose">{brief.purpose}</p>
        <p className="pw-reading-basis">{brief.purpose_basis}</p>
        {item.factor_quality && (
          <div className="pw-source-review">
            <strong>{item.factor_quality.label}</strong>
            <p>{item.factor_quality.review_label}</p>
            {item.factor_quality.source_body_label && (
              <p>原来源访问：{item.factor_quality.source_body_label}</p>
            )}
            {item.factor_quality.base_definition_label && (
              <p>定义依据：{item.factor_quality.base_definition_label}</p>
            )}
            <p>{item.factor_quality.paper_scope_label}</p>
            <p>
              有解释、与源码吻合、能复现计算、已经验证收益，是四个不同的判断。
            </p>
            {item.factor_quality.metadata_corrections?.map((fix) => (
              <p key={fix.version}>元数据已修正：{fix.basis}</p>
            ))}
          </div>
        )}
        {brief.review_notice && (
          <p className="pw-reading-basis">{brief.review_notice}</p>
        )}
        {brief.entry_type &&
          [
            "research_model",
            "development_fixture",
            "signal_component",
          ].includes(brief.entry_type) && (
            <p className="pw-reading-basis">
              资料类型：
              {
                {
                  research_model: "研究模型",
                  development_fixture: "开发样例",
                  signal_component: "规则组件",
                }[brief.entry_type as "research_model"]
              }
              。不计作已经验证的独立交易策略。
            </p>
          )}
        {brief.intake_status && (
          <p className="pw-reading-basis">
            本次采集状态：
            {brief.intake_label ||
              {
                SOURCE_VERIFIED_WITH_EXPLICIT_VARIANT:
                  "来源已核对，保留实现差异",
                SOURCE_VERIFIED_EXPLICIT_IMPLEMENTATION:
                  "定义已核对，实现口径单列",
                QUARANTINE: "待补证候选",
                ADMIT_VARIANT: "规则合同已准入，研究结果另审",
              }[brief.intake_status] ||
              brief.intake_status}
            。资料收录与执行准入分别判断。
          </p>
        )}
      </section>
      <section className="pw-reading-section" id="trading">
        <h2>
          {strategy ? "2. 交易什么，怎样进出场" : "2. 怎样计算，用在哪些场景"}
        </h2>
        {item.factor_quality?.calculation_explanation && (
          <div className="pw-reader-example">
            <strong>
              {item.factor_quality.group === "definition_references"
                ? "相关定义的阅读说明（尚未绑定为本条可执行公式）"
                : "逐条计算释义"}
            </strong>
            <p>{item.factor_quality.calculation_explanation}</p>
            {item.factor_quality.numeric_meaning && (
              <p>数值怎样理解：{item.factor_quality.numeric_meaning}</p>
            )}
            {item.factor_quality.strategy_use && (
              <p>怎样用于研究：{item.factor_quality.strategy_use}</p>
            )}
            {item.factor_quality.failure_modes && (
              <p>使用限制：{item.factor_quality.failure_modes}</p>
            )}
            {item.factor_quality.data_timing && (
              <p>何时可用：{item.factor_quality.data_timing}</p>
            )}
            {item.factor_quality.reference_template?.definition_source_url && (
              <p>
                <ExternalLink
                  url={
                    item.factor_quality.reference_template.definition_source_url
                  }
                >
                  相关定义出处
                </ExternalLink>{" "}
                · {item.factor_quality.reference_template.source_locator}
              </p>
            )}
            {item.factor_quality.source_comparisons?.map((source) => (
              <p key={source.native_id}>
                <ExternalLink url={source.source_url}>
                  {source.native_id} · 已对照的源码位置
                </ExternalLink>
              </p>
            ))}
            {!!item.factor_quality.missing_facts.length && (
              <details>
                <summary>仍需核实什么</summary>
                <ul>
                  {item.factor_quality.missing_facts.map((fact) => (
                    <li key={fact}>{fact}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
        <dl className="pw-reader-facts">
          {brief.trading.map((fact) => (
            <div key={fact.key}>
              <dt>{fact.label}</dt>
              <dd>
                {fact.text}
                {fact.origin && (
                  <small className="pw-reading-basis">
                    {fact.origin === "MANUAL_REVIEW_SUMMARY_UNBOUND"
                      ? "人工审读摘要，尚未逐字段绑定"
                      : fact.origin === "RESEARCH_DESIGN_SUGGESTION"
                        ? "研究用途建议，非原作者交易结论"
                        : `内容依据：${fact.origin}；核对状态：${fact.status}`}
                  </small>
                )}
                {fact.status.toUpperCase() === "UNKNOWN" && (
                  <span className="pw-unknown-label">待补资料</span>
                )}
              </dd>
            </div>
          ))}
        </dl>
        {brief.worked_example && (
          <p className="pw-reader-example">
            {brief.worked_example.text}
            <small>{brief.worked_example.basis}</small>
          </p>
        )}
        <p className="pw-reading-basis">
          {strategy
            ? "这里整理已有条件，不补造仓位、成交价格或退出规则。"
            : "计算窗口不等于预测期或持仓期。跨市场使用需要单独验证。"}
        </p>
      </section>
      <section className="pw-reading-section" id="rationale">
        <h2>3. 论文与盈利依据</h2>
        <h3>为什么可能有效</h3>
        <p>{brief.economic_rationale.text}</p>
        {brief.economic_rationale.status !== "UNKNOWN" && (
          <p className="pw-reading-basis">
            {brief.economic_rationale.status.startsWith("AUTHOR_")
              ? "作者提出的解释；历史相关性不等于已识别因果。"
              : "来源说明或研究解释；尚未作为因果与收益证明核验。"}
          </p>
        )}
        <p className="pw-reading-basis">{brief.economic_rationale.notice}</p>
        {brief.source_review_summary && (
          <p className="pw-source-review">
            本次来源核对：{brief.source_review_summary}
          </p>
        )}
        {brief.economic_rationale.source_locator && (
          <p className="pw-reading-basis">
            解释定位：{brief.economic_rationale.source_locator}{" "}
            <ExternalLink url={brief.economic_rationale.source_url}>
              原文
            </ExternalLink>
          </p>
        )}
        <h3>哪份材料支持什么</h3>
        {brief.papers.length ? (
          brief.papers.map((paper, index) => (
            <div className="pw-paper-evidence" key={paper.paper_id || index}>
              <strong>{paper.relationship}</strong>
              <p>
                <ExternalLink url={paper.url}>{paper.title}</ExternalLink>
                {paper.year ? ` · ${paper.year}` : ""}
              </p>
              <p>{paper.claim}</p>
              {paper.version_read && (
                <p className="pw-reading-basis">
                  实际阅读版本：{paper.version_read}
                </p>
              )}
              {paper.does_not_support?.map((text, index) => (
                <p className="pw-reading-basis" key={index}>
                  不支持的推论：{text}
                </p>
              ))}
              <p className="pw-reading-basis">
                {paper.locator
                  ? `来源记录的位置：${paper.locator}`
                  : "具体公式、页码或实证表位置：当前未收录"}
              </p>
            </div>
          ))
        ) : (
          <p>
            当前没有保存可核对的论文书目与具体实证位置。网页或代码出处保留如下，不替代论文证据。
          </p>
        )}
        {!!brief.definition_sources?.length && (
          <div className="pw-definition-evidence">
            <h3>定义与实现的直接出处</h3>
            {brief.definition_sources.map((source, index) => (
              <p key={index}>
                <ExternalLink url={source.url}>
                  {source.locator || "原始定义"}
                </ExternalLink>
                ：{source.supports?.join("；") || "支持范围未单独说明"}
              </p>
            ))}
          </div>
        )}
        {!!brief.evidence_links?.length && (
          <details>
            <summary>逐项来源短引文与定位</summary>
            {brief.evidence_links.map((source, index) => (
              <div className="pw-paper-evidence" key={source.claim_id || index}>
                <p>
                  <ExternalLink url={source.url}>
                    {source.locator || "打开原始来源"}
                  </ExternalLink>
                </p>
                {source.quote && <p>{source.quote}</p>}
                {source.supports && (
                  <p>支持范围：{readable(source.supports)}</p>
                )}
                <small>来源摘要：{source.source_sha256 || "未提供"}</small>
              </div>
            ))}
          </details>
        )}
        {brief.empirical_scope && (
          <details>
            <summary>论文的样本、持有期与成本边界</summary>
            <p>{readable(brief.empirical_scope)}</p>
          </details>
        )}
        <ExternalLink url={brief.source_url}>
          查看原始网页或代码出处
        </ExternalLink>
        <p className="pw-reading-basis">{brief.empirical_notice}</p>
        {brief.blocked_reasons?.map((reason, index) => (
          <p key={index}>待补：{reason}</p>
        ))}
        {brief.validation && (
          <details>
            <summary>本次定义、数据和验证状态</summary>
            <p>{readable(brief.validation)}</p>
          </details>
        )}
      </section>
    </div>
  );
}

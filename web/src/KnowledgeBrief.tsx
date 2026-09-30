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
            本次采集状态：{brief.intake_status}。资料收录与执行准入分别判断。
          </p>
        )}
      </section>
      <section className="pw-reading-section" id="trading">
        <h2>
          {strategy ? "2. 交易什么，怎样进出场" : "2. 怎样计算，用在哪些场景"}
        </h2>
        <dl className="pw-reader-facts">
          {brief.trading.map((fact) => (
            <div key={fact.key}>
              <dt>{fact.label}</dt>
              <dd>
                {fact.text}
                {fact.origin && (
                  <small className="pw-reading-basis">
                    {fact.origin === "RESEARCH_DESIGN_SUGGESTION"
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
            来源中的解释，尚未作为因果或收益证明核验。
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

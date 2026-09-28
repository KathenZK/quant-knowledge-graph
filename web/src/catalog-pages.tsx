import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, useApi } from "./api";
import {
  ErrorState,
  ExternalLink,
  Loading,
  Parameters,
  Values,
  entityUrl,
  kindLabel,
} from "./components";
import type {
  EntityRef,
  Item,
  Kind,
  RelationGraph,
  SavedItem,
  SearchResult,
  StrategyKnowledge,
  StudySummary,
} from "./types";

export function StrategyRules({ value }: { value: StrategyKnowledge }) {
  const labels: Record<string, string> = {
    entry: "入场与信号",
    exit: "退出与切换",
    position: "仓位",
    rebalance: "观察 / 换仓",
    cash: "现金处理",
    execution: "执行时点",
    costs: "成本",
    unknowns: "未知项",
  };
  return (
    <section className="panel">
      <h2>策略规则与已知边界</h2>
      <p>{value.original_rule_notice}</p>
      {value.original_rule && <blockquote>{value.original_rule}</blockquote>}
      <dl className="facts">
        {Object.keys(labels).map((key) => {
          const val = value.facts[key];
          return (
            <div key={key}>
              <dt>{labels[key] || key}</dt>
              <dd>
                <Values value={val} />
              </dd>
            </div>
          );
        })}
      </dl>
      <details>
        <summary>查看来源支持的结构化规则</summary>
        <Parameters value={value.structured_rule || {}} />
      </details>
      <h3>出处与变体分别判断</h3>
      <dl className="facts">
        <div>
          <dt>来源支持程度</dt>
          <dd>
            {value.source_support} · {value.provenance_type}
            <small>{value.provenance_evidence}</small>
          </dd>
        </div>
        <div>
          <dt>报告的来源作者</dt>
          <dd>
            {value.source_author || "未补充"}
            <small>这不是当前派生策略作者的认证。</small>
          </dd>
        </div>
        <div>
          <dt>当前变体作者</dt>
          <dd>{value.variant_author || "未核实"}</dd>
        </div>
        <div>
          <dt>变化轴</dt>
          <dd>
            <Values value={value.variation_axes} />
          </dd>
        </div>
        <div>
          <dt>解析状态</dt>
          <dd>
            {value.parse_status}
            <small>{value.parse_reason}</small>
          </dd>
        </div>
        <div>
          <dt>研究假设</dt>
          <dd>
            <Values value={value.research_hypotheses} />
          </dd>
        </div>
      </dl>
    </section>
  );
}

export function SummaryStudy({ study }: { study: StudySummary }) {
  return (
    <article className="panel">
      <h3>
        {study.study_type} · {study.conclusion_level}
      </h3>
      <p>
        {study.study_kind} / {study.status}。研究结果不代表买入建议或实盘资格。
      </p>
      <p>
        运行 <code>{study.run_id}</code> ·{" "}
        <Link to={`/jobs/${study.job_id}`}>任务状态</Link>
      </p>
      <h4>定义与版本</h4>
      {study.entity_refs.map((ref) => (
        <p key={ref.entity_id}>
          <Link
            to={entityUrl({
              kind:
                ref.entity_type === "StrategyVariant" ? "strategy" : "variant",
              entity_id: ref.entity_id,
            })}
          >
            {ref.entity_id}
          </Link>
          <br />
          <code>{ref.definition_revision}</code>
        </p>
      ))}
      <h4>样本与数据</h4>
      <Parameters value={study.sample} />
      <h4>实际指标</h4>
      {study.numerical_display === "RESTRICTED" ? (
        <p className="notice">
          研究已实际运行；数值指标受数据展示权限限制。登录后可在任务页查看获准的内部研究证据。
        </p>
      ) : (
        <Parameters value={study.metrics} />
      )}
      <h4>限制</h4>
      <ul>
        {study.limitations.map((text, i) => (
          <li key={i}>{text}</li>
        ))}
      </ul>
      {study.evolution && (
        <section>
          <h4>有依据的演化</h4>
          <dl className="facts">
            <div>
              <dt>改造理由</dt>
              <dd>
                <Values value={study.evolution.reason} />
              </dd>
            </div>
            <div>
              <dt>具体变化</dt>
              <dd>
                <Values value={study.evolution.change} />
              </dd>
            </div>
            <div>
              <dt>解释与限制</dt>
              <dd>
                <Values value={study.evolution.interpretation} />
              </dd>
            </div>
            <div>
              <dt>执行状态</dt>
              <dd>
                {study.evolution.outcome || "未补充"}
                <small>SUCCESS 表示运行成功，不代表盈利或改造显著有效。</small>
              </dd>
            </div>
          </dl>
        </section>
      )}
      {study.lineage.length > 0 && (
        <>
          <h4>父子研究脉络</h4>
          {study.lineage.map((ref) => (
            <p key={ref.entity_id}>
              <Link
                to={entityUrl({
                  kind:
                    ref.entity_type === "StrategyVariant"
                      ? "strategy"
                      : "variant",
                  entity_id: ref.entity_id,
                })}
              >
                {ref.entity_id}
              </Link>{" "}
              · {ref.definition_revision}
            </p>
          ))}
        </>
      )}
    </article>
  );
}

export function RelationsPage() {
  const [params, setParams] = useSearchParams();
  const eid = params.get("id");
  return (
    <>
      <header className="page-title">
        <div>
          <div className="eyebrow">RELATIONS / 关系浏览</div>
          <h1>沿着证据，继续探索。</h1>
          <p>
            策略 → 因子 → 其他策略。语义关系与实证相关性分别展示，最多展开两跳。
          </p>
        </div>
      </header>
      {eid ? (
        <RelationExplorer eid={eid} key={eid} />
      ) : (
        <RelationStart onPick={(id) => setParams({ id })} />
      )}
    </>
  );
}
function RelationStart({ onPick }: { onPick: (id: string) => void }) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const result = useApi<SearchResult>(
    `/v1/web/search?kind=strategy&q=${encodeURIComponent(search)}&page_size=8`,
  );
  return (
    <section className="panel">
      <form
        className="searchbar"
        onSubmit={(e) => {
          e.preventDefault();
          setSearch(query);
        }}
      >
        <label htmlFor="relation-search">从一个策略开始</label>
        <input
          id="relation-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button>搜索</button>
      </form>
      {result.loading ? (
        <Loading />
      ) : result.error ? (
        <ErrorState error={result.error} />
      ) : (
        result.data?.items.map((item) => (
          <p key={item.entity_id}>
            <button
              className="text-button"
              onClick={() => onPick(item.entity_id)}
            >
              {item.name} →
            </button>
          </p>
        ))
      )}
    </section>
  );
}
function RelationExplorer({ eid }: { eid: string }) {
  const [hops, setHops] = useState(1),
    [relation, setRelation] = useState(""),
    [offset, setOffset] = useState(0);
  const data = useApi<RelationGraph>(
    `/v1/web/relations/${encodeURIComponent(eid)}?hops=${hops}&relation=${encodeURIComponent(relation)}&offset=${offset}&limit=24`,
  );
  const types = [
    "VARIANT_OF",
    "IN_FAMILY",
    "USES_FACTOR",
    "PARAMETER_VARIANT",
    "ASSET_VARIANT",
    "DERIVED_FROM",
    "DESCRIBES",
    "RELATED_TO",
    "CATEGORY_LINK_ONLY",
    "SAME_AS",
    "IMPLEMENTATION_OF",
  ];
  const nodes = data.data?.nodes || [];
  const positions = new Map(
    nodes.map((n, i) => [
      n.entity_id,
      { x: 80 + (i % 3) * 290, y: 60 + Math.floor(i / 3) * 110 },
    ]),
  );
  return (
    <>
      <div className="panel relation-controls">
        <label>
          展开范围
          <select
            value={hops}
            onChange={(e) => {
              setHops(Number(e.target.value));
              setOffset(0);
            }}
          >
            <option value={1}>一跳</option>
            <option value={2}>两跳</option>
          </select>
        </label>
        <label>
          关系类型
          <select
            value={relation}
            onChange={(e) => {
              setRelation(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">全部</option>
            {types.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <p>
          当前页最多 24 条边。点击节点打开详情；使用“继续探索”改变中心节点。
        </p>
      </div>
      {data.loading ? (
        <Loading />
      ) : data.error ? (
        <ErrorState error={data.error} retry={data.retry} />
      ) : (
        data.data && (
          <>
            <section className="panel">
              <h2>
                关系图 <span>{data.data.total} 条可见关系</span>
              </h2>
              <div
                className="graph-scroll"
                role="region"
                aria-label="可点击关系图"
                tabIndex={0}
              >
                <svg
                  viewBox={`0 0 900 ${Math.max(240, Math.ceil(nodes.length / 3) * 110 + 40)}`}
                  role="group"
                  aria-label="知识关系图；等价的关系列表位于下方"
                >
                  {data.data.items.map((edge) => {
                    const a = positions.get(edge.from_id)!,
                      b = positions.get(edge.to_id)!;
                    return (
                      <line
                        key={edge.relationship_id}
                        x1={a.x + 100}
                        y1={a.y}
                        x2={b.x + 100}
                        y2={b.y}
                        className="graph-edge"
                      />
                    );
                  })}
                  {nodes.map((node) => {
                    const p = positions.get(node.entity_id)!;
                    return (
                      <a
                        key={node.entity_id}
                        href={entityUrl(node)}
                        aria-label={`打开 ${node.name}`}
                      >
                        <g transform={`translate(${p.x},${p.y - 30})`}>
                          <rect
                            width="215"
                            height="66"
                            rx="8"
                            className={
                              node.entity_id === eid
                                ? "graph-node current"
                                : "graph-node"
                            }
                          />
                          <title>{node.name}</title>
                          <text x="12" y="23">
                            {node.name.length > 19
                              ? node.name.slice(0, 19) + "…"
                              : node.name}
                          </text>
                          <text x="12" y="45" className="graph-kind">
                            {kindLabel[node.kind]}
                          </text>
                        </g>
                      </a>
                    );
                  })}
                </svg>
              </div>
            </section>
            <section className="panel">
              <h2>可核对的关系列表</h2>
              <div className="relationship-list">
                {data.data.items.map((edge) => (
                  <article key={edge.relationship_id}>
                    <div className="relation-path">
                      <Link
                        to={entityUrl({
                          kind: edge.from_kind!,
                          entity_id: edge.from_id,
                        })}
                      >
                        {edge.from_name}
                      </Link>
                      <strong>{edge.relation}</strong>
                      <Link
                        to={entityUrl({
                          kind: edge.to_kind!,
                          entity_id: edge.to_id,
                        })}
                      >
                        {edge.to_name}
                      </Link>
                    </div>
                    <p>{edge.evidence}</p>
                    <small>
                      {edge.review_status || edge.status} · 置信度{" "}
                      {edge.confidence} · {edge.version || "见来源版本"}
                    </small>
                    <p>
                      <ExternalLink url={edge.source}>来源依据</ExternalLink>
                    </p>
                    <div className="actions">
                      <Link
                        to={`/relations?id=${encodeURIComponent(edge.from_id)}`}
                      >
                        从左侧继续探索
                      </Link>
                      <Link
                        to={`/relations?id=${encodeURIComponent(edge.to_id)}`}
                      >
                        从右侧继续探索
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
              {!data.data.items.length && (
                <p>没有此类公开关系；未据此推断等价或收益贡献。</p>
              )}
              <div className="pagination">
                <button
                  disabled={!offset}
                  onClick={() => setOffset(Math.max(0, offset - 24))}
                >
                  上一页
                </button>
                <span>
                  {offset + 1}–{Math.min(offset + 24, data.data.total)} /{" "}
                  {data.data.total}
                </span>
                <button
                  disabled={offset + 24 >= data.data.total}
                  onClick={() => setOffset(offset + 24)}
                >
                  下一页
                </button>
              </div>
            </section>
          </>
        )
      )}
      <p className="notice">
        RULE_LINK_ONLY 只说明规则使用，不是收益归因。RELATED_TO 和同族不代表
        SAME_AS。
      </p>
    </>
  );
}

interface Capability {
  profile_id: string;
  study_type: string;
  entity_types: string[];
  max_entities: number;
  max_trials: number;
  max_seconds: number;
  worker_available: boolean;
}
interface Job {
  job_id: string;
  run_id: string;
  status: string;
  progress: number;
  stage: string;
  error: string | { code: string; message: string } | null;
  worker_available: boolean;
  result_url: string;
  entity_refs: EntityRef[];
  timestamps: Record<string, string | null>;
}
export function SubmitResearch({ items }: { items: SavedItem[] }) {
  const capabilities = useApi<{ items: Capability[] }>(
    "/v1/research/capabilities",
  );
  const [profile, setProfile] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [job, setJob] = useState<Job>();
  const selected = capabilities.data?.items.find(
    (p) => p.profile_id === profile,
  );
  const eligible = selected
    ? items.filter((i) => selected.entity_types.includes(i.entity_type))
    : [];
  async function submit() {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      const request = await api<Record<string, unknown>>(
        "/v1/web/research-requests",
        {
          method: "POST",
          body: JSON.stringify({
            entity_refs: eligible.map(
              ({ entity_type, entity_id, definition_revision }) => ({
                entity_type,
                entity_id,
                definition_revision,
              }),
            ),
            study_type: selected.study_type,
            requested_settings: { profile_id: profile },
          }),
        },
      );
      const result = await api<Job>("/v1/research/jobs", {
        method: "POST",
        body: JSON.stringify(request),
      });
      setJob(result);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "提交失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>提交受控研究</h2>
      <p>
        使用服务端登记的数据与预算配置。需要<Link to="/admin">管理员登录</Link>
        ；匿名浏览不会启动计算。
      </p>
      {capabilities.loading ? (
        <Loading />
      ) : capabilities.error ? (
        <ErrorState error={capabilities.error} retry={capabilities.retry} />
      ) : (
        <>
          <label>
            研究能力
            <select
              value={profile}
              onChange={(e) => setProfile(e.target.value)}
            >
              <option value="">选择已登记能力</option>
              {capabilities.data?.items.map((p) => (
                <option key={p.profile_id} value={p.profile_id}>
                  {p.study_type} · {p.profile_id}
                </option>
              ))}
            </select>
          </label>
          {!capabilities.data?.items.length && (
            <p>服务端尚未配置研究能力。仍可导出正式请求。</p>
          )}
          {selected && (
            <p>
              符合类型的引用 {eligible.length} 个，单次最多{" "}
              {selected.max_entities} 个；预算最多 {selected.max_trials} 次实验
              / {selected.max_seconds} 秒。Worker：
              {selected.worker_available
                ? "在线"
                : "当前离线，提交后等待 worker"}
              。
            </p>
          )}
          <button
            className="primary"
            disabled={
              busy ||
              !selected ||
              eligible.length === 0 ||
              eligible.length > selected.max_entities
            }
            onClick={() => void submit()}
          >
            {busy ? "正在提交…" : "提交研究请求"}
          </button>
        </>
      )}
      {message && <p role="alert">{message}</p>}
      {job && (
        <p role="status">
          已登记 {job.status}。
          <Link to={`/jobs/${job.job_id}`}>查看任务与运行状态 →</Link>
        </p>
      )}
    </section>
  );
}
function InternalEvidence({ id }: { id: string }) {
  const data = useApi<{ items: Record<string, unknown>[]; visibility: string }>(
    `/v1/research/jobs/${encodeURIComponent(id)}/evidence`,
  );
  return (
    <section className="panel">
      <h2>内部研究证据</h2>
      <p>仅当前获授权会话可见；不代表获得公开传播行情或衍生指标的权利。</p>
      {data.loading ? (
        <Loading />
      ) : data.error ? (
        <ErrorState error={data.error} retry={data.retry} />
      ) : (
        data.data?.items.map((value, i) => (
          <details key={i} open>
            <summary>
              结果 {i + 1} ·{" "}
              {String(value.run_id || value.research_run_id || "")}
            </summary>
            <Parameters value={value} />
          </details>
        ))
      )}
    </section>
  );
}
export function JobPage() {
  const { id } = useParams();
  const [evidence, setEvidence] = useState(false);
  const job = useApi<Job>(`/v1/research/jobs/${encodeURIComponent(id || "")}`);
  const [error, setError] = useState("");
  useEffect(() => {
    if (
      !job.data ||
      ["SUCCEEDED", "FAILED", "BLOCKED", "PARTIAL", "CANCELLED"].includes(
        job.data.status,
      )
    )
      return;
    const timer = setTimeout(job.retry, 5000);
    return () => clearTimeout(timer);
  }, [job.data, job.retry]);
  async function cancel() {
    try {
      await api(`/v1/research/jobs/${id}/cancel`, { method: "POST" });
      job.retry();
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <>
      <header className="page-title">
        <div>
          <div className="eyebrow">RESEARCH / 持久任务</div>
          <h1>研究任务状态</h1>
          <p>任务登记、实际计算和可展示结果是不同阶段。</p>
        </div>
      </header>
      {job.loading && !job.data ? (
        <Loading />
      ) : job.error ? (
        <ErrorState error={job.error} retry={job.retry} />
      ) : (
        job.data && (
          <section className="panel">
            <h2>
              {job.data.status} · {job.data.stage}
            </h2>
            <p>
              进度 {Math.round(job.data.progress * 100)}% · Worker{" "}
              {job.data.worker_available ? "在线" : "离线 / 尚未启动"}
            </p>
            <progress value={job.data.progress} max={1} />
            <dl className="facts">
              <div>
                <dt>任务 ID</dt>
                <dd>{job.data.job_id}</dd>
              </div>
              <div>
                <dt>运行 ID</dt>
                <dd>{job.data.run_id}</dd>
              </div>
              <div>
                <dt>可读错误</dt>
                <dd>
                  {typeof job.data.error === "object" && job.data.error
                    ? `${job.data.error.code}: ${job.data.error.message}`
                    : job.data.error || "无"}
                </dd>
              </div>
            </dl>
            <Parameters value={job.data.timestamps} />
            {job.data.entity_refs.map((ref) => (
              <p key={ref.entity_id}>
                <Link
                  to={entityUrl({
                    kind:
                      ref.entity_type === "StrategyVariant"
                        ? "strategy"
                        : "variant",
                    entity_id: ref.entity_id,
                  })}
                >
                  返回原知识条目查看结果 →
                </Link>
              </p>
            ))}
            <button onClick={job.retry}>刷新状态</button>
            <button onClick={() => setEvidence(true)}>查看内部研究证据</button>
            <button
              disabled={[
                "SUCCEEDED",
                "FAILED",
                "BLOCKED",
                "PARTIAL",
                "CANCELLED",
              ].includes(job.data.status)}
              onClick={() => void cancel()}
            >
              取消任务
            </button>
          </section>
        )
      )}
      {evidence && id && <InternalEvidence id={id} />}
      {error && <p role="alert">{error}</p>}
    </>
  );
}

export function AdminPage() {
  const [authenticated, setAuthenticated] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  async function login() {
    try {
      await api("/v1/admin/session", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      setPassword("");
      setAuthenticated(true);
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <>
      <header className="page-title">
        <div>
          <div className="eyebrow">ADMIN / 内容管理</div>
          <h1>管理知识，保留历史。</h1>
          <p>
            公开状态独立于研究准入。隐藏不能撤回历史下载，也不会改写研究
            artifact。
          </p>
        </div>
      </header>
      {!authenticated ? (
        <form
          className="panel admin-login"
          onSubmit={(e) => {
            e.preventDefault();
            void login();
          }}
        >
          <h2>管理员登录</h2>
          <p>凭证由部署者在服务端配置；登录后使用仅限同源的会话 Cookie。</p>
          <label>
            管理密码
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <button className="primary">登录后台</button>
          <button
            type="button"
            onClick={() => {
              void api("/v1/admin/session")
                .then(() => setAuthenticated(true))
                .catch((e) => setError(String(e)));
            }}
          >
            恢复已有会话
          </button>
          {error && <p role="alert">{error}</p>}
        </form>
      ) : (
        <>
          <button
            onClick={() => {
              void api("/v1/admin/session", { method: "DELETE" }).then(() =>
                setAuthenticated(false),
              );
            }}
          >
            退出管理
          </button>
          <AdminWorkspace />
        </>
      )}
    </>
  );
}
function AdminWorkspace() {
  const [tab, setTab] = useState("catalog");
  return (
    <>
      <div className="tabs">
        {[
          ["catalog", "条目与关系"],
          ["imports", "导入与错误"],
          ["research", "研究任务"],
          ["merges", "合并建议"],
          ["audit", "操作审计"],
        ].map(([key, label]) => (
          <button
            key={key}
            aria-pressed={tab === key}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "catalog" ? (
        <AdminCatalog />
      ) : tab === "imports" ? (
        <AdminImports />
      ) : tab === "research" ? (
        <AdminJobs />
      ) : tab === "merges" ? (
        <AdminSuggestions />
      ) : (
        <AdminAudit />
      )}
    </>
  );
}
function AdminCatalog() {
  const [kind, setKind] = useState<Kind>("strategy"),
    [q, setQ] = useState(""),
    [query, setQuery] = useState(""),
    [page, setPage] = useState(1),
    [selected, setSelected] = useState<string[]>([]),
    [editing, setEditing] = useState<Item>(),
    [message, setMessage] = useState("");
  const result = useApi<SearchResult>(
    `/v1/admin/catalog?kind=${kind}&q=${encodeURIComponent(query)}&page=${page}`,
  );
  async function visibility(value: string) {
    try {
      await api("/v1/admin/catalog", {
        method: "PATCH",
        body: JSON.stringify({ ids: selected, patch: { visibility: value } }),
      });
      setMessage(`已更新 ${selected.length} 个条目为 ${value}`);
      setSelected([]);
      result.retry();
    } catch (e) {
      setMessage(String(e));
    }
  }
  return (
    <section className="panel">
      <h2>策略 / 因子 / 关系</h2>
      <form
        className="searchbar"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(q);
          setPage(1);
        }}
      >
        <label>
          条目类型
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value as Kind);
              setPage(1);
              setSelected([]);
            }}
          >
            <option value="strategy">策略</option>
            <option value="variant">因子变体</option>
            <option value="concept">因子概念</option>
          </select>
        </label>
        <label>
          检索
          <input value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <button>查找</button>
      </form>
      <div className="actions">
        <button
          disabled={!selected.length}
          onClick={() => void visibility("HIDDEN")}
        >
          批量隐藏 ({selected.length})
        </button>
        <button
          disabled={!selected.length}
          onClick={() => void visibility("PUBLIC")}
        >
          重新公开 ({selected.length})
        </button>
      </div>
      {message && <p role="status">{message}</p>}
      {result.loading ? (
        <Loading />
      ) : result.error ? (
        <ErrorState error={result.error} />
      ) : (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>选择</th>
                  <th>名称</th>
                  <th>公开状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {result.data?.items.map((item) => (
                  <tr key={item.entity_id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`选择 ${item.name}`}
                        checked={selected.includes(item.entity_id)}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? [...selected, item.entity_id]
                              : selected.filter((id) => id !== item.entity_id),
                          )
                        }
                      />
                    </td>
                    <td>
                      {item.name}
                      <small>{item.source_native_ids.join(" / ")}</small>
                    </td>
                    <td>{item.visibility}</td>
                    <td>
                      <button onClick={() => setEditing(item)}>
                        编辑与审核
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <button disabled={page === 1} onClick={() => setPage(page - 1)}>
              上一页
            </button>
            <span>
              {result.data?.total} 条 · 第 {page} 页
            </span>
            <button
              disabled={page * 20 >= (result.data?.total || 0)}
              onClick={() => setPage(page + 1)}
            >
              下一页
            </button>
          </div>
        </>
      )}
      {editing && (
        <AdminEdit
          item={editing}
          key={editing.entity_id}
          done={() => {
            setEditing(undefined);
            result.retry();
          }}
        />
      )}
    </section>
  );
}
function AdminEdit({ item, done }: { item: Item; done: () => void }) {
  const [name, setName] = useState(item.name),
    [aliases, setAliases] = useState(item.aliases.join("\n")),
    [description, setDescription] = useState(item.description || ""),
    [source, setSource] = useState(item.source_url || ""),
    [message, setMessage] = useState(""),
    [merge, setMerge] = useState(""),
    [reason, setReason] = useState("");
  const relations = useApi<RelationGraph>(
    `/v1/admin/relations/${encodeURIComponent(item.entity_id)}`,
  );
  async function save() {
    try {
      await api("/v1/admin/catalog", {
        method: "PATCH",
        body: JSON.stringify({
          ids: [item.entity_id],
          patch: {
            name,
            aliases: aliases
              .split("\n")
              .map((x) => x.trim())
              .filter(Boolean),
            description,
            source_url: source,
          },
        }),
      });
      done();
    } catch (e) {
      setMessage(String(e));
    }
  }
  async function review(rid: string, patch: Record<string, unknown>) {
    try {
      await api("/v1/admin/relations/" + rid, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      relations.retry();
      setMessage("关系审核已记录");
    } catch (e) {
      setMessage(String(e));
    }
  }
  async function suggest() {
    try {
      await api("/v1/admin/merge-suggestions", {
        method: "POST",
        body: JSON.stringify({ left: item.entity_id, right: merge, reason }),
      });
      setMessage("合并建议已登记；定义和历史引用未改写。");
    } catch (e) {
      setMessage(String(e));
    }
  }
  return (
    <section className="admin-editor panel">
      <h3>编辑知识元信息</h3>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <label>
          名称
          <input
            value={name}
            maxLength={500}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          别名（每行一个）
          <textarea
            value={aliases}
            maxLength={3000}
            onChange={(e) => setAliases(e.target.value)}
          />
        </label>
        <label>
          独立说明 / 错误修正
          <textarea
            value={description}
            maxLength={3000}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <label>
          来源链接
          <input
            value={source}
            maxLength={2000}
            onChange={(e) => setSource(e.target.value)}
          />
        </label>
        <p>
          修正规则内容请在“导入与错误”提交相同原生 ID 的新版本；不覆盖原始快照。
        </p>
        <button className="primary">保存元信息</button>
        <button type="button" onClick={done}>
          关闭编辑
        </button>
      </form>
      <h3>关系审核</h3>
      {relations.data?.items.map((edge) => (
        <article className="admin-edge" key={edge.relationship_id}>
          <p>
            {edge.from_name} → {edge.relation} → {edge.to_name}
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              void review(edge.relationship_id, {
                evidence: String(data.get("evidence") || ""),
              });
            }}
          >
            <label>
              关系依据
              <textarea
                name="evidence"
                defaultValue={edge.evidence}
                maxLength={3000}
              />
            </label>
            <button>保存关系依据</button>
          </form>
          <small>
            {edge.review_status} · {edge.version}
          </small>
          <div className="actions">
            <button
              onClick={() =>
                void review(edge.relationship_id, { review_status: "REVIEWED" })
              }
            >
              标记已核对
            </button>
            <button
              onClick={() =>
                void review(edge.relationship_id, {
                  review_status: "CANDIDATE",
                })
              }
            >
              保留为候选
            </button>
            <button
              onClick={() =>
                void review(edge.relationship_id, { visibility: "HIDDEN" })
              }
            >
              隐藏关系
            </button>
            <button
              onClick={() =>
                void review(edge.relationship_id, { visibility: "PUBLIC" })
              }
            >
              公开关系
            </button>
          </div>
        </article>
      ))}
      <h3>合并建议</h3>
      <label>
        目标实体 ID
        <input value={merge} onChange={(e) => setMerge(e.target.value)} />
      </label>
      <label>
        证据与理由
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <button disabled={!merge || !reason} onClick={() => void suggest()}>
        登记合并建议
      </button>
      {message && <p role="status">{message}</p>}
    </section>
  );
}
interface ImportStatus {
  dispositions: {
    source: string;
    disposition: string;
    is_test: number;
    count: number;
  }[];
  failed: { record_id: string; reason: string }[];
  imports: {
    import_id: number;
    created_at: string;
    status: string;
    processed: number;
    errors: number;
    reason: string;
  }[];
}
function AdminImports() {
  const status = useApi<ImportStatus>("/v1/admin/imports");
  const [text, setText] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  async function ingest() {
    setBusy(true);
    try {
      const value = JSON.parse(text);
      const result = await api<{
        accepted: number;
        revision: number;
        duplicate: number;
      }>("/v1/admin/imports/grokbot", {
        method: "POST",
        body: JSON.stringify(value),
      });
      setMessage(
        `已处理：新增 ${result.accepted}，修订 ${result.revision}，重复 ${result.duplicate}`,
      );
      status.retry();
    } catch (e) {
      setMessage(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function retry() {
    setBusy(true);
    try {
      await api("/v1/admin/imports/retry", { method: "POST" });
      setMessage("重新处理完成");
      status.retry();
    } catch (e) {
      setMessage(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>导入对账与恢复</h2>
      {status.loading ? (
        <Loading />
      ) : status.error ? (
        <ErrorState error={status.error} />
      ) : (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>输入</th>
                  <th>去向</th>
                  <th>数量</th>
                </tr>
              </thead>
              <tbody>
                {status.data?.dispositions.map((r, i) => (
                  <tr key={i}>
                    <td>
                      {r.source}
                      {r.is_test ? "（测试）" : ""}
                    </td>
                    <td>{r.disposition}</td>
                    <td>{r.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>近期导入</h3>
          {status.data?.imports.map((r) => (
            <p key={r.import_id}>
              {r.created_at} · {r.status} · 处理 {r.processed} / 失败 {r.errors}{" "}
              · {r.reason}
            </p>
          ))}
          {status.data?.failed.map((r) => (
            <p key={r.record_id}>
              {r.record_id}：{r.reason}
            </p>
          ))}
        </>
      )}
      <button disabled={busy} onClick={() => void retry()}>
        重新处理投影与索引
      </button>
      <h3>新增批次 / 规则修订</h3>
      <p>
        沿用 ingestion 批次格式。相同 record_id
        的内容修订会保留旧版本；同批次重放不会重复计数。来源文本仅解析，不执行。
      </p>
      <label>
        GrokBot 批次 JSON
        <textarea
          className="code-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder='{"batch_id":"…","collector_version":"…","records":[…]}'
          maxLength={2000000}
        />
      </label>
      <button disabled={busy || !text} onClick={() => void ingest()}>
        导入到现有采集流程
      </button>
      {message && <p role="status">{message}</p>}
    </section>
  );
}
function AdminAudit() {
  const data = useApi<{
    items: {
      audit_id: number;
      created_at: string;
      actor: string;
      action: string;
      entity_id: string;
      before_json: string;
      after_json: string;
    }[];
  }>("/v1/admin/audit");
  return (
    <section className="panel">
      <h2>操作审计</h2>
      {data.loading ? (
        <Loading />
      ) : data.error ? (
        <ErrorState error={data.error} />
      ) : (
        data.data?.items.map((r) => (
          <details key={r.audit_id}>
            <summary>
              {r.created_at} · {r.actor} · {r.action}
            </summary>
            <p>{r.entity_id}</p>
            <pre>{r.before_json}</pre>
            <pre>{r.after_json}</pre>
          </details>
        ))
      )}
    </section>
  );
}

function AdminJobs() {
  const [offset, setOffset] = useState(0);
  const result = useApi<{
    items: {
      job_id: string;
      status: string;
      stage: string;
      study_type: string;
      progress: number;
    }[];
    total: number;
  }>(`/v1/admin/research-jobs?offset=${offset}`);
  return (
    <section className="panel">
      <h2>研究任务与结果</h2>
      <button onClick={result.retry}>刷新任务</button>
      {result.error && <ErrorState error={result.error} />}
      {result.data?.items.length === 0 && <p>尚未提交研究任务。</p>}
      {result.data?.items.map((job) => (
        <article className="admin-edge" key={job.job_id}>
          <Link to={`/jobs/${job.job_id}`}>
            {job.study_type} · {job.job_id}
          </Link>
          <p>
            {job.status} · {job.stage} · {Math.round(job.progress * 100)}%
          </p>
        </article>
      ))}
      <div className="actions">
        <button
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 25))}
        >
          上一页
        </button>
        <button
          disabled={offset + 25 >= (result.data?.total || 0)}
          onClick={() => setOffset(offset + 25)}
        >
          下一页
        </button>
      </div>
    </section>
  );
}
function AdminSuggestions() {
  const result = useApi<{
    items: {
      suggestion_id: string;
      status: string;
      payload: { reason: string };
      left: Pick<Item, "name" | "kind" | "entity_id"> | null;
      right: Pick<Item, "name" | "kind" | "entity_id"> | null;
    }[];
  }>("/v1/admin/merge-suggestions");
  const [message, setMessage] = useState("");
  async function review(id: string, status: string) {
    try {
      await api(`/v1/admin/merge-suggestions/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      result.retry();
      setMessage("审核已记录，历史定义引用保持不变。");
    } catch (error) {
      setMessage(String(error));
    }
  }
  return (
    <section className="panel">
      <h2>合并建议审核</h2>
      <p>
        审核仅记录判断。实际定义合并需要来源证据和新的定义版本，不能覆盖历史研究引用。
      </p>
      {result.error && <ErrorState error={result.error} />}
      {message && <p role="status">{message}</p>}
      {result.data?.items.length === 0 && <p>尚无合并建议。</p>}
      {result.data?.items.map((item) => (
        <article className="admin-edge" key={item.suggestion_id}>
          <p>
            {item.left ? (
              <Link to={entityUrl(item.left)}>{item.left.name}</Link>
            ) : (
              "条目不可用"
            )}{" "}
            →{" "}
            {item.right ? (
              <Link to={entityUrl(item.right)}>{item.right.name}</Link>
            ) : (
              "条目不可用"
            )}
          </p>
          <p>{item.payload.reason}</p>
          <small>{item.status}</small>
          <div className="actions">
            <button onClick={() => void review(item.suggestion_id, "REVIEWED")}>
              标记已核对
            </button>
            <button onClick={() => void review(item.suggestion_id, "REJECTED")}>
              拒绝建议
            </button>
            <button onClick={() => void review(item.suggestion_id, "PENDING")}>
              重新待审
            </button>
          </div>
        </article>
      ))}
    </section>
  );
}

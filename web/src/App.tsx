import { useEffect, useState, type ReactNode } from "react";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Bookmark,
  Check,
  Columns2,
  Download,
  FlaskConical,
  Network,
  Search,
  ShieldCheck,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { api, useApi } from "./api";
import {
  Actions,
  Empty,
  ErrorState,
  ExternalLink,
  Formula,
  Loading,
  ResearchResults,
  Statuses,
  TypeTag,
  Values,
  Parameters,
  entityUrl,
  kindLabel,
} from "./components";
import {
  bookmark,
  download,
  loadNotebook,
  parseNotebook,
  refKey,
  saveNotebook,
  storageKey,
} from "./storage";
import type {
  Detail,
  Item,
  Kind,
  Meta,
  Notebook,
  Results,
  SavedItem,
  SearchResult,
} from "./types";

import {
  AdminPage,
  ResearchCollections,
  JobPage,
  RelationsPage,
  StrategyRules,
  SubmitResearch,
} from "./catalog-pages";

type CompareRef = { kind: Kind; entity_id: string; name: string };
type Workbench = {
  saved: SavedItem[];
  compare: CompareRef[];
  onSave: (item: Item) => void;
  onCompare: (item: Item) => void;
};
const compareUrl = (refs: CompareRef[]) =>
  "/compare?" +
  new URLSearchParams(
    refs.map((r) => ["ref", `${r.kind}/${r.entity_id}`]),
  ).toString();
function initialCompare(): CompareRef[] {
  return new URLSearchParams(window.location.search)
    .getAll("ref")
    .slice(0, 4)
    .flatMap((ref) => {
      const [kind, entity_id] = ref.split("/");
      return ["variant", "concept", "strategy"].includes(kind) && entity_id
        ? [{ kind: kind as Kind, entity_id, name: entity_id }]
        : [];
    });
}
function PageTitle({
  eyebrow,
  title,
  children,
  action,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <header className="page-title">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{children}</p>
      </div>
      {action}
    </header>
  );
}
function ItemActions({ item, bench }: { item: Item; bench: Workbench }) {
  if (!["variant", "concept", "strategy"].includes(item.kind)) return null;
  return (
    <Actions
      item={item}
      saved={bench.saved.some((s) => refKey(s) === refKey(item))}
      compared={bench.compare.some(
        (c) => c.entity_id === item.entity_id && c.kind === item.kind,
      )}
      onSave={bench.onSave}
      onCompare={bench.onCompare}
    />
  );
}
export default function App() {
  const meta = useApi<Meta>("/v1/web/meta");
  if (meta.loading) return <Loading />;
  if (!meta.data)
    return <ErrorState error={meta.error || "服务不可用"} retry={meta.retry} />;
  return <WorkbenchApp key={meta.data.mode} mode={meta.data.mode} />;
}
function WorkbenchApp({ mode }: { mode: "PUBLIC" | "PRIVATE" }) {
  const meta = useApi<Meta>("/v1/web/meta");
  const [notebook, setNotebook] = useState(() => loadNotebook(mode));
  const [compare, setCompare] = useState<CompareRef[]>(initialCompare);
  const [message, setMessage] = useState("");
  const location = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === storageKey(mode)) setNotebook(loadNotebook(mode));
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, [mode]);
  function updateSaved(items: SavedItem[], recover = false) {
    if (notebook.error && !recover) {
      setMessage("请先在研究清单页面恢复备份或重置损坏的存储。");
      return false;
    }
    if (items.length > 500) {
      setMessage("本地清单最多保存 500 个定义引用。");
      return false;
    }
    try {
      saveNotebook(items, mode);
      setNotebook({ items });
      return true;
    } catch {
      setMessage("浏览器存储不可用或空间不足，变更未保存。请先导出备份。");
      return false;
    }
  }
  const bench: Workbench = {
    saved: notebook.items,
    compare,
    onSave: (item) => {
      const found = notebook.items.some((s) => refKey(s) === refKey(item));
      if (
        updateSaved(
          found
            ? notebook.items.filter((s) => refKey(s) !== refKey(item))
            : [...notebook.items, bookmark(item)],
        )
      )
        setMessage(
          found
            ? `已取消收藏 ${item.name}`
            : `已加入清单：${item.name}。仅保存在此浏览器。`,
        );
    },
    onCompare: (item) => {
      if (
        compare.some(
          (c) => c.entity_id === item.entity_id && c.kind === item.kind,
        )
      )
        setCompare(
          compare.filter(
            (c) => c.entity_id !== item.entity_id || c.kind !== item.kind,
          ),
        );
      else if (compare.length < 4)
        setCompare([
          ...compare,
          { kind: item.kind, entity_id: item.entity_id, name: item.name },
        ]);
      else setMessage("最多比较 4 个条目，请先移除一个。");
    },
  };
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        跳到主要内容
      </a>
      <aside className="sidebar">
        <Link className="brand" to="/explore">
          <Network size={27} aria-hidden="true" />
          <span>
            QuantGraph<small>量化知识工作台</small>
          </span>
        </Link>
        <div className="nav-label">研究工作区</div>
        <nav aria-label="主导航">
          <NavLink to="/explore">
            <Search size={19} aria-hidden="true" />
            搜索与浏览
          </NavLink>
          <NavLink to={compareUrl(compare)}>
            <Columns2 size={19} aria-hidden="true" />
            条目比较<span className="nav-count">{compare.length}</span>
          </NavLink>
          <NavLink to="/list">
            <Bookmark size={19} aria-hidden="true" />
            研究清单<span className="nav-count">{notebook.items.length}</span>
          </NavLink>
          <NavLink to="/relations">
            <Network size={19} aria-hidden="true" />
            关系浏览
          </NavLink>
          <NavLink to="/admin">
            <ShieldCheck size={19} aria-hidden="true" />
            管理后台
          </NavLink>
          <NavLink to="/results">
            <FlaskConical size={19} aria-hidden="true" />
            研究结果
          </NavLink>
        </nav>
        <div className="sidebar-note">
          <ShieldCheck size={20} aria-hidden="true" />
          <strong>
            {mode === "PUBLIC" ? "公开知识模式" : "私有本机研究模式"}
          </strong>
          <p>
            可追溯的定义与来源。
            <br />
            研究证据单独判断。
          </p>
          <a href="/v1/web/license" target="_blank" rel="noreferrer">
            来源许可与归属 ↗
          </a>
        </div>
        <div className="sidebar-bottom">
          QUANT PLATFORM<span>KNOWLEDGE → RESEARCH</span>
        </div>
      </aside>
      <div className="workspace">
        <div className="topbar">
          <span>
            <BookOpen size={16} aria-hidden="true" />
            知识库 / 研究工作台
          </span>
          <span className="public-badge">
            <span className="dot green" />
            {mode} · 本地浏览器清单
          </span>
        </div>
        <main id="main" tabIndex={-1}>
          {meta.loading ? (
            <Loading />
          ) : meta.error ? (
            <ErrorState error={meta.error} retry={meta.retry} />
          ) : (
            meta.data && (
              <Routes>
                <Route path="/" element={<Navigate replace to="/explore" />} />
                <Route
                  path="/explore"
                  element={<Explore meta={meta.data} bench={bench} />}
                />
                <Route
                  path="/entity/:kind/:id"
                  element={<DetailPage bench={bench} />}
                />
                <Route path="/compare" element={<ComparePage />} />
                <Route
                  path="/list"
                  element={
                    <NotebookPage
                      meta={meta.data}
                      items={notebook.items}
                      error={notebook.error}
                      update={updateSaved}
                      notify={setMessage}
                    />
                  }
                />
                <Route path="/results" element={<ResultsPage meta={meta} />} />
                <Route path="/relations" element={<RelationsPage />} />
                <Route path="/admin" element={<AdminPage />} />
                <Route path="/jobs/:id" element={<JobPage />} />
                <Route
                  path="*"
                  element={
                    <Empty title="页面不存在">
                      <Link to="/explore">返回知识库</Link>
                    </Empty>
                  }
                />
              </Routes>
            )
          )}
          <footer>
            定义收录 ≠ 收益验证。所有数量来自当前服务端可见内容。
            {meta.data && (
              <span>
                Release <code>{meta.data.release}</code> · Graph{" "}
                {meta.data.graph_api}
              </span>
            )}
          </footer>
        </main>
      </div>
      {message && (
        <div className="toast" role="status">
          <Check size={18} aria-hidden="true" />
          <span>{message}</span>
          <button aria-label="关闭提示" onClick={() => setMessage("")}>
            <X size={16} />
          </button>
        </div>
      )}
      {compare.length > 0 && location.pathname !== "/compare" && (
        <div className="compare-dock">
          <Columns2 size={18} aria-hidden="true" />
          <span>已选 {compare.length} / 4</span>
          <div className="compare-chips">
            {compare.map((c) => (
              <button
                key={c.entity_id}
                onClick={() => setCompare(compare.filter((x) => x !== c))}
                aria-label={`移除比较 ${c.name}`}
              >
                {c.name.startsWith("qkg:") ? kindLabel[c.kind] : c.name}
                <X size={12} />
              </button>
            ))}
          </div>
          {compare.length >= 2 ? (
            <Link className="button primary" to={compareUrl(compare)}>
              开始比较 <ArrowRight size={16} />
            </Link>
          ) : (
            <span className="muted">再选一个条目</span>
          )}
        </div>
      )}
    </div>
  );
}
function Explore({ meta, bench }: { meta: Meta; bench: Workbench }) {
  const [params, setParams] = useSearchParams();
  const defaultKind = meta.counts.strategy > 0 ? "strategy" : "variant";
  const kind = (params.get("kind") || defaultKind) as Kind;
  const [query, setQuery] = useState(params.get("q") || "");
  useEffect(() => setQuery(params.get("q") || ""), [params]);
  const current = new URLSearchParams(params);
  if (!current.has("kind")) current.set("kind", defaultKind);
  const result = useApi<SearchResult>("/v1/web/search?" + current.toString());
  function setFilter(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    if (name !== "page") next.delete("page");
    setParams(next);
  }
  const page = result.data?.page || 1;
  return (
    <>
      <PageTitle eyebrow="EXPLORE / 知识检索" title="从策略出发，沿证据研究。">
        浏览真实采集的策略与因子，比较规则差异，沿关系追溯来源与研究。
      </PageTitle>
      <section className="overview" aria-label="当前公开库统计">
        {[
          ["因子变体", meta.counts.variant, "保留参数差异"],
          ["概念族", meta.counts.concept, "同族不代表等价"],
          ["策略记录", meta.counts.strategy, "采集记录 ≠ 独立策略"],
          ["研究结果", meta.result_count, "独立于定义准入"],
        ].map(([label, num, note]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{num}</strong>
            <small>{note}</small>
          </div>
        ))}
      </section>
      <section className="catalog">
        <div className="catalog-head">
          <div className="tabs" role="group" aria-label="条目类型">
            {(
              [
                "variant",
                "concept",
                "strategy",
                ...(meta.adapter_version === "catalog/v1" ? ["source"] : []),
              ] as Kind[]
            ).map((k) => (
              <button
                key={k}
                aria-pressed={kind === k}
                className={kind === k ? "active" : ""}
                onClick={() => setFilter("kind", k)}
              >
                {kindLabel[k]}
                <span>{meta.counts[k]}</span>
              </button>
            ))}
          </div>
          <span className="muted small">知识默认公开 · 受限附件另行控制</span>
        </div>
        <form
          className="searchbar"
          onSubmit={(event) => {
            event.preventDefault();
            setFilter("q", query.trim());
          }}
        >
          <Search size={21} aria-hidden="true" />
          <label className="sr-only" htmlFor="search-input">
            搜索名称、英文别名或描述
          </label>
          <input
            id="search-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索名称、英文别名或描述，如：均线、MA5、Alpha158:MA5"
            maxLength={200}
          />
          <button className="primary" type="submit">
            搜索
          </button>
        </form>
        <div className="filters">
          {[
            ["category", "方法类别", meta.facets.categories],
            ["family", "方法族", meta.facets.families],
            ["field", "所需数据", meta.facets.fields],
            ["market", "市场", meta.facets.markets],
            ...(meta.facets.frequencies
              ? [["frequency", "频率", meta.facets.frequencies]]
              : []),
            ...(meta.facets.source_types
              ? [["source_type", "来源类型", meta.facets.source_types]]
              : []),
            [
              "result_status",
              "研究状态",
              [
                { value: "unresearched", label: "无可展示研究记录" },
                { value: "researched", label: "有研究记录" },
              ],
            ],
          ].map(([name, label, options]) => (
            <label key={name as string}>
              {label as string}
              <select
                value={params.get(name as string) || ""}
                onChange={(e) => setFilter(name as string, e.target.value)}
              >
                <option value="">全部</option>
                {(options as { value: string; label: string }[]).map(
                  (option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ),
                )}
              </select>
            </label>
          ))}
          <button
            className="text-button"
            onClick={() => {
              setQuery("");
              setParams({ kind });
            }}
          >
            清除筛选
          </button>
        </div>
        <div className="result-meta">
          <span role="status">
            {result.data ? (
              <>
                找到 <strong>{result.data.total}</strong> 个
                {kindLabel[kind] || "条目"}
              </>
            ) : (
              "正在查询…"
            )}
          </span>
          <span>排序：名称 / 别名相关性 · 不按收益排名</span>
        </div>
        {result.loading ? (
          <Loading />
        ) : result.error ? (
          <ErrorState error={result.error} retry={result.retry} />
        ) : !result.data?.items.length ? (
          <Empty
            title={
              kind === "strategy" && !meta.counts.strategy
                ? "当前公开库暂无策略"
                : "没有找到匹配条目"
            }
          >
            <p>试试其他名称、英文别名，或清除筛选条件。</p>
            <p>未公开的记录不会出现在搜索数量或关联关系中。</p>
          </Empty>
        ) : (
          <div
            className="table-scroll"
            role="region"
            aria-label="搜索结果表格"
            tabIndex={0}
          >
            <table className="results-table">
              <thead>
                <tr>
                  <th scope="col">名称与定义</th>
                  <th scope="col">方法与类型</th>
                  <th scope="col">所需数据</th>
                  <th scope="col">研究状态</th>
                  <th scope="col">操作</th>
                </tr>
              </thead>
              <tbody>
                {result.data.items.map((item) => (
                  <tr key={item.entity_id}>
                    <td>
                      <Link className="entity-name" to={entityUrl(item)}>
                        {item.test_record ? "[验收测试] " : ""}
                        {item.name}
                        <ArrowUpRight size={14} aria-hidden="true" />
                      </Link>
                      <div className="alias-line">
                        {item.aliases.slice(0, 3).join(" · ") ||
                          item.family_label}
                      </div>
                      {item.kind === "strategy" ? (
                        <p className="strategy-summary">{item.description}</p>
                      ) : (
                        <Formula value={item.formula} />
                      )}
                    </td>
                    <td>
                      <TypeTag kind={item.kind} />
                      <div className="cell-secondary">
                        {item.category_label}
                        {item.family && ` / ${item.family}`}
                      </div>
                    </td>
                    <td>
                      <div className="field-tags">
                        {item.required_fields.map((f) => (
                          <code key={f}>{f}</code>
                        ))}
                      </div>
                      <div className="cell-secondary">
                        {item.markets.includes("equity")
                          ? "股票 · equity"
                          : item.markets.join(" · ") || "未补充"}
                      </div>
                    </td>
                    <td>
                      <span className="status-label">
                        <span className="dot" />
                        {item.statuses.result}
                      </span>
                      <div className="cell-secondary">
                        已收录 · 查看证据与权限
                      </div>
                    </td>
                    <td>
                      <ItemActions item={item} bench={bench} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {result.data && result.data.total > 0 && (
          <div className="pagination">
            <span>
              每页 {result.data.page_size} 条 · 第 {page} /{" "}
              {Math.ceil(result.data.total / result.data.page_size)} 页
            </span>
            <div>
              <button
                disabled={page <= 1}
                onClick={() => setFilter("page", String(page - 1))}
              >
                <ArrowLeft size={15} />
                上一页
              </button>
              <button
                disabled={page * result.data.page_size >= result.data.total}
                onClick={() => setFilter("page", String(page + 1))}
              >
                下一页
                <ArrowRight size={15} />
              </button>
            </div>
          </div>
        )}
      </section>
      <p className="footnote">
        中文检索包含界面词汇映射；来源名称与原生别名保持原样。概念族、参数变体和完整策略分别建模。
      </p>
    </>
  );
}
function DetailPage({ bench }: { bench: Workbench }) {
  const { kind, id } = useParams();
  const result = useApi<Detail>(
    `/v1/web/entities/${encodeURIComponent(kind || "")}/${encodeURIComponent(id || "")}`,
  );
  if (result.loading) return <Loading />;
  if (result.error || !result.data)
    return (
      <ErrorState error={result.error || "条目不存在"} retry={result.retry} />
    );
  const item = result.data;
  return (
    <>
      <Link className="back-link" to="/explore">
        <ArrowLeft size={16} />
        返回知识库
      </Link>
      <PageTitle
        eyebrow="DEFINITION / 定义与证据"
        title={item.name}
        action={<ItemActions item={item} bench={bench} />}
      >
        {item.aliases.join(" · ") || item.family_label || "来源原生名称"}
      </PageTitle>
      <div className="detail-subtitle">
        <TypeTag kind={item.kind} />
        <span>{item.category_label}</span>
        <span>{item.source_name || "来源未补充"}</span>
      </div>
      <Statuses item={item} />
      <div className="detail-grid">
        <div>
          {item.strategy && <StrategyRules value={item.strategy} />}
          <section className="panel">
            <h2>
              {item.kind === "strategy" ? "策略知识与数据需求" : "定义与计算"}
            </h2>
            {item.kind === "strategy" ? (
              <p>规则来自采集证据和既有解析，缺失的交易假设保持待补充。</p>
            ) : item.kind === "concept" ? (
              <p>
                来源内的概念族，用于组织相关定义。成员之间不自动构成数学等价关系。
              </p>
            ) : (
              <p>
                以下是来源中保存的原始定义表达式。参数和数据字段来自该定义，公式只展示，不在网页执行。
              </p>
            )}
            {item.kind !== "strategy" && (
              <div className="formula-block">
                <span>
                  原始公式 <small>{item.source_name}</small>
                </span>
                <Formula value={item.formula} />
              </div>
            )}
            <dl className="facts">
              <div>
                <dt>来源描述</dt>
                <dd>
                  <Values value={item.description} />
                </dd>
              </div>
              <div>
                <dt>中文方法词汇</dt>
                <dd>
                  {item.family_label || "未补充"}
                  <small>仅用于检索和阅读，不是收益机制证据。</small>
                </dd>
              </div>
              <div>
                <dt>计算维度</dt>
                <dd>{item.axis}</dd>
              </div>
              <div>
                <dt>参数</dt>
                <dd>
                  <Parameters value={item.parameters} />
                </dd>
              </div>
              <div>
                <dt>所需数据</dt>
                <dd>
                  {item.required_fields.join(" / ") || "未补充"}
                  <small>仅从语法抽取，仍需行情和数据口径审核。</small>
                </dd>
              </div>
              <div>
                <dt>历史输入跨度</dt>
                <dd>
                  {item.lookback
                    ? `${item.lookback.value} 条观测（含当前条；结构推导，未运行验证）`
                    : "未补充"}
                </dd>
              </div>
              <div>
                <dt>频率 / 市场</dt>
                <dd>
                  {item.frequency === "daily"
                    ? "日频"
                    : item.frequency || "未补充"}{" "}
                  / {item.markets.join(", ") || "未补充"}
                </dd>
              </div>
              <div>
                <dt>经济逻辑</dt>
                <dd>
                  <Values value={item.economic_logic} />
                  {!item.economic_logic && (
                    <small>没有来源证据时不补写收益驱动解释。</small>
                  )}
                </dd>
              </div>
            </dl>
          </section>
          <section className="panel">
            <h2>
              实现与差异 <span>{item.implementations.length}</span>
            </h2>
            {item.implementations.length ? (
              item.implementations.map((impl) => (
                <div className="implementation" key={impl.implementation_id}>
                  <ExternalLink url={impl.code_url}>查看来源实现</ExternalLink>
                  <dl className="facts">
                    <div>
                      <dt>语言 / 状态</dt>
                      <dd>
                        {impl.language} / {impl.status}
                      </dd>
                    </div>
                    <div>
                      <dt>位置</dt>
                      <dd>{impl.source_locator}</dd>
                    </div>
                    <div>
                      <dt>版本</dt>
                      <dd>
                        <code>{impl.revision || "未补充"}</code>
                      </dd>
                    </div>
                    <div>
                      <dt>文件 SHA-256</dt>
                      <dd>
                        <code>{impl.sha256}</code>
                      </dd>
                    </div>
                  </dl>
                  <p className="muted">
                    来源配置已抽取，执行状态：
                    {impl.executed ? "来源记录标记已执行" : "未执行"}
                    。尚未证明不同实现计算等价。
                  </p>
                </div>
              ))
            ) : (
              <p className="muted">没有独立实现记录。</p>
            )}
          </section>
          <section className="panel">
            <h2>
              关系与证据 <span>{item.relations.length}</span>
            </h2>
            <Link
              className="button"
              to={`/relations?id=${encodeURIComponent(item.entity_id)}`}
            >
              打开关系图与两跳浏览 →
            </Link>
            <p className="muted">
              RELATED_TO / CATEGORY_LINK_ONLY 仅表示关联；RULE_LINK_ONLY
              仅表示规则引用，均不是等价或收益贡献证明。
            </p>
            {item.relations.length ? (
              <div className="relations">
                {item.relations.map((edge) => (
                  <details key={edge.relationship_id}>
                    <summary>
                      <code>{edge.relation}</code>
                      <span>
                        {edge.from_name || edge.from_type} →{" "}
                        {edge.to_name || edge.to_type}
                      </span>
                    </summary>
                    <dl className="facts">
                      <div>
                        <dt>原始证据</dt>
                        <dd>{edge.evidence}</dd>
                      </div>
                      <div>
                        <dt>置信度 / 状态</dt>
                        <dd>
                          {edge.confidence} / {edge.status}
                        </dd>
                      </div>
                      <div>
                        <dt>端点</dt>
                        <dd>
                          {edge.from_kind ? (
                            <Link
                              to={entityUrl({
                                kind: edge.from_kind,
                                entity_id: edge.from_id,
                              })}
                            >
                              {edge.from_name}
                            </Link>
                          ) : (
                            <code>{edge.from_id}</code>
                          )}
                          <br />
                          {edge.to_kind ? (
                            <Link
                              to={entityUrl({
                                kind: edge.to_kind,
                                entity_id: edge.to_id,
                              })}
                            >
                              {edge.to_name}
                            </Link>
                          ) : (
                            <code>{edge.to_id}</code>
                          )}
                        </dd>
                      </div>
                      <div>
                        <dt>来源</dt>
                        <dd>
                          <ExternalLink url={edge.source}>
                            {edge.source_label || "证据引用"}
                          </ExternalLink>
                        </dd>
                      </div>
                    </dl>
                  </details>
                ))}
              </div>
            ) : (
              <p className="muted">尚无可公开展示的关系。</p>
            )}
          </section>
          <section className="panel">
            <h2>研究记录</h2>
            <ResearchResults results={item.results} compact />
          </section>
        </div>
        <div>
          <section className="panel provenance">
            <h2>来源与定义版本</h2>
            <strong>{item.source_name || "见关联变体"}</strong>
            <p>
              <ExternalLink url={item.source_url}>原始来源</ExternalLink>
            </p>
            <dl className="facts vertical">
              <div>
                <dt>来源原生 ID</dt>
                <dd>
                  <Values value={item.source_native_ids} />
                </dd>
              </div>
              <div>
                <dt>作者</dt>
                <dd>{item.authors.join(", ") || "此定义未单独署名"}</dd>
              </div>
              <div>
                <dt>来源版本</dt>
                <dd>
                  <code>{item.source_revision || "见关联变体"}</code>
                </dd>
              </div>
              <div>
                <dt>定义引用版本</dt>
                <dd>
                  <code>{item.definition_revision}</code>
                  <small>按实际定义内容固定的书签版本。</small>
                </dd>
              </div>
              <div>
                <dt>实体 ID</dt>
                <dd>
                  <code>{item.entity_id}</code>
                </dd>
              </div>
              <div>
                <dt>来源定位</dt>
                <dd>{item.source_locator || "见关联变体"}</dd>
              </div>
            </dl>
            {item.papers.map((p) => (
              <div className="paper" key={p.paper_id}>
                <ExternalLink url={p.url}>{p.title || "来源文献"}</ExternalLink>
                <p>
                  {p.authors.join(", ")} · {p.year}
                </p>
                <small>集合级参考文献，不等于此公式的单独经济论证。</small>
              </div>
            ))}
          </section>
          <section className="panel rights">
            <ShieldCheck size={21} aria-hidden="true" />
            <h2>使用与展示权限</h2>
            {Object.entries(item.rights).map(([key, value]) => (
              <p key={key}>{value}</p>
            ))}
            {item.source_name?.toLowerCase().includes("qlib") && (
              <a href="/v1/web/license" target="_blank" rel="noreferrer">
                Qlib / Microsoft MIT 完整声明 ↗
              </a>
            )}
          </section>
          <section className="panel">
            <h2>
              相关定义与策略 <span>{item.related.length}</span>
            </h2>
            {item.concept && (
              <Link to={entityUrl(item.concept)}>{item.concept.name} →</Link>
            )}
            <p className="muted">参数或构造不同，不能视为完全相同。</p>
            <div className="related-list">
              {item.related.map((related) => (
                <div key={related.entity_id}>
                  <Link to={entityUrl(related)}>{related.name}</Link>
                  <button
                    aria-label={`比较 ${related.name}`}
                    onClick={() => bench.onCompare(related)}
                  >
                    <Columns2 size={14} />
                  </button>
                </div>
              ))}
            </div>
            {!item.related.length && <p>未补充</p>}
          </section>
          <section className="panel">
            <h2>相关策略</h2>
            {item.related_strategies.length ? (
              item.related_strategies.map((s) => (
                <Link
                  key={s.strategy_id}
                  to={entityUrl({ kind: "strategy", entity_id: s.strategy_id })}
                >
                  {s.canonical_name}
                </Link>
              ))
            ) : (
              <p className="muted">没有可公开展示的策略关联。</p>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
function ComparePage() {
  const [params] = useSearchParams();
  const refs = params.getAll("ref");
  return (
    <>
      <PageTitle eyebrow="COMPARE / 比较定义" title="先看差异，再提假设。">
        并排比较 2–4 个条目的规则、仓位、执行假设、公式、来源与研究状态。
      </PageTitle>
      {refs.length >= 2 && refs.length <= 4 ? (
        <CompareTable query={params.toString()} />
      ) : (
        <Empty title="选择至少两个条目">
          <p>在搜索结果或详情页点击“比较”，最多选择 4 个。</p>
          <Link className="button primary" to="/explore">
            去知识库选择
          </Link>
        </Empty>
      )}
    </>
  );
}
function CompareTable({ query }: { query: string }) {
  const result = useApi<{ items: Detail[] }>("/v1/web/compare?" + query);
  if (result.loading) return <Loading />;
  if (result.error || !result.data)
    return (
      <ErrorState error={result.error || "比较不可用"} retry={result.retry} />
    );
  const rows: [string, (item: Detail) => ReactNode][] = [
    ["类型", (item) => <TypeTag kind={item.kind} />],
    ["原始公式", (item) => <Formula value={item.formula} />],
    [
      "参数",
      (item) =>
        item.strategy ? (
          <details>
            <summary>查看来源中的结构化参数</summary>
            <Parameters value={item.parameters} />
          </details>
        ) : (
          <Parameters value={item.parameters} />
        ),
    ],
    ["入场逻辑", (item) => <Values value={item.strategy?.facts.entry} />],
    ["出场逻辑", (item) => <Values value={item.strategy?.facts.exit} />],
    [
      "仓位 / 现金",
      (item) => (
        <Values
          value={
            item.strategy
              ? {
                  position: item.strategy.facts.position,
                  cash: item.strategy.facts.cash,
                }
              : null
          }
        />
      ),
    ],
    [
      "执行 / 成本假设",
      (item) => (
        <Values
          value={
            item.strategy
              ? {
                  execution: item.strategy.facts.execution,
                  costs: item.strategy.facts.costs,
                }
              : null
          }
        />
      ),
    ],
    [
      "市场 / 频率",
      (item) => `${item.markets.join(" / ")} · ${item.frequency || "未补充"}`,
    ],
    ["变化轴", (item) => <Values value={item.strategy?.variation_axes} />],
    ["时序 / 截面", (item) => item.axis],
    ["所需数据", (item) => item.required_fields.join(" / ") || "未补充"],
    ["方法族", (item) => `${item.category_label} / ${item.family || "未补充"}`],
    [
      "来源 / 版本",
      (item) => (
        <>
          <ExternalLink url={item.source_url}>
            {item.source_name || "未补充"}
          </ExternalLink>
          <code className="block">{item.source_revision || "未补充"}</code>
        </>
      ),
    ],
    ["定义引用版本", (item) => <code>{item.definition_revision}</code>],
    [
      "实现差异",
      (item) =>
        item.implementations.length
          ? item.implementations.map((impl) => (
              <div key={impl.implementation_id}>
                <ExternalLink url={impl.code_url}>
                  {impl.language} · {impl.source_locator}
                </ExternalLink>
                <p>
                  {impl.status} · {impl.executed ? "来源标记执行" : "未执行"}
                </p>
              </div>
            ))
          : "未补充独立实现",
    ],
    ["经济逻辑", (item) => item.economic_logic || "未补充"],
    ["状态", (item) => <Statuses item={item} />],
  ];
  const strategyRows = [
    "入场逻辑",
    "出场逻辑",
    "仓位 / 现金",
    "执行 / 成本假设",
    "市场 / 频率",
    "变化轴",
  ];
  const hasStrategy = result.data.items.some(
    (item) => item.kind === "strategy",
  );
  const displayRows = hasStrategy
    ? [
        rows[0],
        ...strategyRows.map((label) => rows.find((row) => row[0] === label)!),
        ...rows.slice(1).filter((row) => !strategyRows.includes(row[0])),
      ]
    : rows.filter((row) => !strategyRows.includes(row[0]));
  return (
    <>
      <div className="notice">
        <ShieldCheck size={18} aria-hidden="true" />
        同名、同族或来源相同不构成等价证据。不同市场、成本或区间的研究收益不做排名。
      </div>
      <div
        className="table-scroll comparison"
        role="region"
        aria-label="条目比较表格"
        tabIndex={0}
      >
        <table>
          <thead>
            <tr>
              <th scope="col">比较维度</th>
              {result.data.items.map((item) => (
                <th scope="col" key={item.entity_id}>
                  <Link to={entityUrl(item)}>
                    {item.name}
                    <ArrowUpRightIcon />
                  </Link>
                  <span>{item.aliases[0] || item.family_label}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayRows.map(([label, render]) => (
              <tr key={label}>
                <th scope="row">{label}</th>
                {result.data!.items.map((item) => (
                  <td key={item.entity_id}>{render(item)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
function ArrowUpRightIcon() {
  return <ArrowRight size={14} aria-hidden="true" />;
}
function NotebookPage({
  meta,
  items,
  error,
  update,
  notify,
}: {
  meta: Meta;
  items: SavedItem[];
  error?: string;
  update: (items: SavedItem[], recover?: boolean) => boolean;
  notify: (message: string) => void;
}) {
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [importError, setImportError] = useState("");
  const [study, setStudy] = useState(
    items.some((i) => i.entity_type === "FactorVariant")
      ? "FACTOR_DIAGNOSTIC"
      : "STRATEGY_REPLICATION",
  );
  const [settings, setSettings] = useState({
    market: "",
    start_date: "",
    end_date: "",
    notes: "",
  });
  const shown = items.filter((i) => !filter || i.group === filter);
  const groups = [...new Set(items.map((i) => i.group))].sort();
  async function importFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setImportError("");
    try {
      if (file.size > 1_000_000) throw new Error("清单超过 1 MB。");
      const parsed = parseNotebook(await file.text(), meta.mode);
      const resolved = await api<{ items: Item[] }>(
        "/v1/web/references/resolve",
        {
          method: "POST",
          body: JSON.stringify({
            refs: parsed.items.map(
              ({ entity_type, entity_id, definition_revision }) => ({
                entity_type,
                entity_id,
                definition_revision,
              }),
            ),
          }),
        },
      );
      const imports = parsed.items.map((item, index) => ({
        ...item,
        name: resolved.items[index].name,
      }));
      const merged = new Map(items.map((i) => [refKey(i), i]));
      imports.forEach((i) => {
        if (!merged.has(refKey(i))) merged.set(refKey(i), i);
      });
      if (update([...merged.values()], true))
        notify("清单已导入；重复引用保留原备注。备注和分组仅保存在此浏览器。");
    } catch (e) {
      setImportError(
        e instanceof Error
          ? e.message + " 导入未生效。"
          : "导入失败，原清单未改变。",
      );
    } finally {
      setBusy(false);
    }
  }
  async function exportRequest() {
    setBusy(true);
    try {
      const request = await api<unknown>("/v1/web/research-requests", {
        method: "POST",
        body: JSON.stringify({
          entity_refs: shown
            .filter((i) =>
              study === "FACTOR_DIAGNOSTIC"
                ? i.entity_type === "FactorVariant"
                : i.entity_type === "StrategyVariant",
            )
            .map(({ entity_type, entity_id, definition_revision }) => ({
              entity_type,
              entity_id,
              definition_revision,
            })),
          study_type: study,
          requested_settings: settings,
        }),
      });
      download("research-request.json", request);
      notify("已导出 DRAFT 研究请求。研究尚未运行。");
    } catch (e) {
      notify(e instanceof Error ? e.message : "导出失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageTitle
        eyebrow="NOTEBOOK / 研究清单"
        title="把想法留给下一步。"
        action={
          <div className="actions">
            <label className="button import-button">
              <Upload size={16} />
              导入清单
              <input
                type="file"
                accept="application/json,.json"
                aria-label="导入清单文件"
                disabled={busy}
                onChange={(e) => {
                  void importFile(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </label>
            <button
              disabled={!items.length}
              onClick={() =>
                download("quantgraph-list.json", {
                  schema_version: "quantgraph-list/v1",
                  mode: meta.mode,
                  items,
                } satisfies Notebook)
              }
            >
              <Download size={16} />
              导出清单
            </button>
          </div>
        }
      >
        收藏固定定义版本，记录备注，按研究问题分组。
      </PageTitle>
      <div className="notice">
        <ShieldCheck size={18} aria-hidden="true" />
        清单与备注仅存当前浏览器，不会云同步或公开。清除浏览器数据前，请先导出备份。
      </div>
      {error && (
        <div className="error" role="alert">
          <span>{error}</span>
          <button
            onClick={() => {
              if (window.confirm("重置将删除此浏览器中的损坏清单。确定继续？"))
                update([], true);
            }}
          >
            重置损坏清单
          </button>
        </div>
      )}
      {importError && <ErrorState error={importError} />}
      <div className="notebook-grid">
        <section className="panel notebook-items">
          <div className="section-head">
            <h2>
              已收藏 <span>{items.length}</span>
            </h2>
            <label>
              分组
              <select
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              >
                <option value="">全部分组</option>
                {groups.map((g) => (
                  <option key={g} value={g}>
                    {g || "未分组"}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {!shown.length ? (
            <Empty title="清单还是空的">
              <p>从知识库收藏一个定义，开始记录研究问题。</p>
              <Link to="/explore">去搜索 →</Link>
            </Empty>
          ) : (
            shown.map((item) => (
              <article className="saved-card" key={refKey(item)}>
                <div className="saved-title">
                  <div>
                    <TypeTag kind={item.kind} />
                    <Link to={entityUrl(item)}>{item.name}</Link>
                  </div>
                  <button
                    className="icon-button"
                    aria-label={`取消收藏 ${item.name}`}
                    onClick={() =>
                      update(items.filter((i) => refKey(i) !== refKey(item)))
                    }
                  >
                    <Trash2 size={17} />
                  </button>
                </div>
                <code className="saved-ref">
                  {item.entity_id}
                  <br />
                  {item.definition_revision}
                </code>
                <div className="saved-inputs">
                  <label>
                    分组
                    <input
                      value={item.group}
                      maxLength={100}
                      onChange={(e) =>
                        update(
                          items.map((i) =>
                            refKey(i) === refKey(item)
                              ? { ...i, group: e.target.value }
                              : i,
                          ),
                        )
                      }
                    />
                  </label>
                  <label>
                    研究备注
                    <textarea
                      value={item.note}
                      maxLength={4000}
                      placeholder="想验证什么？需要哪些数据或对照？"
                      onChange={(e) =>
                        update(
                          items.map((i) =>
                            refKey(i) === refKey(item)
                              ? { ...i, note: e.target.value }
                              : i,
                          ),
                        )
                      }
                    />
                  </label>
                </div>
              </article>
            ))
          )}
        </section>
        <section>
          {meta.adapter_version === "catalog/v1" && (
            <SubmitResearch items={shown} />
          )}
          <section className="panel request-panel">
            <div className="eyebrow">NEXT STEP</div>
            <h2>导出研究请求</h2>
            <p>
              将当前分组中符合所选研究类型的引用整理为草稿。导出不会启动研究。
            </p>
            <label>
              研究类型
              <select value={study} onChange={(e) => setStudy(e.target.value)}>
                <option value="FACTOR_DIAGNOSTIC">
                  因子诊断 / FACTOR_DIAGNOSTIC
                </option>
                <option value="STRATEGY_REPLICATION">
                  策略复现 / STRATEGY_REPLICATION
                </option>
              </select>
            </label>
            <label>
              市场范围
              <input
                value={settings.market}
                onChange={(e) =>
                  setSettings({ ...settings, market: e.target.value })
                }
                placeholder="待研究方确认，如：中国股票"
                maxLength={200}
              />
            </label>
            <div className="date-fields">
              <label>
                期望开始日期
                <input
                  type="date"
                  value={settings.start_date}
                  onChange={(e) =>
                    setSettings({ ...settings, start_date: e.target.value })
                  }
                />
              </label>
              <label>
                期望结束日期
                <input
                  type="date"
                  value={settings.end_date}
                  onChange={(e) =>
                    setSettings({ ...settings, end_date: e.target.value })
                  }
                />
              </label>
            </div>
            <label>
              研究设置说明
              <textarea
                value={settings.notes}
                onChange={(e) =>
                  setSettings({ ...settings, notes: e.target.value })
                }
                placeholder="数据、成本与对照设置需在研究端冻结"
                maxLength={2000}
              />
            </label>
            <div className="request-contract">
              <code>{meta.contracts.request}</code>
              <span className="tag">DRAFT</span>
            </div>
            {!meta.contracts.export_enabled && (
              <p className="contract-pending">
                正式契约等待任务 A
                接入。当前可用“导出清单”保存引用；研究请求导出尚未开放。
              </p>
            )}
            <button
              className="primary full"
              disabled={busy || !shown.length || !meta.contracts.export_enabled}
              onClick={() => void exportRequest()}
            >
              <Download size={16} />
              {busy ? "正在校验…" : "校验并导出请求"}
            </button>
            <small>
              清单备注不自动进入请求。只有这里填写的研究设置会随请求提交校验。
            </small>
          </section>
        </section>
      </div>
    </>
  );
}
function ResultsPage({ meta }: { meta: Meta }) {
  const result = useApi<Results>("/v1/web/results");
  return (
    <>
      <PageTitle eyebrow="EVIDENCE / 研究结果" title="结论需要证据。">
        按研究方法、数据区间、成本和限制理解结果，不把研究通过解释成买入建议。
      </PageTitle>
      {meta.adapter_version === "catalog/v1" && <ResearchCollections />}
      {result.loading ? (
        <Loading />
      ) : result.error ? (
        <ErrorState error={result.error} retry={result.retry} />
      ) : (
        result.data && <ResearchResults results={result.data} />
      )}
    </>
  );
}

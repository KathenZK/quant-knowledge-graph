import HostedNotebookImport, { HostedSyncStatus } from "./HostedNotebook";
import { isHosted, hostedSave, hostedNoteKey } from "./hosted-transport";
import { applicationFetch } from "./api";
import { useCallback, useEffect, useState, type ReactNode } from "react";
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
  BookOpen,
  Bookmark,
  Check,
  ChevronDown,
  Columns2,
  Download,
  FileText,
  FolderOpen,
  Layers3,
  Network,
  Search,
  Star,
  Upload,
  X,
} from "lucide-react";
import { useApi as useReadApi } from "./api";
import {
  Empty,
  ErrorState,
  ExternalLink,
  Formula,
  Loading,
} from "./components";
import { download, loadNotebook } from "./storage";
import type { Facet, Kind } from "./types";
import {
  downloadText,
  emptyRecord,
  kindNames,
  personalApi,
  personalPath,
  personalStatuses,
  readable,
  recordPath,
  relationLabels,
  sameRecord,
  personalPatch,
  differenceLabel,
  type Duplicate,
  type PersonalDetail,
  type PersonalGraph,
  type PersonalItem,
  type PersonalMeta,
  type PersonalRecord,
} from "./personal-data";
import PersonalRestore from "./PersonalRestore";
import ResearchInDetails, { LegacyResearchEntry } from "./ResearchInDetails";
import KnowledgeBrief from "./KnowledgeBrief";
import "./personal.css";

function useApi<T>(url: string) {
  const result = useReadApi<T>(url);
  return {
    ...result,
    error: result.error?.replace("当前公开版本中", "当前知识快照中"),
  };
}
type CompareRef = { kind: Kind; entity_id: string; name: string };
type Workspace = {
  records: PersonalRecord[];
  compare: CompareRef[];
  save: (item: PersonalItem, values: Partial<PersonalRecord>) => Promise<void>;
  toggleCompare: (item: PersonalItem) => void;
  notify: (message: string) => void;
  refresh: () => void;
};
const selectionKey = (r: PersonalRecord) =>
  isHosted ? hostedNoteKey(r) : r.entity_id;
const compareUrl = (refs: CompareRef[]) =>
  "/compare?" +
  new URLSearchParams(
    refs.map((item) => ["ref", `${item.kind}/${item.entity_id}`]),
  ).toString();
const valueLabels: Record<string, string> = {
  daily_eod: "日线收盘（daily_eod）",
  daily: "日线（daily）",
  monthly: "月度（monthly）",
  weekly: "周度（weekly）",
  equity: "股票（equity）",
  crypto: "加密资产（crypto）",
  close: "收盘价",
  open: "开盘价",
  high: "最高价",
  low: "最低价",
  volume: "成交量",
  vwap: "成交均价",
  returns: "收益率",
  funding_rate: "资金费率",
  unknown: "来源未说明",
  UNKNOWN: "来源未说明",
};
const humanValue = (value: string | null | undefined) =>
  value ? valueLabels[value] || value : "来源未说明";
const humanList = (values: string[] | undefined) =>
  values?.length ? values.map(humanValue).join("、") : "来源未说明";
const humanDate = (value: string | number | undefined) => {
  if (!value) return "未记录";
  const date = new Date(
    typeof value === "number" ? (value < 1e12 ? value * 1000 : value) : value,
  );
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Shanghai",
        hour12: false,
      }).format(date) + " UTC+8";
};
const tokenList = (text: string) => [
  ...new Set(
    text
      .split(/[,，\n]/)
      .map((part) => part.trim())
      .filter(Boolean),
  ),
];
function Title({
  kicker,
  title,
  children,
  actions,
}: {
  kicker: string;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="pw-title">
      <div>
        <span className="pw-kicker">{kicker}</span>
        <h1>{title}</h1>
        {children && <p>{children}</p>}
      </div>
      {actions && <div className="pw-actions">{actions}</div>}
    </header>
  );
}
export function Highlight({ text, terms }: { text: string; terms: string[] }) {
  const valid = [
    ...new Set(terms.map((term) => term.trim()).filter(Boolean)),
  ].sort((a, b) => b.length - a.length);
  if (!valid.length) return <>{text}</>;
  const pattern = valid
    .map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  const parts = text.split(new RegExp(`(${pattern})`, "gi"));
  return (
    <>
      {parts.map((part, index) =>
        valid.some((term) => term.toLowerCase() === part.toLowerCase()) ? (
          <mark key={index}>{part}</mark>
        ) : (
          part
        ),
      )}
    </>
  );
}
function SmallState({
  item,
  workspace,
}: {
  item: PersonalItem;
  workspace: Workspace;
}) {
  const record = workspace.records.find((row) => sameRecord(row, item));
  return (
    <span
      className={`pw-state ${record?.status === "值得研究" ? "research" : ""}`}
    >
      {record?.status || "待读"}
    </span>
  );
}
function ItemActions({
  item,
  workspace,
}: {
  item: PersonalItem;
  workspace: Workspace;
}) {
  const starred = workspace.records.some(
    (row) => sameRecord(row, item) && row.starred,
  );
  const compared = workspace.compare.some(
    (row) => row.entity_id === item.entity_id && row.kind === item.kind,
  );
  return (
    <div className="pw-actions">
      <button
        aria-label={`${starred ? "取消收藏" : "收藏"} ${item.name}`}
        aria-pressed={starred}
        className={starred ? "pw-pressed" : ""}
        onClick={() =>
          void workspace
            .save(item, { starred: !starred })
            .catch((error) => workspace.notify(String(error.message || error)))
        }
      >
        <Star size={16} fill={starred ? "currentColor" : "none"} />
        {starred ? "已收藏" : "收藏"}
      </button>
      <button
        aria-label={`比较 ${item.name}`}
        aria-pressed={compared}
        className={compared ? "pw-pressed" : ""}
        onClick={() => workspace.toggleCompare(item)}
      >
        <Columns2 size={16} />
        {compared ? "已选比较" : "比较"}
      </button>
    </div>
  );
}
export function RuntimeInformation({
  meta: initialMeta,
}: {
  meta: PersonalMeta;
}) {
  const [meta, setMeta] = useState(initialMeta);
  useEffect(() => {
    let active = true;
    let pending = false;
    const recheck = async () => {
      if (pending || document.visibilityState === "hidden") return;
      pending = true;
      try {
        const current = await personalApi<PersonalMeta>("/v1/web/meta");
        if (active && current.mode === "personal_local") setMeta(current);
      } catch {
        /* Temporary service restart leaves the current page and unsaved notes intact. */
      } finally {
        pending = false;
      }
    };
    const check = () => {
      void recheck();
    };
    window.addEventListener("focus", check);
    document.addEventListener("visibilitychange", check);
    const timer = window.setInterval(check, 60_000);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", check);
      document.removeEventListener("visibilitychange", check);
    };
  }, []);
  const embeddedId = import.meta.env.VITE_QUANTGRAPH_BUILD_ID || "";
  const serverId = meta.build?.build_id || "";
  const mismatch = Boolean(embeddedId && serverId && embeddedId !== serverId);
  const counts = {
    ...meta.counts,
    ...meta.knowledge_counts,
    ...meta.layer_counts,
  };
  const issue = mismatch
    ? "服务已更新，本页仍是旧版本。请先保存正在编辑的笔记，再刷新页面。"
    : meta.build && meta.build.status !== "CURRENT"
      ? meta.build.message || "当前构建尚未与源码核对，请重新启动工作台。"
      : "";
  return (
    <div className="pw-runtime">
      {issue && (
        <p className="pw-error" role="status">
          {issue}
        </p>
      )}
      <details aria-label="运行信息与数据快照">
        <summary>
          运行信息与数据快照{" "}
          <span>
            个人本地模式 · v{meta.application_version || "未知"} ·{" "}
            {embeddedId || "开发预览"}
          </span>
        </summary>
        <dl className="pw-runtime-meta">
          <div>
            <dt>本页构建版本</dt>
            <dd>
              <code>{embeddedId || "开发预览，未嵌入构建版本"}</code>
            </dd>
          </div>
          <div>
            <dt>服务构建版本</dt>
            <dd>
              <code>{serverId || "未记录"}</code> ·{" "}
              {mismatch
                ? "本页需要刷新"
                : meta.build?.status === "CURRENT"
                  ? "已核对当前源码"
                  : meta.build?.status || "未核对"}
            </dd>
          </div>
          <div>
            <dt>构建时间</dt>
            <dd
              title={
                import.meta.env.VITE_QUANTGRAPH_BUILD_AT || meta.build?.built_at
              }
            >
              {humanDate(
                import.meta.env.VITE_QUANTGRAPH_BUILD_AT ||
                  meta.build?.built_at,
              )}
              （北京时间）
            </dd>
          </div>
          <div>
            <dt>Catalog 快照</dt>
            <dd>{readable(meta.snapshot || meta.release || meta.dataset)}</dd>
          </div>
          <div>
            <dt>最近导入时间</dt>
            <dd title={meta.imported_at || meta.last_imported_at}>
              {humanDate(meta.imported_at || meta.last_imported_at)}（北京时间）
            </dd>
          </div>
        </dl>
        <p>各层分别计数，不相加为独立方法数量。</p>
        <dl className="pw-runtime-counts">
          {Object.entries(counts).map(([key, value]) => (
            <div key={key}>
              <dt>{countLabel(key)}</dt>
              <dd>{readable(value)}</dd>
            </div>
          ))}
        </dl>
        {meta.reading_coverage && (
          <details>
            <summary>已有原文的可读覆盖</summary>
            <dl className="pw-runtime-counts">
              {Object.entries(meta.reading_coverage).map(([key, value]) => (
                <div key={key}>
                  <dt>{countLabel(key)}</dt>
                  <dd>{readable(value)}</dd>
                </div>
              ))}
            </dl>
          </details>
        )}
      </details>
    </div>
  );
}
const countLabel = (key: string) =>
  ({
    strategy: "策略记录",
    variant: "因子变体",
    concept: "因子概念",
    family: "策略概念",
    template: "策略模板",
    source: "来源记录",
    collected_strategy_records: "已采集策略记录",
    structured_strategy_variants: "已结构化策略变体",
    readable_strategy_records: "有可读原文的策略",
    strategy_families: "策略方法族",
    independent_strategies: "独立策略数（未认定）",
    explanation: "计数说明",
    source_fact_records: "有来源事实的条目",
    readable_strategy_rules: "可读策略原文",
    formula_records: "公式记录",
    normalized_factor_records: "已规范化因子来源定义",
    factor_browse_records: "因子浏览条目",
    rule_reference_factors: "策略规则中的因子引用",
    readable: "已有可读定义",
    metadata_only: "仅来源元信息",
    strategy_records: "策略来源记录",
    strategy_concepts: "策略概念",
    strategy_templates: "策略模板",
    strategy_variants: "策略变体",
    factor_concepts: "因子概念",
    factor_definitions: "因子定义",
    factor_variants: "因子变体",
    rule_references: "规则引用",
    relations: "关系",
    sources: "来源",
    implementations: "实现引用",
    source_records: "来源记录",
    strategy_with_original_rule: "保有原始规则的策略",
    factor_with_formula: "保有公式的因子",
  })[key] || key;
export default function PersonalApp({ meta }: { meta: PersonalMeta }) {
  const notebook = useApi<{ items: PersonalRecord[]; total: number }>(
    "/v1/personal/items",
  );
  const [records, setRecords] = useState<PersonalRecord[]>([]);
  const [compare, setCompare] = useState<CompareRef[]>([]);
  const [message, setMessage] = useState("");
  const location = useLocation();
  useEffect(() => {
    if (notebook.data) setRecords(notebook.data.items);
  }, [notebook.data]);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);
  const workspace: Workspace = {
    records,
    compare,
    notify: setMessage,
    refresh: notebook.retry,
    save: async (item, values) => {
      const saved = isHosted
        ? await hostedSave(item, values)
        : await personalApi<PersonalRecord>(recordPath(item), {
            method: "PUT",
            body: JSON.stringify(personalPatch(values)),
          });
      setRecords((rows) => [
        ...rows.filter((row) =>
          isHosted
            ? !sameRecord(row, saved)
            : row.kind !== saved.kind || row.entity_id !== saved.entity_id,
        ),
        saved,
      ]);
    },
    toggleCompare: (item) => {
      const found = compare.some(
        (row) => row.entity_id === item.entity_id && row.kind === item.kind,
      );
      if (!found && compare.length >= 4) {
        setMessage("最多比较 4 个条目，请先移除一个。");
        return;
      }
      setCompare(
        found
          ? compare.filter(
              (row) =>
                row.entity_id !== item.entity_id || row.kind !== item.kind,
            )
          : [
              ...compare,
              { kind: item.kind, entity_id: item.entity_id, name: item.name },
            ],
      );
    },
  };
  return (
    <div className="personal-workbench">
      <a className="skip-link" href="#personal-main">
        跳到主要内容
      </a>
      <aside className="pw-sidebar">
        <Link className="pw-brand" to="/strategies">
          <div className="pw-brand-icon">
            <Network size={23} />
          </div>
          <span>
            QuantGraph<small>个人知识工作台</small>
          </span>
        </Link>
        <div className="pw-nav-label">阅读 · 理解 · 判断</div>
        <nav aria-label="主导航">
          <NavLink to="/strategies">
            <BookOpen size={19} />
            策略<span>{meta.counts.strategy}</span>
          </NavLink>
          <NavLink to="/factors">
            <Layers3 size={19} />
            因子
            <span>
              {meta.layer_counts?.factor_browse_records || meta.counts.variant}
            </span>
          </NavLink>
          <NavLink to="/families">
            <Network size={19} />
            方法族
          </NavLink>
          <NavLink to="/list">
            <Bookmark size={19} />
            我的清单<span>{records.filter((item) => item.starred).length}</span>
          </NavLink>
        </nav>
        <Link className="pw-compare-nav" to={compareUrl(compare)}>
          <Columns2 size={18} />
          条目比较 <span>{compare.length} / 4</span>
        </Link>
        <div className="pw-sidebar-bottom">
          <span className="pw-local-label">
            <span className="pw-live-dot" />
            {isHosted ? "仅本人访问" : "仅本机使用"}
          </span>
          <p>从定义到规则，从来源到自己的判断。</p>
          <small>
            知识收录 ≠ 收益验证
            <br />
            {isHosted
              ? "批注保存到云端，可跨设备读取"
              : "个人笔记保存在本地服务中"}
          </small>
        </div>
      </aside>
      <div className="pw-workspace">
        <div className="pw-topbar">
          <span>
            <BookOpen size={15} /> KNOWLEDGE NOTEBOOK
          </span>
          <Link to="/list">
            我的研究选择 <ArrowRight size={14} />
          </Link>
        </div>
        <main id="personal-main" tabIndex={-1}>
          {meta.warnings?.length ? (
            <details className="pw-snapshot-notes">
              <summary>资料快照与阅读边界</summary>
              {meta.warnings.map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </details>
          ) : null}
          {(meta.initialized === false ||
            meta.initialization?.status === "MISSING") &&
          location.pathname !== "/results" ? (
            <Empty title="完整 Catalog 尚未初始化">
              <p>
                {meta.initialization?.message ||
                  "没有加载完整个人资料。请按项目启动说明指定已有 Catalog。"}
              </p>
            </Empty>
          ) : (
            <>
              <Routes>
                <Route
                  path="/"
                  element={<Navigate to="/strategies" replace />}
                />
                <Route
                  path="/explore"
                  element={<Navigate to="/strategies" replace />}
                />
                <Route
                  path="/strategies"
                  element={
                    <Browse
                      key="strategy"
                      kind="strategy"
                      meta={meta}
                      workspace={workspace}
                    />
                  }
                />
                <Route
                  path="/factors"
                  element={
                    <Browse
                      key="variant"
                      kind="variant"
                      meta={meta}
                      workspace={workspace}
                    />
                  }
                />
                <Route path="/families" element={<Families meta={meta} />} />
                <Route
                  path="/entity/:kind/:id"
                  element={<DetailPage workspace={workspace} />}
                />
                <Route path="/compare" element={<Compare />} />
                <Route path="/results" element={<LegacyResearchEntry />} />
                <Route
                  path="/list"
                  element={
                    <Notebook workspace={workspace} error={notebook.error} />
                  }
                />
                <Route
                  path="*"
                  element={
                    <Empty title="没有这个页面">
                      <Link to="/strategies">返回策略知识库</Link>
                    </Empty>
                  }
                />
              </Routes>
            </>
          )}
          <footer className="pw-footer">
            <div className="pw-footer-line">
              来源事实、整理说明、个人判断分开保存。
              <span>QuantGraph · 个人本地工作台</span>
            </div>
            <RuntimeInformation meta={meta} />
          </footer>
        </main>
      </div>
      {message && (
        <div className="pw-toast" role="status">
          <Check size={18} />
          <span>{message}</span>
          <button aria-label="关闭提示" onClick={() => setMessage("")}>
            <X size={16} />
          </button>
        </div>
      )}
      {compare.length > 0 && location.pathname !== "/compare" && (
        <div className="pw-compare-dock">
          <Columns2 size={18} />
          <strong>比较 {compare.length} / 4</strong>
          <div>
            {compare.map((item) => (
              <button
                key={item.entity_id}
                onClick={() =>
                  setCompare(compare.filter((row) => row !== item))
                }
                aria-label={`移除比较 ${item.name}`}
              >
                {item.name}
                <X size={12} />
              </button>
            ))}
          </div>
          {compare.length >= 2 ? (
            <Link className="button primary" to={compareUrl(compare)}>
              查看差异 <ArrowRight size={15} />
            </Link>
          ) : (
            <span>再选择一个条目</span>
          )}
        </div>
      )}
    </div>
  );
}
function SnapshotProgress({
  meta,
  kind,
}: {
  meta: PersonalMeta;
  kind: string;
}) {
  const snapshot = meta.snapshot_progress;
  return (
    <div className="pw-snapshot-progress">
      {snapshot && (
        <p>
          截至 {snapshot.as_of_utc}，原始{" "}
          {snapshot.corpus_records.toLocaleString()} 条记录中，
          {snapshot.executed_records.toLocaleString()} 条已有执行证据，共{" "}
          {snapshot.execution_versions.toLocaleString()} 个实现版本。已导入{" "}
          {snapshot.imported_runs} 批
          {snapshot.awaiting_import_runs
            ? `，另 ${snapshot.awaiting_import_runs} 批等待兼容校验`
            : ""}
          。
        </p>
      )}
      {meta.intake_summary && meta.intake_summary.reviewed_records > 0 && (
        <p>
          本次补证与采集资料 {meta.intake_summary.reviewed_records} 条，其中{" "}
          {meta.intake_summary.source_reviews} 条补回既有记录。
          {kind === "variant"
            ? "因子原论文说明、规则组件和Qlib特征分别标注；"
            : "隔离候选和研究模型仍可阅读；"}
          资料入库不增加回测次数。
        </p>
      )}
    </div>
  );
}
function Browse({
  kind,
  meta,
  workspace,
}: {
  kind: "strategy" | "variant";
  meta: PersonalMeta;
  workspace: Workspace;
}) {
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") || "");
  useEffect(() => setQuery(params.get("q") || ""), [params]);
  const [advanced, setAdvanced] = useState(false);
  const effective = new URLSearchParams(params);
  effective.set("kind", kind);
  effective.set("page_size", "18");
  if (!effective.has("collapse_templates"))
    effective.set("collapse_templates", "true");
  const results = useApi<{
    items: PersonalItem[];
    total: number;
    page: number;
    page_size: number;
    total_before_collapse?: number;
    query?: {
      constraints?: { key: string; text: string; explanation: string }[];
    };
  }>("/v1/web/search?" + effective.toString());
  const filter = (name: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    if (name !== "page") next.delete("page");
    setParams(next);
  };
  const filterSpec: [string, string, Facet[]][] = [
    ["method_family", "方法类型", meta.facets.method_families || []],
    ["market", "市场", meta.facets.markets || []],
    ["frequency", "频率", meta.facets.frequencies || []],
    [
      "personal_status",
      "我的阅读状态",
      personalStatuses.map((value) => ({ value, label: value })),
    ],
  ];
  const extraSpec: [string, string, Facet[]][] = [
    ["family", "原始方法族", meta.facets.families || []],
    [
      "asset_scope",
      "规则涉及资产",
      [
        { value: "single", label: "单资产" },
        { value: "multi", label: "多资产" },
        { value: "unknown", label: "来源未说明" },
      ],
    ],
    [
      "axis",
      "计算结构",
      meta.facets.axes || [
        { value: "time_series", label: "时序：观察同一对象的历史" },
        { value: "cross_sectional", label: "截面：同时比较不同对象" },
      ],
    ],
    ["field", "所需数据", meta.facets.fields || []],
    ["extra_data", "额外数据", meta.facets.extra_data || []],
    ["completeness", "内容完整度", meta.facets.completeness || []],
    ["source_type", "来源类型", meta.facets.source_types || []],
  ];
  const activeCount = [...params.keys()].filter(
    (key) => !["q", "page", "collapse_templates"].includes(key),
  ).length;
  return (
    <>
      <Title
        kicker={
          kind === "strategy" ? "STRATEGIES / 策略知识" : "FACTORS / 因子知识"
        }
        title={
          kind === "strategy"
            ? "找到方法，读懂规则。"
            : "从一个定义，看清一个因子。"
        }
      >
        {kind === "strategy"
          ? "查看已有来源中的信号、入场、出场与参数，把值得研究的方法留下。"
          : "阅读原始公式、变量、计算口径与实现差异，沿关系理解它如何被使用。"}
      </Title>
      <SnapshotProgress meta={meta} kind={kind} />
      <section className="pw-catalog">
        <form
          className="pw-search"
          onSubmit={(event) => {
            event.preventDefault();
            filter("q", query.trim());
          }}
        >
          <Search size={21} />
          <label className="sr-only" htmlFor="pw-search-input">
            搜索名称、别名、规则、公式和来源
          </label>
          <input
            id="pw-search-input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={
              kind === "strategy"
                ? "搜索中文、英文、规则词，如：趋势、RSI、突破…"
                : "搜索名称、缩写或公式，如：均线、MA、成交量…"
            }
            maxLength={2000}
          />
          <button type="submit" className="primary">
            搜索
          </button>
        </form>
        <div className="pw-filters">
          {filterSpec.map(([key, label, options]) => (
            <Filter
              key={key}
              name={label}
              options={options}
              value={params.get(key) || ""}
              onChange={(value) => filter(key, value)}
            />
          ))}
          <button
            aria-expanded={advanced}
            className="pw-quiet"
            onClick={() => setAdvanced(!advanced)}
          >
            更多筛选 {activeCount > 0 && `(${activeCount})`}
            <ChevronDown size={15} />
          </button>
        </div>
        {advanced && (
          <div className="pw-advanced">
            {extraSpec.map(([key, label, options]) => (
              <Filter
                key={key}
                name={label}
                options={options}
                value={params.get(key) || ""}
                onChange={(value) => filter(key, value)}
              />
            ))}
            <label className="pw-checkbox">
              <input
                type="checkbox"
                checked={params.get("daily_ohlcv") === "true"}
                onChange={(event) =>
                  filter("daily_ohlcv", event.target.checked ? "true" : "")
                }
              />
              只需日线开高低收与成交量
            </label>
            <p>
              筛选基于已有明确字段；未知项不会被当作满足条件。规则涉及资产统计信号与持仓规则明确提到的资产，不代表同时持仓数量。
            </p>
          </div>
        )}
        <div className="pw-results-bar">
          <span role="status">
            {results.data ? (
              <>
                找到 <strong>{results.data.total.toLocaleString()}</strong> 个
                {kind === "strategy" ? "策略条目" : "因子条目"}
              </>
            ) : (
              "正在检索…"
            )}
          </span>
          <div>
            <label className="pw-checkbox">
              <input
                type="checkbox"
                checked={effective.get("collapse_templates") === "true"}
                onChange={(event) =>
                  filter("collapse_templates", String(event.target.checked))
                }
              />
              折叠同模板变体
            </label>
            {params.size > 0 && (
              <button
                className="pw-quiet"
                onClick={() => {
                  setQuery("");
                  setParams({});
                }}
              >
                清除筛选
              </button>
            )}
          </div>
        </div>
        {results.data?.query?.constraints?.map((constraint, index) => (
          <p
            className="pw-search-explanation"
            key={`${constraint.key}-${index}`}
          >
            <strong>{constraint.text}：</strong>
            {constraint.explanation}
          </p>
        ))}
        {results.loading ? (
          <Loading />
        ) : results.error ? (
          <ErrorState error={results.error} retry={results.retry} />
        ) : !results.data?.items.length ? (
          <Empty title="没有找到匹配条目">
            <p>试试中英文别名、一个规则词，或放宽筛选条件。</p>
          </Empty>
        ) : (
          <div className="pw-results">
            {results.data.items.map((item) => (
              <ResultCard
                key={item.entity_id}
                item={item}
                workspace={workspace}
                query={params.get("q") || ""}
              />
            ))}
          </div>
        )}
        {results.data && results.data.total > results.data.page_size && (
          <div className="pw-pagination">
            <button
              disabled={results.data.page <= 1}
              onClick={() => filter("page", String(results.data!.page - 1))}
            >
              上一页
            </button>
            <span>
              第 {results.data.page} /{" "}
              {Math.ceil(results.data.total / results.data.page_size)} 页
            </span>
            <button
              disabled={
                results.data.page * results.data.page_size >= results.data.total
              }
              onClick={() => filter("page", String(results.data!.page + 1))}
            >
              下一页
            </button>
          </div>
        )}
      </section>
    </>
  );
}
function Filter({
  name,
  options,
  value,
  onChange,
}: {
  name: string;
  options: Facet[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="pw-filter">
      <span>{name}</span>
      <select
        aria-label={name}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">全部</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
function ResultCard({
  item,
  workspace,
  query,
}: {
  item: PersonalItem;
  workspace: Workspace;
  query: string;
}) {
  const terms = [query, ...(item.matches || []).map((match) => match.term)];
  return (
    <article className="pw-result">
      <div className="pw-result-reading">
        <div className="pw-result-top">
          <span className="pw-kind">{kindNames[item.kind]}</span>
          <span>
            {item.knowledge?.method_family?.label ||
              item.family_label ||
              item.category_label}
          </span>
          <SmallState item={item} workspace={workspace} />
        </div>
        <Link className="pw-result-name" to={personalPath(item)}>
          <Highlight text={item.name} terms={terms} />
          <ArrowRight size={16} />
        </Link>
        {item.aliases?.length > 0 && (
          <div className="pw-alias">
            <Highlight
              text={item.aliases.slice(0, 4).join(" · ")}
              terms={terms}
            />
          </div>
        )}
        <p>
          <Highlight
            text={
              item.knowledge?.summary ||
              item.description ||
              "当前保留来源资料；详细规则与未知项见详情。"
            }
            terms={terms}
          />
        </p>
        {item.kind !== "strategy" && item.formula && (
          <Formula value={item.formula} />
        )}
        <div className="pw-result-meta">
          <span>
            数据：
            {item.required_fields?.length
              ? humanList(item.required_fields)
              : "来源未说明"}
          </span>
          <span>频率：{humanValue(item.frequency)}</span>
          <span>
            来源：{item.source_name || item.source_type || "已收录资料"}
          </span>
        </div>
        {item.matches?.length ? (
          <div className="pw-match">
            命中{" "}
            {item.matches.slice(0, 2).map((match, index) => (
              <span key={index}>
                {match.label}：
                <Highlight text={match.text.slice(0, 180)} terms={terms} />
              </span>
            ))}
          </div>
        ) : null}
        {item.group && item.group.count > 1 && (
          <Link
            className="pw-group-link"
            to={`${item.kind === "strategy" ? "/strategies" : "/factors"}?template_id=${encodeURIComponent(item.group.id)}&collapse_templates=false`}
          >
            同模板还有 {item.group.count - 1} 个变体 · 展开查看
          </Link>
        )}
      </div>
      <ItemActions item={item} workspace={workspace} />
    </article>
  );
}
const familyDescriptions: Record<string, string> = {
  trend: "观察价格或其他序列的持续方向。具体入场、退出和窗口需要逐条核对。",
  momentum: "比较过去变化的方向或强弱。历史时间窗口与排名对象会改变方法含义。",
  mean_reversion:
    "围绕相对基准的偏离构造规则。偏离定义、基准和回归条件须看原始资料。",
  value:
    "将价格与基本面度量联系起来。估值口径、数据时点和资产范围不能混为一谈。",
  quality:
    "使用经营、财务或稳定性特征刻画对象。不同定义可能使用不同的数据口径。",
  volatility: "刻画变化幅度或波动特征。它可能用于信号、风险缩放或过滤条件。",
  liquidity: "刻画成交活跃程度、交易规模或交易摩擦相关特征。",
  allocation:
    "定义多个资产或信号之间的配置规则。仓位、调仓与现金处理是关键差异。",
  relative_value:
    "比较对象之间的相对价格或估值关系。对照对象与对齐时间需核对。",
  unknown: "现有材料不足以确定分类。条目的原始规则、公式与来源仍可阅读。",
};
function Families({ meta }: { meta: PersonalMeta }) {
  const location = useLocation();
  useEffect(() => {
    if (location.hash)
      requestAnimationFrame(() =>
        document
          .getElementById(decodeURIComponent(location.hash.slice(1)))
          ?.scrollIntoView(),
      );
  }, [location.hash]);
  const families =
    meta.method_families ||
    (meta.facets.method_families || []).map((row) => ({
      ...row,
      count: 0,
      representatives: [],
    }));
  return (
    <>
      <Title
        kicker="METHOD FAMILIES / 方法族"
        title="沿着一个方法，理解它的变体。"
      >
        分类用于组织阅读；同属一类，不表示定义等价或已有共同收益机制的证据。
      </Title>
      {!families.length ? (
        <Empty title="当前快照尚未提供方法分类">
          <p>可以从策略或因子详情沿已有关系继续阅读。</p>
        </Empty>
      ) : (
        <div className="pw-family-grid">
          {families.map((family) => (
            <section
              className="pw-family-card"
              key={family.value}
              id={family.value}
            >
              <span className="pw-kicker">
                {family.count ? `${family.count} 个真实条目` : "现有资料分类"}
              </span>
              <h2>{family.label}</h2>
              <p>
                {("description" in family && family.description) ||
                  familyDescriptions[family.value] ||
                  "由现有来源字段整理的阅读分类。请按具体定义比较结构、参数和数据需求。"}
              </p>
              {"common_structures" in family && family.common_structures && (
                <div className="pw-family-structures">
                  <h3>常见结构与区别</h3>
                  <ul>
                    {family.common_structures.map((text, index) => (
                      <li key={index}>{text}</li>
                    ))}
                  </ul>
                </div>
              )}
              {family.representatives.length > 0 && (
                <div className="pw-family-examples">
                  <h3>从这些条目读起</h3>
                  {family.representatives.slice(0, 3).map((row) => (
                    <Link key={row.entity_id} to={personalPath(row)}>
                      {row.name}
                      <ArrowRight size={13} />
                    </Link>
                  ))}
                </div>
              )}
              <div className="pw-family-links">
                <Link
                  to={`/strategies?method_family=${encodeURIComponent(family.value)}`}
                >
                  策略与变体 →
                </Link>
                <Link
                  to={`/factors?method_family=${encodeURIComponent(family.value)}`}
                >
                  相关因子 →
                </Link>
              </div>
              <small>
                {"questions" in family && family.questions?.length
                  ? "继续核对：" + family.questions.join("；")
                  : "继续比較：结构相同吗？窗口与数据要求哪里不同？"}
              </small>
            </section>
          ))}
        </div>
      )}
    </>
  );
}
function DetailPage({ workspace }: { workspace: Workspace }) {
  const { kind, id } = useParams();
  const [params] = useSearchParams();
  const pinned = new URLSearchParams();
  if (isHosted) {
    for (const key of ["definition_revision", "snapshot_batch"])
      if (params.get(key)) pinned.set(key, params.get(key)!);
  }
  const result = useApi<PersonalDetail>(
    `/v1/web/entities/${encodeURIComponent(kind || "")}/${encodeURIComponent(id || "")}${pinned.size ? "?" + pinned : ""}`,
  );
  if (result.loading) return <Loading />;
  if (result.error || !result.data)
    return (
      <ErrorState error={result.error || "条目不存在"} retry={result.retry} />
    );
  return (
    <Reading
      key={`${kind}/${id}/${pinned}`}
      item={result.data}
      workspace={workspace}
    />
  );
}
function Section({
  id,
  title,
  label,
  children,
}: {
  id: string;
  title: string;
  label?: string;
  children: ReactNode;
}) {
  return (
    <section className="pw-reading-section" id={id}>
      <div className="pw-section-heading">
        <h2>{title}</h2>
        {label && <span>{label}</span>}
      </div>
      {children}
    </section>
  );
}
function Reading({
  item,
  workspace,
}: {
  item: PersonalDetail;
  workspace: Workspace;
}) {
  const location = useLocation();
  useEffect(() => {
    if (location.hash)
      requestAnimationFrame(() => {
        const target = document.getElementById(location.hash.slice(1));
        if (target instanceof HTMLDetailsElement) target.open = true;
        target?.scrollIntoView?.();
      });
  }, [location.hash]);
  const knowledge = item.knowledge;
  const rules = knowledge?.reading || [];
  const params =
    knowledge?.parameters ||
    Object.entries(item.parameters || {}).map(([name, value]) => ({
      name,
      value,
      meaning: "来源未说明",
    }));
  const unknowns = knowledge?.unknowns || item.strategy?.unknowns || [];
  const source = knowledge?.source;
  const factor =
    item.kind === "variant" ||
    item.kind === "concept" ||
    item.source_type === "factor_source_record";
  const family = knowledge?.method_family;
  const summary =
    knowledge?.summary ||
    item.description ||
    "来源保留了此记录；请阅读下方已有规则、定义和未知项。";
  return (
    <>
      <Link className="pw-back" to={factor ? "/factors" : "/strategies"}>
        <ArrowLeft size={15} />
        返回{factor ? "因子" : "策略"}知识库
      </Link>
      <Title
        kicker={`${kindNames[item.kind]} / ${family?.label || item.category_label || "已有资料"}`}
        title={item.name}
        actions={<ItemActions item={item} workspace={workspace} />}
      >
        {item.aliases?.join(" · ")}
      </Title>
      <div className="pw-detail-layout">
        <article className="pw-reading">
          {item.is_historical && (
            <div className="pw-notice">
              正在阅读保存的历史定义；原文与旧引用保持不变。
              {item.current_entity_id &&
                item.current_entity_id !== item.entity_id && (
                  <Link
                    to={personalPath({
                      kind: item.kind,
                      entity_id: item.current_entity_id,
                    })}
                  >
                    查看当前版本 →
                  </Link>
                )}
            </div>
          )}
          <KnowledgeBrief item={item} />
          <details className="pw-reading-technical" id="reading-details">
            <summary>完整规则、计算细节与来源沿革</summary>
            <section className="pw-summary">
              <span className="pw-kicker">一句话理解 · 来源整理</span>
              <p>{summary}</p>
              <div className="pw-summary-tags">
                <SmallState item={item} workspace={workspace} />
                <span>
                  知识：
                  {rules.some((rule) => rule.status !== "UNKNOWN") ||
                  item.formula
                    ? "已有可读定义"
                    : "来源资料"}
                </span>
                <span>
                  研究：
                  {item.results?.total
                    ? `${item.results.total} 条记录`
                    : "尚未研究"}
                </span>
              </div>
            </section>
            <Section
              id="logic"
              title={factor ? "定义与计算对象" : "方法逻辑"}
              label="来源观点与整理说明"
            >
              <p className="pw-prose">
                {item.economic_logic ||
                  (factor
                    ? "这是技术特征或经验构造，来源未给出独立经济解释。"
                    : "来源未单独说明方法的经济逻辑；请结合下面的原始规则理解。")}
              </p>
              {knowledge?.source_facts?.length ? (
                <details className="pw-source-facts">
                  <summary>查看来源支持的事实与定位</summary>
                  {knowledge.source_facts.map((fact, index) => (
                    <div key={index}>
                      <strong>{fact.label}</strong>
                      <p>{fact.text}</p>
                      {fact.source && <small>依据：{fact.source}</small>}
                    </div>
                  ))}
                </details>
              ) : null}
            </Section>
            {factor && (
              <Section id="formula" title="公式与变量" label="原始定义保留">
                <Formula value={knowledge?.formula || item.formula} />
                {knowledge?.explanation_basis && (
                  <p className="pw-muted">
                    释义依据：{knowledge.explanation_basis}
                  </p>
                )}
                {knowledge?.variables?.length ? (
                  <dl className="pw-definition-list">
                    {knowledge.variables.map((variable) => (
                      <div key={variable.name}>
                        <dt>
                          <code>{variable.name}</code>
                        </dt>
                        <dd>{variable.meaning}</dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <p className="pw-muted">
                    来源未提供单独的变量释义。可在原始公式和来源资料中核对。
                  </p>
                )}
                <dl className="pw-definition-list">
                  <div>
                    <dt>计算结构</dt>
                    <dd>{axisLabel(item.axis)}</dd>
                  </div>
                  <div>
                    <dt>所需数据</dt>
                    <dd>{humanList(item.required_fields)}</dd>
                  </div>
                  <div>
                    <dt>历史窗口</dt>
                    <dd>
                      {item.lookback
                        ? `${item.lookback.value} ${item.lookback.unit}`
                        : "来源未说明"}
                    </dd>
                  </div>
                </dl>
              </Section>
            )}
            <Section
              id="rules"
              title={factor ? "计算语义" : "具体规则"}
              label="已知项与未知项分别展示"
            >
              {rules.length ? (
                <div className="pw-rule-grid">
                  {rules.map((rule, index) => (
                    <div
                      className={
                        rule.status === "UNKNOWN"
                          ? "pw-rule unknown"
                          : "pw-rule"
                      }
                      key={`${rule.key}-${index}`}
                    >
                      <h3>
                        {rule.label}
                        <span>
                          {rule.status === "UNKNOWN"
                            ? "未说明"
                            : rule.status === "SOURCE_REPORTED"
                              ? "来源明确"
                              : rule.status === "CARD_IMPLEMENTATION"
                                ? "资料卡实现约定"
                                : rule.status === "CARD_REPORTED"
                                  ? "资料卡说明"
                                  : "从来源整理"}
                        </span>
                      </h3>
                      <p>{rule.text || "来源未说明"}</p>
                      {rule.evidence && (
                        <details>
                          <summary>定位依据</summary>
                          <p>{rule.evidence}</p>
                        </details>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="pw-rule-grid">
                  {(factor
                    ? ["缺失值处理", "预热期", "复权口径"]
                    : [
                        "信号",
                        "入场",
                        "出场",
                        "持仓与仓位",
                        "换仓频率",
                        "现金处理",
                        "多空方向",
                        "数据与时间条件",
                      ]
                  ).map((label) => (
                    <div className="pw-rule unknown" key={label}>
                      <h3>{label}</h3>
                      <p>来源未说明</p>
                    </div>
                  ))}
                </div>
              )}
              {!factor &&
                (knowledge?.original_rule || item.strategy?.original_rule) && (
                  <details className="pw-original-inline">
                    <summary>完整原始规则（不受解析状态限制）</summary>
                    <pre>
                      {knowledge?.original_rule || item.strategy?.original_rule}
                    </pre>
                  </details>
                )}
            </Section>
            <Section
              id="parameters"
              title="参数说明"
              label="不推测缺失单位与作用"
            >
              {params.length ? (
                <div className="pw-table-scroll">
                  <table className="pw-table">
                    <thead>
                      <tr>
                        <th>参数</th>
                        <th>数值</th>
                        <th>作用 / 单位</th>
                      </tr>
                    </thead>
                    <tbody>
                      {params.map((parameter, index) => (
                        <tr key={index}>
                          <th>
                            <code>{parameter.name}</code>
                          </th>
                          <td>{readable(parameter.value)}</td>
                          <td>
                            {parameter.meaning}
                            {"unit" in parameter && parameter.unit
                              ? ` / ${parameter.unit}`
                              : ""}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="pw-muted">
                  没有可单独提取的参数。已有原文仍完整保留在规则和技术详情中。
                </p>
              )}
            </Section>
            <Section
              id="example"
              title={factor ? "简单计算例子" : "一个说明用途的例子"}
              label="不代表真实交易或回测"
            >
              {knowledge?.example ? (
                <div className="pw-example">
                  <p>{knowledge.example.text}</p>
                  <small>依据：{knowledge.example.basis}</small>
                </div>
              ) : (
                <p className="pw-muted">
                  现有定义不足以提供确定的计算例子，暂不补造数值或执行条件。
                </p>
              )}
            </Section>
            <Section
              id="sources"
              title="来源与沿革"
              label="作者、材料与版本分开核对"
            >
              <dl className="pw-definition-list">
                <div>
                  <dt>来源材料</dt>
                  <dd>
                    {item.source_name || item.source_type || "已收录来源"}
                  </dd>
                </div>
                <div>
                  <dt>提出者 / 来源作者</dt>
                  <dd>
                    {source?.author ||
                      item.strategy?.source_author ||
                      item.authors?.join("、") ||
                      "来源未说明"}
                  </dd>
                </div>
                {item.strategy && (
                  <div>
                    <dt>具体策略变体作者</dt>
                    <dd>
                      {item.strategy.variant_author ||
                        "来源未说明；指标作者不等于派生策略作者"}
                    </dd>
                  </div>
                )}
                <div>
                  <dt>来源定位</dt>
                  <dd>
                    {source?.locator ||
                      item.source_locator ||
                      "当前记录未提供定位"}
                  </dd>
                </div>
                <div>
                  <dt>原生编号</dt>
                  <dd>
                    {readable(source?.native_ids || item.source_native_ids)}
                  </dd>
                </div>
                <div>
                  <dt>版本</dt>
                  <dd>
                    {source?.revision || item.source_revision || "来源未记录"}
                  </dd>
                </div>
              </dl>
              <dl className="pw-definition-list">
                <div>
                  <dt>材料发表时间</dt>
                  <dd>
                    {source?.publication_date
                      ? readable(source.publication_date)
                      : "未确认；不以采集时间代替"}
                  </dd>
                </div>
                {source?.reference_year && (
                  <div>
                    <dt>来源记录的文献年份</dt>
                    <dd>
                      {readable(source.reference_year)}（未核为正式发表日期）
                    </dd>
                  </div>
                )}
                {source?.reported_date && (
                  <div>
                    <dt>来源报告的时间</dt>
                    <dd>
                      {source.reported_date}
                      {source.date_status === "UNVERIFIED_REPORTED_DATE"
                        ? "（未独立确认准确含义）"
                        : ""}
                    </dd>
                  </div>
                )}
                <div>
                  <dt>{source?.collected_at_label || "资料采集时间"}</dt>
                  <dd title={source?.collected_at}>
                    {humanDate(source?.collected_at)}
                  </dd>
                </div>
                {source?.ingestion_observed_at && (
                  <div>
                    <dt>迁移 / 入库观察时间</dt>
                    <dd title={source.ingestion_observed_at}>
                      {humanDate(source.ingestion_observed_at)}
                      {source.collection_time_notice && (
                        <small className="pw-block">
                          {source.collection_time_notice}
                        </small>
                      )}
                    </dd>
                  </div>
                )}
                {source?.variant_created_at && (
                  <div>
                    <dt>该变体创建时间</dt>
                    <dd>{humanDate(source.variant_created_at)}</dd>
                  </div>
                )}
              </dl>
              <SourceCheck id={item.entity_id} />
              <div className="pw-source-links">
                <ExternalLink url={source?.url || item.source_url}>
                  打开来源资料
                </ExternalLink>
                {family && (
                  <Link to={`/families#${encodeURIComponent(family.value)}`}>
                    所属方法族：{family.label} →
                  </Link>
                )}
              </div>
              {item.papers?.length > 0 && (
                <div className="pw-papers">
                  {item.papers.map((paper) => (
                    <p key={paper.paper_id}>
                      <ExternalLink url={paper.url}>
                        {paper.title || paper.paper_id}
                      </ExternalLink>{" "}
                      · {paper.year || "发表年未确认"} ·{" "}
                      {paper.authors?.join("、") || "作者未确认"}
                    </p>
                  ))}
                </div>
              )}
              <details>
                <summary>来源许可和个人阅读边界</summary>
                <p>
                  来源许可：{item.license || "未记录"}
                  。个人阅读不改变公开分发或商业使用授权结论。
                </p>
                <dl className="pw-definition-list">
                  {Object.entries(item.rights || {}).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>
              </details>
            </Section>
            <Section
              id="related"
              title="沿关系继续阅读"
              label="点击节点或名称查看详情"
            >
              <RelationExplorer item={item} />
            </Section>
            {factor && item.implementations?.length > 0 && (
              <Section
                id="implementations"
                title="实现与差异"
                label="同名不能证明计算等价"
              >
                {item.implementations.map((impl) => (
                  <div
                    className="pw-implementation"
                    key={impl.implementation_id}
                  >
                    <strong>
                      {impl.language} ·{" "}
                      {impl.source_locator || impl.implementation_id}
                    </strong>
                    <p>
                      版本：{impl.revision || "未说明"} · 是否执行：
                      {impl.executed ? "已有执行记录" : "未执行"} · 许可：
                      {impl.license || "未记录"}
                    </p>
                    {impl.code_url && (
                      <ExternalLink url={impl.code_url}>
                        查看该实现
                      </ExternalLink>
                    )}
                    <small>
                      现有记录未提供跨实现等价验证时，不能视为相同口径。
                    </small>
                  </div>
                ))}
              </Section>
            )}
            <Section
              id="unknowns"
              title="局限与未知"
              label="研究前值得核对的问题"
            >
              {unknowns.length ? (
                <ul className="pw-unknowns">
                  {unknowns.map((unknown, index) => (
                    <li key={index}>{unknown}</li>
                  ))}
                </ul>
              ) : (
                <p>当前来源没有单独列出限制。这不表示方法不存在限制。</p>
              )}
              {item.strategy?.research_hypotheses?.length ? (
                <div className="pw-hypotheses">
                  <h3>待验证的研究假设</h3>
                  {item.strategy.research_hypotheses.map(
                    (hypothesis, index) => (
                      <p key={index}>{hypothesis}</p>
                    ),
                  )}
                </div>
              ) : null}
            </Section>
          </details>
          <Section id="research" title="已有研究" label="只读研究记录">
            <ResearchInDetails item={item} />
            {item.results?.total ? (
              <PersonalResearch results={item.results} />
            ) : item.kind !== "strategy" ? (
              <p>尚无与该因子定义版本绑定的本地诊断或回测结果。</p>
            ) : null}
          </Section>
          <Section
            id="personal"
            title="我的判断"
            label="你的整理独立于原始来源"
          >
            <ScopedNoteEditor item={item} workspace={workspace} />
          </Section>
          <DuplicateSuggestions
            item={item}
            notify={workspace.notify}
            refresh={workspace.refresh}
          />
          <details className="pw-technical" id="technical">
            <summary>原始资料与技术详情</summary>
            <dl className="pw-definition-list">
              <div>
                <dt>稳定 ID</dt>
                <dd>
                  <code>{item.entity_id}</code>
                </dd>
              </div>
              <div>
                <dt>定义版本</dt>
                <dd>
                  <code>{item.definition_revision}</code>
                </dd>
              </div>
              <div>
                <dt>解析状态</dt>
                <dd>
                  {item.strategy?.parse_status ||
                    item.statuses?.implementation ||
                    "未记录"}
                </dd>
              </div>
              {item.strategy?.parse_reason && (
                <div>
                  <dt>解析说明</dt>
                  <dd>{item.strategy.parse_reason}</dd>
                </div>
              )}
              <div>
                <dt>来源摘要</dt>
                <dd>
                  <code>
                    {source?.sha256 || item.source_sha256 || "未记录"}
                  </code>
                </dd>
              </div>
            </dl>
            {item.prior_version_ids?.length ? (
              <div>
                <h3>保留的历史定义</h3>
                {item.prior_version_ids.map((id) => (
                  <p key={id}>
                    <Link to={personalPath({ kind: item.kind, entity_id: id })}>
                      {id} →
                    </Link>
                  </p>
                ))}
              </div>
            ) : null}
            <h3>原始规则 / 定义</h3>
            <pre>
              {knowledge?.original_rule ||
                item.strategy?.original_rule ||
                item.formula ||
                item.description ||
                "当前快照缺少原文"}
            </pre>
            {knowledge?.normalized_formula != null && (
              <details>
                <summary>已有标准化公式（不代表数学等价已验证）</summary>
                <pre>{readable(knowledge.normalized_formula)}</pre>
              </details>
            )}
            {item.strategy?.structured_rule && (
              <details>
                <summary>已有执行结构</summary>
                <pre>
                  {JSON.stringify(item.strategy.structured_rule, null, 2)}
                </pre>
              </details>
            )}
          </details>
        </article>
        <aside className="pw-reading-aside">
          <div>
            <span className="pw-kicker">本文导航</span>
            <nav aria-label="详情章节">
              <Link to={`${location.pathname}${location.search}#overview`}>
                {factor ? "因子含义" : "策略用途"}
              </Link>
              <Link to={`${location.pathname}${location.search}#trading`}>
                {factor ? "计算与场景" : "标的与进出场"}
              </Link>
              <Link to={`${location.pathname}${location.search}#rationale`}>
                论文与盈利依据
              </Link>
              <Link to={`${location.pathname}${location.search}#research`}>
                已有研究结果
              </Link>
              {factor && (
                <Link
                  to={`${location.pathname}${location.search}#reading-details`}
                >
                  公式与变量
                </Link>
              )}
              <Link
                to={`${location.pathname}${location.search}#reading-details`}
              >
                {factor ? "计算语义" : "具体规则"}
              </Link>
              <Link
                to={`${location.pathname}${location.search}#reading-details`}
              >
                参数说明
              </Link>
              <Link
                to={`${location.pathname}${location.search}#reading-details`}
              >
                来源与沿革
              </Link>
              <Link
                to={`${location.pathname}${location.search}#reading-details`}
              >
                相关方法
              </Link>
              <Link
                to={`${location.pathname}${location.search}#reading-details`}
              >
                局限与未知
              </Link>
              <Link to={`${location.pathname}${location.search}#personal`}>
                我的判断
              </Link>
            </nav>
            <div className="pw-aside-facts">
              <span>所需数据</span>
              <strong>{humanList(item.required_fields)}</strong>
              <span>频率</span>
              <strong>{humanValue(item.frequency)}</strong>
              <span>市场</span>
              <strong>{humanList(item.markets)}</strong>
            </div>
          </div>
        </aside>
      </div>
    </>
  );
}
function axisLabel(axis: string) {
  return (
    {
      time_series: "时序：比较同一对象的历史",
      cross_sectional: "截面：同时比较不同对象",
      TS: "时序",
      CS: "截面",
      TIME_SERIES: "时序",
      CROSS_SECTIONAL: "截面",
      UNKNOWN: "来源未说明",
    }[axis] ||
    axis ||
    "来源未说明"
  );
}
function ScopedNoteEditor({
  item,
  workspace,
}: {
  item: PersonalItem;
  workspace: Workspace;
}) {
  const [params] = useSearchParams();
  const target = {
    ...item,
    ...(isHosted &&
    params.get("research_run") &&
    params.get("research_variant") &&
    params.get("research_manifest")
      ? {
          origin_run_id: params.get("research_run")!,
          variant_id: params.get("research_variant")!,
          manifest_sha256: params.get("research_manifest")!,
        }
      : {}),
  };
  return (
    <NoteEditor
      key={JSON.stringify([
        target.entity_id,
        target.definition_revision,
        target.origin_run_id,
        target.variant_id,
        target.manifest_sha256,
      ])}
      item={target}
      workspace={workspace}
    />
  );
}
export function NoteEditor({
  item,
  workspace,
}: {
  item: PersonalItem;
  workspace: Workspace;
}) {
  const draftKey =
    "quantgraph-unsaved:" +
    JSON.stringify([
      item.kind,
      item.entity_id,
      item.definition_revision,
      item.origin_run_id,
      item.variant_id,
      item.manifest_sha256,
    ]);
  const serverRecord = useApi<PersonalRecord>(recordPath(item));
  const workspaceRecord = workspace.records.find((row) =>
    sameRecord(row, item),
  );
  const saved =
    workspaceRecord &&
    (!serverRecord.data ||
      (workspaceRecord.updated_at || "") > (serverRecord.data.updated_at || ""))
      ? workspaceRecord
      : serverRecord.data;
  const [draft, setDraft] = useState<PersonalRecord>(() => {
    if (isHosted) {
      try {
        const raw = sessionStorage.getItem(draftKey);
        if (raw) {
          const cached = JSON.parse(raw);
          if (
            cached.entity_id === item.entity_id &&
            cached.definition_revision === item.definition_revision
          )
            return cached;
        }
      } catch {
        /* original text remains in the browser */
      }
    }
    return {
      ...emptyRecord(item),
      ...saved,
      origin_run_id: item.origin_run_id,
      variant_id: item.variant_id,
      manifest_sha256: item.manifest_sha256,
    };
  });
  const [dirty, setDirty] = useState(() => {
    try {
      return isHosted && !!sessionStorage.getItem(draftKey);
    } catch {
      return false;
    }
  });
  const [draftPersisted, setDraftPersisted] = useState(false);
  const [tagsText, setTagsText] = useState((draft.tags || []).join(", "));
  const [aliasesText, setAliasesText] = useState(
    (draft.aliases || []).join(", "),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!dirty) {
      setDraft({
        ...emptyRecord(item),
        ...saved,
        origin_run_id: item.origin_run_id,
        variant_id: item.variant_id,
        manifest_sha256: item.manifest_sha256,
      });
      setTagsText((saved?.tags || []).join(", "));
      setAliasesText((saved?.aliases || []).join(", "));
    }
  }, [saved, item, dirty]);
  useEffect(() => {
    if (!isHosted) return;
    try {
      if (dirty)
        sessionStorage.setItem(
          draftKey,
          JSON.stringify({
            ...draft,
            tags: tokenList(tagsText),
            aliases: tokenList(aliasesText),
          }),
        );
      else sessionStorage.removeItem(draftKey);
      setDraftPersisted(dirty);
    } catch {
      setDraftPersisted(false);
    }
  }, [draftKey, draft, dirty, tagsText, aliasesText]);
  const change = <K extends keyof PersonalRecord>(
    key: K,
    value: PersonalRecord[K],
  ) => {
    setDraft({ ...draft, [key]: value });
    setDirty(true);
  };
  const submit = async () => {
    if (serverRecord.loading || serverRecord.error) return;
    setBusy(true);
    setError("");
    try {
      await workspace.save(item, {
        ...draft,
        tags: tokenList(tagsText),
        aliases: tokenList(aliasesText),
      });
      setDirty(false);
      serverRecord.retry();
      workspace.notify("个人判断已保存。刷新或更换浏览器仍可读取。");
    } catch (error) {
      serverRecord.retry();
      setError(
        error instanceof Error ? error.message : "保存失败，编辑内容仍保留。",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      className="pw-note-form"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      {isHosted && item.origin_run_id && (
        <p className="pw-notice">
          这份批注固定关联 {item.origin_run_id} / {item.variant_id}
          。来源ID关联不等于定义版本已精确复现。
        </p>
      )}
      {serverRecord.error && (
        <ErrorState error={serverRecord.error} retry={serverRecord.retry} />
      )}
      {dirty && (
        <p className="pw-reading-basis">
          有未保存草稿，尚未写入云端。
          {draftPersisted
            ? "当前浏览器会话已暂存，刷新后可恢复。"
            : "请保留本页，保存失败后可重试。"}
        </p>
      )}
      {isHosted &&
        dirty &&
        serverRecord.data &&
        serverRecord.data.record_revision !== draft.record_revision && (
          <div className="pw-notice">
            <p>云端有较新批注，你的草稿没有丢失。</p>
            <details>
              <summary>读取云端版本后比较</summary>
              <p>批注：{serverRecord.data.note}</p>
              <p>问题：{serverRecord.data.questions}</p>
              <p>标签：{serverRecord.data.tags.join("、")}</p>
            </details>
            <button
              type="button"
              onClick={() => {
                setDraft(serverRecord.data!);
                setTagsText(serverRecord.data!.tags.join(", "));
                setAliasesText(serverRecord.data!.aliases.join(", "));
                setDirty(false);
                setError("");
              }}
            >
              采用云端版本
            </button>
            <button
              type="button"
              onClick={() => {
                setDraft({
                  ...draft,
                  record_revision: serverRecord.data!.record_revision,
                });
                setError("");
                setDirty(true);
              }}
            >
              保留我的草稿，下一次保存作为新修订
            </button>
          </div>
        )}
      <fieldset disabled={busy || serverRecord.loading || !!serverRecord.error}>
        {saved &&
          (saved.version_changed ||
            saved.definition_revision !== item.definition_revision) && (
            <p className="pw-notice">
              来源定义已有修订。以下笔记仍关联原保存版本，保存判断不会自动替换历史引用。
            </p>
          )}
        {serverRecord.data?.linked_notes?.length ? (
          <details className="pw-linked-notes">
            <summary>
              查看归并前分别保存的 {serverRecord.data.linked_notes.length}{" "}
              份个人笔记
            </summary>
            {serverRecord.data.linked_notes.map((note) => (
              <div key={note.entity_id}>
                <Link to={personalPath(note)}>{note.name}</Link>
                <p>
                  {note.note ||
                    note.reason ||
                    note.summary ||
                    "该引用没有文字备注"}
                </p>
                <small>原版本：{note.definition_revision}</small>
              </div>
            ))}
          </details>
        ) : null}
        <div className="pw-form-row">
          <label>
            阅读状态
            <select
              value={draft.status}
              onChange={(event) =>
                change("status", event.target.value as PersonalRecord["status"])
              }
            >
              {personalStatuses.map((status) => (
                <option key={status}>{status}</option>
              ))}
            </select>
          </label>
          <label>
            主题分组
            <input
              maxLength={100}
              value={draft.group}
              onChange={(event) => change("group", event.target.value)}
              placeholder="例如：低换手趋势方法"
            />
          </label>
        </div>
        <label>
          标签（逗号分隔）
          <input
            maxLength={1000}
            value={tagsText}
            onChange={(event) => {
              setTagsText(event.target.value);
              setDirty(true);
            }}
            placeholder="如：价格、趋势、待核对退出规则"
          />
        </label>
        <label>
          研究选择的理由
          <textarea
            maxLength={12000}
            value={draft.reason}
            onChange={(event) => change("reason", event.target.value)}
            placeholder="为什么值得研究，或为什么暂不研究？"
            rows={2}
          />
        </label>
        <label>
          备注
          <textarea
            maxLength={12000}
            value={draft.note}
            onChange={(event) => change("note", event.target.value)}
            placeholder="记录自己的理解、比较结果和阅读线索"
            rows={3}
          />
        </label>
        <label>
          我的问题与研究假设
          <textarea
            maxLength={12000}
            value={draft.questions}
            onChange={(event) => change("questions", event.target.value)}
            placeholder="哪些条件需要验证？还缺哪些证据？"
            rows={3}
          />
        </label>
        <details className="pw-note-extras">
          <summary>我的整理、别名与来源问题</summary>
          <label>
            我的整理
            <textarea
              maxLength={20000}
              rows={4}
              value={draft.summary}
              onChange={(event) => change("summary", event.target.value)}
              placeholder="用自己的话整理方法，不会覆盖作者原文"
            />
          </label>
          <label>
            补充别名（逗号分隔）
            <input
              maxLength={1000}
              value={aliasesText}
              onChange={(event) => {
                setAliasesText(event.target.value);
                setDirty(true);
              }}
            />
          </label>
          <label>
            来源 / 规则问题
            <textarea
              maxLength={12000}
              rows={3}
              value={draft.problem}
              onChange={(event) => change("problem", event.target.value)}
              placeholder="例如：退出条件不一致、来源链接失效、参数单位缺失"
            />
          </label>
        </details>
        <div className="pw-note-save">
          <label className="pw-checkbox">
            <input
              type="checkbox"
              checked={draft.starred}
              onChange={(event) => change("starred", event.target.checked)}
            />
            收藏到我的清单
          </label>
          <span>
            {dirty
              ? "有未保存的修改"
              : saved?.updated_at
                ? `已保存 · ${humanDate(saved.updated_at)}`
                : "尚未保存个人判断"}
          </span>
          <button className="primary" disabled={busy || !dirty} type="submit">
            {busy ? "保存中…" : "保存个人判断"}
          </button>
        </div>
        {error && (
          <p className="pw-error" role="alert">
            {error}
          </p>
        )}
      </fieldset>
    </form>
  );
}
function RelationExplorer({ item }: { item: PersonalDetail }) {
  const [hops, setHops] = useState(1),
    [relation, setRelation] = useState(""),
    [layer, setLayer] = useState("method"),
    [confidence, setConfidence] = useState(""),
    [offset, setOffset] = useState(0),
    [view, setView] = useState("list");
  const graph = useApi<PersonalGraph>(
    `/v1/web/relations/${encodeURIComponent(item.entity_id)}?${new URLSearchParams({ hops: String(hops), relation, layer, confidence: confidence || "0", offset: String(offset), limit: "20" })}`,
  );
  const edges = graph.data?.items || [];
  const nodes = graph.data?.nodes || [];
  const positions = new Map(
    nodes.map((node, index) => [
      node.entity_id,
      { x: 40 + (index % 3) * 245, y: 55 + Math.floor(index / 3) * 115 },
    ]),
  );
  const control = (action: () => void) => {
    action();
    setOffset(0);
  };
  return (
    <div className="pw-relations">
      <div className="pw-relation-controls">
        <label>
          展开范围
          <select
            value={hops}
            onChange={(event) =>
              control(() => setHops(Number(event.target.value)))
            }
          >
            <option value={1}>一跳 · 直接相关</option>
            <option value={2}>两跳 · 沿关系探索</option>
          </select>
        </label>
        <label>
          关系范围
          <select
            value={layer}
            onChange={(event) => control(() => setLayer(event.target.value))}
          >
            <option value="method">方法关系</option>
            <option value="source">来源关系</option>
            <option value="all">全部关系</option>
          </select>
        </label>
        <label>
          关系类型
          <select
            value={relation}
            onChange={(event) => control(() => setRelation(event.target.value))}
          >
            <option value="">全部类型</option>
            {[
              ...new Set([
                ...Object.keys(relationLabels),
                ...(graph.data?.types || []),
              ]),
            ].map((type) => (
              <option key={type} value={type}>
                {relationLabels[type] || type}
              </option>
            ))}
          </select>
        </label>
        <label>
          证据置信度
          <select
            value={confidence}
            onChange={(event) =>
              control(() => setConfidence(event.target.value))
            }
          >
            <option value="">全部</option>
            <option value="0.8">≥ 0.8</option>
            <option value="1">1.0</option>
          </select>
        </label>
      </div>
      <div className="pw-relations-toolbar">
        <span>{graph.data?.total ?? "…"} 条关系 · 每页最多 20 条</span>
        <div role="group" aria-label="关系展示方式">
          <button
            aria-pressed={view === "list"}
            onClick={() => setView("list")}
          >
            <FileText size={15} />
            列表
          </button>
          <button
            aria-pressed={view === "graph"}
            onClick={() => setView("graph")}
          >
            <Network size={15} />
            图形
          </button>
        </div>
      </div>
      {graph.loading ? (
        <Loading />
      ) : graph.error ? (
        <ErrorState error={graph.error} retry={graph.retry} />
      ) : !edges.length ? (
        <Empty title="当前条件下没有已有关系">
          <p>试试来源关系或两跳展开。没有证据时不会自动补造连接。</p>
          {item.related?.length > 0 && (
            <div>
              {item.related.slice(0, 6).map((related) => (
                <p key={related.entity_id}>
                  <Link to={personalPath(related)}>{related.name} →</Link>
                </p>
              ))}
            </div>
          )}
        </Empty>
      ) : (
        <>
          {view === "graph" && (
            <div
              className="pw-graph"
              role="region"
              aria-label="可点击方法关系图"
              tabIndex={0}
            >
              <svg
                viewBox={`0 0 780 ${Math.max(230, Math.ceil(nodes.length / 3) * 115 + 30)}`}
                role="group"
                aria-label="点击节点打开详情，连接依据见下面的列表"
              >
                {edges.map((edge) => {
                  const a = positions.get(edge.from_id),
                    b = positions.get(edge.to_id);
                  return a && b ? (
                    <line
                      key={edge.relationship_id}
                      x1={a.x + 100}
                      y1={a.y}
                      x2={b.x + 100}
                      y2={b.y}
                      stroke={layer === "source" ? "#b29873" : "#a4beb7"}
                      strokeDasharray={edge.confidence < 1 ? "5 4" : undefined}
                    />
                  ) : null;
                })}
                {nodes.map((node) => {
                  const pos = positions.get(node.entity_id)!;
                  return (
                    <a
                      key={node.entity_id}
                      href={personalPath(node)}
                      aria-label={`打开 ${node.name}`}
                    >
                      <g transform={`translate(${pos.x},${pos.y - 26})`}>
                        <rect
                          width={205}
                          height={61}
                          rx={8}
                          fill={
                            node.entity_id === item.entity_id
                              ? "#e5f1eb"
                              : "#fff"
                          }
                          stroke="#aec3b9"
                        />
                        <text x={12} y={23}>
                          {node.name.length > 18
                            ? node.name.slice(0, 17) + "…"
                            : node.name}
                        </text>
                        <text className="pw-svg-kind" x={12} y={43}>
                          {kindNames[node.kind] || node.entity_type}
                        </text>
                        <title>{node.name}</title>
                      </g>
                    </a>
                  );
                })}
              </svg>
            </div>
          )}
          <div className="pw-relation-list">
            {edges.map((edge) => {
              const from = nodes.find(
                (node) => node.entity_id === edge.from_id,
              );
              const to = nodes.find((node) => node.entity_id === edge.to_id);
              return (
                <article className="pw-relation" key={edge.relationship_id}>
                  <div className="pw-relation-names">
                    {from ? (
                      <Link to={personalPath(from)}>{from.name}</Link>
                    ) : (
                      <span>{edge.from_name || edge.from_id}</span>
                    )}
                    <span className="pw-edge-type">
                      {edge.explanation?.label ||
                        relationLabels[edge.relation] ||
                        edge.relation}
                    </span>
                    {to ? (
                      <Link to={personalPath(to)}>{to.name}</Link>
                    ) : (
                      <span>{edge.to_name || edge.to_id}</span>
                    )}
                  </div>
                  <p>
                    {edge.explanation?.text ||
                      edge.evidence ||
                      "当前关系记录未说明连接依据"}
                  </p>
                  {edge.explanation?.text && edge.evidence && (
                    <small>连接依据：{edge.evidence}</small>
                  )}
                  <div className="pw-relation-info">
                    <span>
                      {["CONFIRMED", "APPROVED", "ACCEPTED"].includes(
                        edge.review_status || edge.status,
                      )
                        ? "已确认"
                        : "来源记录 / 候选"}
                    </span>
                    <span>置信度 {edge.confidence}</span>
                    {edge.role && <span>规则作用：{edge.role}</span>}
                    <span>
                      定位：
                      {edge.source_label || edge.source || "当前记录未提供"}
                    </span>
                  </div>
                  {[
                    "RULE_LINK_ONLY",
                    "USES_FACTOR",
                    "CATEGORY_LINK_ONLY",
                  ].includes(edge.relation) && (
                    <small>
                      此连接描述规则引用或分类，不代表已验证收益归因。
                    </small>
                  )}
                </article>
              );
            })}
          </div>
        </>
      )}
      {graph.data && graph.data.total > 20 && (
        <div className="pw-pagination">
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 20))}
          >
            上一批关系
          </button>
          <span>
            {offset + 1}–{Math.min(offset + 20, graph.data.total)} /{" "}
            {graph.data.total}
          </span>
          <button
            disabled={offset + 20 >= graph.data.total}
            onClick={() => setOffset(offset + 20)}
          >
            下一批关系
          </button>
        </div>
      )}
    </div>
  );
}
const relationshipOnly = (suggestion: Duplicate) =>
  ["TEMPLATE_VARIANT", "NAME_COLLISION"].includes(suggestion.classification);
function DuplicateSuggestions({
  item,
  notify,
  refresh,
}: {
  item: PersonalItem;
  notify: (value: string) => void;
  refresh: () => void;
}) {
  const suggestions = useApi<{ items: Duplicate[]; total: number }>(
    `/v1/personal/duplicates?entity_id=${encodeURIComponent(item.entity_id)}`,
  );
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Duplicate | null>(null);
  const [error, setError] = useState("");
  const act = async (suggestion: Duplicate, action: string) => {
    setBusy(true);
    setError("");
    try {
      await personalApi(
        `/v1/personal/duplicates/${encodeURIComponent(suggestion.suggestion_id)}/decision`,
        {
          method: "POST",
          body: JSON.stringify({
            action,
            canonical_id: suggestion.left.entity_id,
          }),
        },
      );
      setPending(null);
      suggestions.retry();
      refresh();
      notify(
        action === "undo"
          ? "已撤销本次判断，原始来源与笔记保留。"
          : action === "reject"
            ? "已否决重复建议。"
            : relationshipOnly(suggestion)
              ? "已确认分组或差异；两个条目继续保留各自身份与笔记。"
              : "已保存归并判断；原始记录、旧 ID 和个人笔记仍保留。",
      );
    } catch (error) {
      setError(error instanceof Error ? error.message : "操作失败");
    } finally {
      setBusy(false);
    }
  };
  return (
    <details className="pw-duplicates">
      <summary>
        重复、别名与身份核对{" "}
        {suggestions.data?.total ? `(${suggestions.data.total})` : ""}
      </summary>
      <p>
        同名、同模板或公式相似不等于同一方法。确认只调整个人关联，原始材料保留。
      </p>
      <button
        disabled={busy || isHosted}
        title={isHosted ? "重新采集由研究端处理" : undefined}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            await personalApi("/v1/personal/duplicates/refresh", {
              method: "POST",
              body: "{}",
            });
            suggestions.retry();
          } catch (error) {
            setError(error instanceof Error ? error.message : "扫描失败");
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "处理中…" : "检查已有资料的重复建议"}
      </button>
      {suggestions.error && (
        <ErrorState error={suggestions.error} retry={suggestions.retry} />
      )}
      <div>
        {suggestions.data?.items.map((suggestion) => (
          <article className="pw-duplicate" key={suggestion.suggestion_id}>
            <div>
              <Link to={personalPath(suggestion.left)}>
                {suggestion.left.name}
              </Link>
              <span> ↔ </span>
              <Link to={personalPath(suggestion.right)}>
                {suggestion.right.name}
              </Link>
            </div>
            <p>
              {{
                SAME_ORIGINAL_RECORD: "同一原始记录",
                SAME_CONTENT_CANDIDATE: "相同内容候选",
                TEMPLATE_VARIANT: "模板变体，需保留参数差异",
                NAME_COLLISION: "同名但定义不同",
              }[suggestion.classification] || suggestion.classification}{" "}
              ·{" "}
              {{
                PENDING: "待判断",
                CONFIRMED: "已确认",
                REJECTED: "已否决",
                UNDONE: "已撤销",
                AUTO_MERGED: "完全重复已归并",
              }[suggestion.status] || suggestion.status}
            </p>
            <p>{readable(suggestion.evidence)}</p>
            <div className="pw-actions">
              {["PENDING", "UNDONE"].includes(suggestion.status) && (
                <>
                  <button
                    disabled={busy}
                    onClick={() => setPending(suggestion)}
                  >
                    {relationshipOnly(suggestion)
                      ? "确认分组/差异…"
                      : "确认归并…"}
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => void act(suggestion, "reject")}
                  >
                    否决建议
                  </button>
                </>
              )}
              {["CONFIRMED", "REJECTED", "AUTO_MERGED"].includes(
                suggestion.status,
              ) && (
                <button
                  disabled={busy}
                  onClick={() => void act(suggestion, "undo")}
                >
                  撤销判断
                </button>
              )}
            </div>
            {pending?.suggestion_id === suggestion.suggestion_id && (
              <div className="pw-confirm">
                <p>
                  {relationshipOnly(suggestion)
                    ? "确认这条分组或定义差异建议。两个条目保留各自身份、参数和笔记，不作同一方法归并。此判断可以撤销。"
                    : `将以「${suggestion.left.name}」作为个人查看的主条目，旧 ID、来源和笔记保持可追溯。此判断可以撤销。`}
                </p>
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() => void act(suggestion, "confirm")}
                >
                  {relationshipOnly(suggestion)
                    ? "确认此分组判断"
                    : "确认此身份判断"}
                </button>
                <button onClick={() => setPending(null)}>取消</button>
              </div>
            )}
          </article>
        ))}
      </div>
      {suggestions.data?.total === 0 && (
        <p className="pw-muted">当前没有这条记录的重复建议。</p>
      )}
      {error && (
        <p role="alert" className="pw-error">
          {error}
        </p>
      )}
    </details>
  );
}
function Compare() {
  const [params] = useSearchParams();
  const refs = params.getAll("ref");
  return (
    <>
      <Title kicker="COMPARE / 阅读差异" title="先看哪里不同，再决定研究什么。">
        比较规则、参数、数据需求与来源。不同样本或成本的研究结果不会被排成收益榜。
      </Title>
      {refs.length < 2 || refs.length > 4 ? (
        <Empty title="请选择 2–4 个条目">
          <p>在列表或详情点击“比较”，选择要并排阅读的方法。</p>
          <Link className="button primary" to="/strategies">
            去选择条目
          </Link>
        </Empty>
      ) : (
        <ComparisonTable query={params.toString()} />
      )}
    </>
  );
}
function ComparisonTable({ query }: { query: string }) {
  const result = useApi<{
    items: PersonalDetail[];
    differences?: {
      key: string;
      label: string;
      values: unknown[];
      same: boolean;
      known?: boolean;
      status?: string;
    }[];
    conclusions?: string[];
  }>("/v1/web/compare?" + query);
  if (result.loading) return <Loading />;
  if (result.error || !result.data)
    return (
      <ErrorState error={result.error || "比较不可用"} retry={result.retry} />
    );
  const { items, differences, conclusions } = result.data;
  const rows: [string, (item: PersonalDetail) => ReactNode][] = [
    [
      "一句话理解",
      (item) => item.knowledge?.summary || item.description || "来源未说明",
    ],
    [
      "原始公式",
      (item) => <Formula value={item.knowledge?.formula || item.formula} />,
    ],
    [
      "规则与计算语义",
      (item) => (
        <div className="pw-compare-rules">
          {item.knowledge?.reading?.length
            ? item.knowledge.reading.map((rule, index) => (
                <p key={index}>
                  <strong>{rule.label}</strong>
                  {rule.text}
                </p>
              ))
            : readable(item.strategy?.facts)}
        </div>
      ),
    ],
    [
      "参数与窗口",
      (item) => (
        <div>
          {(
            item.knowledge?.parameters ||
            Object.entries(item.parameters || {}).map(([name, value]) => ({
              name,
              value,
              meaning: "",
            }))
          ).map((parameter, index) => (
            <p key={index}>
              <strong>{parameter.name}：</strong>
              {readable(parameter.value)}
              {parameter.meaning ? ` · ${parameter.meaning}` : ""}
            </p>
          ))}
        </div>
      ),
    ],
    ["已保存的研究结果", (item) => <ResearchInDetails item={item} compact />],
    ["所需数据", (item) => humanList(item.required_fields)],
    ["时序 / 截面", (item) => axisLabel(item.axis)],
    [
      "市场与频率",
      (item) => `${humanList(item.markets)} / ${humanValue(item.frequency)}`,
    ],
    [
      "来源与版本",
      (item) => (
        <>
          <p>{item.source_name || "来源未说明"}</p>
          <ExternalLink url={item.source_url}>来源材料</ExternalLink>
          <small className="pw-block">
            {item.source_revision || "版本未记录"}
          </small>
        </>
      ),
    ],
    [
      "实现差异",
      (item) =>
        item.implementations?.length
          ? item.implementations.map((implementation) => (
              <p key={implementation.implementation_id}>
                {implementation.language} · {implementation.source_locator} ·{" "}
                {implementation.revision || "版本未说明"}
              </p>
            ))
          : "当前没有独立实现记录，无法判断等价性",
    ],
    [
      "局限与未知",
      (item) => (
        <ul>
          {(
            item.knowledge?.unknowns ||
            item.strategy?.unknowns || ["来源未单独列出"]
          ).map((text, index) => (
            <li key={index}>{text}</li>
          ))}
        </ul>
      ),
    ],
  ];
  return (
    <>
      <section className="pw-difference-summary">
        <span className="pw-kicker">关键差异摘要 · 根据已有字段整理</span>
        {conclusions?.length ? (
          <ul>
            {conclusions.map((conclusion, index) => (
              <li key={index}>{conclusion}</li>
            ))}
          </ul>
        ) : (
          <p>现有证据不足以概括规则等价性；请逐项核对以下差异。</p>
        )}
        {differences?.length ? (
          <div className="pw-difference-tags">
            {differences
              .filter((difference) => !difference.same)
              .map((difference) => (
                <span key={difference.key}>{differenceLabel(difference)}</span>
              ))}
          </div>
        ) : null}
      </section>
      <div
        className="pw-table-scroll pw-comparison"
        role="region"
        aria-label="方法比较表"
        tabIndex={0}
      >
        <table className="pw-table">
          <thead>
            <tr>
              <th>比较内容</th>
              {items.map((item) => (
                <th key={item.entity_id}>
                  <span className="pw-kind">{kindNames[item.kind]}</span>
                  <Link to={personalPath(item)}>{item.name} →</Link>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, value]) => (
              <tr key={label}>
                <th scope="row">{label}</th>
                {items.map((item) => (
                  <td key={item.entity_id}>{value(item)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
function Notebook({
  workspace,
  error,
}: {
  workspace: Workspace;
  error?: string;
}) {
  const [group, setGroup] = useState(""),
    [status, setStatus] = useState(""),
    [query, setQuery] = useState(""),
    [onlyStarred, setOnlyStarred] = useState(false);
  const [selected, setSelected] = useState<string[]>([]),
    [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const restoreFileProcessed = useCallback(() => setRestoreFile(null), []);
  const [legacy, setLegacy] = useState(() =>
    (["PUBLIC", "PRIVATE"] as const).map((mode) => ({
      mode,
      ...loadNotebook(mode),
    })),
  );
  const groups = [
    ...new Set(workspace.records.map((item) => item.group).filter(Boolean)),
  ].sort();
  const shown = workspace.records.filter(
    (item) =>
      (!group || item.group === group) &&
      (!status || item.status === status) &&
      (!onlyStarred || item.starred) &&
      (!query ||
        [
          item.name,
          item.note,
          item.summary,
          item.reason,
          item.questions,
          item.tags.join(" "),
        ].some((text) =>
          text.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
        )),
  );
  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setFailure("");
    try {
      await action();
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "操作未完成");
    } finally {
      setBusy(false);
    }
  };
  const exportItems = (format: string) =>
    run(async () => {
      const response = await applicationFetch("/v1/personal/export", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-QuantGraph-Request": "1",
        },
        body: JSON.stringify({
          ids: selected.length ? selected : shown.map(selectionKey),
          format,
        }),
      });
      if (!response.ok)
        throw new Error("导出未完成。原笔记仍保留，请稍后重试。");
      const unavailable = new Set([
        "PINNED_DEFINITION_UNAVAILABLE",
        "SOURCE_NO_LONGER_IN_CURRENT_CATALOG",
      ]);
      let missing = false;
      if (format === "markdown") {
        const markdown = await response.text();
        missing = [...unavailable].some((status) =>
          markdown.includes(`- 资料状态：${status}`),
        );
        downloadText("quantgraph-research-notes.md", markdown);
      } else {
        const value = await response.json();
        missing =
          Array.isArray(value.items) &&
          value.items.some((item: { availability?: string }) =>
            unavailable.has(item.availability || ""),
          );
        download("quantgraph-research-notes.json", value);
      }
      workspace.notify(
        missing
          ? "部分固定定义缺失。已保留原引用；缺失条目未导出替代规则，也未生成研究请求。"
          : "已导出条目、固定版本、规则、来源与个人问题。未运行研究任务。",
      );
    });
  return (
    <>
      <Title
        kicker="MY NOTEBOOK / 我的清单"
        title="把理解留住，把研究问题想清楚。"
        actions={
          <>
            <button
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  download(
                    "quantgraph-personal-backup.json",
                    await personalApi("/v1/personal/backup"),
                  );
                  workspace.notify("完整个人备份已下载，包含笔记和身份判断。");
                })
              }
            >
              <Download size={15} />
              完整备份
            </button>
            <label className="button pw-import">
              <Upload size={15} />
              恢复备份
              <input
                type="file"
                accept=".json,application/json"
                aria-label="恢复个人备份"
                disabled={busy}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) setRestoreFile(file);
                  event.target.value = "";
                }}
              />
            </label>
          </>
        }
      >
        {isHosted
          ? "收藏、阅读状态、批注和研究问题保存在云端，不依赖当前浏览器。"
          : "收藏、阅读状态、个人整理和问题保存在同一个本地服务中，不依赖当前浏览器。"}
      </Title>
      <div className="pw-notice">
        <FolderOpen size={18} />
        {isHosted
          ? "使用同一账户可读取已保存批注。云端接收状态单独显示；研究端拉取后继续研究。"
          : "同一台机器的浏览器连接此服务，都可读取这些笔记。备份只含个人层；原始来源资料保持独立。"}
      </div>
      {error && <ErrorState error={error} retry={workspace.refresh} />}
      {isHosted ? (
        <HostedNotebookImport
          file={restoreFile}
          onFileProcessed={restoreFileProcessed}
          refresh={workspace.refresh}
        />
      ) : (
        <Migration
          legacy={legacy}
          busy={busy}
          migrate={(mode, items) =>
            void run(async () => {
              const digest = await crypto.subtle.digest(
                "SHA-256",
                new TextEncoder().encode(JSON.stringify(items)),
              );
              const contentId = Array.from(new Uint8Array(digest), (byte) =>
                byte.toString(16).padStart(2, "0"),
              ).join("");
              const result = await personalApi<{
                imported?: number;
                preserved?: number;
                skipped?: number;
                already_migrated?: boolean;
                replayed?: boolean;
              }>("/v1/personal/migrate", {
                method: "POST",
                body: JSON.stringify({
                  migration_id: `localStorage-v1:${mode}:${contentId}`,
                  items,
                }),
              });
              workspace.refresh();
              setLegacy(legacy.filter((row) => row.mode !== mode));
              workspace.notify(
                result.already_migrated || result.replayed
                  ? "这份浏览器清单此前已迁移，本次没有重复导入。"
                  : `浏览器清单已迁移：新增 ${result.imported || 0} 条，保留已有 ${result.preserved || 0} 条。浏览器原清单仍保留。`,
              );
            })
          }
        />
      )}
      {isHosted ? (
        <HostedSyncStatus />
      ) : (
        <PersonalRestore
          file={restoreFile}
          onFileProcessed={restoreFileProcessed}
          refresh={workspace.refresh}
          notify={workspace.notify}
        />
      )}
      {failure && (
        <p className="pw-error" role="alert">
          {failure}
        </p>
      )}
      <section className="pw-notebook-tools">
        <div className="pw-notebook-search">
          <Search size={18} />
          <input
            aria-label="搜索我的清单"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索名称、笔记、问题或标签"
          />
        </div>
        <Filter
          name="主题分组"
          value={group}
          onChange={setGroup}
          options={groups.map((value) => ({ value, label: value }))}
        />
        <Filter
          name="阅读状态"
          value={status}
          onChange={setStatus}
          options={personalStatuses.map((value) => ({ value, label: value }))}
        />
        <label className="pw-checkbox">
          <input
            type="checkbox"
            checked={onlyStarred}
            onChange={(event) => setOnlyStarred(event.target.checked)}
          />
          只看收藏
        </label>
      </section>
      <div className="pw-notebook-toolbar">
        <label className="pw-checkbox">
          <input
            type="checkbox"
            checked={
              shown.length > 0 &&
              shown.every((item) => selected.includes(selectionKey(item)))
            }
            onChange={(event) =>
              setSelected(event.target.checked ? shown.map(selectionKey) : [])
            }
          />
          选择当前结果
        </label>
        <span>
          {shown.length} 条记录 · 已选 {selected.length} 条
        </span>
        <div className="pw-actions">
          <button
            disabled={busy || !shown.length}
            onClick={() => void exportItems("markdown")}
          >
            <Download size={15} />
            导出 Markdown
          </button>
          <button
            disabled={busy || !shown.length}
            onClick={() => void exportItems("json")}
          >
            <Download size={15} />
            兼容 JSON
          </button>
        </div>
      </div>
      {!shown.length ? (
        <Empty
          title={
            workspace.records.length
              ? "没有符合条件的个人记录"
              : "从一个想研究的方法开始"
          }
        >
          <p>在策略或因子详情中收藏，写下你的理解和问题。</p>
          <Link className="button primary" to="/strategies">
            去阅读策略 <ArrowRight size={15} />
          </Link>
        </Empty>
      ) : (
        <div className="pw-notebook-list">
          {shown.map((record) => (
            <article className="pw-saved" key={selectionKey(record)}>
              <div className="pw-saved-title">
                <input
                  type="checkbox"
                  aria-label={`选择 ${record.name}`}
                  checked={selected.includes(selectionKey(record))}
                  onChange={(event) =>
                    setSelected(
                      event.target.checked
                        ? [...selected, selectionKey(record)]
                        : selected.filter((id) => id !== selectionKey(record)),
                    )
                  }
                />
                <div>
                  <span className="pw-kind">{kindNames[record.kind]}</span>
                  <Link to={personalPath(record)}>{record.name} →</Link>
                </div>
                <span className="pw-state">{record.status}</span>
                {record.starred && <Star size={16} fill="currentColor" />}
              </div>
              <div className="pw-saved-meta">
                <span>
                  <FolderOpen size={13} />
                  {record.group || "未分组"}
                </span>
                {record.tags.map((tag) => (
                  <span className="pw-tag" key={tag}>
                    {tag}
                  </span>
                ))}
              </div>
              {record.reason && (
                <p>
                  <strong>选择理由：</strong>
                  {record.reason}
                </p>
              )}
              {record.questions && (
                <p>
                  <strong>问题与假设：</strong>
                  {record.questions}
                </p>
              )}
              {record.note && <p className="pw-note-preview">{record.note}</p>}
              <details>
                <summary>查看已保存的判断与固定版本</summary>
                <p>{record.summary || "尚未补充我的整理"}</p>
                <code>
                  {record.entity_id}
                  <br />
                  {record.definition_revision}
                </code>
                {record.problem && <p>来源 / 规则问题：{record.problem}</p>}
              </details>
              <Link
                className="pw-edit-note"
                to={`${personalPath(record)}#personal`}
              >
                阅读原文与编辑判断 <ArrowRight size={14} />
              </Link>
            </article>
          ))}
        </div>
      )}
      <p className="pw-muted">
        导出包含所选条目；未选择时导出当前筛选结果。定义、个人问题与研究记录一同保留，供后续研究参考。
      </p>
    </>
  );
}
function Migration({
  legacy,
  busy,
  migrate,
}: {
  legacy: {
    mode: "PUBLIC" | "PRIVATE";
    items: ReturnType<typeof loadNotebook>["items"];
    error?: string;
  }[];
  busy: boolean;
  migrate: (
    mode: string,
    items: ReturnType<typeof loadNotebook>["items"],
  ) => void;
}) {
  return (
    <>
      {legacy
        .filter((row) => row.items.length || row.error)
        .map((row) => (
          <section className="pw-migration" key={row.mode}>
            <h2>
              发现旧浏览器清单 ·{" "}
              {row.mode === "PUBLIC" ? "公开模式" : "私有模式"}
            </h2>
            {row.error ? (
              <p className="pw-error">{row.error} 原内容未删除。</p>
            ) : (
              <>
                <p>
                  这份清单有 {row.items.length}{" "}
                  条。可一次迁移到本地服务，之后由服务端去重，保留原来的备注和分组。
                </p>
                <button
                  disabled={busy}
                  onClick={() => migrate(row.mode, row.items)}
                >
                  迁移这份浏览器清单
                </button>
              </>
            )}
          </section>
        ))}
    </>
  );
}
function SourceCheck({ id }: { id: string }) {
  const check = useApi<{
    status: string;
    message: string;
    checked_at?: string | number;
  }>(`/v1/personal/source-check/${encodeURIComponent(id)}`);
  const [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  return (
    <div className="pw-source-check">
      <span>{check.data?.message || "来源链接尚未检查"}</span>
      {check.data?.checked_at && (
        <small title={String(check.data.checked_at)}>
          最近检查：{humanDate(check.data.checked_at)}
        </small>
      )}
      <button
        disabled={busy || isHosted}
        title={isHosted ? "实时来源复查由研究端处理" : undefined}
        onClick={async () => {
          setBusy(true);
          setFailure("");
          try {
            await personalApi(
              `/v1/personal/source-check/${encodeURIComponent(id)}`,
              { method: "POST", body: "{}" },
            );
            check.retry();
          } catch (error) {
            setFailure(error instanceof Error ? error.message : "检查未完成");
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "检查中…" : "检查来源链接"}
      </button>
      {failure && <span role="alert">{failure}</span>}
    </div>
  );
}

function PersonalResearch({ results }: { results: PersonalDetail["results"] }) {
  if (!results.items?.length)
    return (
      <p className="pw-muted">
        尚未研究。已有定义和来源仍可作为阅读与选题资料。
      </p>
    );
  const statusText: Record<string, string> = {
    SUCCEEDED: "计算已完成",
    COMPLETED: "已完成",
    FAILED: "计算未完成",
    BLOCKED: "条件不满足",
    PASS: "通过该项检查",
    INSUFFICIENT_EVIDENCE: "证据不足",
    EXPLORATORY_ANALYSIS: "探索性研究",
    RETROSPECTIVE_ANALYSIS: "回顾性研究",
    FACTOR_DIAGNOSTIC: "因子诊断",
    STRATEGY_REPLICATION: "策略复现",
    FACTOR_DEFINITION_CHECK: "定义与计算检查",
  };
  return (
    <div className="pw-retained-research">
      {results.items.map((raw, index) => {
        const study = raw as unknown as Record<string, unknown>;
        const translate = (value: unknown) =>
          typeof value === "string"
            ? statusText[value] || value
            : readable(value);
        const limitations = Array.isArray(study.limitations)
          ? study.limitations
          : [];
        return (
          <article
            key={String(study.run_id || index)}
            className="pw-implementation"
          >
            <h3>
              {translate(
                study.study_type || study.study_kind || "已有研究记录",
              )}
            </h3>
            <p>
              {translate(
                study.conclusion_level ||
                  study.classification ||
                  study.research_status ||
                  study.status,
              )}
            </p>
            {study.failure_reason ? (
              <p>已记录的问题：{readable(study.failure_reason)}</p>
            ) : null}
            {study.conclusion_reason ? (
              <p>结论依据：{readable(study.conclusion_reason)}</p>
            ) : null}
            <details>
              <summary>查看样本、方法与已有结果</summary>
              <dl className="pw-definition-list">
                <div>
                  <dt>样本与数据</dt>
                  <dd>{readable(study.sample)}</dd>
                </div>
                <div>
                  <dt>研究方法</dt>
                  <dd>{readable(study.methods || study.study_kind)}</dd>
                </div>
                <div>
                  <dt>保留的结果</dt>
                  <dd>
                    {study.numerical_display === "RESTRICTED"
                      ? "现有记录限制数值展示；原权限判断保持不变。"
                      : readable(study.metrics || study.results)}
                  </dd>
                </div>
                <div>
                  <dt>原始记录状态</dt>
                  <dd>{readable(study.execution_status || study.status)}</dd>
                </div>
                <div>
                  <dt>研究引用</dt>
                  <dd>
                    <code>{readable(study.run_id || study.request_id)}</code>
                  </dd>
                </div>
              </dl>
            </details>
            {limitations.length > 0 && (
              <ul>
                {limitations.map((text, i) => (
                  <li key={i}>{readable(text)}</li>
                ))}
              </ul>
            )}
            <small>
              只读历史记录。不同数据区间、成本与研究方法的结果不作直接收益排名。
            </small>
          </article>
        );
      })}
    </div>
  );
}

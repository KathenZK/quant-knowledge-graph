import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  Bookmark,
  Check,
  Columns2,
  SearchX,
  AlertCircle,
  LoaderCircle,
} from "lucide-react";
import type { Item, Kind, Results } from "./types";
export const kindLabel: Record<Kind, string> = {
  variant: "因子变体",
  concept: "概念族",
  strategy: "策略",
};
export const entityUrl = (item: { kind: Kind; entity_id: string }) =>
  `/entity/${item.kind}/${encodeURIComponent(item.entity_id)}`;
export function safeUrl(value: string | null | undefined): string | null {
  if (!value || Array.from(value).some((char) => char.charCodeAt(0) < 32))
    return null;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}
export function ExternalLink({
  url,
  children,
}: {
  url: string | null | undefined;
  children: ReactNode;
}) {
  const href = safeUrl(url);
  return href ? (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="external"
    >
      {children}
      <ArrowUpRight size={13} aria-hidden="true" />
      <span className="sr-only">（新窗口）</span>
    </a>
  ) : (
    <span>
      {children}
      <span className="muted"> · 链接未提供或不安全</span>
    </span>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      <SearchX size={30} aria-hidden="true" />
      <h2>{title}</h2>
      <div className="muted">{children}</div>
    </div>
  );
}
export function Loading() {
  return (
    <p role="status" className="loading">
      <LoaderCircle size={18} aria-hidden="true" />
      正在读取公开知识库…
    </p>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: string;
  retry?: () => void;
}) {
  return (
    <div role="alert" className="error">
      <AlertCircle size={18} aria-hidden="true" />
      <span>{error}</span>
      {retry && <button onClick={retry}>重试</button>}
    </div>
  );
}
export function Formula({ value }: { value: string | null | undefined }) {
  return value ? (
    <code className="formula">{value}</code>
  ) : (
    <span className="muted">未补充独立公式</span>
  );
}
export function Values({ value }: { value: unknown }) {
  if (
    value === null ||
    value === undefined ||
    value === "" ||
    (Array.isArray(value) && !value.length) ||
    (typeof value === "object" &&
      !Array.isArray(value) &&
      !Object.keys(value).length)
  )
    return <span className="muted">未补充</span>;
  return (
    <span className="wrap">
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </span>
  );
}

export function Parameters({ value }: { value: Record<string, unknown> }) {
  const labels: Record<string, string> = {
    window_or_lag: "窗口 / 滞后",
    unit: "单位",
    operators: "来源算子",
    numeric_literals: "数值常量",
    generator_default_config: "来源默认配置",
  };
  if (!Object.keys(value).length) return <Values value={null} />;
  return (
    <dl className="parameters">
      {Object.entries(value).map(([key, val]) => (
        <div key={key}>
          <dt>{labels[key] || key}</dt>
          <dd>
            {val === true ? (
              "是"
            ) : val === false ? (
              "否"
            ) : val === "trading_bars" ? (
              "交易观察条数"
            ) : Array.isArray(val) ? (
              val.join(" / ")
            ) : (
              <Values value={val} />
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}
export function TypeTag({ kind }: { kind: Kind }) {
  return (
    <span className={`tag tag-${kind}`}>
      {kindLabel[kind]} <span lang="en">{kind}</span>
    </span>
  );
}
export function Actions({
  item,
  saved,
  compared,
  onSave,
  onCompare,
}: {
  item: Item;
  saved: boolean;
  compared: boolean;
  onSave: (item: Item) => void;
  onCompare: (item: Item) => void;
}) {
  return (
    <div className="actions">
      <button
        aria-label={`${saved ? "取消收藏" : "收藏"} ${item.name}`}
        aria-pressed={saved}
        onClick={() => onSave(item)}
        className={saved ? "selected" : ""}
      >
        {saved ? (
          <Check size={16} aria-hidden="true" />
        ) : (
          <Bookmark size={16} aria-hidden="true" />
        )}
        <span>{saved ? "已收藏" : "收藏"}</span>
      </button>
      <button
        aria-label={`${compared ? "移出比较" : "比较"} ${item.name}`}
        aria-pressed={compared}
        onClick={() => onCompare(item)}
        className={compared ? "selected" : ""}
      >
        <Columns2 size={16} aria-hidden="true" />
        <span>{compared ? "已选" : "比较"}</span>
      </button>
    </div>
  );
}
export function Statuses({ item }: { item: Item }) {
  const labels = {
    catalog: "收录状态",
    implementation: "计算实现",
    readiness: "研究准备",
    result: "研究结果",
    display: "展示权限",
  };
  return (
    <dl className="statuses">
      {Object.entries(item.statuses).map(([key, val]) => (
        <div key={key}>
          <dt>{labels[key as keyof typeof labels]}</dt>
          <dd>
            <span
              className={`dot ${key === "catalog" || key === "display" ? "green" : ""}`}
            />
            {val}
          </dd>
        </div>
      ))}
    </dl>
  );
}
export function ResearchResults({
  results,
  compact = false,
}: {
  results: Results;
  compact?: boolean;
}) {
  return (
    <div>
      {!compact && (
        <div className="study-levels">
          {[
            ["computational_test", "计算测试", "核验公式与计算实现"],
            ["exploratory", "探索研究", "提出和筛选假设"],
            ["retrospective", "历史回顾", "说明历史样本表现"],
            ["confirmatory", "确认性研究", "按冻结合约检验假设"],
          ].map(([id, name, desc]) => (
            <div key={id}>
              <strong>{name}</strong>
              <code>{id}</code>
              <p>{desc}</p>
            </div>
          ))}
        </div>
      )}
      <Empty title="尚未研究">
        <p>{results.reason}</p>
        <p>没有收益指标或盈利曲线。研究结论也不代表买入建议或实盘资格。</p>
        <Link to="/explore">浏览定义与来源 →</Link>
      </Empty>
    </div>
  );
}

import type { Detail, Facet, Item, Kind, Meta, RelationGraph } from "./types";

export type PersonalStatus =
  "待读" | "已理解" | "值得研究" | "重复方法" | "暂不研究";
export const personalStatuses: PersonalStatus[] = [
  "待读",
  "已理解",
  "值得研究",
  "重复方法",
  "暂不研究",
];
export interface PersonalRecord {
  kind: Kind;
  entity_id: string;
  name: string;
  entity_type: string;
  definition_revision: string;
  stable_id?: string;
  stable_knowledge_id?: string;
  linked_notes?: PersonalRecord[];
  version_changed?: boolean;
  current_definition_revision?: string;
  starred: boolean;
  status: PersonalStatus;
  tags: string[];
  group: string;
  note: string;
  summary: string;
  questions: string;
  reason: string;
  aliases: string[];
  problem: string;
  updated_at?: string;
}
export interface Knowledge {
  reader_brief?: {
    version: string;
    purpose: string;
    purpose_basis: string;
    trading: {
      key: string;
      label: string;
      text: string;
      status: string;
      origin?: string;
      evidence?: string;
    }[];
    source_url?: string;
    economic_rationale: {
      text: string;
      status: string;
      notice: string;
      causal_status?: string;
      source_url?: string;
      source_locator?: string;
    };
    papers: {
      paper_id?: string;
      title: string;
      url?: string;
      year?: number;
      authors: string[];
      relationship: string;
      status: string;
      locator?: string;
      claim: string;
      version_read?: string;
      does_not_support?: string[];
    }[];
    empirical_notice: string;
    intake_status?: string;
    entry_type?: string;
    review_notice?: string;
    source_review_summary?: string;
    empirical_scope?: Record<string, unknown>;
    blocked_reasons?: string[];
    validation?: Record<string, string>;
    novelty?: Record<string, unknown>;
    worked_example?: { text: string; basis: string };
  };
  version?: string;
  summary: string;
  method_family: { value: string; label: string; basis?: string };
  source_facts: { label: string; text: string; source?: string }[];
  reading: {
    key: string;
    label: string;
    text: string;
    status: string;
    evidence?: string;
  }[];
  parameters: {
    name: string;
    value: unknown;
    meaning: string;
    unit?: string;
  }[];
  variables: { name: string; meaning: string }[];
  example: { text: string; basis: string } | null;
  unknowns: string[];
  source: {
    url?: string;
    locator?: string;
    native_ids?: string[];
    revision?: string;
    sha256?: string;
    author?: string;
    publication_date?: string | number;
    reference_year?: string | number;
    reported_date?: string;
    date_status?: string;
    collected_at?: string;
    collected_at_label?: string;
    collected_at_basis?: string;
    ingestion_observed_at?: string;
    collection_time_notice?: string;
    variant_created_at?: string;
  };
  layers?: {
    source_facts?: unknown[];
    explanations?: unknown[];
    user_notes?: unknown[];
    hypotheses?: unknown[];
  };
  formula?: string;
  normalized_formula?: unknown;
  explanation_basis?: string;
  original_rule?: string;
}
export type PersonalItem = Item & {
  is_historical?: boolean;
  current_entity_id?: string;
  stable_knowledge_id?: string;
  prior_version_ids?: string[];
  knowledge?: Knowledge;
  matches?: {
    field: string;
    label: string;
    text: string;
    term: string;
    start: number;
    end: number;
  }[];
  matched_fields?: string[];
  group?: { id: string; count: number };
  completeness?: string;
};
export type PersonalDetail = Detail & PersonalItem;
export interface PersonalMeta extends Omit<Meta, "mode" | "facets"> {
  intake_summary?: {
    reviewed_records: number;
    by_status: Record<string, number>;
    by_type: Record<string, number>;
    source_reviews: number;
    new_backtests_from_import: number;
  };
  snapshot_progress?: {
    as_of_utc: string;
    corpus_records: number;
    executed_records: number;
    execution_versions: number;
    imported_runs: number;
    awaiting_import_runs?: number;
    collection_cards?: number;
    factor_cards?: number;
  };
  mode: "personal_local";
  initialized?: boolean;
  message?: string;
  layer_counts?: Record<string, number>;
  facets: Meta["facets"] & {
    method_families?: Facet[];
    axes?: Facet[];
    extra_data?: Facet[];
    completeness?: Facet[];
    scopes?: Facet[];
  };
  dataset?: string | Record<string, unknown>;
  snapshot?: string | Record<string, unknown>;
  imported_at?: string;
  last_imported_at?: string;
  application_version?: string;
  build?: {
    status: "CURRENT" | "STALE" | "MISSING" | "INVALID";
    build_id?: string;
    source_fingerprint?: string;
    built_at?: string;
    app_version?: string;
    message?: string;
  };
  knowledge_counts?: Record<string, unknown>;
  reading_coverage?: Record<string, unknown>;
  method_families?: {
    value: string;
    label: string;
    count: number;
    description?: string;
    common_structures?: string[];
    questions?: string[];
    representatives: { entity_id: string; kind: Kind; name: string }[];
  }[];
  initialization?: { status: string; message?: string };
  warnings?: string[];
}
export type PersonalGraph = Omit<RelationGraph, "items"> & {
  items: (RelationGraph["items"][number] & {
    role?: string;
    explanation?: { category: string; label: string; text: string };
  })[];
};
export interface Duplicate {
  suggestion_id: string;
  left: { entity_id: string; name: string; kind: Kind };
  right: { entity_id: string; name: string; kind: Kind };
  classification: string;
  evidence: unknown;
  status: string;
  canonical_id?: string;
}
export function readable(value: unknown): string {
  if (value == null || value === "") return "来源未说明";
  if (Array.isArray(value))
    return value.length ? value.map(readable).join("、") : "来源未说明";
  if (typeof value === "object")
    return Object.entries(value)
      .map(([key, val]) => `${key}：${readable(val)}`)
      .join("；");
  return String(value);
}
export function personalPath(item: { kind: Kind; entity_id: string }) {
  return `/entity/${item.kind}/${encodeURIComponent(item.entity_id)}`;
}
export function recordPath(item: { kind: Kind; entity_id: string }) {
  return `/v1/personal/items/${item.kind}/${encodeURIComponent(item.entity_id)}`;
}
export function emptyRecord(item: PersonalItem): PersonalRecord {
  return {
    kind: item.kind,
    entity_id: item.entity_id,
    name: item.name,
    entity_type: item.entity_type,
    definition_revision: item.definition_revision,
    starred: false,
    status: "待读",
    tags: [],
    group: "",
    note: "",
    summary: "",
    questions: "",
    reason: "",
    aliases: [],
    problem: "",
  };
}
export async function personalApi<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-QuantGraph-Request": "1",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let detail = "";
    try {
      const error = await response.json();
      detail =
        typeof error.detail === "string"
          ? error.detail
          : typeof error.detail?.message === "string"
            ? error.detail.message
            : typeof error.error === "string"
              ? error.error
              : "";
    } catch {
      /* Non-JSON failures still have a useful status. */
    }
    throw new Error(
      detail ||
        (response.status === 404
          ? "当前快照中未找到此内容。"
          : response.status === 409
            ? "保存遇到版本冲突，请刷新后核对。原笔记仍保留。"
            : "操作未完成，请重试。"),
    );
  }
  return response.json() as Promise<T>;
}
export function downloadText(
  name: string,
  text: string,
  type = "text/markdown;charset=utf-8",
) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const relationLabels: Record<string, string> = {
  VARIANT_OF: "具体变体",
  IN_FAMILY: "属于同一方法族",
  USES_FACTOR: "规则使用因子",
  PARAMETER_VARIANT: "参数变体",
  ASSET_VARIANT: "资产变体",
  MARKET_VARIANT: "市场变体",
  FREQUENCY_VARIANT: "频率变体",
  DERIVED_FROM: "由此派生",
  COMPOSED_OF: "组合构成",
  DESCRIBES: "来源描述",
  RELATED_TO: "相关候选",
  CATEGORY_LINK_ONLY: "同一分类",
  SAME_AS: "同一实体",
  IMPLEMENTATION_OF: "实现引用",
  RULE_LINK_ONLY: "规则引用，未经收益归因",
  ALIAS_OF: "别名",
  CORRELATED_WITH: "实证相关",
  SIMILAR_TO: "相似候选",
  TEMPLATE_OF: "方法模板",
};
export const kindNames: Record<Kind, string> = {
  strategy: "策略",
  variant: "因子变体",
  concept: "因子概念",
  family: "策略概念",
  template: "策略模板",
  source: "来源记录",
};

export function sameRecord(record: PersonalRecord, item: PersonalItem) {
  return (
    record.kind === item.kind &&
    (record.entity_id === item.entity_id ||
      (!!item.stable_knowledge_id &&
        record.stable_knowledge_id === item.stable_knowledge_id) ||
      !!item.prior_version_ids?.includes(record.entity_id))
  );
}
export function personalPatch(record: Partial<PersonalRecord>) {
  const keys = [
    "starred",
    "status",
    "tags",
    "group",
    "note",
    "summary",
    "questions",
    "reason",
    "aliases",
    "problem",
  ] as const;
  return Object.fromEntries(
    keys.filter((key) => key in record).map((key) => [key, record[key]]),
  );
}

export function differenceLabel(value: {
  label: string;
  known?: boolean;
  status?: string;
}) {
  return (
    value.label +
    (value.known === false || value.status === "UNKNOWN" ? "待确认" : "不同")
  );
}

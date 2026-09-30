import type { EntityRef, Item, Notebook, SavedItem } from "./types";
export const STORAGE_KEY = "quantgraph:PUBLIC:research-list:v1";
type Mode = "PUBLIC" | "PRIVATE";
export const storageKey = (mode: Mode) => `quantgraph:${mode}:research-list:v1`;
export const refKey = (ref: EntityRef) =>
  `${ref.entity_type}:${ref.entity_id}@${ref.definition_revision}`;
export const kindFor = (ref: EntityRef) =>
  (
    ({
      FactorVariant: "variant",
      FactorConcept: "concept",
      Strategy: "strategy",
      StrategyVariant: "strategy",
      StrategyConcept: "family",
      StrategyTemplate: "template",
      SourceRecord: "source",
      FactorSourceRecord: "source",
    }) as const
  )[ref.entity_type];
const isObject = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === "object" && !Array.isArray(v);
const bounded = (v: unknown, max: number) =>
  typeof v === "string" && v.length <= max;
export function parseNotebook(raw: string, mode: Mode = "PUBLIC"): Notebook {
  if (raw.length > 1_000_000) throw new Error("清单超过 1 MB。");
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error("清单不是有效的 JSON，原清单未改变。");
  }
  if (
    !isObject(value) ||
    value.schema_version !== "quantgraph-list/v1" ||
    value.mode !== mode ||
    !Array.isArray(value.items) ||
    value.items.length > 500
  )
    throw new Error(`清单格式不正确，或不属于 ${mode} 模式。`);
  const items: SavedItem[] = value.items.map((v: unknown) => {
    if (
      !isObject(v) ||
      ![
        "FactorVariant",
        "FactorConcept",
        "Strategy",
        "StrategyVariant",
      ].includes(String(v.entity_type)) ||
      !bounded(v.entity_id, 200) ||
      !String(v.entity_id).startsWith("qkg:") ||
      !bounded(v.definition_revision, 200) ||
      !v.definition_revision ||
      !bounded(v.name, 500) ||
      !bounded(v.note, 4000) ||
      !bounded(v.group, 100)
    )
      throw new Error("条目引用、备注或分组格式不正确。");
    const ref = {
      entity_type: v.entity_type,
      entity_id: v.entity_id,
      definition_revision: v.definition_revision,
    } as EntityRef;
    if (v.kind !== kindFor(ref)) throw new Error("条目类型不一致。");
    return {
      ...ref,
      kind: kindFor(ref),
      name: v.name as string,
      note: v.note as string,
      group: v.group as string,
    };
  });
  if (new Set(items.map(refKey)).size !== items.length)
    throw new Error("清单含重复的定义引用。");
  return { schema_version: "quantgraph-list/v1", mode, items };
}
export function loadNotebook(mode: Mode = "PUBLIC"): {
  items: SavedItem[];
  error?: string;
} {
  try {
    const raw = localStorage.getItem(storageKey(mode));
    return { items: raw ? parseNotebook(raw, mode).items : [] };
  } catch {
    return {
      items: [],
      error:
        "浏览器清单无法读取或格式已损坏。原内容保留；请恢复备份，或明确重置后继续。",
    };
  }
}
export function saveNotebook(items: SavedItem[], mode: Mode = "PUBLIC") {
  localStorage.setItem(
    storageKey(mode),
    JSON.stringify({
      schema_version: "quantgraph-list/v1",
      mode,
      items,
    }),
  );
}
export function bookmark(item: Item): SavedItem {
  return {
    entity_type: item.entity_type,
    entity_id: item.entity_id,
    definition_revision: item.definition_revision,
    name: item.name,
    kind: item.kind,
    note: "",
    group: "待研究",
  };
}
export function download(name: string, data: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

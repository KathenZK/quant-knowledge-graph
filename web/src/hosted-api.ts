/* eslint-disable @typescript-eslint/no-explicit-any */
import { load, snapshotId } from "./hosted-data";
import { corpusApi } from "./hosted-corpus-api";
import { remote, hostedNoteKey } from "./hosted-transport";
type Item = Record<string, any>;
const norm = (v: unknown) =>
  String(v ?? "")
    .normalize("NFKC")
    .toLocaleLowerCase()
    .replace(/\s+/g, " ")
    .trim();
async function detail(
  kind: string,
  id: string,
  batch?: string,
  revision?: string,
): Promise<Item> {
  batch = batch || (await snapshotId());
  const manifest = await load<Record<string, any>>(
    "/catalog/manifest.json",
    batch,
  );
  if (!manifest[id] || manifest[id].kind !== kind)
    throw new Error("当前固定快照没有此条目");
  const d = await load<Item>(
    `/catalog/details/${manifest[id].file}.json.gz`,
    batch,
  );
  if (revision && d.definition_revision !== revision)
    throw new Error("PINNED_DEFINITION_UNAVAILABLE：没有用新定义替换原引用");
  return { ...d, snapshot_batch: batch };
}
async function search(u: URL) {
  const snapshot = await snapshotId();
  const p = u.searchParams,
    q = norm(p.get("q")),
    kind = p.get("kind") || "strategy",
    notes = await remote<Item[]>("/v1/personal/items")
      .then((r: any) => r.items)
      .catch(() => []);
  const map = await load<Record<string, string[]>>("/catalog/indexes.json");
  const paths =
    kind === "all"
      ? Object.entries(map)
          .filter(([k]) => k !== "factor_source")
          .flatMap(([, v]) => v)
      : kind === "variant"
        ? [...(map.variant || []), ...(map.factor_source || [])]
        : map[kind] || [];
  const all: Item[] = (
    await Promise.all(paths.map((path) => load<Item[]>(path)))
  ).flat();
  let rows = all.filter((i) => {
    if (
      kind !== "all" &&
      i.kind !== kind &&
      !(kind === "variant" && i.source_type === "factor_source_record")
    )
      return false;
    for (const k of ["category", "family", "frequency", "source_type"])
      if (p.get(k) && i[k] !== p.get(k)) return false;
    for (const [k, field] of [
      ["market", "markets"],
      ["field", "required_fields"],
    ])
      if (p.get(k) && !i[field]?.includes(p.get(k))) return false;
    if (
      p.get("template_id") &&
      i.strategy?.template_id !== p.get("template_id")
    )
      return false;
    if (
      p.get("method_family") &&
      i.knowledge?.method_family?.value !== p.get("method_family")
    )
      return false;
    const f = i.knowledge?.filters || {};
    if (
      p.get("factor_scope") &&
      p.get("factor_scope") !== "all" &&
      i.factor_quality?.group !== p.get("factor_scope")
    )
      return false;
    for (const k of ["axis", "extra_data", "completeness", "asset_scope"])
      if (p.get(k) && f[k] !== p.get(k)) return false;
    if (p.get("daily_ohlcv") === "true" && !f.daily_ohlcv) return false;
    const note = notes.find((n: Item) => n.entity_id === i.entity_id);
    if (
      p.get("personal_status") &&
      (note?.status || "待读") !== p.get("personal_status")
    )
      return false;
    if (
      p.has("starred") &&
      Boolean(note?.starred) !== (p.get("starred") === "true")
    )
      return false;
    if (!q) return true;
    const fields = [
      i.name,
      ...(i.aliases || []),
      ...(i.source_native_ids || []),
      i.formula,
      ...Object.values(i.search_fields || {}),
      ...(note?.aliases || []),
      note?.note,
      note?.summary,
      note?.questions,
    ].map(norm);
    return (
      fields.some((t) => t.includes(q)) ||
      q.split(" ").every((term) => fields.some((t) => t.includes(term)))
    );
  });
  rows.sort((a, b) => {
    const exact = (i: Item) =>
      [i.name, ...(i.aliases || []), ...(i.source_native_ids || [])].some(
        (x) => norm(x) === q,
      )
        ? 0
        : 1;
    return (
      exact(a) - exact(b) ||
      a.name.localeCompare(b.name, "zh-CN") ||
      a.entity_id.localeCompare(b.entity_id)
    );
  });
  const before = rows.length;
  if (p.get("collapse_templates") === "true") {
    const seen = new Set();
    rows = rows.filter((i) => {
      const key = i.group?.id || i.entity_id;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }
  const page = Math.max(1, Number(p.get("page")) || 1),
    size = Math.min(50, Math.max(1, Number(p.get("page_size")) || 20));
  return {
    items: rows.slice((page - 1) * size, page * size).map((i) => ({
      ...i,
      snapshot_batch: snapshot,
      matches: q
        ? [
            {
              field: "rule",
              label: "已有名称 / 原文",
              text:
                Object.values(i.search_fields || {}).find((x) =>
                  norm(x).includes(q),
                ) || i.name,
              term: q,
              start: 0,
              end: q.length,
            },
          ]
        : [],
    })),
    total: rows.length,
    record_total: before,
    total_before_collapse: before,
    page,
    page_size: size,
    query: { text: q, constraints: [] },
  };
}
async function relations(u: URL) {
  const id = decodeURIComponent(u.pathname.split("/").pop()!),
    all: Item[] = await load("/catalog/edges.json"),
    index: Item[] = await load("/catalog/nodes.json"),
    nodes = new Map(index.map((i) => [i.entity_id, i]));
  if (!nodes.has(id)) throw new Error("未找到关系起点");
  const p = u.searchParams,
    layer = p.get("layer") || "all",
    rel = p.get("relation"),
    confidence = Number(p.get("confidence")) || 0,
    hops = Math.min(2, Math.max(1, Number(p.get("hops")) || 1));
  const allowed = all.filter(
    (e) =>
      (!rel || e.relation === rel) &&
      (e.confidence || 0) >= confidence &&
      (layer === "all" ||
        !layer ||
        (layer === "method"
          ? ["structure", "component"].includes(e.explanation.category)
          : e.explanation.category === layer)),
  );
  let frontier = new Set([id]);
  const visited = new Set([id]),
    found = new Map<string, Item>();
  for (let step = 0; step < hops; step++) {
    const next = new Set<string>();
    for (const e of allowed)
      if (frontier.has(e.from_id) || frontier.has(e.to_id)) {
        found.set(e.relationship_id, e);
        next.add(e.from_id);
        next.add(e.to_id);
      }
    frontier = new Set([...next].filter((x) => !visited.has(x)));
    next.forEach((x) => visited.add(x));
  }
  const sorted = [...found.values()].sort(
      (a, b) =>
        a.relation.localeCompare(b.relation) ||
        a.relationship_id.localeCompare(b.relationship_id),
    ),
    offset = Math.max(0, Number(p.get("offset")) || 0),
    limit = Math.min(100, Number(p.get("limit")) || 20),
    items = sorted.slice(offset, offset + limit),
    ids = new Set([id]);
  items.forEach((e) => {
    ids.add(e.from_id);
    ids.add(e.to_id);
  });
  return {
    items,
    total: sorted.length,
    offset,
    limit,
    hops,
    nodes: [...ids].map((eid) => {
      const n = nodes.get(eid)!;
      return {
        entity_id: eid,
        name: n.name,
        kind: n.kind,
        entity_type: n.entity_type,
      };
    }),
    types: [...new Set(sorted.map((e) => e.relation))],
    categories: [
      { value: "source", label: "来源与实现" },
      { value: "component", label: "策略与因子使用关系" },
      { value: "structure", label: "概念、模板与变体" },
    ],
  };
}
async function compare(u: URL) {
  const refs = u.searchParams.getAll("ref");
  if (refs.length < 2 || refs.length > 4 || new Set(refs).size !== refs.length)
    throw new Error("请选择2–4个不同条目");
  const items = await Promise.all(
    refs.map((r) => {
      const slash = r.indexOf("/");
      return detail(r.slice(0, slash), r.slice(slash + 1));
    }),
  );
  const fields: [string, string, (i: Item) => unknown][] = [
    ["name", "名称", (i) => i.name],
    [
      "rule",
      "规则或定义",
      (i) => i.knowledge?.original_rule || i.knowledge?.original_definition,
    ],
    ["formula", "公式", (i) => i.formula],
    ["parameters", "参数", (i) => i.knowledge?.parameters],
    ["fields", "输入数据", (i) => i.required_fields],
    ["frequency", "频率", (i) => i.frequency],
    ["scope", "适用市场", (i) => i.markets],
    ["method", "方法归类", (i) => i.knowledge?.method_family?.label],
    ["axis", "比较对象与计算范围", (i) => i.knowledge?.filters?.axis],
    ["source", "来源", (i) => i.source_url],
    ["unknowns", "未说明事项", (i) => i.knowledge?.unknowns],
  ];
  const differences = fields.map(([key, label, fn]) => {
    const values = items.map(fn),
      known = values.every(
        (v) =>
          v != null &&
          ![
            "",
            "unknown",
            "尚未归类",
            "未分类",
            "待分类",
            "待确认",
            "[]",
            "{}",
          ].includes(typeof v === "object" ? JSON.stringify(v) : String(v)),
      );
    return {
      key,
      label,
      values,
      known,
      status: known ? "KNOWN" : "UNKNOWN",
      same: known && new Set(values.map((v) => JSON.stringify(v))).size === 1,
    };
  });
  const changed = differences
      .filter((d) => d.known && !d.same && d.key !== "name")
      .map((d) => d.label),
    missing = differences.filter((d) => !d.known).map((d) => d.label);
  return {
    items,
    differences,
    conclusions: [
      changed.length
        ? "当前条目的已知不同之处：" + changed.join("、") + "。"
        : "已知字段未显示可确定差异；不能据此认定等价。",
      ...(missing.length
        ? ["暂不能比较、需要核对的字段：" + missing.join("、") + "。"]
        : []),
      "下表保留原文、公式和参数差异；同名或同族不代表收益机制相同，未知不按相同处理。",
    ],
  };
}
export async function hostedRequest<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const u = new URL(url, window.location.origin),
    path = u.pathname,
    method = (init?.method || "GET").toUpperCase();
  if (path.startsWith("/v1/personal/corpus-research"))
    return corpusApi<T>(url, init);
  if (path === "/v1/personal/source-portfolios") {
    if (method !== "GET") throw new Error("来源组合只读");
    const all = await load<Item[]>("/data/source-portfolios.json.gz");
    const id = u.searchParams.get("record_id");
    return all
      .map((p) => ({
        ...p,
        records: p.records.filter((r: Item) => !id || r.id === id),
      }))
      .filter((p) => p.records.length) as T;
  }
  if (path === "/v1/web/meta") return load<T>("/catalog/meta.json");
  if (path === "/v1/web/search") return search(u) as Promise<T>;
  if (path === "/v1/web/compare") return compare(u) as Promise<T>;
  if (path.startsWith("/v1/web/relations/")) return relations(u) as Promise<T>;
  if (
    path.startsWith("/v1/web/entities/") ||
    path.startsWith("/v1/web/export/")
  ) {
    const parts = path.split("/");
    return detail(
      decodeURIComponent(parts[4]),
      decodeURIComponent(parts.slice(5).join("/")),
      u.searchParams.get("snapshot_batch") || undefined,
      u.searchParams.get("definition_revision") || undefined,
    ) as Promise<T>;
  }
  if (path === "/v1/personal/duplicates" && method === "GET")
    return {
      items: [],
      total: 0,
      notice: "此端不执行身份合并；无建议不代表没有重复",
    } as T;
  if (path.startsWith("/v1/personal/source-check/") && method === "GET")
    return {
      status: "NOT_CHECKED",
      message: "来源链接和已有证据可读，实时重新采集由研究端处理",
    } as T;
  return remote<T>(url, init);
}
export async function hostedFetch(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  if (url === "/v1/personal/export") {
    const query = JSON.parse(String(init?.body || "{}"));
    const all = await remote<any>("/v1/personal/items");
    const items = await Promise.all(
      all.items
        .filter(
          (r: Item) =>
            !query.ids?.length || query.ids.includes(hostedNoteKey(r)),
        )
        .map(async (r: Item) => {
          let definition;
          try {
            const manifest = await load<Record<string, any>>(
              "/catalog/manifest.json",
              r.snapshot_batch,
            );
            const entry = manifest[r.entity_id];
            if (entry && entry.kind === r.kind)
              definition = await load<Item>(
                `/catalog/details/${entry.file}.json.gz`,
                r.snapshot_batch,
              );
            if (definition?.definition_revision !== r.definition_revision)
              definition = undefined;
          } catch {
            /* retain the pinned note without substituting a definition */
          }
          return {
            ...r,
            definition,
            availability: definition
              ? "AVAILABLE"
              : "PINNED_DEFINITION_UNAVAILABLE",
          };
        }),
    );
    if (query.format === "markdown")
      return new Response(
        items
          .map(
            (r: Item) =>
              `# ${r.name}\n\n- 固定版本：${r.definition_revision}\n- 资料状态：${r.availability}\n\n${r.definition?.knowledge?.original_rule || r.definition?.formula || ""}\n\n我的笔记：${r.note}\n\n研究问题：${r.questions}`,
          )
          .join("\n\n"),
        { headers: { "Content-Type": "text/markdown;charset=utf-8" } },
      );
    return Response.json({
      schema_version: "quantgraph-cloud-notes-export/v1",
      items,
    });
  }
  return fetch(url, init);
}

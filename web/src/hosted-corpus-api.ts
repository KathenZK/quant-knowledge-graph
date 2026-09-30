import { load } from "./hosted-data";
type Row = {
  id: string;
  name: string;
  status: string;
  families: string[];
  search_text?: string;
  [key: string]: unknown;
};
type Manifest = {
  default_run: string;
  details: Record<string, string>;
  runs: { run_id: string }[];
  workscope_records?: Record<string, string>;
  data_quality_file?: string;
};
export async function corpusApi<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  if (init?.method && init.method !== "GET")
    throw new Error("本页面仅提供只读研究资料");
  const u = new URL(url, window.location.origin);
  const batch = u.searchParams.get("snapshot_batch") || undefined;
  const fixedLoad = <V>(path: string) => load<V>(path, batch);
  const m = await fixedLoad<Manifest>("/data/manifest.json");
  const run = u.searchParams.get("run_id") || m.default_run;
  if (!m.runs.some((r) => r.run_id === run))
    throw new Error("该运行尚未包含在当前快照");
  const prefix = "/v1/personal/corpus-research";
  const sub = u.pathname.slice(prefix.length);
  if (!sub) return fixedLoad<T>(`/data/runs/${run}/summary.json`);
  if (sub === "/data-quality") {
    const rows = m.data_quality_file
      ? await fixedLoad<Record<string, unknown>[]>(m.data_quality_file)
      : [];
    return rows.filter(
      (row) =>
        row.origin_run_id === run &&
        row.variant_id === u.searchParams.get("variant_id") &&
        row.origin_manifest_sha256 ===
          u.searchParams.get("origin_manifest_sha256"),
    ) as T;
  }
  if (sub.startsWith("/implementations/")) {
    const vid = decodeURIComponent(sub.slice("/implementations/".length));
    const key = m.details[`${run}|${vid}`];
    if (!key) throw new Error("该实现不在本批快照中");
    return fixedLoad<T>(`/data/implementations/${key}.json.gz`);
  }
  if (sub.startsWith("/records/")) {
    const id = decodeURIComponent(sub.slice("/records/".length));
    if (!u.searchParams.has("run_id") && m.workscope_records?.[id]) {
      const chunk = await fixedLoad<Record<string, unknown>>(
        m.workscope_records[id],
      );
      if (!chunk[id]) throw new Error("工作项与固定快照不一致");
      return chunk[id] as T;
    }
    const rows = await fixedLoad<Row[]>(`/data/runs/${run}/index.json.gz`);
    const row = rows.find((x) => x.id === id);
    if (!row) throw new Error("未找到原始记录");
    const detail = await fixedLoad<Record<string, unknown>>(
      `/data/records/${id}.json.gz`,
    );
    return { ...row, ...detail, run_id: run } as T;
  }
  if (sub === "/records") {
    const rows = await fixedLoad<Row[]>(`/data/runs/${run}/index.json.gz`);
    const q = (u.searchParams.get("q") || "").trim().toLocaleLowerCase();
    const status = u.searchParams.get("status") || "";
    const family = u.searchParams.get("family") || "";
    const matches = rows.filter(
      (x) =>
        (!q ||
          (x.search_text || `${x.id} ${x.name}`)
            .toLocaleLowerCase()
            .includes(q)) &&
        (!status || x.status === status) &&
        (!family || x.families.includes(family)),
    );
    const page = Math.max(1, Number(u.searchParams.get("page")) || 1);
    const size = 20;
    return {
      run_id: run,
      items: matches.slice((page - 1) * size, page * size),
      total: matches.length,
      page,
      page_size: size,
    } as T;
  }
  throw new Error("当前快照没有该只读视图");
}

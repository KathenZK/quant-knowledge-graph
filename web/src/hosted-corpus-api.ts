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
};
export async function corpusApi<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  if (init?.method && init.method !== "GET")
    throw new Error("本页面仅提供只读研究资料");
  const u = new URL(url, window.location.origin);
  const m = await load<Manifest>("/data/manifest.json");
  const run = u.searchParams.get("run_id") || m.default_run;
  if (!m.runs.some((r) => r.run_id === run))
    throw new Error("该运行尚未包含在当前快照");
  const prefix = "/v1/personal/corpus-research";
  const sub = u.pathname.slice(prefix.length);
  if (!sub) return load<T>(`/data/runs/${run}/summary.json`);
  if (sub.startsWith("/implementations/")) {
    const vid = decodeURIComponent(sub.slice("/implementations/".length));
    const key = m.details[`${run}|${vid}`];
    if (!key) throw new Error("该实现不在本批快照中");
    return load<T>(`/data/implementations/${key}.json.gz`);
  }
  const rows = await load<Row[]>(`/data/runs/${run}/index.json.gz`);
  if (sub.startsWith("/records/")) {
    const id = decodeURIComponent(sub.slice("/records/".length));
    const row = rows.find((x) => x.id === id);
    if (!row) throw new Error("未找到原始记录");
    const detail = await load<Record<string, unknown>>(
      `/data/records/${id}.json.gz`,
    );
    return { ...row, ...detail, run_id: run } as T;
  }
  if (sub === "/records") {
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

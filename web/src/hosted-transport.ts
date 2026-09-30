import type { PersonalItem, PersonalRecord } from "./personal-data";
export const isHosted = import.meta.env.VITE_QUANTGRAPH_DEPLOYMENT === "sites";
export async function remote<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-QuantGraph-Request": "1",
      ...init?.headers,
    },
  });
  if (!r.ok) {
    let detail = "";
    try {
      detail = (await r.json()).detail || "";
    } catch {
      /* status fallback */
    }
    throw new Error(
      detail ||
        (r.status === 401
          ? "请先登录此私有站点。"
          : "云端操作未完成，输入仍保留，请重试。"),
    );
  }
  return r.json() as Promise<T>;
}
export type NoteScope = {
  origin_run_id?: string;
  variant_id?: string;
  manifest_sha256?: string;
};
export function hostedRecordPath(
  item: {
    kind: string;
    entity_id: string;
    definition_revision: string;
    snapshot_batch?: string;
  } & NoteScope,
) {
  const query = new URLSearchParams({
    definition_revision: item.definition_revision,
  });
  if (item.snapshot_batch) query.set("snapshot_batch", item.snapshot_batch);
  for (const k of ["origin_run_id", "variant_id", "manifest_sha256"] as const)
    if (item[k]) query.set(k, item[k]!);
  return (
    "/v1/personal/items/" +
    item.kind +
    "/" +
    encodeURIComponent(item.entity_id) +
    "?" +
    query
  );
}
const pending = new Map<string, string>();
export async function hostedSave(
  item: PersonalItem,
  values: Partial<PersonalRecord>,
) {
  const binding = {
    ...item,
    kind: values.kind || item.kind,
    entity_id: values.entity_id || item.entity_id,
    definition_revision: values.definition_revision || item.definition_revision,
    origin_run_id: values.origin_run_id,
    variant_id: values.variant_id,
    manifest_sha256: values.manifest_sha256,
  };
  const url = hostedRecordPath(binding);
  const current =
    values.record_revision === undefined
      ? await remote<PersonalRecord>(url)
      : values;
  const fields = [
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
  ];
  const patch = Object.fromEntries(
    fields
      .filter((k) => k in values)
      .map((k) => [k, values[k as keyof PersonalRecord]]),
  );
  const expected = current.record_revision || 0;
  const key = JSON.stringify([url, expected, patch]);
  let mutation = pending.get(key);
  if (!mutation) {
    mutation = crypto.randomUUID();
    pending.set(key, mutation);
  }
  const saved = await remote<PersonalRecord>(url, {
    method: "PUT",
    body: JSON.stringify({
      mutation_id: mutation,
      expected_record_revision: expected,
      patch,
    }),
  });
  pending.delete(key);
  return saved;
}

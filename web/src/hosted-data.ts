let active: Promise<string> | undefined;
export function snapshotId() {
  if (!active)
    active = fetch("/v1/sync/status")
      .then(async (r) => {
        if (!r.ok) throw new Error("资料快照状态暂不可读");
        const v = await r.json();
        if (typeof v.active_batch !== "string")
          throw new Error("资料快照身份缺失");
        return v.active_batch as string;
      })
      .catch((e) => {
        active = undefined;
        throw e;
      });
  return active;
}
const cache = new Map<string, Promise<unknown>>();
export async function load<T = unknown>(
  path: string,
  batch?: string,
): Promise<T> {
  batch = batch || (await snapshotId());
  const key = JSON.stringify([path, batch]);
  if (!cache.has(key))
    cache.set(
      key,
      fetch(
        "/v1/snapshot/assets?" +
          new URLSearchParams({ path, ...(batch ? { batch_id: batch } : {}) }),
      )
        .then(async (r) => {
          if (!r.ok) throw new Error("固定资料暂不可读，请重试");
          const bytes = await r.arrayBuffer(),
            head = new Uint8Array(bytes);
          if (head[0] === 31 && head[1] === 139) {
            if (typeof DecompressionStream === "undefined")
              throw new Error("浏览器需要支持压缩资料读取");
            return new Response(
              new Response(bytes).body!.pipeThrough(
                new DecompressionStream("gzip"),
              ),
            ).json();
          }
          return JSON.parse(new TextDecoder().decode(bytes));
        })
        .catch((e) => {
          cache.delete(key);
          throw e;
        }),
    );
  return cache.get(key) as Promise<T>;
}

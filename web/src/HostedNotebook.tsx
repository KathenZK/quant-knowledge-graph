import { useEffect, useState } from "react";
import { remote, hostedRecordPath } from "./hosted-transport";
import type { PersonalRecord } from "./personal-data";
import { personalPatch } from "./personal-data";
import { download } from "./storage";
const keys = [
  "quantgraph-private-site-notebook-v1",
  "quantgraph:PUBLIC:research-list:v1",
  "quantgraph:PRIVATE:research-list:v1",
];
export function HostedSyncStatus() {
  const [state, setState] = useState<{
    feedback_last_event: number;
    cloud_received_cursor: number;
    cloud_received_at?: string;
  } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    remote<typeof state>("/v1/sync/status")
      .then(setState)
      .catch((e) => setError(String(e.message)));
  }, []);
  return (
    <div className="pw-notice" aria-live="polite">
      {error
        ? `云端状态暂不可读：${error}`
        : state
          ? `批注存于云端，研究端已收到 ${state.cloud_received_cursor} / ${state.feedback_last_event} 条修改。收到不代表研究已完成。`
          : "正在读取云端同步状态…"}
    </div>
  );
}
function rows(value: unknown): Partial<PersonalRecord>[] {
  const x = value as { items?: unknown };
  const list = Array.isArray(value) ? value : x?.items;
  if (!Array.isArray(list) || list.length > 5000)
    throw new Error("不是可读取的笔记清单");
  return list as Partial<PersonalRecord>[];
}
export default function HostedNotebookImport({
  file,
  onFileProcessed,
  refresh,
}: {
  file: File | null;
  onFileProcessed: () => void;
  refresh: () => void;
}) {
  const [candidates, setCandidates] = useState<
    { label: string; items: Partial<PersonalRecord>[] }[]
  >([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<{ id: string; status: string }[]>([]);
  useEffect(() => {
    const found = [];
    for (const key of keys) {
      let raw: string | null = null;
      try {
        raw = localStorage.getItem(key);
      } catch {
        /* storage may be disabled; cloud notes remain available */
      }
      if (raw) {
        try {
          found.push({ label: key, items: rows(JSON.parse(raw)) });
        } catch {
          found.push({ label: key, items: [] });
        }
      }
    }
    setCandidates(found);
  }, []);
  useEffect(() => {
    if (!file) return;
    if (file.size > 8000000) {
      setMessage("文件超过8MB，未导入");
      onFileProcessed();
      return;
    }
    file
      .text()
      .then((text) => {
        setCandidates((current) => [
          ...current,
          { label: file.name, items: rows(JSON.parse(text)) },
        ]);
        setMessage("已读取备份，请明确点击导入。尚未改动云端。");
      })
      .catch((e) => setMessage(String(e.message)))
      .finally(onFileProcessed);
  }, [file, onFileProcessed]);
  async function ingest(candidate: {
    label: string;
    items: Partial<PersonalRecord>[];
  }) {
    setBusy(true);
    setMessage("");
    const report = [];
    for (const row of candidate.items) {
      const id = String(row.entity_id || "未知引用");
      try {
        if (
          !row.entity_id ||
          !row.kind ||
          !row.entity_type ||
          !row.definition_revision
        )
          throw new Error("缺少固定对象版本");
        const url = hostedRecordPath(row as PersonalRecord);
        const old = await remote<PersonalRecord>(url);
        if (old.record_revision) {
          report.push({ id, status: "已有云端批注，保留现有内容，待手动比较" });
          continue;
        }
        const source = JSON.stringify([candidate.label, row]);
        const digest = [
          ...new Uint8Array(
            await crypto.subtle.digest(
              "SHA-256",
              new TextEncoder().encode(source),
            ),
          ),
        ]
          .map((b) => b.toString(16).padStart(2, "0"))
          .join("");
        await remote(url, {
          method: "PUT",
          body: JSON.stringify({
            mutation_id: "browser-import-" + digest,
            expected_record_revision: 0,
            patch: { ...personalPatch(row), starred: row.starred ?? true },
          }),
        });
        report.push({ id, status: "已导入" });
      } catch (e) {
        report.push({ id, status: e instanceof Error ? e.message : "未导入" });
      }
    }
    setResult(report);
    setMessage("逐项导入结束；浏览器原件和备份均未删除。冲突不会覆盖云端。");
    setBusy(false);
    refresh();
  }
  return (
    <section className="pw-reading-section">
      <h2>导入原有浏览器笔记</h2>
      <p>
        先保留原件，再逐项存入云端。已有批注或缺少固定版本的记录会列出，不会自动覆盖或改绑。
      </p>
      {candidates.length ? (
        candidates.map((c, i) => (
          <div key={i}>
            <span>
              {c.label} · {c.items.length} 条
            </span>{" "}
            <button
              disabled={busy || !c.items.length}
              onClick={() => void ingest(c)}
            >
              导入这些笔记
            </button>{" "}
            <button
              disabled={busy}
              onClick={() =>
                download("quantgraph-original-notes.json", { items: c.items })
              }
            >
              备份原件
            </button>
          </div>
        ))
      ) : (
        <p>当前浏览器未发现旧笔记；也可用上方恢复按钮读取备份。</p>
      )}
      {message && <p role="status">{message}</p>}
      {!!result.length && (
        <details open>
          <summary>逐项结果</summary>
          {result.map((r, i) => (
            <p key={i}>
              {r.id}：{r.status}
            </p>
          ))}
        </details>
      )}
    </section>
  );
}

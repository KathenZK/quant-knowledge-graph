import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Download, RotateCcw } from "lucide-react";
import { download } from "./storage";
import { personalApi, readable } from "./personal-data";

export type RestoreChoice = "KEEP_LOCAL" | "USE_BACKUP";
type Counts = {
  added: number;
  identical: number;
  conflicts: number;
  invalid: number;
};
type Timestamp = {
  created_at?: string | null;
  updated_at?: string | null;
  status?: "VALID" | "MISSING" | "INVALID";
  normalized_updated_at?: string | null;
};
export interface RestoreConflict {
  id: string;
  section: string;
  identity: Record<string, unknown>;
  local: Record<string, unknown>;
  backup: Record<string, unknown>;
  local_records?: Record<string, unknown>[];
  backup_records?: Record<string, unknown>[];
  versions: { local: Record<string, unknown>; backup: Record<string, unknown> };
  timestamps: { local: Timestamp; backup: Timestamp };
  reason: string;
}
export interface RestoreResult {
  status: "APPLIED";
  verified: boolean;
  counts: Partial<Counts>;
  result?: Record<string, unknown>;
  pre_restore_backup?: { id: string; download_url: string };
  replayed?: boolean;
  summary: string;
}
export interface RestorePreview {
  preview_token: string;
  backup_digest: string | null;
  counts_complete?: boolean;
  can_apply: boolean;
  counts: Counts;
  sections: Record<string, Counts>;
  conflicts: RestoreConflict[];
  invalid: { section: string; index?: number; reason: string }[];
  status: "PREVIEW" | "APPLIED";
  summary: string;
  decisions?: Record<string, RestoreChoice>;
  result?: RestoreResult;
  applied_at?: string;
}
const fieldLabels: Record<string, string> = {
  starred: "收藏",
  status: "阅读状态",
  tags: "标签",
  group: "分组",
  note: "备注",
  summary: "我的整理",
  questions: "问题与假设",
  reason: "研究选择理由",
  aliases: "个人别名",
  problem: "来源或规则问题",
  entity_id: "稳定实体引用",
  stable_id: "个人记录主键",
  stable_knowledge_id: "知识沿革身份",
  definition_revision: "固定定义版本",
  record_revision: "个人记录版本",
  created_at: "创建时间",
  updated_at: "修改时间",
};
const sectionLabels: Record<string, string> = {
  items: "个人笔记与收藏",
  duplicates: "重复判断",
  redirects: "身份关联",
  migrations: "迁移历史",
  audit: "操作历史",
};
function formatTime(value?: string | null) {
  if (!value) return "未提供";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? `${value}（格式无效）`
    : `${date.toISOString()}（UTC）`;
}
function ContentValue({ value }: { value: unknown }) {
  if (typeof value === "boolean") return <>{value ? "是" : "否"}</>;
  if (
    value === "" ||
    value == null ||
    (Array.isArray(value) && value.length === 0)
  )
    return <span className="pw-muted">空白</span>;
  return <>{readable(value)}</>;
}
export function RestoreConflictCard({
  conflict,
  choice,
  disabled,
  onChoose,
}: {
  conflict: RestoreConflict;
  choice?: RestoreChoice;
  disabled?: boolean;
  onChoose: (value: RestoreChoice) => void;
}) {
  const fields = [
    "starred",
    "status",
    "group",
    "tags",
    "note",
    "summary",
    "questions",
    "reason",
    "aliases",
    "problem",
  ].filter((key) => key in conflict.local || key in conflict.backup);
  return (
    <fieldset className="pw-restore-conflict" data-conflict-id={conflict.id}>
      <legend>
        {readable(
          conflict.identity.name ||
            conflict.identity.entity_id ||
            conflict.identity.id ||
            conflict.id,
        )}
      </legend>
      <p className="pw-restore-reason">
        {sectionLabels[conflict.section] || conflict.section} ·{" "}
        {conflict.reason}
      </p>
      <div className="pw-restore-versions">
        {(["local", "backup"] as const).map((side) => (
          <div key={side}>
            <h3>{side === "local" ? "本机当前内容" : "备份中的内容"}</h3>
            <dl>
              <div>
                <dt>实体引用</dt>
                <dd>
                  <code>
                    {readable(
                      conflict.versions[side]?.entity_id ||
                        conflict[side].entity_id,
                    )}
                  </code>
                </dd>
              </div>
              <div>
                <dt>固定定义版本</dt>
                <dd>
                  <code>
                    {readable(
                      conflict.versions[side]?.definition_revision ||
                        conflict[side].definition_revision,
                    )}
                  </code>
                </dd>
              </div>
              <div>
                <dt>个人记录版本</dt>
                <dd>
                  <code>
                    {readable(
                      conflict.versions[side]?.record_revision ||
                        conflict[side].record_revision,
                    )}
                  </code>
                </dd>
              </div>
              <div>
                <dt>修改时间</dt>
                <dd>
                  {formatTime(conflict.timestamps[side]?.updated_at)}
                  {conflict.timestamps[side]?.status &&
                    conflict.timestamps[side].status !== "VALID" && (
                      <small>时间缺失或无效；不会据此选择版本。</small>
                    )}
                </dd>
              </div>
            </dl>
          </div>
        ))}
      </div>
      {fields.length > 0 && (
        <div className="pw-table-scroll">
          <table className="pw-table pw-restore-diff">
            <caption>双方个人内容；时间仅供核对，不自动决定取舍</caption>
            <thead>
              <tr>
                <th>内容</th>
                <th>本机</th>
                <th>备份</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((key) => (
                <tr
                  key={key}
                  className={
                    JSON.stringify(conflict.local[key]) !==
                    JSON.stringify(conflict.backup[key])
                      ? "pw-restore-changed"
                      : undefined
                  }
                >
                  <th scope="row">{fieldLabels[key]}</th>
                  <td>
                    <ContentValue value={conflict.local[key]} />
                  </td>
                  <td>
                    <ContentValue value={conflict.backup[key]} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <details>
        <summary>查看完整双方记录与身份字段</summary>
        <div className="pw-restore-raw">
          <section>
            <h3>本机原记录</h3>
            <pre>
              {JSON.stringify(
                conflict.local_records || conflict.local,
                null,
                2,
              )}
            </pre>
          </section>
          <section>
            <h3>备份原记录</h3>
            <pre>
              {JSON.stringify(
                conflict.backup_records || conflict.backup,
                null,
                2,
              )}
            </pre>
          </section>
        </div>
      </details>
      <div className="pw-restore-choices">
        <label>
          <input
            type="radio"
            name={`restore-${conflict.id}`}
            value="KEEP_LOCAL"
            checked={choice === "KEEP_LOCAL"}
            disabled={disabled}
            onChange={() => onChoose("KEEP_LOCAL")}
          />
          保留本机内容 <code>KEEP_LOCAL</code>
        </label>
        <label>
          <input
            type="radio"
            name={`restore-${conflict.id}`}
            value="USE_BACKUP"
            checked={choice === "USE_BACKUP"}
            disabled={disabled}
            onChange={() => onChoose("USE_BACKUP")}
          />
          采用备份内容 <code>USE_BACKUP</code>
        </label>
      </div>
    </fieldset>
  );
}
function CountRow({
  counts,
  label,
  complete = true,
}: {
  counts: Counts;
  label: string;
  complete?: boolean;
}) {
  return (
    <div className="pw-restore-counts" aria-label={label}>
      <strong>{label}</strong>
      <span>
        新增 <b>{complete ? counts.added : "未计算"}</b>
      </span>
      <span>
        内容相同 <b>{complete ? counts.identical : "未计算"}</b>
      </span>
      <span>
        待选择冲突 <b>{complete ? counts.conflicts : "未计算"}</b>
      </span>
      <span>
        无效 <b>{counts.invalid}</b>
      </span>
    </div>
  );
}
export default function PersonalRestore({
  file,
  onFileProcessed,
  refresh,
  notify,
}: {
  file: File | null;
  onFileProcessed: () => void;
  refresh: () => void;
  notify: (message: string) => void;
}) {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("restore") || "";
  const [preview, setPreview] = useState<RestorePreview | null>(null);
  const [decisions, setDecisions] = useState<Record<string, RestoreChoice>>({});
  const [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  const [name, setName] = useState("备份文件"),
    [result, setResult] = useState<RestoreResult | null>(null);
  useEffect(() => {
    if (!file) return;
    let active = true;
    const controller = new AbortController();
    setBusy(true);
    setFailure("");
    setPreview(null);
    setResult(null);
    setDecisions({});
    setName(file.name);
    navigate({ search: "" }, { replace: true });
    void (async () => {
      try {
        if (file.size > 8 * 1024 * 1024)
          throw new Error("备份超过 8 MiB，未上传也未改动本机记录。");
        const backup = JSON.parse(await file.text());
        const report = await personalApi<RestorePreview>(
          "/v1/personal/restore/preview",
          {
            method: "POST",
            body: JSON.stringify({ backup }),
            signal: controller.signal,
          },
        );
        if (!active) return;
        setPreview(report);
        setDecisions(report.decisions || {});
        navigate(
          {
            search: new URLSearchParams({
              restore: report.preview_token,
            }).toString(),
          },
          { replace: true },
        );
      } catch (error) {
        if (active)
          setFailure(
            error instanceof Error
              ? error.message
              : "预览失败。本机记录未改变。",
          );
      } finally {
        if (active) {
          setBusy(false);
          onFileProcessed();
        }
      }
    })();
    return () => {
      active = false;
      controller.abort();
    };
  }, [file, onFileProcessed, navigate]);
  useEffect(() => {
    if (!token || file || preview?.preview_token === token) return;
    let active = true;
    setBusy(true);
    setFailure("");
    personalApi<RestorePreview>(
      `/v1/personal/restore/reports/${encodeURIComponent(token)}`,
    )
      .then((report) => {
        if (active) {
          setPreview(report);
          setDecisions(report.decisions || {});
          setResult(report.status === "APPLIED" ? report.result || null : null);
        }
      })
      .catch((error) => {
        if (active)
          setFailure(
            error instanceof Error ? error.message : "无法读取恢复报告",
          );
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [token, file, preview?.preview_token]);
  const close = () => {
    setPreview(null);
    setFailure("");
    setResult(null);
    setDecisions({});
    navigate({ search: "" }, { replace: true });
  };
  const unresolved =
    preview?.conflicts.filter((conflict) => !decisions[conflict.id]).length ||
    0;
  const apply = async () => {
    if (!preview || unresolved || !preview.can_apply) return;
    setBusy(true);
    setFailure("");
    try {
      const applied = await personalApi<RestoreResult>("/v1/personal/restore", {
        method: "POST",
        body: JSON.stringify({
          preview_token: preview.preview_token,
          decisions,
        }),
      });
      setResult(applied);
      setPreview({
        ...preview,
        status: "APPLIED",
        can_apply: false,
        decisions,
        result: applied,
      });
      refresh();
      notify(applied.summary || "恢复已完成并核对。原有记录的恢复点已保存。");
    } catch (error) {
      setFailure(
        error instanceof Error
          ? error.message
          : "恢复状态尚未确认，请重新读取报告核对。双方内容仍可在报告中查看。",
      );
    } finally {
      setBusy(false);
    }
  };
  const refreshReport = async () => {
    if (!preview) return;
    setBusy(true);
    setFailure("");
    try {
      const report = await personalApi<RestorePreview>(
        `/v1/personal/restore/reports/${encodeURIComponent(preview.preview_token)}`,
      );
      setPreview(report);
      if (report.status === "APPLIED") {
        setResult(report.result || null);
        refresh();
      }
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "读取报告失败");
    } finally {
      setBusy(false);
    }
  };
  if (!file && !token && !preview && !failure) return null;
  return (
    <section className="pw-restore-preview" aria-labelledby="restore-title">
      <h2 id="restore-title">恢复预览 · {name}</h2>
      <p>
        先核对，再恢复。内容不同的记录需要你逐条选择；时间较新不代表自动采用。固定定义版本与个人引用一同保留。
      </p>
      {busy && <p role="status">正在核对恢复资料…</p>}
      {failure && (
        <div role="alert" className="pw-error">
          <p>{failure}</p>
          <p>
            不确定状态时先读取报告；预览失效或本机已有新修改时，请重新选择原备份生成新预览。
          </p>
          {preview && (
            <button disabled={busy} onClick={() => void refreshReport()}>
              <RotateCcw size={14} />
              重新读取恢复报告
            </button>
          )}
        </div>
      )}
      {preview && (
        <>
          <CountRow
            counts={preview.counts}
            label="全部身份与关系组"
            complete={preview.counts_complete !== false}
          />
          {preview.sections.items && (
            <CountRow
              counts={preview.sections.items}
              label="其中：笔记与收藏身份组"
            />
          )}
          <p>{preview.summary}</p>
          {preview.invalid.length > 0 && (
            <div className="pw-error">
              <strong>存在无效记录，本次不能恢复任何内容。</strong>
              <ul>
                {preview.invalid.map((item, index) => (
                  <li key={index}>
                    {sectionLabels[item.section] || item.section}
                    {item.index != null ? ` · 第 ${item.index + 1} 项` : ""}：
                    {item.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {preview.conflicts.map((conflict) => (
            <RestoreConflictCard
              key={conflict.id}
              conflict={conflict}
              choice={decisions[conflict.id]}
              disabled={busy || preview.status === "APPLIED"}
              onChoose={(value) =>
                setDecisions((current) => ({
                  ...current,
                  [conflict.id]: value,
                }))
              }
            />
          ))}
          {result ? (
            <div className="pw-restore-result" role="status">
              <h3>{result.verified ? "恢复已完成并核对" : "恢复结果待核对"}</h3>
              <p>{result.summary}</p>
              {result.replayed && (
                <p>这是同一次恢复的重复请求，没有重复新增。</p>
              )}
              {result.pre_restore_backup && (
                <button
                  onClick={async () => {
                    const url = result.pre_restore_backup!.download_url;
                    if (!url.startsWith("/v1/personal/restore/backups/")) {
                      setFailure("恢复点地址不正确，请在报告中核对。");
                      return;
                    }
                    try {
                      download(
                        "quantgraph-before-restore.json",
                        await personalApi(url),
                      );
                    } catch (error) {
                      setFailure(
                        error instanceof Error
                          ? error.message
                          : "下载恢复点失败",
                      );
                    }
                  }}
                >
                  <Download size={14} />
                  下载执行前恢复点
                </button>
              )}
            </div>
          ) : (
            <p className="pw-restore-pending">
              {unresolved
                ? `还有 ${unresolved} 个冲突未选择。本机不会因此被修改，双方内容保存在这份报告中。`
                : preview.counts.invalid
                  ? "无效记录须修正后重新预览。"
                  : "所有冲突已选择。执行前服务会再次检查本机是否发生变化，并保存恢复点。"}
            </p>
          )}
          <div className="pw-actions">
            <button
              disabled={busy}
              onClick={() =>
                download("quantgraph-restore-report.json", {
                  ...preview,
                  decisions,
                  result: result || preview.result,
                })
              }
            >
              <Download size={14} />
              下载完整恢复报告
            </button>
            {preview.status !== "APPLIED" && (
              <button
                className="primary"
                disabled={
                  busy ||
                  !preview.can_apply ||
                  unresolved > 0 ||
                  preview.counts.invalid > 0
                }
                onClick={() => void apply()}
              >
                按已选择的内容恢复
              </button>
            )}
            <button disabled={busy} onClick={close}>
              {result ? "关闭报告" : "暂不恢复"}
            </button>
          </div>
        </>
      )}
    </section>
  );
}

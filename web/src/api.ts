import { isHosted } from "./hosted-transport";
import { hostedRequest, hostedFetch } from "./hosted-api";
import { useEffect, useState } from "react";
export async function api<T>(url: string, init?: RequestInit): Promise<T> {
  if (isHosted) return hostedRequest<T>(url, init);
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-QuantGraph-Request": "1",
      ...init?.headers,
    },
  });
  if (!response.ok)
    throw new Error(
      response.status === 401
        ? "请先登录管理后台，再提交或查看研究任务。"
        : response.status === 404
          ? "当前公开版本中没有此条目。"
          : response.status === 409
            ? "引用不在当前公开版本中，或定义版本已变化。请核对原始备份，系统不会自动替换引用。"
            : response.status === 422
              ? "请求参数或引用格式不正确。"
              : response.status === 503 && url.endsWith("/research-requests")
                ? "研究请求导出服务暂时不可用。清单可先保存或备份，研究未运行。"
                : "服务暂时不可用，请重试。",
    );
  return response.json() as Promise<T>;
}
export function useApi<T>(url: string) {
  const [state, setState] = useState<{
    data?: T;
    error?: string;
    loading: boolean;
  }>({ loading: true });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true });
    api<T>(url, { signal: controller.signal })
      .then((data) => setState({ data, loading: false }))
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({
            error: error instanceof Error ? error.message : "加载失败。",
            loading: false,
          });
      });
    return () => controller.abort();
  }, [url, attempt]);
  return { ...state, retry: () => setAttempt((n) => n + 1) };
}

export function applicationFetch(url: string, init?: RequestInit) {
  return isHosted ? hostedFetch(url, init) : fetch(url, init);
}

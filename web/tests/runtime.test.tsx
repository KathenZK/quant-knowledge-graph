import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RuntimeInformation } from "../src/PersonalApp";
import { personalApi, type PersonalMeta } from "../src/personal-data";
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
const meta = {
  mode: "personal_local",
  counts: { strategy: 5818, variant: 1207 },
  facets: {},
  application_version: "0.2.0",
  snapshot: "TEST snapshot",
  build: { status: "CURRENT", build_id: "old-page-build" },
} as PersonalMeta;
describe("runtime version disclosure", () => {
  it("rechecks on focus and warns an old page without replacing unsaved input", async () => {
    vi.stubEnv("VITE_QUANTGRAPH_BUILD_ID", "old-page-build");
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...meta,
        build: { ...meta.build, build_id: "new-served-build" },
      }),
    });
    vi.stubGlobal("fetch", fetch);
    render(
      <>
        <textarea aria-label="unsaved note" defaultValue="TEST 未保存内容" />
        <RuntimeInformation meta={meta} />
      </>,
    );
    fireEvent(window, new Event("focus"));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "服务已更新，本页仍是旧版本",
      ),
    );
    expect(screen.getByRole("textbox")).toHaveValue("TEST 未保存内容");
    expect(fetch).toHaveBeenCalledWith("/v1/web/meta", expect.anything());
  });
  it("shows a stale build warning even when page and served build ids match", () => {
    vi.stubEnv("VITE_QUANTGRAPH_BUILD_ID", "old-page-build");
    render(
      <RuntimeInformation
        meta={{
          ...meta,
          build: {
            ...meta.build!,
            status: "STALE",
            message: "TEST 源码已变化，请正常重启",
          },
        }}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("源码已变化");
  });
  it("preserves the server conflict reason instead of hiding it behind a generic error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => ({
          detail: {
            code: "STALE_PREVIEW",
            message: "TEST 预览后本机已变化，请重新预览",
          },
        }),
      }),
    );
    await expect(personalApi("/v1/personal/restore")).rejects.toThrow(
      "预览后本机已变化",
    );
  });
});

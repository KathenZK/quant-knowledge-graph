import React from "react";
import { beforeAll, afterEach, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  cleanup,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { PersonalItem, PersonalRecord } from "../src/personal-data";
vi.stubEnv("VITE_QUANTGRAPH_DEPLOYMENT", "sites");
const { hostedSave } = await import("../src/hosted-transport");
const { NoteEditor } = await import("../src/PersonalApp");
const { default: HostedNotebookImport } = await import("../src/HostedNotebook");
const item = {
  kind: "source",
  entity_id: "private-intake:factor:synthetic",
  entity_type: "FactorSourceRecord",
  definition_revision: "v1",
  name: "合成因子",
} as unknown as PersonalItem;
const note = {
  ...item,
  starred: false,
  status: "待读",
  tags: ["原标签"],
  group: "",
  note: "原笔记",
  summary: "",
  questions: "原问题",
  reason: "",
  aliases: [],
  problem: "",
  record_revision: 1,
  updated_at: "2026-09-30T00:00:00Z",
} as PersonalRecord;
beforeAll(() => vi.stubGlobal("scrollTo", () => {}));
afterEach(() => {
  cleanup();
  sessionStorage.clear();
  localStorage.clear();
  vi.unstubAllGlobals();
});
it("retries a lost response with the same idempotency key and original revision", async () => {
  const requests: unknown[] = [];
  let attempt = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init: RequestInit) => {
      requests.push(JSON.parse(String(init.body)));
      if (++attempt === 1) throw new Error("offline");
      return Response.json({ ...note, record_revision: 2 });
    }),
  );
  await expect(hostedSave(item, { ...note, note: "待检验" })).rejects.toThrow(
    "offline",
  );
  await hostedSave(item, { ...note, note: "待检验" });
  expect(requests[0]).toEqual(requests[1]);
  expect(requests[0]).toMatchObject({
    expected_record_revision: 1,
    patch: { note: "待检验" },
  });
});
it("does not permit an empty loading draft or editing during an outstanding save", async () => {
  let resolveRead: (v: Response) => void = () => {};
  let resolveSave: () => void = () => {};
  vi.stubGlobal(
    "fetch",
    () =>
      new Promise<Response>((r) => {
        resolveRead = r;
      }),
  );
  const save = vi.fn(
    () =>
      new Promise<void>((r) => {
        resolveSave = r;
      }),
  );
  const workspace = {
    records: [],
    compare: [],
    save,
    toggleCompare: () => {},
    notify: () => {},
    refresh: () => {},
  };
  render(
    <MemoryRouter>
      <NoteEditor item={item} workspace={workspace} />
    </MemoryRouter>,
  );
  expect(screen.getByRole("button", { name: /保存/ })).toBeDisabled();
  resolveRead(Response.json(note));
  await waitFor(() => expect(screen.getByDisplayValue("原笔记")).toBeEnabled());
  fireEvent.change(screen.getByDisplayValue("原笔记"), {
    target: { value: "新草稿" },
  });
  fireEvent.click(screen.getByRole("button", { name: /保存/ }));
  await waitFor(() => expect(save).toHaveBeenCalled());
  expect(screen.getByDisplayValue("新草稿")).toBeDisabled();
  resolveSave();
});
it("offers explicit import for the actual old Site key without overwriting cloud notes", async () => {
  localStorage.setItem(
    "quantgraph-private-site-notebook-v1",
    JSON.stringify([note]),
  );
  const fetch = vi.fn(async () => Response.json(note));
  vi.stubGlobal("fetch", fetch);
  render(
    <HostedNotebookImport
      file={null}
      onFileProcessed={() => {}}
      refresh={() => {}}
    />,
  );
  fireEvent.click(await screen.findByRole("button", { name: "导入这些笔记" }));
  await screen.findByText(/已有云端批注/);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(localStorage.getItem("quantgraph-private-site-notebook-v1")).toContain(
    "原笔记",
  );
});

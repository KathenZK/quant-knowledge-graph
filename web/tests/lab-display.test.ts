import { beforeEach, expect, it, vi } from "vitest";
import { fidelityLabel, statusLabel } from "../src/CorpusResearch";
import { corpusApi } from "../src/hosted-corpus-api";
import { load } from "../src/hosted-data";

vi.mock("../src/hosted-data", () => ({ load: vi.fn() }));
beforeEach(() => {
  vi.mocked(load).mockReset();
});

it("labels execution adaptation separately from standardized reproduction", () => {
  expect(fidelityLabel("ADAPTED")).toBe("执行改编回测");
  expect(statusLabel("tested_adapted_only")).toBe("仅有执行改编回测");
  expect(fidelityLabel("HYPOTHESIS")).toBe("假设性回测");
});

it("uses the pinned workscope shard before legacy records and resolves the added implementation", async () => {
  const old = { origin_run_id: "old", variant_id: "old-v" };
  const added = { origin_run_id: "new", variant_id: "new-v" };
  const record = { id: "M0300", related_results: [old, added] };
  const manifest = {
    default_run: "old",
    runs: [{ run_id: "old" }, { run_id: "new" }],
    details: { "new|new-v": "fixed-key" },
    workscope_records: { M0300: "/data/workscope/records-3.json.gz" },
  };
  vi.mocked(load).mockImplementation(async (path: string) => {
    if (path === "/data/manifest.json") return manifest as never;
    if (path === "/data/workscope/records-3.json.gz")
      return { M0300: record } as never;
    if (path === "/data/implementations/fixed-key.json.gz")
      return { id: "M0300", fidelity_class: "ADAPTED", curve: [] } as never;
    throw new Error("Unexpected legacy fallback: " + path);
  });
  expect(
    await corpusApi("/v1/personal/corpus-research/records/M0300?snapshot_batch=fixed"),
  ).toEqual(record);
  const detail = await corpusApi<{ fidelity_class: string }>(
    "/v1/personal/corpus-research/implementations/new-v?run_id=new&snapshot_batch=fixed",
  );
  expect(detail.fidelity_class).toBe("ADAPTED");
  expect(vi.mocked(load).mock.calls.every((call) => call[1] === "fixed")).toBe(true);
});

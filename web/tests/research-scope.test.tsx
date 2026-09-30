import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import ResearchAssurance from "../src/ResearchAssurance";
import ResearchInterpretation, {
  type Interpretation,
} from "../src/ResearchInterpretation";
import { type CorpusDetail } from "../src/CorpusResearch";
import { nativeResearchId } from "../src/ResearchInDetails";
import type { PersonalItem } from "../src/personal-data";

afterEach(() => vi.unstubAllGlobals());
const detail = {
  run_id: "run",
  variant_id: "v",
  metrics: { evidence_subtype: "FUND_VEHICLE_BUY_HOLD_PROXY" },
  spec: {},
  lineage: { declared_lineage: { source_run_manifest_sha256: "original" } },
} as unknown as CorpusDetail;
it("shows version-bound lifecycle warnings and separates four assurance axes", async () => {
  const fetch = vi.fn(async (url: RequestInfo | URL) => {
    expect(String(url)).toContain("data-quality");
    return Response.json([
      {
        overlay_id: "synthetic",
        asset: "SMH",
        warning_zh: "2011年前身连续链尚未核验",
        strict_comparability_eligible: false,
      },
    ]);
  });
  vi.stubGlobal("fetch", fetch);
  render(<ResearchAssurance detail={detail} />);
  expect(
    await screen.findByText("2011年前身连续链尚未核验"),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/本项测试的是基金载体买入持有代理/),
  ).toBeInTheDocument();
  for (const label of [
    "数据质量",
    "当时可得信息（PIT）",
    "实现忠实度",
    "统计证据",
  ])
    expect(screen.getByText(label)).toBeInTheDocument();
  expect(fetch.mock.calls[0][0]).toContain("origin_manifest_sha256=original");
});
it("does not treat unavailable quality annotations as a pass", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new Error("offline");
    }),
  );
  render(<ResearchAssurance detail={detail} />);
  expect(
    await screen.findByText(/最新数据质量注解暂不可读/),
  ).toBeInTheDocument();
});
it("never transfers an interpretation to another collection revision", async () => {
  const row = {
    interpretation_version: "v1",
    record_id: "id",
    actual_tested_rule: "实际入场",
    source_and_implementation_differences: "规则解释",
    observed_findings: [],
    mechanism_hypothesis: { text: "假说", verification_status: "UNTESTED" },
    failure_or_applicability_conditions: "条件",
    robustness_scope: "费用",
    unverified_claims: [],
    research_priority: { category: "pending", reason: "待研究" },
    next_falsification_test: "下一步",
    evidence_bindings: [
      {
        origin_run_id: "run",
        variant_id: "same",
        origin_manifest_sha256: "original",
        collection_manifest_sha256: "old",
      },
    ],
  } satisfies Interpretation;
  const { rerender } = render(
    <ResearchInterpretation
      rows={[row]}
      selected={{
        origin_run_id: "run",
        variant_id: "same",
        manifest_sha256: "old",
      }}
    />,
  );
  expect(screen.getByText("实际入场")).toBeInTheDocument();
  rerender(
    <ResearchInterpretation
      rows={[row]}
      selected={{
        origin_run_id: "run",
        variant_id: "same",
        manifest_sha256: "new",
      }}
    />,
  );
  await waitFor(() =>
    expect(screen.queryByText("实际入场")).not.toBeInTheDocument(),
  );
  expect(screen.getByText(/这个版本尚无人工研究总结/)).toBeInTheDocument();
});
it("recognizes a typed non-strategy work item only at its exact definition revision", () => {
  const item = {
    kind: "source",
    definition_revision: "revision",
    research_scope: {
      in_scope: true,
      record_id: "component",
      definition_revision: "revision",
    },
  } as PersonalItem;
  expect(nativeResearchId(item)).toBe("component");
  expect(
    nativeResearchId({ ...item, definition_revision: "changed" }),
  ).toBeUndefined();
});

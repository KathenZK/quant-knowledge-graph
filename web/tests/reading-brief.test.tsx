import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import KnowledgeBrief from "../src/KnowledgeBrief";
import ResearchInDetails, {
  LegacyResearchEntry,
  nativeResearchId,
} from "../src/ResearchInDetails";
import type { PersonalDetail } from "../src/personal-data";

const item = {
  kind: "strategy",
  entity_id: "synthetic:catalog",
  name: "合成策略",
  source_native_ids: ["M9999"],
  knowledge: {
    original_rule: "合成规则",
    source: { native_ids: ["M9999"] },
    reader_brief: {
      version: "reader-brief/v1",
      purpose: "比较价格与参考水平",
      purpose_basis: "根据规则整理",
      trading: [
        { key: "entry", label: "入场", text: "条件未说明", status: "UNKNOWN" },
      ],
      economic_rationale: {
        text: "未收录盈利机制证据",
        status: "UNKNOWN",
        notice: "操作规则不证明盈利",
      },
      papers: [
        {
          paper_id: "platform",
          title: "合成平台论文",
          authors: [],
          relationship: "平台或集合引用",
          status: "COLLECTION_REFERENCE",
          claim: "不证明具体因子收益",
        },
      ],
      empirical_notice: "定义和实证分别判断",
    },
  },
} as unknown as PersonalDetail;
afterEach(() => vi.unstubAllGlobals());
describe("Readable detail and research integration", () => {
  it("keeps source matching, formula repair and empirical status separate", () => {
    render(
      <KnowledgeBrief
        item={{
          ...item,
          kind: "variant",
          factor_quality: {
            group: "basic_features",
            label: "基础价量特征",
            review_label: "原式已对照源码；参数元数据已修正",
            paper_scope_label: "平台论文没有逐条收益证据",
            missing_facts: ["算子运行语义待核"],
            calculation_explanation: "当根实体长度除以当根振幅",
            numeric_meaning: "描述当根价格形状",
            strategy_use: "可作为模型输入候选，需单独验证",
            metadata_corrections: [
              {
                version: "synthetic-v1",
                field: "window_or_lag",
                previous: 2,
                current: null,
                basis: "当前观测需求1不表示滞后1",
              },
            ],
          },
        }}
      />,
    );
    expect(screen.getByText("平台论文没有逐条收益证据")).toBeInTheDocument();
    expect(screen.getByText(/当前观测需求1不表示滞后1/)).toBeInTheDocument();
    expect(
      screen.getByText(/怎样用于研究：可作为模型输入候选/),
    ).toBeInTheDocument();
    expect(screen.queryByText("已经验证盈利")).not.toBeInTheDocument();
  });
  it("shows a related definition as an unbound reference, not the original formula", () => {
    render(
      <KnowledgeBrief
        item={{
          ...item,
          kind: "variant",
          factor_quality: {
            group: "definition_references",
            label: "待补定义的指标引用",
            review_label: "来源正文待恢复",
            paper_scope_label: "定义不构成alpha证据",
            missing_facts: [],
            calculation_explanation: "教学定义示意",
            reference_template: {
              definition_source_url: "https://example.com/definition",
              source_locator: "合成定位",
            },
          },
        }}
      />,
    );
    expect(screen.getByText(/尚未绑定为本条可执行公式/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /相关定义出处/ })).toHaveAttribute(
      "href",
      "https://example.com/definition",
    );
    expect(screen.getByText("来源正文待恢复")).toBeInTheDocument();
  });
  it("shows three understandable sections without fabricating missing evidence", () => {
    render(<KnowledgeBrief item={item} />);
    expect(
      screen.getByRole("heading", { name: "1. 这项策略做什么" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "2. 交易什么，怎样进出场" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "3. 论文与盈利依据" }),
    ).toBeInTheDocument();
    expect(screen.getByText("平台或集合引用")).toBeInTheDocument();
    expect(screen.getByText("待补资料")).toBeInTheDocument();
  });
  it("never associates a factor with strategy results by matching source name", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    render(
      <MemoryRouter>
        <ResearchInDetails item={{ ...item, kind: "variant" }} />
      </MemoryRouter>,
    );
    expect(nativeResearchId({ ...item, kind: "variant" })).toBeUndefined();
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByText(/因子定义版本单独关联/)).toBeInTheDocument();
  });
  it("keeps identical variant IDs scoped to their origin runs in comparison", async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      return {
        ok: true,
        json: async () =>
          url.includes("/implementations/")
            ? {
                name: "合成",
                run_id: url.includes("run-b") ? "run-b" : "run-a",
                variant_id: "same-id",
                spec: {},
                lineage: {
                  manifest_sha256: url.includes("run-b")
                    ? "b".repeat(64)
                    : "a".repeat(64),
                },
                metrics: {
                  periods: {
                    full: {
                      start: "2024-01-01",
                      end: "2024-12-31",
                      cagr: url.includes("run-b") ? 0.2 : 0.1,
                    },
                  },
                },
                fidelity_class: "HYPOTHESIS",
              }
            : {
                id: "M9999",
                audit: { 规则: "合成规则" },
                related_results: [
                  {
                    origin_run_id: "run-a",
                    manifest_sha256: "a".repeat(64),
                    variant_id: "same-id",
                    fidelity_class: "STANDARDIZED",
                  },
                  {
                    origin_run_id: "run-b",
                    manifest_sha256: "b".repeat(64),
                    variant_id: "same-id",
                    fidelity_class: "HYPOTHESIS",
                  },
                ],
              },
      } as Response;
    });
    vi.stubGlobal("fetch", fetch);
    render(
      <MemoryRouter>
        <ResearchInDetails item={item} compact />
      </MemoryRouter>,
    );
    const select = await screen.findByLabelText("合成策略的历史实现");
    fireEvent.change(select, {
      target: { value: JSON.stringify(["run-b", "same-id", "b".repeat(64)]) },
    });
    expect(await screen.findByText("20.00%")).toBeInTheDocument();
    expect(
      fetch.mock.calls.some(([url]) => String(url).includes("run_id=run-b")),
    ).toBe(true);
    fireEvent.change(select, {
      target: { value: JSON.stringify(["run-a", "same-id", "a".repeat(64)]) },
    });
    expect(await screen.findByText("10.00%")).toBeInTheDocument();
  });
  it("redirects old native record links into the existing strategy detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          ({ ok: true, json: async () => ({ items: [item] }) }) as Response,
      ),
    );
    function Location() {
      const l = useLocation();
      return <p>{l.pathname + l.search + l.hash}</p>;
    }
    render(
      <MemoryRouter initialEntries={["/results?record=M9999"]}>
        <Routes>
          <Route path="/results" element={<LegacyResearchEntry />} />
          <Route path="*" element={<Location />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(
        screen.getByText("/entity/strategy/synthetic%3Acatalog#research"),
      ).toBeInTheDocument(),
    );
  });
});

it("keeps two comparison selections independent and restores them with history", async () => {
  const second = {
    ...item,
    entity_id: "synthetic:second",
    name: "第二策略",
    source_native_ids: ["M9998"],
    knowledge: { ...item.knowledge, source: { native_ids: ["M9998"] } },
  } as PersonalDetail;
  const values = {
    first: JSON.stringify(["run-a", "one", "a".repeat(64)]),
    second: JSON.stringify(["run-b", "two", "b".repeat(64)]),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("data-quality") || url.includes("source-portfolios"))
        return Response.json([]);
      if (url.includes("/implementations/")) {
        const first = url.includes("run-a");
        return Response.json({
          name: first ? "第一结果" : "第二结果",
          run_id: first ? "run-a" : "run-b",
          variant_id: first ? "one" : "two",
          spec: {},
          lineage: { manifest_sha256: (first ? "a" : "b").repeat(64) },
          metrics: { periods: { full: { cagr: first ? 0.11 : 0.22 } } },
        });
      }
      const first = url.includes("M9999");
      return Response.json({
        audit: { 规则: "合成规则" },
        related_results: [
          {
            origin_run_id: first ? "run-a" : "run-b",
            variant_id: first ? "one" : "two",
            manifest_sha256: (first ? "a" : "b").repeat(64),
            fidelity_class: "HYPOTHESIS",
          },
        ],
      });
    }),
  );
  function HistoryControls() {
    const navigate = useNavigate();
    return (
      <>
        <button onClick={() => navigate("?unrelated=preserved")}>
          另一个历史状态
        </button>
        <button onClick={() => navigate(-1)}>返回选择</button>
      </>
    );
  }
  render(
    <MemoryRouter>
      <HistoryControls />
      <ResearchInDetails item={item} compact />
      <ResearchInDetails item={second} compact />
    </MemoryRouter>,
  );
  const first = await screen.findByLabelText("合成策略的历史实现"),
    other = await screen.findByLabelText("第二策略的历史实现");
  fireEvent.change(first, { target: { value: values.first } });
  expect(await screen.findByText("11.00%")).toBeInTheDocument();
  fireEvent.change(other, { target: { value: values.second } });
  expect(await screen.findByText("22.00%")).toBeInTheDocument();
  expect(screen.getByText("11.00%")).toBeInTheDocument();
  expect(first).toHaveValue(values.first);
  expect(other).toHaveValue(values.second);
  fireEvent.click(screen.getByText("另一个历史状态"));
  await waitFor(() =>
    expect(screen.queryByText("11.00%")).not.toBeInTheDocument(),
  );
  fireEvent.click(screen.getByText("返回选择"));
  expect(await screen.findByText("11.00%")).toBeInTheDocument();
  expect(await screen.findByText("22.00%")).toBeInTheDocument();
});

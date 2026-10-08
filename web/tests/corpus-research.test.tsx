import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import CorpusResearch, {
  EquityChart,
  ResearchDetail,
  SourceRecordDetail,
  metricValue,
  type CorpusDetail,
} from "../src/CorpusResearch";

const detail: CorpusDetail = {
  run_id: "synthetic-run",
  id: "SYNTHETIC-1",
  variant_id: "SYNTHETIC-1@A",
  name: "合成研究样例",
  family: "synthetic-family",
  metrics: {
    periods: {
      full: {
        start: "2024-01-01",
        end: "2024-12-31",
        cagr: 0.1,
        sharpe: 0,
        max_drawdown: -0.2,
      },
    },
    cost_sensitivity: {
      "0": { full: { cagr: 0.1 } },
      "5": { full: { cagr: 0.08 } },
    },
    supplemental_defaults_flag: true,
  },
  spec: {
    source_url: "javascript:alert(1)",
    rule_excerpt: "<img src=x onerror=alert(1)>",
    assumptions: ["合成假设，非真实结果"],
  },
  audit: {
    source_verification_status: "not_individually_checked",
    source_rule_attribution_status: "unverified",
  },
  curve: [
    { date: "2024-01-01", equity: 1, drawdown: 0 },
    { date: "2024-01-02", equity: 0.8, drawdown: -0.2 },
  ],
  lineage: { source_record_id: "SYNTHETIC-1", definition_binding: "unproven" },
  limitations: ["仅用于界面测试"],
};
afterEach(() => vi.unstubAllGlobals());
describe("private corpus research evidence", () => {
  it("does not turn missing values into zero, profitability or verification", () => {
    expect(metricValue(undefined)).toBe("未提供");
    expect(metricValue(NaN)).toBe("未提供");
    expect(metricValue(0)).toBe("0.00");
    expect(metricValue(-0.2, true)).toBe("-20.00%");
    const { container } = render(<ResearchDetail detail={detail} />);
    expect(screen.getByText("尚未逐条核验来源")).toBeInTheDocument();
    expect(screen.getByText("来源归属未核验")).toBeInTheDocument();
    expect(screen.getByText(/包含额外补充默认假设/)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    expect(screen.getByText("0.00")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("比较区间"), {
      target: { value: "holdout" },
    });
    expect(screen.queryByText("10.00%")).not.toBeInTheDocument();
    expect(screen.getByText(/不随上方区间切换/)).toBeInTheDocument();
  });
  it("does not invent a curve when daily evidence is missing", () => {
    render(<EquityChart points={[]} />);
    expect(screen.getByText(/不补造曲线/)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
  it("only queries personal endpoints and preserves unmatched records", async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const summary = {
        available: true,
        run_id: "synthetic-run",
        runs: [{ run_id: "synthetic-run" }],
        counts: {
          corpus_records: 2,
          tested_records: 1,
          tested_variants: 1,
          used_data_series: 1,
          data_files: 1,
        },
        coverage_counts: { tested: 1, screened_data: 1 },
        families: [],
        limitations: [],
      };
      const records = {
        items: [
          {
            id: "SYNTHETIC-2",
            name: "数据缺失样例",
            status: "screened_data",
            reason: "缺少指定数据，不代表策略失效",
            tested_variants: 0,
            families: [],
            audit: {},
            implementations: [],
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      };
      return {
        ok: true,
        json: async () => (url.includes("/records?") ? records : summary),
      } as Response;
    });
    vi.stubGlobal("fetch", fetch);
    render(
      <MemoryRouter initialEntries={["/results"]}>
        <CorpusResearch />
      </MemoryRouter>,
    );
    expect(
      await screen.findByText("SYNTHETIC-2 · 数据缺失样例"),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("覆盖状态"), {
      target: { value: "screened_data" },
    });
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(([url]) =>
          String(url).includes("status=screened_data"),
        ),
      ).toBe(true),
    );
    expect(
      fetch.mock.calls.every(([url]) =>
        String(url).startsWith("/v1/personal/corpus-research"),
      ),
    ).toBe(true);
    expect(
      await screen.findByText("缺少指定数据，不代表策略失效"),
    ).toBeInTheDocument();
  });
});

it("closes stale detail when filters change and keeps multiple source implementations distinct", async () => {
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const summary = {
      available: true,
      run_id: "synthetic-run",
      runs: [{ run_id: "synthetic-run" }],
      counts: {
        corpus_records: 1,
        tested_records: 1,
        tested_variants: 2,
        used_data_series: 1,
        data_files: 1,
      },
      coverage_counts: { tested: 1 },
      families: [{ value: "synthetic-family", count: 2 }],
      limitations: [],
    };
    const records = {
      items: [
        {
          id: "SYNTHETIC-1",
          name: "双实现样例",
          status: "tested",
          reason: "仅用于测试",
          tested_variants: 2,
          families: ["synthetic-family"],
          audit: {},
          implementations: [
            { variant_id: "SYNTHETIC-1@A", family: "synthetic-family" },
            { variant_id: "SYNTHETIC-1@B", family: "synthetic-family" },
          ],
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    };
    return {
      ok: true,
      json: async () =>
        url.includes("/implementations/")
          ? detail
          : url.includes("/records?")
            ? records
            : summary,
    } as Response;
  });
  vi.stubGlobal("fetch", fetch);
  render(
    <MemoryRouter initialEntries={["/results"]}>
      <CorpusResearch />
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: /SYNTHETIC-1@A/ }));
  expect(
    await screen.findByRole("heading", { name: "合成研究样例" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "关闭实现详情" }));
  expect(
    screen.queryByRole("heading", { name: "合成研究样例" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /SYNTHETIC-1@B/ }));
  expect(
    await screen.findByRole("heading", { name: "合成研究样例" }),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("实现方法分组"), {
    target: { value: "synthetic-family" },
  });
  expect(
    screen.queryByRole("heading", { name: "合成研究样例" }),
  ).not.toBeInTheDocument();
});

it("shows source evidence for an untested record without inventing a result", () => {
  render(
    <SourceRecordDetail
      record={{
        id: "SYNTHETIC-U",
        name: "待补数据",
        status: "screened_data",
        reason: "所需数据尚未接入",
        tested_variants: 0,
        families: [],
        implementations: [],
        source_url: "javascript:alert(1)",
        audit: {
          规则: "原始规则全文",
          source_verification_status: "not_individually_checked",
          source_rule_attribution_status: "unverified",
        },
      }}
    />,
  );
  expect(screen.getByText("原始规则全文")).toBeInTheDocument();
  expect(screen.getByText(/本条没有附带逐条来源检查/)).toBeInTheDocument();
  expect(screen.getByText(/0 个本次回测实现/)).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

it("pins opened evidence to its run and clears unavailable filters when switching runs", async () => {
  function Location() {
    return <output data-testid="location">{useLocation().search}</output>;
  }
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const summary = {
        available: true,
        run_id: url.includes("run_id=next-run") ? "next-run" : "synthetic-run",
        runs: [{ run_id: "synthetic-run" }, { run_id: "next-run" }],
        counts: {
          corpus_records: 1,
          tested_records: 1,
          tested_variants: 1,
          used_data_series: 1,
          data_files: 1,
        },
        coverage_counts: { tested: 1 },
        families: [{ value: "synthetic-family", count: 1 }],
        limitations: [],
      };
      const records = {
        items: [
          {
            id: "SYNTHETIC-1",
            name: "固定引用",
            status: "tested",
            reason: "仅用于测试",
            tested_variants: 1,
            families: ["synthetic-family"],
            audit: {},
            implementations: [
              { variant_id: "SYNTHETIC-1@A", family: "synthetic-family" },
            ],
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      };
      return {
        ok: true,
        json: async () =>
          url.includes("/implementations/")
            ? detail
            : url.includes("/records?")
              ? records
              : summary,
      } as Response;
    }),
  );
  render(
    <MemoryRouter
      initialEntries={["/results?family=synthetic-family&status=tested"]}
    >
      <CorpusResearch />
      <Location />
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: /SYNTHETIC-1@A/ }));
  expect(screen.getByTestId("location").textContent).toContain(
    "run_id=synthetic-run",
  );
  fireEvent.change(await screen.findByLabelText("研究快照"), {
    target: { value: "next-run" },
  });
  expect(screen.getByTestId("location").textContent).toBe("?run_id=next-run");
  await waitFor(() =>
    expect(screen.getByLabelText("研究快照")).toHaveValue("next-run"),
  );
});

it("labels hypothesis evidence prominently and derives period choices from retained data", () => {
  const hypothetical: CorpusDetail = {
    ...detail,
    fidelity_class: "HYPOTHESIS",
    fidelity_reason: "以全资金替代原始100股，仅检验信号",
    metrics: {
      ...detail.metrics,
      periods: {
        full: detail.metrics.periods!.full,
        stress_window: { cagr: -0.15 },
      },
    },
  };
  render(<ResearchDetail detail={hypothetical} />);
  expect(screen.getByText("假设性回测")).toBeInTheDocument();
  expect(
    screen.getByText("以全资金替代原始100股，仅检验信号"),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("option", { name: "2026 观察段" }),
  ).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("比较区间"), {
    target: { value: "stress_window" },
  });
  expect(screen.getByText("-15.00%")).toBeInTheDocument();
});

it("links each cross-run result to its own immutable origin protocol", () => {
  render(
    <MemoryRouter>
      <SourceRecordDetail
        record={{
          id: "SYNTHETIC-U",
          name: "跨批次样例",
          status: "not_evaluated_in_this_run",
          reason: "本批没有实验",
          tested_variants: 0,
          families: [],
          implementations: [],
          audit: {},
          related_results: [
            {
              origin_run_id: "original-run",
              variant_id: "same-id",
              fidelity_class: "STANDARDIZED",
              protocol_sha256: "a".repeat(64),
              manifest_sha256: "b".repeat(64),
            },
            {
              origin_run_id: "hypothesis-run",
              variant_id: "same-id",
              fidelity_class: "HYPOTHESIS",
              fidelity_reason: "仓位假设",
              protocol_sha256: "c".repeat(64),
              manifest_sha256: "d".repeat(64),
            },
          ],
        }}
      />
    </MemoryRouter>,
  );
  expect(
    screen.getByRole("link", { name: "same-id · 标准化规则实现" }),
  ).toHaveAttribute("href", "/results?run_id=original-run&variant=same-id");
  expect(
    screen.getByRole("link", { name: "same-id · 假设性回测" }),
  ).toHaveAttribute("href", "/results?run_id=hypothesis-run&variant=same-id");
  expect(screen.getByText("仓位假设")).toBeInTheDocument();
});

it("shows capital exhaustion as NA and keeps native windows separate", () => {
  const d: CorpusDetail = {
    ...detail,
    metrics: {
      ...detail.metrics,
      primary_window_id: "0",
      retained_windows: [
        {
          window_id: "0",
          curve: detail.curve,
          curve_meta: { observations: 2 },
          source_window: {
            evaluation_start: "2024-01-01",
            evaluation_end: "2024-01-02",
            periods: {
              full: { observations: 2, cagr: 0.1 },
              latest_2026: { observations: 243, cagr: 0, max_drawdown: 0 },
            },
          },
          capital_state: { state: "MODEL_CAPITAL_EXTINGUISHED" },
          presentation_periods: {
            full: { observations: 2, cagr: -1, max_drawdown: -1 },
            latest_2026: {
              observations: 0,
              status: "no_positive_equity",
              cagr: null,
              max_drawdown: null,
            },
          },
        },
        {
          window_id: "1",
          capital_state: { state: "POSITIVE_TERMINAL_EQUITY" },
          curve: [{ date: "2026-07-01", equity: 1.1, drawdown: 0 }],
          curve_meta: { observations: 1 },
          source_window: {
            evaluation_start: "2026-07-01",
            evaluation_end: "2026-07-01",
            periods: { full: { observations: 0, cagr: 0 } },
          },
        },
      ],
    },
  };
  render(<ResearchDetail detail={d} />);
  expect(screen.getByText(/模型资本耗尽/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("比较区间"), {
    target: { value: "latest_2026" },
  });
  expect(screen.getByText("资本已耗尽，此区间不适用")).toBeInTheDocument();
  expect(
    Array.from(document.querySelectorAll(".cr-metrics td")).map(
      (el) => el.textContent,
    ),
  ).not.toContain("0.00%");
  fireEvent.change(screen.getByLabelText("独立数据窗口"), {
    target: { value: "1" },
  });
  fireEvent.change(screen.getByLabelText("比较区间"), {
    target: { value: "full" },
  });
  expect(screen.getByText("样本不足（0个观察）")).toBeInTheDocument();
  expect(screen.queryByText(/模型资本耗尽/)).not.toBeInTheDocument();
});

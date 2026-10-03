import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { ResearchDetail, type CorpusDetail } from "../src/CorpusResearch";

it("uses the existing full-period detail and comparison shape for accepted fixed-quantity research", () => {
  // Synthetic values only: this verifies rendering, not real M1266 performance.
  const controlNote =
    "M1266自身控制：信号收盘冻结90%数量，非满仓含费控制；没有fee0/20或delay2匹配控制。原pending是发布时状态，协调验收不等于Site部署。";
  const metric = { cagr: 0.1, sharpe: 0, max_drawdown: -0.2 };
  const detail: CorpusDetail = {
    id: "M1266",
    run_id: "synthetic-m1266",
    variant_id: "synthetic-m1266-base",
    name: "合成固定数量展示",
    family: "synthetic",
    fidelity_class: "ADAPTED",
    metrics: {
      periods: { full: metric },
      same_instrument_benchmark: { full: { ...metric, cagr: 0.2 } },
      cost_sensitivity: {
        "0": { full: { ...metric, cagr: 0.11 } },
        "20": { full: { ...metric, cagr: 0.09 } },
      },
      additional_native_bar_lag: { full: { ...metric, cagr: 0.12 } },
      risk_match_note: controlNote,
      implementation_fidelity: "ADAPTED_SOURCE_CORRECTED_VARIANT",
    },
    spec: {
      source_url: "https://example.org/source",
      rule_excerpt: "自撰操作规则摘要：EMA趋势中的回撤入场与持仓峰值退出。",
      assumptions: ["100根预热，731评价日，旧曝光窗口非OOS。", controlNote],
    },
    audit: { accepted: false, trusted: false },
    curve: [
      { date: "2023-01-01", equity: 1, drawdown: 0 },
      { date: "2024-12-31", equity: 1.2, drawdown: -0.1 },
    ],
    curve_meta: {
      observations: 731,
      total_observations: 731,
      returned_points: 25,
      sampling: "首个点为首评价开盘前锚点，不是Jan1收盘；仅保留月末抽样。",
    },
    lineage: { definition_revision_bound: false },
    limitations: ["原基准25点保留，当前UI不绘制其附加曲线。非严格复现。"],
  };
  render(<ResearchDetail detail={detail} />);
  expect(screen.getByLabelText("比较区间")).toHaveValue("full");
  expect(screen.getByText(/自撰操作规则摘要：EMA/)).toBeInTheDocument();
  expect(screen.getByText("执行改编回测")).toBeInTheDocument();
  expect(screen.getByText(/完整 731 个观察值，显示 25 点/)).toBeInTheDocument();
  expect(screen.getByText(/首评价开盘前锚点/)).toBeInTheDocument();
  expect(screen.getByText("0 bps / 成交金额")).toBeInTheDocument();
  expect(screen.getByText("20 bps / 成交金额")).toBeInTheDocument();
  expect(screen.getByText("相同工具买入持有")).toBeInTheDocument();
  const comparison = screen.getByRole("heading", { name: "2. 分段结果与基准" })
    .parentElement!.parentElement!;
  expect(within(comparison).getByText(/M1266自身控制/)).toBeInTheDocument();
  expect(screen.getAllByText("未提供").length).toBeGreaterThan(0);
  expect(screen.getByText(/当前UI不绘制其附加曲线/)).toBeInTheDocument();
});

import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  ExternalLink,
  Formula,
  Values,
  safeUrl,
  ResearchResults,
} from "../src/components";
import {
  loadNotebook,
  parseNotebook,
  refKey,
  saveNotebook,
  STORAGE_KEY,
} from "../src/storage";
import type { Notebook } from "../src/types";

// Synthetic data used only in tests. Never loaded by the production app.
const fixture: Notebook = {
  schema_version: "quantgraph-list/v1",
  mode: "PUBLIC",
  items: [
    {
      entity_id: "qkg:factor:test-only",
      entity_type: "FactorVariant",
      definition_revision: "sha256:test-only",
      kind: "variant",
      name: "TEST ONLY",
      group: "待研究",
      note: "<img src=x onerror=alert(1)>",
    },
  ],
};
beforeEach(() => localStorage.clear());
describe("browser notebook", () => {
  it("round trips pinned references and notes", () => {
    saveNotebook(fixture.items);
    expect(loadNotebook().items).toEqual(fixture.items);
    expect(parseNotebook(JSON.stringify(fixture))).toEqual(fixture);
    expect(refKey(fixture.items[0])).not.toBe(
      refKey({ ...fixture.items[0], definition_revision: "next" }),
    );
  });
  it("preserves corrupt storage without overwriting it", () => {
    localStorage.setItem(STORAGE_KEY, "{broken");
    expect(loadNotebook().error).toBeTruthy();
    expect(localStorage.getItem(STORAGE_KEY)).toBe("{broken");
  });
  it("round trips PRIVATE without leaking into PUBLIC or importing across modes", () => {
    saveNotebook(fixture.items, "PRIVATE");
    expect(loadNotebook("PRIVATE").items).toEqual(fixture.items);
    expect(loadNotebook().items).toEqual([]);
    expect(() => parseNotebook(JSON.stringify(fixture), "PRIVATE")).toThrow();
    expect(() =>
      parseNotebook(JSON.stringify({ ...fixture, mode: "PRIVATE" })),
    ).toThrow();
  });
  it("keeps PRIVATE storage isolated", () => {
    localStorage.setItem(
      "quantgraph:PRIVATE:research-list:v1",
      JSON.stringify(fixture),
    );
    expect(loadNotebook().items).toEqual([]);
    expect(() =>
      parseNotebook(JSON.stringify({ ...fixture, mode: "PRIVATE" })),
    ).toThrow();
  });
  it.each([
    "not json",
    "{}",
    "[]",
    JSON.stringify({ ...fixture, schema_version: "research-request/v1" }),
    JSON.stringify({ ...fixture, items: [fixture.items[0], fixture.items[0]] }),
    JSON.stringify({
      ...fixture,
      items: [{ ...fixture.items[0], kind: "strategy" }],
    }),
    JSON.stringify({
      ...fixture,
      items: [{ ...fixture.items[0], note: "x".repeat(4001) }],
    }),
    "x".repeat(1_000_001),
  ])("rejects invalid or oversized imports", (raw) => {
    expect(() => parseNotebook(raw)).toThrow();
  });
  it("reports storage denial", () => {
    const spy = vi
      .spyOn(Storage.prototype, "getItem")
      .mockImplementation(() => {
        throw new Error("denied");
      });
    expect(loadNotebook().error).toBeTruthy();
    spy.mockRestore();
  });
});
describe("untrusted source rendering", () => {
  it.each([
    "javascript:alert(1)",
    "data:text/html,<h1>evil</h1>",
    "//evil.example",
    "file:///tmp/key",
    "https://user:pass@example.com",
    "https://x\n.example",
  ])("rejects unsafe URL %s", (url) => {
    expect(safeUrl(url)).toBeNull();
    render(<ExternalLink url={url}>source</ExternalLink>);
    expect(screen.queryByRole("link")).toBeNull();
  });
  it("allows web URLs with opener isolation", () => {
    render(<ExternalLink url="https://example.com/path">source</ExternalLink>);
    expect(screen.getByRole("link")).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
  });
  it("renders formulas as text, never HTML or code", () => {
    const { container } = render(
      <Formula value={"<img src=x onerror=alert(1)> eval(document.cookie)"} />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText(/onerror/)).toBeInTheDocument();
  });
  it.each([null, undefined, [], {}])(
    "shows missing comparison field explicitly",
    (value) => {
      render(<Values value={value} />);
      expect(screen.getByText("未补充")).toBeInTheDocument();
    },
  );
  it("shows research levels with honest empty results", () => {
    render(
      <BrowserRouter>
        <ResearchResults
          results={{
            items: [],
            total: 0,
            status: "尚未研究",
            reason: "真实空状态",
            levels: [],
            contract: "factor-study-result/v1",
            contract_status: "PENDING_TASK_A",
          }}
        />
      </BrowserRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "尚未研究" }),
    ).toBeInTheDocument();
    expect(screen.getByText("computational_test")).toBeInTheDocument();
    expect(screen.getByText("confirmatory")).toBeInTheDocument();
  });
});

it("a failed retained study shows its failure separately from numerical rights", async () => {
  const { SummaryStudy } = await import("../src/catalog-pages");
  render(
    <BrowserRouter>
      <SummaryStudy
        study={{
          job_id: "test-only-job",
          run_id: "test-only-run",
          study_type: "STRATEGY_REPLICATION",
          study_kind: "EXPLORATORY_ANALYSIS",
          conclusion_level: "INSUFFICIENT_EVIDENCE",
          status: "FAILED",
          numerical_display: "RESTRICTED",
          classification: "DATA_OR_REPRODUCTION_FAILURE",
          execution_status: "FAILED",
          failure_reason: "SYNTHETIC missing execution data",
          source_reproduction: "NOT_ESTABLISHED",
          entity_refs: [],
          lineage: [],
          sample: {},
          metrics: {},
          limitations: [],
          promotion_allowed: false,
        }}
      />
    </BrowserRouter>,
  );
  expect(
    screen.getByText("SYNTHETIC missing execution data"),
  ).toBeInTheDocument();
  expect(screen.getByText(/研究未成功完成/)).toBeInTheDocument();
  expect(screen.queryByText(/研究已实际运行；/)).not.toBeInTheDocument();
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Highlight } from "../src/PersonalApp";
import {
  personalPatch,
  differenceLabel,
  readable,
  sameRecord,
  type PersonalItem,
  type PersonalRecord,
} from "../src/personal-data";
describe("personal reading boundaries", () => {
  it("highlights bilingual matches without interpreting source HTML or regex", () => {
    const { container } = render(
      <Highlight
        text={"均线 MA(5) <img src=x onerror=alert(1)>"}
        terms={["均线", "MA(5)"]}
      />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(
      [...container.querySelectorAll("mark")].map((item) => item.textContent),
    ).toEqual(["均线", "MA(5)"]);
    expect(screen.getByText(/onerror/)).toBeInTheDocument();
  });
  it("only sends personal fields, preserving source identity and server metadata", () => {
    expect(
      personalPatch({
        entity_id: "old",
        definition_revision: "old-revision",
        stable_id: "stable",
        updated_at: "yesterday",
        note: "my reasoning",
        starred: true,
      }),
    ).toEqual({ starred: true, note: "my reasoning" });
  });
  it("matches historical notes after the source catalog ID changes", () => {
    const record = {
      kind: "strategy",
      entity_id: "prior",
      stable_knowledge_id: "grok:1",
    } as PersonalRecord;
    expect(
      sameRecord(record, {
        kind: "strategy",
        entity_id: "current",
        stable_knowledge_id: "grok:1",
      } as PersonalItem),
    ).toBe(true);
    expect(
      sameRecord(record, {
        kind: "strategy",
        entity_id: "current",
        prior_version_ids: ["prior"],
      } as PersonalItem),
    ).toBe(true);
    expect(
      sameRecord(record, {
        kind: "strategy",
        entity_id: "different",
        stable_knowledge_id: "grok:2",
      } as PersonalItem),
    ).toBe(false);
  });
  it("makes unknowns explicit and preserves valid zeros", () => {
    expect(readable(null)).toBe("来源未说明");
    expect(readable([])).toBe("来源未说明");
    expect(readable({ window: 0 })).toBe("window：0");
  });
});

it("does not label unknown comparison fields as established differences", () => {
  expect(
    differenceLabel({ label: "公式", known: false, status: "UNKNOWN" }),
  ).toBe("公式待确认");
  expect(differenceLabel({ label: "窗口", known: true })).toBe("窗口不同");
});

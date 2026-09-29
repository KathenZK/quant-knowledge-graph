import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  RestoreConflictCard,
  type RestoreConflict,
} from "../src/PersonalRestore";
const conflict: RestoreConflict = {
  id: "identity-1",
  section: "items",
  identity: { name: "TEST 同一个定义" },
  local: {
    entity_id: "old-id",
    definition_revision: "old-definition",
    note: "TEST 本机较新 <img src=x onerror=alert(1)>",
    status: "待读",
  },
  backup: {
    entity_id: "old-id",
    definition_revision: "old-definition",
    note: "TEST 备份较旧",
    status: "值得研究",
  },
  versions: {
    local: {
      definition_revision: "old-definition",
      record_revision: "local-r2",
    },
    backup: {
      definition_revision: "old-definition",
      record_revision: "backup-r1",
    },
  },
  timestamps: {
    local: { updated_at: "2026-09-29T10:00:00+08:00", status: "VALID" },
    backup: { updated_at: "bad-time", status: "INVALID" },
  },
  reason: "同一身份，内容不同，需要明确选择。",
};
describe("explicit restore conflict decisions", () => {
  it("does not choose based on recency and displays both pinned definitions safely", () => {
    const onChoose = vi.fn();
    const { container } = render(
      <RestoreConflictCard conflict={conflict} onChoose={onChoose} />,
    );
    expect(
      screen
        .getAllByRole("radio")
        .every((radio) => !(radio as HTMLInputElement).checked),
    ).toBe(true);
    expect(screen.getByText(/bad-time（格式无效）/)).toBeVisible();
    expect(screen.getByText("2026-09-29T02:00:00.000Z（UTC）")).toBeVisible();
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("TEST 备份较旧")).toBeVisible();
    fireEvent.click(screen.getByRole("radio", { name: /采用备份内容/ }));
    expect(onChoose).toHaveBeenCalledWith("USE_BACKUP");
  });
  it("keeps applied choices disabled and exposes complete historical rows", () => {
    render(
      <RestoreConflictCard
        conflict={{
          ...conflict,
          local_records: [
            conflict.local,
            { entity_id: "prior-id", note: "TEST historical" },
          ],
        }}
        choice="KEEP_LOCAL"
        disabled
        onChoose={vi.fn()}
      />,
    );
    expect(screen.getByRole("radio", { name: /保留本机内容/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /采用备份内容/ })).toBeDisabled();
    fireEvent.click(screen.getByText("查看完整双方记录与身份字段"));
    expect(screen.getByText(/TEST historical/)).toBeVisible();
  });
});

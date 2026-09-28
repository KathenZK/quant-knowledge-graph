import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs/promises";
import path from "node:path";
import type { Detail, SearchResult } from "../src/types";
const output = process.env.QUANTGRAPH_ACCEPTANCE_OUTPUT!;
const shots = path.join(output, "safe-screenshots");
async function accessible(page: Page) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    result.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes.map((n) => n.target),
    })),
  ).toEqual([]);
}
async function screenshot(page: Page, name: string) {
  await fs.mkdir(shots, { recursive: true });
  await page.screenshot({ path: path.join(shots, name), fullPage: false });
}

test("actual strategy → detail → variants → factor → reverse strategies → notebook request", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  const meta = await (await request.get("/v1/web/meta")).json();
  expect(meta.counts.strategy).toBeGreaterThanOrEqual(50);
  // Select an actual parser-supported corpus item, without introducing fixture knowledge.
  const results: SearchResult = await (
    await request.get("/v1/web/search?kind=strategy&q=M4018")
  ).json();
  expect(results.total).toBe(1);
  const source = results.items[0];
  const detail: Detail = await (
    await request.get(`/v1/web/entities/strategy/${source.entity_id}`)
  ).json();
  const sibling = detail.related.find((i) => i.kind === "strategy")!;
  const factor = detail.related.find((i) => i.kind === "variant")!;
  expect(sibling).toBeTruthy();
  expect(factor).toBeTruthy();
  await page.goto("/explore");
  await page
    .getByRole("textbox", { name: "搜索名称、英文别名或描述" })
    .fill("M4018");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(
    page.getByRole("link", { name: source.name, exact: true }),
  ).toBeVisible();
  await accessible(page);
  await screenshot(page, "01-strategy-search.png");
  await page.getByRole("link", { name: source.name, exact: true }).click();
  await expect(
    page.getByRole("heading", { name: source.name, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("策略规则与已知边界", { exact: true }),
  ).toBeVisible();
  await accessible(page);
  await screenshot(page, "02-strategy-detail.png");
  await page
    .getByRole("button", { name: "收藏 " + source.name, exact: true })
    .click();
  await page
    .getByRole("button", { name: "比较 " + source.name, exact: true })
    .click();
  await page
    .getByRole("button", { name: "比较 " + sibling.name, exact: true })
    .click();
  await page.getByRole("link", { name: /开始比较/ }).click();
  await expect(page.getByRole("table")).toContainText("入场逻辑");
  await expect(page.getByRole("table")).toContainText("仓位 / 现金");
  await accessible(page);
  await screenshot(page, "03-strategy-compare.png");
  await page.goto(`/entity/variant/${encodeURIComponent(factor.entity_id)}`);
  await expect(
    page.getByRole("heading", { name: factor.name, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: source.name, exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("link", { name: "打开关系图与两跳浏览 →" }).click();
  await page.getByLabel("展开范围").selectOption("2");
  await expect(
    page.getByRole("heading", { name: "可核对的关系列表" }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "可点击关系图" }),
  ).toBeVisible();
  await accessible(page);
  await screenshot(page, "04-relations.png");
  await page.goto("/list");
  await page.reload();
  await expect(
    page.getByRole("link", { name: source.name, exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "研究类型", exact: true })
    .selectOption("STRATEGY_REPLICATION");
  const event = page.waitForEvent("download");
  await page.getByRole("button", { name: "校验并导出请求" }).click();
  const download = await event;
  const draft = JSON.parse(await fs.readFile((await download.path())!, "utf8"));
  expect(draft.schema_version).toBe("research-request/v1");
  expect(draft.study_type).toBe("STRATEGY_REPLICATION");
  expect(draft.entity_refs[0]).toEqual({
    entity_type: "StrategyVariant",
    entity_id: source.entity_id,
    definition_revision: source.definition_revision,
  });
  expect(draft.status).toBe("DRAFT");
  await fs.writeFile(
    path.join(output, "research-request.json"),
    JSON.stringify(draft, null, 2),
  );
  await accessible(page);
  await screenshot(page, "05-notebook.png");
  expect(errors).toEqual([]);
});

test("real corpus coverage and each relation class", async ({ request }) => {
  const meta = await (await request.get("/v1/web/meta")).json();
  const families = meta.facets.families.filter((f: { value: string }) =>
    [
      "moving_average",
      "relative_momentum_rotation",
      "absolute_momentum",
      "indicator:rsi",
      "indicator:atr",
    ].includes(f.value),
  );
  expect(families).toHaveLength(5);
  let checked = 0;
  for (const f of families) {
    const values: SearchResult = await (
      await request.get(
        `/v1/web/search?kind=strategy&family=${encodeURIComponent(f.value)}&page_size=50`,
      )
    ).json();
    expect(values.total).toBeGreaterThan(0);
    for (const v of values.items.slice(0, 15)) {
      const d: Detail = await (
        await request.get(`/v1/web/entities/strategy/${v.entity_id}`)
      ).json();
      expect(d.strategy).toBeTruthy();
      expect(d.source_url).toMatch(/^https?:/);
      expect(d.definition_revision).toMatch(/^[a-f0-9]{64}$/);
      checked++;
    }
  }
  expect(checked).toBeGreaterThanOrEqual(50);
  const f: SearchResult = await (
    await request.get("/v1/web/search?kind=variant&q=MA5")
  ).json();
  const ma = f.items.find((i) => i.name === "MA5")!;
  const relations = await (
    await request.get(`/v1/web/relations/${ma.entity_id}?hops=2`)
  ).json();
  expect(
    relations.items.some(
      (r: { from_type: string; to_type: string }) =>
        r.from_type.startsWith("Factor") && r.to_type.startsWith("Factor"),
    ),
  ).toBeTruthy();
  await fs.writeFile(
    path.join(output, "coverage.json"),
    JSON.stringify(
      {
        actual_details: checked,
        families: families.map((f: { value: string }) => f.value),
        counts: meta.counts,
      },
      null,
      2,
    ),
  );
});

test("admin UI hides and republishes actual item; imports are idempotent and excluded from real count", async ({
  page,
  request,
}) => {
  const initial = await (await request.get("/v1/web/meta")).json();
  await page.goto("/admin");
  await page
    .getByLabel("管理密码")
    .fill(await fs.readFile(path.join(output, "admin-secret"), "utf8"));
  await page.getByRole("button", { name: "登录后台", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "策略 / 因子 / 关系" }),
  ).toBeVisible();
  await page.getByLabel("检索", { exact: true }).fill("M4018");
  await page.getByRole("button", { name: "查找", exact: true }).click();
  await expect(page.getByRole("checkbox")).toHaveCount(1);
  const checked = await (
    await request.get("/v1/web/search?kind=strategy&q=M4018")
  ).json();
  const item = checked.items[0];
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: /批量隐藏/ }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "已更新" }),
  ).toContainText("HIDDEN");
  for (const route of [
    `/v1/web/entities/strategy/${item.entity_id}`,
    `/v1/web/export/strategy/${item.entity_id}`,
    `/v1/web/relations/${item.entity_id}`,
    `/v1/web/results?kind=strategy&eid=${item.entity_id}`,
  ])
    expect((await request.get(route)).status()).toBe(404);
  expect(
    (await (await request.get("/v1/web/search?kind=strategy&q=M4018")).json())
      .total,
  ).toBe(0);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: /重新公开/ }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "已更新" }),
  ).toContainText("PUBLIC");
  expect(
    (await request.get(`/v1/web/entities/strategy/${item.entity_id}`)).status(),
  ).toBe(200);
  await screenshot(page, "06-admin.png");
  await accessible(page);
  await page.getByRole("button", { name: "导入与错误", exact: true }).click();
  const batch = {
    batch_id: "CATALOG-E2E-EXPLICIT-FIXTURE",
    collector_version: "acceptance-test-only",
    records: [
      {
        record_id: "TEST-CATALOG-ONLY",
        name: "明确标记的验收测试记录",
        source_url: "https://example.org/test-only",
        raw_market: "美股 ETF",
        raw_rule: "日频：若 RSI(7)>53 → 满仓 QQQ，否则 SHV。",
        collected_at: "2026-09-28T00:00:00Z",
        metadata: { fixture: true },
      },
    ],
  };
  await page.getByLabel("GrokBot 批次 JSON").fill(JSON.stringify(batch));
  await page
    .getByRole("button", { name: "导入到现有采集流程", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "已处理" }),
  ).toContainText("新增 1");
  await page
    .getByRole("button", { name: "导入到现有采集流程", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "已处理" }),
  ).toContainText("重复 1");
  expect(
    (
      await (
        await request.get(
          "/v1/web/search?kind=strategy&q=明确标记的验收测试记录",
        )
      ).json()
    ).total,
  ).toBe(1);
  const after = await (await request.get("/v1/web/meta")).json();
  expect(after.knowledge_counts.collected_strategy_records).toBe(
    initial.knowledge_counts.collected_strategy_records,
  );
  expect(after.test_counts.strategy).toBe(1);
});

test("narrow screen, keyboard and genuine empty result state", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/explore?kind=strategy&q=M4018");
  await expect(
    page.getByRole("link", { name: /SI·HYG自均线择时/ }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await accessible(page);
  await screenshot(page, "07-narrow.png");
  await page.goto("/results");
  await expect(
    page.getByRole("heading", { name: /尚未研究或展示权限受限/ }),
  ).toBeVisible();
  await accessible(page);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "跳到主要内容" })).toBeFocused();
});

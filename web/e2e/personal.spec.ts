import {
  test,
  expect,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import type { PersonalItem } from "../src/personal-data";
const artifacts = path.resolve("../.artifacts/acceptance/personal-browser");
const clientErrors = new WeakMap<Page, string[]>();
test.afterEach(async ({ page }, info) => {
  await fs.mkdir(artifacts, { recursive: true });
  await fs.writeFile(
    path.join(
      artifacts,
      info.title.replace(/[^a-z0-9]+/gi, "-").slice(0, 140) +
        "-client-errors.json",
    ),
    JSON.stringify(
      {
        title: info.title,
        status: info.status,
        errors: clientErrors.get(page) || [],
      },
      null,
      2,
    ),
  );
});
async function results(request: APIRequestContext, kind: string, q: string) {
  const response = await request.get(
    `/v1/web/search?${new URLSearchParams({ kind, q, page_size: "6", collapse_templates: "false" })}`,
  );
  expect(
    response.ok(),
    `${response.status()} ${await response.text()}`,
  ).toBeTruthy();
  return (await response.json()).items as PersonalItem[];
}
const entityPath = (item: PersonalItem) =>
  `/entity/${item.kind}/${encodeURIComponent(item.entity_id)}`;
function watch(page: Page) {
  const errors: string[] = [];
  clientErrors.set(page, errors);
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.url().includes("/v1/") && response.status() >= 400)
      errors.push(`${response.status()} ${response.url()}`);
  });
  return errors;
}
test("real search, complete source rules, two-hop relations and comparison", async ({
  page,
  request,
}) => {
  const errors = watch(page);
  await fs.mkdir(artifacts, { recursive: true });
  const rows = await results(request, "strategy", "RSI");
  expect(rows.length).toBeGreaterThanOrEqual(2);
  await page.goto("/strategies");
  await expect(
    page.getByRole("navigation", { name: "主导航" }),
  ).not.toContainText("后台");
  await page
    .getByRole("textbox", { name: "搜索名称、别名、规则、公式和来源" })
    .fill("RSI");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.locator(".pw-result").first()).toBeVisible();
  await expect(page.locator("mark").first()).toBeVisible();
  await page.screenshot({
    path: path.join(artifacts, "01-strategy-search.png"),
  });
  await page.goto(entityPath(rows[0]));
  await expect(
    page.getByRole("heading", { name: rows[0].name, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "具体规则", exact: true }),
  ).toBeVisible();
  await page
    .getByText("完整原始规则（不受解析状态限制）", { exact: true })
    .click();
  const detail = await (
    await request.get(
      `/v1/web/entities/${rows[0].kind}/${encodeURIComponent(rows[0].entity_id)}`,
    )
  ).json();
  await expect(page.locator(".pw-original-inline pre")).toHaveText(
    detail.knowledge.original_rule,
  );
  await page.getByLabel("展开范围").selectOption("2");
  await page.getByRole("button", { name: "图形", exact: true }).click();
  await expect(page.locator(".pw-relations .loading")).toHaveCount(0);
  await expect(page.locator(".pw-relations .error")).toHaveCount(0);
  await page.goto(
    "/compare?" +
      new URLSearchParams(
        rows
          .slice(0, 2)
          .map((item) => ["ref", `${item.kind}/${item.entity_id}`]),
      ),
  );
  await expect(page.getByText("关键差异摘要 · 根据已有字段整理")).toBeVisible();
  await expect(page.getByRole("region", { name: "方法比较表" })).toBeVisible();
  await page.screenshot({ path: path.join(artifacts, "02-compare.png") });
  expect(errors).toEqual([]);
});
test("real factor definition, family reading and narrow screen", async ({
  page,
  request,
}) => {
  const errors = watch(page);
  const factors = await results(request, "variant", "MA5");
  expect(factors.length).toBeGreaterThan(0);
  await page.goto(entityPath(factors[0]));
  await expect(
    page.getByRole("heading", { name: "公式与变量", exact: true }),
  ).toBeVisible();
  await expect(page.locator("#formula .formula")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "简单计算例子", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(artifacts, "03-factor-reading.png"),
  });
  await page.goto("/families");
  await expect(page.locator(".pw-family-card").first()).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/factors?q=均线");
  await expect(page.locator(".pw-result").first()).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: path.join(artifacts, "04-narrow-factors.png"),
  });
  expect(errors).toEqual([]);
});
test("server notebook crosses browser contexts and exports definitions; backup merge preserves notes", async ({
  page,
  request,
  browser,
}) => {
  const errors = watch(page);
  const item = (await results(request, "strategy", "RSI"))[0];
  await page.goto(entityPath(item));
  await page
    .getByRole("combobox", { name: "阅读状态", exact: true })
    .selectOption("值得研究");
  await page
    .getByRole("textbox", { name: "主题分组", exact: true })
    .fill("浏览器验收 · 实际资料");
  await page
    .getByRole("textbox", { name: "备注", exact: true })
    .fill(
      "已对照原始规则。需要核对退出条件。<script>window.testInjection=1</script>",
    );
  await page
    .getByRole("textbox", { name: "标签（逗号分隔）", exact: true })
    .fill("验收, 待核对");
  await page
    .getByRole("textbox", { name: "研究选择的理由", exact: true })
    .fill("规则可读，但需要核对参数与执行时点。");
  await page
    .getByRole("textbox", { name: "我的问题与研究假设", exact: true })
    .fill("退出时点是否与来源一致？");
  await page.getByLabel("收藏到我的清单", { exact: true }).check();
  await page.getByRole("button", { name: "保存个人判断", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("个人判断已保存");
  expect(await page.evaluate(() => "testInjection" in window)).toBe(false);
  const second = await browser.newContext();
  const other = await second.newPage();
  await other.goto("http://127.0.0.1:8792" + entityPath(item));
  await expect(
    other.getByRole("textbox", { name: "备注", exact: true }),
  ).toHaveValue(/已对照原始规则/);
  await second.close();
  await page.goto("/list");
  await expect(
    page.locator(".pw-saved").filter({ hasText: item.name }),
  ).toContainText("值得研究");
  const downloadWait = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "导出 Markdown", exact: true })
    .click();
  const output = await downloadWait;
  const file = await output.path();
  const content = await fs.readFile(file!, "utf8");
  await fs.copyFile(file!, path.join(artifacts, "research-notes.md"));
  expect(content).toContain(item.entity_id);
  expect(content).toContain("退出时点是否与来源一致");
  const backup = await (await request.get("/v1/personal/backup")).json();
  await fs.writeFile(
    path.join(artifacts, "personal-backup.json"),
    JSON.stringify(backup, null, 2),
  );
  const before = await (await request.get("/v1/personal/items")).json();
  const response = await request.post("/v1/personal/restore", {
    headers: { "X-QuantGraph-Request": "1" },
    data: { backup, mode: "merge" },
  });
  expect(response.ok()).toBeTruthy();
  expect(
    (await (await request.get("/v1/personal/items")).json()).items,
  ).toEqual(before.items);
  await page.screenshot({
    path: path.join(artifacts, "05-personal-notebook.png"),
  });
  expect(errors).toEqual([]);
});
test("accessibility and keyboard semantics on actual results", async ({
  page,
}) => {
  await page.goto("/strategies?q=RSI");
  await expect(page.locator(".pw-result").first()).toBeVisible();
  const audit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    audit.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes
        .slice(0, 4)
        .map((n) => ({ target: n.target, summary: n.failureSummary })),
    })),
  ).toEqual([]);
});

test("one-time browser migration and reversible real duplicate decisions", async ({
  page,
  request,
}) => {
  const errors = watch(page);
  const item = (await results(request, "strategy", "RSI"))[1];
  const notebook = {
    schema_version: "quantgraph-list/v1",
    mode: "PRIVATE",
    items: [
      {
        kind: item.kind,
        entity_id: item.entity_id,
        entity_type: item.entity_type,
        definition_revision: item.definition_revision,
        name: item.name,
        note: "旧浏览器清单迁移验收",
        group: "旧清单",
      },
    ],
  };
  await page.goto("/list");
  await page.evaluate(
    (value) =>
      localStorage.setItem(
        "quantgraph:PRIVATE:research-list:v1",
        JSON.stringify(value),
      ),
    notebook,
  );
  await page.reload();
  await page
    .getByRole("button", { name: "迁移这份浏览器清单", exact: true })
    .click();
  await expect(
    page.locator(".pw-saved").filter({ hasText: item.name }),
  ).toContainText("旧浏览器清单迁移验收");
  const count = (await (await request.get("/v1/personal/items")).json()).total;
  await page.reload();
  await page
    .getByRole("button", { name: "迁移这份浏览器清单", exact: true })
    .click();
  await expect(page.getByRole("status")).toBeVisible();
  expect((await (await request.get("/v1/personal/items")).json()).total).toBe(
    count,
  );
  const scan = await request.post("/v1/personal/duplicates/refresh", {
    headers: { "X-QuantGraph-Request": "1" },
    data: {},
  });
  expect(scan.ok()).toBeTruthy();
  const suggestions = (await scan.json()).items;
  const suggestion = suggestions.find(
    (row: { classification: string; status: string }) =>
      row.classification === "TEMPLATE_VARIANT" &&
      ["PENDING", "UNDONE"].includes(row.status),
  );
  expect(suggestion).toBeTruthy();
  await page.goto(entityPath(suggestion.left));
  await page.locator(".pw-duplicates > summary").click();
  const card = page
    .locator(".pw-duplicate")
    .filter({ hasText: suggestion.right.name })
    .first();
  await card
    .getByRole("button", { name: "确认分组/差异…", exact: true })
    .click();
  await card
    .getByRole("button", { name: "确认此分组判断", exact: true })
    .click();
  await expect(card).toContainText("已确认");
  const confirmed = (
    await (
      await request.get(
        `/v1/personal/duplicates?entity_id=${encodeURIComponent(suggestion.left.entity_id)}`,
      )
    ).json()
  ).items.find(
    (row: { suggestion_id: string }) =>
      row.suggestion_id === suggestion.suggestion_id,
  );
  expect(confirmed.canonical_id).toBeNull();
  expect(confirmed.relation_only).toBe(true);
  await card.getByRole("button", { name: "撤销判断", exact: true }).click();
  await expect(card).toContainText("已撤销");
  await card.getByRole("button", { name: "否决建议", exact: true }).click();
  await expect(card).toContainText("已否决");
  await card.getByRole("button", { name: "撤销判断", exact: true }).click();
  await expect(card).toContainText("已撤销");
  expect(errors).toEqual([]);
});

test("real method relationships: strategy to factor to another strategy; MA5 and MA10 retain their windows", async ({
  page,
  request,
}) => {
  const errors = watch(page);
  const strategyId =
    "qkg:strategy-variant:f7829c2d-5b2c-55e3-83f7-e42c67b3eba4";
  const factorId = "qkg:factor-variant:a053d565-092c-577c-adaa-5949bdae6ac4";
  const detail = await (
    await request.get(
      `/v1/web/entities/strategy/${encodeURIComponent(strategyId)}`,
    )
  ).json();
  const factor = await (
    await request.get(
      `/v1/web/entities/variant/${encodeURIComponent(factorId)}`,
    )
  ).json();
  await page.goto(`/entity/strategy/${encodeURIComponent(strategyId)}`);
  await expect(
    page.getByRole("heading", { name: detail.name, exact: true }),
  ).toBeVisible();
  await expect(page.locator("#sources")).toContainText("原始采集时间（未知）");
  await expect(page.locator("#sources")).toContainText("迁移 / 入库观察时间");
  const factorLink = page
    .locator(
      `.pw-relation-list a[href="/entity/variant/${encodeURIComponent(factorId)}"]`,
    )
    .first();
  await expect(factorLink).toBeVisible();
  await factorLink.click();
  await expect(
    page.getByRole("heading", { name: factor.name, exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".pw-relation-list .pw-relation").first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "图形", exact: true }).click();
  await expect(page.locator(".pw-graph svg a").first()).toBeVisible();
  await page.locator("#related").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: path.join(artifacts, "06-factor-strategy-relationships.png"),
  });
  const related = page
    .locator(".pw-relation-list a[href*='/entity/strategy/']")
    .filter({ hasNotText: detail.name })
    .first();
  const relatedName = await related.innerText();
  await related.click();
  await expect(
    page.getByRole("heading", { name: relatedName, exact: true }),
  ).toBeVisible();
  const ma5 = (await results(request, "variant", "MA5")).find(
    (item) => item.name === "MA5",
  );
  const ma10 = (await results(request, "variant", "MA10")).find(
    (item) => item.name === "MA10",
  );
  expect(ma5).toBeTruthy();
  expect(ma10).toBeTruthy();
  await page.goto(
    "/compare?" +
      new URLSearchParams(
        [ma5!, ma10!].map((item) => ["ref", `${item.kind}/${item.entity_id}`]),
      ),
  );
  const parameterRow = page.getByRole("row").filter({
    has: page.getByRole("rowheader", { name: "参数与窗口", exact: true }),
  });
  await expect(parameterRow).toContainText("5");
  await expect(parameterRow).toContainText("10");
  await page.screenshot({
    path: path.join(artifacts, "07-factor-window-comparison.png"),
  });
  expect(errors).toEqual([]);
});

test("asset-scope filters only include explicit rule assets, leaving unknowns separate", async ({
  page,
}) => {
  const errors = watch(page);
  await page.goto("/strategies");
  await expect(page.locator(".pw-result").first()).toBeVisible();
  await page.getByRole("button", { name: /更多筛选/ }).click();
  for (const scope of ["single", "multi", "unknown"]) {
    const responseWait = page.waitForResponse(
      (response) =>
        response.url().includes("/v1/web/search?") &&
        new URL(response.url()).searchParams.get("asset_scope") === scope &&
        response.ok(),
    );
    await page
      .getByRole("combobox", { name: "规则涉及资产", exact: true })
      .selectOption(scope);
    const data = await (await responseWait).json();
    expect(data.total).toBeGreaterThan(0);
    expect(
      data.items.every(
        (item: { knowledge: { filters: { asset_scope: string } } }) =>
          item.knowledge.filters.asset_scope === scope,
      ),
    ).toBe(true);
    await expect(page.locator(".pw-result").first()).toBeVisible();
  }
  await expect(page.getByText(/不代表同时持仓数量/)).toBeVisible();
  expect(errors).toEqual([]);
});

import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs/promises";
import path from "node:path";
const artifacts = path.resolve(".artifacts/public-screenshots");
const storageKey = "quantgraph:PUBLIC:research-list:v1";

async function assertAccessible(page: Page) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    result.violations.map((v) => ({
      rule: v.id,
      nodes: v.nodes.map((n) => ({
        target: n.target,
        failure: n.failureSummary,
      })),
    })),
  ).toEqual([]);
}

test("real public workflow: search → detail → compare → save → reload → export/import → results", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  const privateNotesRequests: string[] = [];
  page.on("request", (req) => {
    if (req.postData()?.includes("公开样例备注"))
      privateNotesRequests.push(req.url());
  });
  await fs.mkdir(artifacts, { recursive: true });
  await page.goto("/explore");
  await page
    .getByRole("textbox", { name: "搜索名称、英文别名或描述" })
    .fill("均线");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "MA5", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("status").first()).toContainText("5");
  await assertAccessible(page);
  await page.screenshot({
    path: path.join(artifacts, "01-search.png"),
    fullPage: false,
  });
  await page.getByRole("link", { name: "MA5", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "MA5", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Mean($close, 5)/$close").first()).toBeVisible();
  await expect(page.getByText("经济逻辑", { exact: true })).toBeVisible();
  await assertAccessible(page);
  await page.screenshot({
    path: path.join(artifacts, "02-detail.png"),
    fullPage: false,
  });
  await page.getByRole("button", { name: "收藏 MA5", exact: true }).click();
  await page.getByRole("button", { name: "比较 MA5", exact: true }).click();
  await page.getByRole("button", { name: "比较 MA20", exact: true }).click();
  await page.getByRole("link", { name: /开始比较/ }).click();
  await expect(page.getByRole("table")).toContainText("MA5");
  await expect(page.getByRole("table")).toContainText("MA20");
  await expect(page.getByRole("table")).toContainText(
    "Mean($close, 20)/$close",
  );
  await page.getByRole("button", { name: "关闭提示" }).click();
  await assertAccessible(page);
  await page.screenshot({
    path: path.join(artifacts, "03-compare.png"),
    fullPage: false,
  });
  await page.getByRole("link", { name: /研究清单 1/ }).click();
  await page
    .getByRole("textbox", { name: "研究备注" })
    .fill("公开样例备注：比较 5 与 20 日输入窗口，先核对计算语义。");
  await page
    .getByRole("textbox", { name: "分组", exact: true })
    .fill("均线定义比较");
  await page.reload();
  await expect(page.getByRole("textbox", { name: "研究备注" })).toHaveValue(
    /公开样例备注/,
  );
  await expect(
    page.getByRole("textbox", { name: "分组", exact: true }),
  ).toHaveValue("均线定义比较");
  await assertAccessible(page);
  await page.screenshot({
    path: path.join(artifacts, "04-notebook.png"),
    fullPage: false,
  });
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出清单", exact: true }).click();
  const file = await downloaded;
  const value = JSON.parse(await fs.readFile((await file.path())!, "utf8"));
  expect(value.schema_version).toBe("quantgraph-list/v1");
  expect(value.mode).toBe("PUBLIC");
  expect(value.items[0].definition_revision).toMatch(/^[a-f0-9]{64}$/);
  const refs = value.items.map(
    ({
      entity_type,
      entity_id,
      definition_revision,
    }: Record<string, string>) => ({
      entity_type,
      entity_id,
      definition_revision,
    }),
  );
  expect(
    (await request.post("/v1/web/references/resolve", { data: { refs } })).ok(),
  ).toBeTruthy();
  await page.getByRole("button", { name: "取消收藏 MA5", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "清单还是空的" }),
  ).toBeVisible();
  await page.getByLabel("导入清单文件").setInputFiles({
    name: "public-list.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(value)),
  });
  await expect(page.getByRole("textbox", { name: "研究备注" })).toHaveValue(
    /公开样例备注/,
  );
  expect(privateNotesRequests).toEqual([]);
  const requestDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "校验并导出请求" }).click();
  const draftFile = await requestDownload;
  const draft = JSON.parse(
    await fs.readFile((await draftFile.path())!, "utf8"),
  );
  await fs.mkdir(path.resolve(".artifacts/request-evidence"), {
    recursive: true,
  });
  await fs.writeFile(
    path.resolve(".artifacts/request-evidence/research-request.json"),
    JSON.stringify(draft, null, 2) + "\n",
  );
  expect(draft.schema_version).toBe("research-request/v1");
  expect(draft.status).toBe("DRAFT");
  expect(draft.entity_refs).toEqual(refs);
  expect(JSON.stringify(draft)).not.toContain("公开样例备注");
  await page.getByRole("link", { name: "研究结果", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "无可展示结果" }),
  ).toBeVisible();
  await expect(page.getByText("confirmatory", { exact: true })).toBeVisible();
  await assertAccessible(page);
  await page.screenshot({
    path: path.join(artifacts, "05-results.png"),
    fullPage: false,
  });
  expect(errors).toEqual([]);
});

test("English alias, pagination, empty states and invalid IDs", async ({
  page,
}) => {
  await page.goto("/explore");
  await expect(page.getByRole("button", { name: "下一页" })).toBeEnabled();
  await page.getByRole("button", { name: "下一页" }).click();
  await expect(page.getByText(/第 2 \/ 26 页/)).toBeVisible();
  const search = page.getByRole("textbox", {
    name: "搜索名称、英文别名或描述",
  });
  await search.fill("Alpha158:MA5");
  await search.press("Enter");
  await expect(
    page.getByRole("link", { name: "MA5", exact: true }),
  ).toBeVisible();
  await search.fill("not-a-record");
  await search.press("Enter");
  await expect(
    page.getByRole("heading", { name: "没有找到匹配条目" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "策略 0", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "当前公开库暂无策略" }),
  ).toBeVisible();
  await page.goto("/entity/variant/nonexistent");
  await expect(page.getByRole("alert")).toContainText(
    "当前公开版本中没有此条目",
  );
});

test("API failure can retry without a fake empty result", async ({ page }) => {
  await page.route("**/v1/web/search?*", (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: "{}" }),
  );
  await page.goto("/explore");
  await expect(page.getByRole("alert")).toContainText("服务暂时不可用");
  await expect(
    page.getByRole("heading", { name: "没有找到匹配条目" }),
  ).toHaveCount(0);
  await page.unroute("**/v1/web/search?*");
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "BETA10", exact: true }),
  ).toBeVisible();
});

test("damaged storage and malformed or private imports do not erase original bytes", async ({
  page,
}) => {
  await page.addInitScript(
    (key) => localStorage.setItem(key, "{corrupt"),
    storageKey,
  );
  await page.goto("/list");
  await expect(page.getByRole("alert")).toContainText("格式已损坏");
  for (const body of [
    "bad JSON",
    JSON.stringify({
      schema_version: "quantgraph-list/v1",
      mode: "PRIVATE",
      items: [],
    }),
  ]) {
    await page.getByLabel("导入清单文件").setInputFiles({
      name: "TEST-ONLY-invalid.json",
      mimeType: "application/json",
      buffer: Buffer.from(body),
    });
    await expect(page.getByText(/导入未生效/)).toBeVisible();
    expect(
      await page.evaluate((key) => localStorage.getItem(key), storageKey),
    ).toBe("{corrupt");
  }
});

test("missing fields and unsafe source strings render safely (synthetic attack fixture)", async ({
  page,
  request,
}) => {
  const response = await request.get("/v1/web/search?family=MA");
  const { items } = await response.json();
  const details = await Promise.all(
    items
      .slice(0, 2)
      .map(async (item: { entity_id: string }) =>
        (
          await request.get("/v1/web/entities/variant/" + item.entity_id)
        ).json(),
      ),
  );
  const attack = '<img src=x onerror="window.__XSS_TEST_ONLY__=true">';
  const injected = details.map((item) => ({
    ...item,
    formula: attack,
    parameters: {},
    source_name: attack,
    source_url: "javascript:alert(1)",
    source_revision: null,
    implementations: [],
    economic_logic: null,
  }));
  await page.route("**/v1/web/compare?*", (route) =>
    route.fulfill({ json: { items: injected } }),
  );
  const qs = new URLSearchParams(
    items
      .slice(0, 2)
      .map((item: { entity_id: string }) => [
        "ref",
        "variant/" + item.entity_id,
      ]),
  );
  await page.goto("/compare?" + qs);
  await expect(page.getByRole("table")).toContainText(attack);
  await expect(page.locator('a[href^="javascript:"]')).toHaveCount(0);
  await expect(page.locator("img")).toHaveCount(0);
  await expect(page.getByRole("table")).toContainText("未补充");
  expect(
    await page.evaluate(() =>
      Object.prototype.hasOwnProperty.call(window, "__XSS_TEST_ONLY__"),
    ),
  ).toBeFalsy();
});

test("keyboard, form labels, contrast and narrow viewport", async ({
  page,
}) => {
  await page.goto("/explore?q=均线");
  await expect(
    page.getByRole("link", { name: "MA5", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "跳到主要内容" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
  await page.getByRole("textbox", { name: "搜索名称、英文别名或描述" }).focus();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("MA5");
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("link", { name: "MA5", exact: true }),
  ).toBeVisible();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  for (const url of ["/explore?q=均线", "/list", "/results"]) {
    await page.goto(url);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
  }
  await page.goto("/explore?q=均线");
  await expect(
    page.getByRole("link", { name: "MA5", exact: true }),
  ).toBeVisible();
  await assertAccessible(page);
  await page.screenshot({
    path: path.join(artifacts, "06-mobile.png"),
    fullPage: true,
  });
});

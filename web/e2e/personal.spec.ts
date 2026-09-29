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
const artifacts = path.resolve("../.artifacts/polish-v1/browser-evidence");
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
test("server notebook crosses browser contexts and exports definitions; identical backup preview preserves notes", async ({
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
    .fill("TEST 浏览器验收 · 实际资料");
  await page
    .getByRole("textbox", { name: "备注", exact: true })
    .fill(
      "TEST 已对照原始规则。需要核对退出条件。<script>window.testInjection=1</script>",
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
  const preview = await (
    await request.post("/v1/personal/restore/preview", {
      headers: { "X-QuantGraph-Request": "1" },
      data: { backup },
    })
  ).json();
  expect(preview.counts.conflicts).toBe(0);
  const response = await request.post("/v1/personal/restore", {
    headers: { "X-QuantGraph-Request": "1" },
    data: { preview_token: preview.preview_token, decisions: {} },
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

test("explicit restore choices preserve both versions, add a real record and export pinned strategy and factor", async ({
  page,
  request,
}) => {
  const errors = watch(page);
  const strategy = (await results(request, "strategy", "M4018"))[0];
  const factor = (await results(request, "variant", "MA5"))[0];
  const added = (await results(request, "strategy", "RSI")).find(
    (item) =>
      item.entity_id !== strategy.entity_id && item.name !== strategy.name,
  )!;
  const write = async (item: PersonalItem, note: string) => {
    await page.goto(entityPath(item));
    await page.getByRole("textbox", { name: "备注", exact: true }).fill(note);
    await page
      .getByRole("textbox", { name: "主题分组", exact: true })
      .fill("TEST 恢复回归");
    await page
      .getByRole("combobox", { name: "阅读状态", exact: true })
      .selectOption("值得研究");
    await page.getByLabel("收藏到我的清单", { exact: true }).check();
    await page
      .getByRole("button", { name: "保存个人判断", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText("个人判断已保存");
  };
  await write(strategy, "TEST 备份中的策略判断 B");
  await write(factor, "TEST 备份中的因子判断 B");
  await page.goto("/list");
  const backupDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "完整备份", exact: true }).click();
  const backup = JSON.parse(
    await fs.readFile((await (await backupDownload).path())!, "utf8"),
  );
  const addedDetail = await (
    await request.get(
      `/v1/web/entities/${added.kind}/${encodeURIComponent(added.entity_id)}`,
    )
  ).json();
  // A real catalog record, with explicitly marked test notes, represents a record only present in the backup.
  // Python uses the production backup envelope/hash helper so the test never bypasses validation.
  const { execFileSync } = await import("node:child_process");
  const enriched = execFileSync(
    path.resolve("../.venv/bin/python"),
    [
      "-c",
      `import json,sys
from quantgraph.graph.personal_store import blank
from quantgraph.graph.personal_restore import envelope
backup,item=json.load(sys.stdin)
row=blank(item)
row.update(note='TEST 仅存在备份的真实条目',starred=True,status='值得研究',group='TEST 恢复回归')
backup['payload']['items']=[r for r in backup['payload']['items'] if r['entity_id'] != row['entity_id']]+[row]
print(json.dumps(envelope(backup['payload']),ensure_ascii=False))`,
    ],
    { input: JSON.stringify([backup, addedDetail]), encoding: "utf8" },
  );
  const fixture = JSON.parse(enriched);
  // Make the strategy local copy differ, and make the factor local copy newer than the backup.
  await write(strategy, "TEST 本机策略判断 A，明确选择采用备份 B");
  await write(factor, "TEST 本机因子判断 C，明确选择保留本机");
  await page.goto("/list");
  const original = await (await request.get("/v1/personal/items")).json();
  // The added record may already exist from an earlier workflow. Select a never-saved real identity instead.
  if (
    original.items.some(
      (item: PersonalItem) => item.entity_id === added.entity_id,
    )
  ) {
    const savedIds = new Set(
      original.items.map((item: PersonalItem) => item.entity_id),
    );
    const candidates = await results(request, "strategy", "SMA");
    const unsaved = candidates.find((item) => !savedIds.has(item.entity_id));
    expect(unsaved).toBeTruthy();
    const detail = await (
      await request.get(
        `/v1/web/entities/${unsaved!.kind}/${encodeURIComponent(unsaved!.entity_id)}`,
      )
    ).json();
    const fresh = execFileSync(
      path.resolve("../.venv/bin/python"),
      [
        "-c",
        `import json,sys
from quantgraph.graph.personal_store import blank
from quantgraph.graph.personal_restore import envelope
backup,item,old_id=json.load(sys.stdin)
row=blank(item);row.update(note='TEST 仅存在备份的真实条目',starred=True,status='值得研究',group='TEST 恢复回归')
backup['payload']['items']=[r for r in backup['payload']['items'] if r['entity_id'] != old_id]+[row]
print(json.dumps(envelope(backup['payload']),ensure_ascii=False))`,
      ],
      {
        input: JSON.stringify([fixture, detail, added.entity_id]),
        encoding: "utf8",
      },
    );
    Object.assign(fixture, JSON.parse(fresh));
  }
  await page.getByLabel("恢复个人备份").setInputFiles({
    name: "TEST-restore-backup.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(fixture)),
  });
  await expect(page.locator(".pw-restore-counts").first()).toContainText(
    "新增",
  );
  await expect(page.locator(".pw-restore-conflict")).toHaveCount(2);
  await expect(
    page.getByRole("button", { name: "按已选择的内容恢复" }),
  ).toBeDisabled();
  expect(
    (await (await request.get("/v1/personal/items")).json()).items,
  ).toEqual(original.items);
  const token = new URL(page.url()).searchParams.get("restore")!;
  const preview = await (
    await request.get(`/v1/personal/restore/reports/${token}`)
  ).json();
  expect(preview.sections.items.added).toBe(1);
  expect(preview.sections.items.conflicts).toBe(2);
  expect(
    preview.conflicts.every(
      (conflict: { versions: { local: unknown; backup: unknown } }) =>
        conflict.versions.local && conflict.versions.backup,
    ),
  ).toBe(true);
  await page.reload();
  await expect(page.locator(".pw-restore-conflict")).toHaveCount(2);
  await expect(page.getByRole("radio", { checked: true })).toHaveCount(0);
  const strategyCard = page
    .locator(".pw-restore-conflict")
    .filter({ has: page.getByText(strategy.name, { exact: true }) });
  const factorCard = page
    .locator(".pw-restore-conflict")
    .filter({ has: page.getByText(factor.name, { exact: true }) });
  await strategyCard.getByRole("radio", { name: /采用备份内容/ }).check();
  await expect(
    page.getByRole("button", { name: "按已选择的内容恢复" }),
  ).toBeDisabled();
  await factorCard.getByRole("radio", { name: /保留本机内容/ }).check();
  await page.screenshot({
    path: path.join(artifacts, "08-explicit-restore-decisions.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "按已选择的内容恢复" }).click();
  await expect(
    page.getByRole("heading", { name: "恢复已完成并核对", exact: true }),
  ).toBeVisible();
  const after = (await (await request.get("/v1/personal/items")).json()).items;
  expect(
    after.find((item: PersonalItem) => item.entity_id === strategy.entity_id)
      .note,
  ).toBe("TEST 备份中的策略判断 B");
  expect(
    after.find((item: PersonalItem) => item.entity_id === factor.entity_id)
      .note,
  ).toBe("TEST 本机因子判断 C，明确选择保留本机");
  expect(
    after.some(
      (item: { note: string }) => item.note === "TEST 仅存在备份的真实条目",
    ),
  ).toBe(true);
  const reportDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载完整恢复报告" }).click();
  await (
    await reportDownload
  ).saveAs(path.join(artifacts, "restore-report.json"));
  const pointDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载执行前恢复点" }).click();
  await (
    await pointDownload
  ).saveAs(path.join(artifacts, "before-restore.json"));
  const report = await (
    await request.get(`/v1/personal/restore/reports/${token}`)
  ).json();
  expect(report.status).toBe("APPLIED");
  const replay = await request.post("/v1/personal/restore", {
    headers: { "X-QuantGraph-Request": "1" },
    data: { preview_token: token, decisions: report.decisions },
  });
  expect((await replay.json()).replayed).toBe(true);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "恢复已完成并核对", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "关闭报告" }).click();
  for (const item of [strategy, factor])
    await page
      .getByRole("checkbox", { name: `选择 ${item.name}`, exact: true })
      .check();
  const jsonDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "兼容 JSON", exact: true }).click();
  const jsonFile = (await (await jsonDownload).path())!;
  const exported = JSON.parse(await fs.readFile(jsonFile, "utf8"));
  expect(exported.items).toHaveLength(2);
  for (const item of [strategy, factor]) {
    const saved = exported.items.find(
      (value: PersonalItem) => value.entity_id === item.entity_id,
    );
    expect(saved.definition_revision).toBe(item.definition_revision);
    expect(saved.original_note_ref.definition_revision).toBe(
      item.definition_revision,
    );
    expect(saved.starred).toBe(true);
    expect(saved.group).toBe("TEST 恢复回归");
    expect(saved.availability).toBe("AVAILABLE");
    const detail = await (
      await request.get(
        `/v1/web/entities/${item.kind}/${encodeURIComponent(item.entity_id)}`,
      )
    ).json();
    expect(saved.knowledge.original_rule || saved.formula).toBe(
      detail.knowledge.original_rule || detail.formula,
    );
  }
  await fs.copyFile(
    jsonFile,
    path.join(artifacts, "strategy-factor-pinned-export.json"),
  );
  const mdDownload = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "导出 Markdown", exact: true })
    .click();
  const mdFile = (await (await mdDownload).path())!;
  const markdown = await fs.readFile(mdFile, "utf8");
  for (const item of [strategy, factor]) {
    expect(markdown).toContain(item.entity_id);
    expect(markdown).toContain(item.definition_revision!);
  }
  await fs.copyFile(
    mdFile,
    path.join(artifacts, "strategy-factor-pinned-export.md"),
  );
  await page.screenshot({
    path: path.join(artifacts, "09-two-kind-notebook.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("invalid backup stays a preview and runtime panel identifies the served build", async ({
  page,
  request,
}) => {
  const errors = watch(page);
  const before = await (await request.get("/v1/personal/items")).json();
  await page.goto("/list");
  await page.getByLabel("恢复个人备份").setInputFiles({
    name: "TEST-unsupported-backup.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify({ schema_version: "quantgraph-personal-backup/v999" }),
    ),
  });
  await expect(
    page.getByText("存在无效记录，本次不能恢复任何内容。"),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "按已选择的内容恢复" }),
  ).toBeDisabled();
  expect(
    (await (await request.get("/v1/personal/items")).json()).items,
  ).toEqual(before.items);
  await expect(page.locator(".pw-restore-counts").first()).toContainText(
    "未计算",
  );
  const meta = await (await request.get("/v1/web/meta")).json();
  await fs.writeFile(
    path.join(artifacts, "verified-runtime-version.json"),
    JSON.stringify(
      Object.fromEntries(
        [
          "application_version",
          "build",
          "snapshot",
          "imported_at",
          "counts",
          "test_counts",
          "reading_coverage",
        ].map((key) => [key, meta[key]]),
      ),
      null,
      2,
    ),
  );
  const panel = page.getByLabel("运行信息与数据快照");
  await panel.locator("summary").first().click();
  await expect(panel).toContainText(meta.build.build_id);
  await expect(panel).toContainText("已核对当前源码");
  await expect(panel).toContainText(String(meta.counts.strategy));
  await expect(panel).not.toContainText("/Users/");
  await page.screenshot({
    path: path.join(artifacts, "10-invalid-restore-runtime.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("real restart retains strategy and factor notes in the disposable runtime", async ({
  page,
  request,
}) => {
  const before = (await (await request.get("/v1/personal/items")).json()).items;
  const target = path.resolve("../.artifacts/polish-v1/browser-runtime");
  const state = JSON.parse(
    await fs.readFile(path.join(target, "server-generation.json"), "utf8"),
  );
  await fs.writeFile(
    path.join(target, "restart-request"),
    "TEST owned server restart",
  );
  await expect
    .poll(
      async () =>
        JSON.parse(
          await fs.readFile(
            path.join(target, "server-generation.json"),
            "utf8",
          ),
        ).generation,
    )
    .toBe(state.generation + 1);
  await expect
    .poll(async () => {
      try {
        return (await request.get("/health")).status();
      } catch {
        return 0;
      }
    })
    .toBe(200);
  const errors = watch(page);
  await page.goto("/list");
  await expect(
    page.locator(".pw-saved").filter({ hasText: "TEST 备份中的策略判断 B" }),
  ).toBeVisible();
  await expect(
    page.locator(".pw-saved").filter({ hasText: "TEST 本机因子判断 C" }),
  ).toBeVisible();
  expect(
    (await (await request.get("/v1/personal/items")).json()).items,
  ).toEqual(before);
  await page.screenshot({
    path: path.join(artifacts, "11-notebook-after-process-restart.png"),
    fullPage: true,
  });
  await fs.writeFile(
    path.join(artifacts, "restart-evidence.json"),
    JSON.stringify(
      {
        before_generation: state.generation,
        after_generation: state.generation + 1,
        record_count: before.length,
        preserved: true,
      },
      null,
      2,
    ),
  );
  expect(errors).toEqual([]);
});

test("marked test revision stays out of real counts and preserves the old note definition in browser exports", async ({
  page,
  request,
}) => {
  test.setTimeout(90000);
  const { execFileSync, spawn } = await import("node:child_process");
  const python = path.resolve("../.venv/bin/python");
  const helper = path.resolve("e2e/personal_qa.py");
  const old = JSON.parse(
    execFileSync(python, [helper, "seed"], { encoding: "utf8" }),
  );
  const child = spawn(python, [helper, "serve"], { stdio: "pipe" });
  let log = "";
  child.stdout.on("data", (chunk) => {
    log += String(chunk);
  });
  child.stderr.on("data", (chunk) => {
    log += String(chunk);
  });
  const url = "http://127.0.0.1:8793";
  try {
    await expect
      .poll(async () => {
        try {
          return (await request.get(url + "/health")).status();
        } catch {
          return 0;
        }
      })
      .toBe(200);
    const errors = watch(page);
    await page.goto(url + "/strategies?q=TEST_POLISH_ORIGINAL");
    await page.locator(".pw-result-name").first().click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      "TEST_POLISH_ORIGINAL",
    );
    await page
      .getByRole("textbox", { name: "备注", exact: true })
      .fill("TEST 修订前笔记，固定原定义 20 日");
    await page
      .getByRole("textbox", { name: "主题分组", exact: true })
      .fill("TEST 修订隔离验收");
    await page.getByLabel("收藏到我的清单", { exact: true }).check();
    await page
      .getByRole("button", { name: "保存个人判断", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText("个人判断已保存");
    const revised = JSON.parse(
      execFileSync(python, [helper, "revise"], { encoding: "utf8" }),
    );
    expect(revised.entity_id).not.toBe(old.entity_id);
    expect(revised.definition_revision).not.toBe(old.definition_revision);
    expect(revised.counts).toEqual(old.before);
    await page.goto(url + "/strategies?q=TEST_POLISH_UPDATED");
    await page.locator(".pw-result-name").first().click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      "TEST_POLISH_UPDATED",
    );
    await expect(
      page.getByText(
        "来源定义已有修订。以下笔记仍关联原保存版本，保存判断不会自动替换历史引用。",
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("textbox", { name: "备注", exact: true }),
    ).toHaveValue("TEST 修订前笔记，固定原定义 20 日");
    await page
      .getByText("完整原始规则（不受解析状态限制）", { exact: true })
      .click();
    await expect(page.locator(".pw-original-inline pre")).toContainText(
      "**21** 日",
    );
    await page.screenshot({
      path: path.join(artifacts, "12-marked-revision-preserves-note.png"),
      fullPage: true,
    });
    await page.goto(url + "/list");
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "兼容 JSON", exact: true }).click();
    const output = (await (await download).path())!;
    const exported = JSON.parse(await fs.readFile(output, "utf8"));
    expect(exported.items).toHaveLength(1);
    expect(exported.items[0].entity_id).toBe(old.entity_id);
    expect(exported.items[0].definition_revision).toBe(old.definition_revision);
    expect(exported.items[0].knowledge.original_rule).toContain("**20** 日");
    expect(exported.items[0].availability).toBe("PINNED_HISTORICAL_DEFINITION");
    await fs.copyFile(
      output,
      path.join(artifacts, "test-revision-pinned-export.json"),
    );
    const missing = JSON.parse(
      execFileSync(python, [helper, "missing"], { encoding: "utf8" }),
    );
    expect(missing.backup_saved).toBe(true);
    await page.reload();
    await page.getByText("查看已保存的判断与固定版本", { exact: true }).click();
    await expect(page.locator(".pw-saved")).toContainText(
      "TEST_MISSING_OLD_DEFINITION",
    );
    const missingDownload = page.waitForEvent("download");
    await page.getByRole("button", { name: "兼容 JSON", exact: true }).click();
    const missingFile = (await (await missingDownload).path())!;
    await expect(page.getByRole("status")).toContainText("部分固定定义缺失");
    const missingExport = JSON.parse(await fs.readFile(missingFile, "utf8"));
    expect(missingExport.items[0].availability).toBe(
      "PINNED_DEFINITION_UNAVAILABLE",
    );
    expect(missingExport.items[0].definition_revision).toBe(
      "TEST_MISSING_OLD_DEFINITION",
    );
    expect(missingExport.items[0].rule).toBeFalsy();
    expect(missingExport.items[0].formula).toBeFalsy();
    expect(missingExport.items[0].knowledge).toEqual({});
    expect(missingExport.items[0].current_definition_snapshot.entity_id).toBe(
      revised.entity_id,
    );
    expect(
      missingExport.items[0].current_definition_snapshot.knowledge
        .original_rule,
    ).toContain("**21** 日");
    expect(
      missingExport.items[0].current_definition_ref.definition_revision,
    ).toBe(revised.definition_revision);
    expect(missingExport.research_requests).toEqual([]);
    await fs.copyFile(
      missingFile,
      path.join(artifacts, "test-missing-definition-export.json"),
    );
    const missingMarkdownDownload = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "导出 Markdown", exact: true })
      .click();
    const missingMarkdownFile = (await (await missingMarkdownDownload).path())!;
    const missingMarkdown = await fs.readFile(missingMarkdownFile, "utf8");
    expect(missingMarkdown).toContain("PINNED_DEFINITION_UNAVAILABLE");
    await expect(page.getByRole("status")).toContainText("部分固定定义缺失");
    expect(
      missingMarkdown.split("### 规则或公式")[1].split("### 参数")[0],
    ).toContain("来源未说明");
    await fs.copyFile(
      missingMarkdownFile,
      path.join(artifacts, "test-missing-definition-export.md"),
    );
    await page.screenshot({
      path: path.join(artifacts, "14-missing-definition-note-reference.png"),
      fullPage: true,
    });
    const meta = await (await request.get(url + "/v1/web/meta")).json();
    expect(meta.counts).toEqual(old.before);
    expect(meta.test_counts.strategy).toBeGreaterThan(0);
    await page.goto(url + "/strategies?q=隔离测试原版");
    await expect(page.getByText("没有找到匹配条目")).toBeVisible();
    expect(errors).toEqual([]);
    await fs.writeFile(
      path.join(artifacts, "test-revision-evidence.json"),
      JSON.stringify(
        {
          old,
          revised,
          real_counts_unchanged: true,
          default_search_excludes_test: true,
          pinned_old_definition: true,
        },
        null,
        2,
      ),
    );
  } finally {
    child.kill("SIGTERM");
    await new Promise<void>((resolve) => {
      if (child.exitCode != null) resolve();
      else child.once("exit", () => resolve());
    });
    await fs.writeFile(path.join(artifacts, "test-revision-server.log"), log);
  }
});

test("a complete real formula longer than 200 characters remains searchable", async ({
  page,
  request,
}) => {
  const { execFileSync } = await import("node:child_process");
  const record = JSON.parse(
    execFileSync(
      path.resolve("../.venv/bin/python"),
      [
        "-c",
        `import json
from pathlib import Path
from quantgraph.graph.personal_catalog import PersonalCatalogRepository
catalog=PersonalCatalogRepository(Path('../.artifacts/polish-v1/browser-runtime/catalog.sqlite'))
items=[item for item in catalog.all_items() if item['kind'] in {'variant','source'} and isinstance(item.get('formula'),str) and 200 < len(item['formula']) <= 2000]
assert items
item=max(items,key=lambda row:len(row['formula']))
print(json.dumps({key:item[key] for key in ['entity_id','name','formula']},ensure_ascii=False))`,
      ],
      { encoding: "utf8" },
    ),
  );
  const errors = watch(page);
  await page.goto("/factors");
  const input = page.getByRole("textbox", {
    name: "搜索名称、别名、规则、公式和来源",
  });
  await expect(input).toHaveAttribute("maxlength", "2000");
  await input.fill(record.formula);
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.locator(".pw-result-name").first()).toContainText(
    record.name,
  );
  const response = await request.get(
    `/v1/web/search?${new URLSearchParams({ kind: "variant", q: record.formula })}`,
  );
  expect(response.ok()).toBe(true);
  expect((await response.json()).items[0].entity_id).toBe(record.entity_id);
  await page.screenshot({
    path: path.join(artifacts, "13-full-formula-search.png"),
    fullPage: true,
  });
  await fs.writeFile(
    path.join(artifacts, "full-formula-search.json"),
    JSON.stringify(
      { entity_id: record.entity_id, length: record.formula.length, rank: 1 },
      null,
      2,
    ),
  );
  expect(errors).toEqual([]);
});

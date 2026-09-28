/** Opt-in real registered-worker acceptance. Never substitutes a mocked result. */
import { test, expect } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import type { Detail, EntityRef } from "../src/types";
const configPath = process.env.QUANTGRAPH_PRODUCT_CONFIG;
if (!configPath)
  throw new Error(
    "Set QUANTGRAPH_PRODUCT_CONFIG to an isolated operator config and start its platform first",
  );
const config = JSON.parse(await fs.readFile(configPath, "utf8"));
const output = path.join(path.dirname(configPath), "browser-acceptance");
for (const name of ["factor", "replication", "evolution"]) {
  test(`real UI ${name}: search → save → request → registered worker → original detail`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    const {
      entity_ref: ref,
      profile_id: profile,
    }: { entity_ref: EntityRef; profile_id: string } =
      config.acceptance_cases[name];
    const kind = ref.entity_type === "StrategyVariant" ? "strategy" : "variant";
    const detail: Detail = await (
      await page.request.get(`/v1/web/entities/${kind}/${ref.entity_id}`)
    ).json();
    expect(detail.definition_revision).toBe(ref.definition_revision);
    await page.goto("/admin");
    await page
      .getByLabel("管理密码")
      .fill((await fs.readFile(config.admin_password_file, "utf8")).trim());
    await page.getByRole("button", { name: "登录后台", exact: true }).click();
    await expect(page.getByRole("button", { name: "退出管理" })).toBeVisible();
    await page.goto(`/explore?kind=${kind}`);
    await page
      .getByRole("textbox", { name: "搜索名称、英文别名或描述" })
      .fill(kind === "strategy" ? detail.source_native_ids[0] : detail.name);
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page
      .getByRole("link", { name: detail.name, exact: true })
      .first()
      .click();
    await expect(
      page.getByRole("heading", { name: detail.name, exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: `收藏 ${detail.name}`, exact: true })
      .click();
    await page.goto("/list");
    await page.reload();
    await page.getByLabel("研究能力").selectOption(profile);
    await expect(page.getByText(/Worker：在线/)).toBeVisible();
    const requestResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith("/v1/web/research-requests") &&
        r.request().method() === "POST",
    );
    const submitResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith("/v1/research/jobs") &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "提交研究请求", exact: true })
      .click();
    const draft = await (await requestResponse).json();
    const response = await submitResponse;
    expect(draft.schema_version).toBe("research-request/v1");
    expect(draft.status).toBe("DRAFT");
    expect(draft.entity_refs).toEqual([ref]);
    expect(response.status()).toBe(202);
    const submitted = await response.json();
    await page.getByRole("link", { name: "查看任务与运行状态 →" }).click();
    let job = submitted;
    await expect
      .poll(
        async () => {
          job = await (
            await page.request.get(`/v1/research/jobs/${submitted.job_id}`)
          ).json();
          return job.status;
        },
        { timeout: 330000, intervals: [2000, 5000] },
      )
      .toBe("SUCCEEDED");
    await page.getByRole("button", { name: "刷新状态", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: /SUCCEEDED/ }),
    ).toBeVisible();
    // Authenticated evidence exists; numerical payload is checked privately, never screenshotted or committed.
    const evidence = await (
      await page.request.get(`/v1/research/jobs/${job.job_id}/evidence`)
    ).json();
    expect(evidence.items.length).toBeGreaterThan(0);
    expect(evidence.visibility).toBe("AUTHENTICATED_INTERNAL_RESEARCH");
    await page
      .getByRole("button", { name: "查看内部研究证据", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "内部研究证据", exact: true }),
    ).toBeVisible();
    await page.getByRole("link", { name: "返回原知识条目查看结果 →" }).click();
    await expect(
      page
        .getByText(
          "研究已实际运行；数值指标受数据展示权限限制。登录后可在任务页查看获准的内部研究证据。",
          { exact: true },
        )
        .first(),
    ).toBeVisible();
    const publicResults = await (
      await page.request.get(
        `/v1/web/results?kind=${kind}&eid=${encodeURIComponent(ref.entity_id)}`,
      )
    ).json();
    const studies = publicResults.items.filter(
      (r: { job_id: string }) => r.job_id === job.job_id,
    );
    expect(studies.length).toBeGreaterThan(0);
    expect(
      studies.every(
        (r: { metrics: object; numerical_display: string }) =>
          r.numerical_display === "RESTRICTED" &&
          Object.keys(r.metrics).length === 0,
      ),
    ).toBe(true);
    await fs.mkdir(output, { recursive: true });
    await page
      .getByRole("heading", { name: "研究记录", exact: true })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: path.join(output, `${name}-public-result.png`),
    });
    await fs.writeFile(
      path.join(output, `${name}-mapping.json`),
      JSON.stringify({ request: draft, job, results: studies }, null, 2),
    );
    expect(errors).toEqual([]);
    await page.goto("/admin");
    await page.getByRole("button", { name: "恢复已有会话" }).click();
    await page.getByRole("button", { name: "研究任务", exact: true }).click();
    await expect(
      page.getByRole("link", { name: new RegExp(job.job_id) }),
    ).toBeVisible();
  });
}

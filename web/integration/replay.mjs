// Real local integration acceptance. No route mocks and no manufactured results.
import { chromium, expect } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
const graph = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const [labArg, lockArg] = process.argv.slice(2);
if (!labArg || !lockArg)
  throw new Error("Usage: replay.mjs LAB_ROOT PRIVATE_INPUT_LOCK");
const lab = path.resolve(labArg);
const sha = (data) => createHash("sha256").update(data).digest("hex");
const lock = JSON.parse(await fs.readFile(lockArg, "utf8"));
for (const key of ["manifest", "acquisition_contract"]) {
  if (sha(await fs.readFile(lock[key].uri)) !== lock[key].sha256)
    throw new Error("Input lock mismatch: " + key);
}
const out = path.join(
  graph,
  "web/.artifacts/integration",
  new Date().toISOString().replaceAll(":", "-"),
);
await fs.mkdir(out, { recursive: true });
const journal = path.join(out, "factor-studies.sqlite");
const publicPort = 8778,
  privatePort = 8779;
const origin = `http://127.0.0.1:${publicPort}`;
const evidence = {
  graph_commit: execFileSync("git", ["rev-parse", "HEAD"], {
    cwd: graph,
    encoding: "utf8",
  }).trim(),
  lab_commit: execFileSync("git", ["rev-parse", "HEAD"], {
    cwd: lab,
    encoding: "utf8",
  }).trim(),
  steps: [],
  input_lock: lock,
};
for (const cwd of [graph, lab]) {
  if (
    execFileSync("git", ["status", "--porcelain", "--untracked-files=no"], {
      cwd,
      encoding: "utf8",
    }).trim()
  )
    throw new Error("Commit tracked changes before acceptance: " + cwd);
}
const processes = [];
async function server(port, privateMode = false) {
  try {
    await fetch(`http://127.0.0.1:${port}/health`);
    throw new Error("Port already occupied");
  } catch (e) {
    if (e.message === "Port already occupied") throw e;
  }
  const proc = spawn(
    path.join(graph, ".venv/bin/python"),
    [
      "-m",
      "quantgraph.api.web",
      "--port",
      String(port),
      ...(privateMode ? ["--private-study-journal", journal] : []),
    ],
    { cwd: graph, stdio: "ignore" },
  );
  processes.push(proc);
  for (let n = 0; n < 100; n++) {
    if (proc.exitCode !== null) throw new Error("Server exited");
    try {
      if ((await fetch(`http://127.0.0.1:${port}/health`)).ok) return;
    } catch {
      /* Wait for this isolated process to become ready. */
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("Server startup timeout");
}
function command(executable, args, cwd) {
  return new Promise((resolve, reject) => {
    const proc = spawn(executable, args, {
      cwd,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let output = "";
    proc.stdout.on("data", (c) => (output += c));
    proc.stderr.on("data", (c) => (output += c));
    proc.on("error", reject);
    proc.on("close", async (code) => {
      await fs.writeFile(path.join(out, "lab.log"), output);
      if (code === 0) resolve();
      else reject(new Error("Lab command failed; private lab.log retained"));
    });
  });
}
let browser;
try {
  await server(publicPort);
  browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [];
  const monitor = (p) => {
    p.on("pageerror", (e) => errors.push(e.message));
    p.on("console", (e) => {
      if (e.type() === "error") errors.push(e.text());
    });
  };
  monitor(page);
  await page.goto(origin + "/explore");
  evidence.steps.push({ step: 1, status: "PASS" });
  await page
    .getByRole("textbox", { name: "搜索名称、英文别名或描述" })
    .fill("Alpha158:MA5");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "MA5", exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: path.join(out, "01-public-search.png") });
  evidence.steps.push({ step: 2, status: "PASS" });
  await page.getByRole("link", { name: "MA5", exact: true }).click();
  const detailPath = new URL(page.url()).pathname;
  await expect(page.getByText("Mean($close, 5)/$close").first()).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "来源与定义版本" }),
  ).toBeVisible();
  await page.screenshot({ path: path.join(out, "02-public-definition.png") });
  evidence.steps.push({ step: 3, status: "PASS" });
  await page.getByRole("button", { name: "收藏 MA5", exact: true }).click();
  await page.getByRole("link", { name: /研究清单 1/ }).click();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "取消收藏 MA5", exact: true }),
  ).toBeVisible();
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "校验并导出请求" }).click();
  const download = await downloadEvent;
  const requestPath = path.join(out, "research-request.json");
  await download.saveAs(requestPath);
  const draft = JSON.parse(await fs.readFile(requestPath, "utf8"));
  expect(draft.schema_version).toBe("research-request/v1");
  expect(draft.status).toBe("DRAFT");
  evidence.request_id = draft.request_id;
  evidence.entity_ref = draft.entity_refs[0];
  await page.screenshot({ path: path.join(out, "03-public-export.png") });
  evidence.steps.push({ step: 4, status: "PASS" });
  const apiPath =
    "/v1/web/entities/variant/" +
    encodeURIComponent(draft.entity_refs[0].entity_id);
  const before = await (await fetch(origin + apiPath)).json();
  const studyOut = path.join(out, "lab");
  await command(
    path.join(lab, ".venv/bin/python"),
    [
      path.join(
        lab,
        "research/platform/factor-research-loop/scripts/from_web.py",
      ),
      "--request",
      requestPath,
      "--settings",
      path.join(
        lab,
        "research/platform/factor-research-loop/specs/web-integration-ma5.json",
      ),
      "--graph-root",
      graph,
      "--manifest",
      lock.manifest.uri,
      "--acquisition-contract",
      lock.acquisition_contract.uri,
      "--output",
      studyOut,
      "--journal",
      journal,
      ...(lock.exposure_ledger
        ? ["--exposure-ledger", lock.exposure_ledger]
        : []),
    ],
    lab,
  );
  const plan = JSON.parse(
    await fs.readFile(path.join(studyOut, "study/plan.json"), "utf8"),
  );
  const result = JSON.parse(
    await fs.readFile(
      path.join(studyOut, "study/runs/MA5/result.json"),
      "utf8",
    ),
  );
  const assessment = result.trial_registry.assessment;
  expect(plan.request_id).toBe(draft.request_id);
  expect(result.mapping.identity.definition_revision).toBe(
    draft.entity_refs[0].definition_revision,
  );
  expect(result.sample.real_market_data).toBe(true);
  expect(result.status).toBe("SUCCESS");
  expect(assessment.permitted_conclusion_level).toBe("EXPLORATORY_RESULT");
  expect(assessment.holdout_evidence_status).toBe("OBSERVED");
  expect(assessment.registry_selection_scope.completed_trials).toBe(2);
  const factorFile = await fs.stat(
    path.join(studyOut, "study/runs/MA5/factor-values.parquet"),
  );
  expect(factorFile.size).toBeGreaterThan(0);
  for (const attempt of assessment.registry_selection_scope.attempts) {
    expect(Date.parse(attempt.timestamps.planned)).toBeLessThanOrEqual(
      Date.parse(attempt.timestamps.started),
    );
    expect(Date.parse(attempt.timestamps.started)).toBeLessThan(
      Date.parse(attempt.timestamps.completed),
    );
  }
  evidence.run_id = result.run_id;
  evidence.plan_sha256 = plan.plan_sha256;
  evidence.trials = assessment.registry_selection_scope.attempts.map((a) => ({
    id: a.attempt_id,
    timestamps: a.timestamps,
  }));
  evidence.steps.push(
    ...[5, 6, 7, 8, 9].map((step) => ({ step, status: "PASS" })),
  );
  await server(privatePort, true);
  const privateOrigin = `http://127.0.0.1:${privatePort}`;
  const privatePage = await browser.newPage();
  monitor(privatePage);
  await privatePage.goto(privateOrigin + detailPath);
  await expect(
    privatePage.getByText(result.run_id, { exact: true }),
  ).toBeVisible();
  await expect(
    privatePage.getByText("EXPLORATORY_RESULT / OBSERVED", { exact: true }),
  ).toBeVisible();
  const privateDetail = await (await fetch(privateOrigin + apiPath)).json();
  expect(privateDetail.results.items[0]).toEqual(result);
  const after = await (
    await fetch(origin + apiPath + "?profile=research")
  ).json();
  expect(after).toEqual(before); // Includes statuses, relations, result counts and permissions.
  await privatePage.goto(privateOrigin + "/list");
  await expect(
    privatePage.getByRole("heading", { name: "清单还是空的" }),
  ).toBeVisible();
  await page.goto(origin + detailPath);
  await expect(page.getByText(/内部结果受权限限制/)).toBeVisible();
  await page
    .getByRole("heading", { name: "研究记录", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: path.join(out, "04-public-result-permission.png"),
  });
  evidence.steps.push({
    step: 10,
    status: "PASS",
    public: "GENERIC_PERMISSION_NOTICE",
    private: "SAME_ENTITY_RESULT_VERIFIED",
  });
  expect(errors).toEqual([]);
  evidence.browser_errors = errors;
  evidence.private_public_isolation = "PASS";
  evidence.status = "PASS";
} catch (error) {
  evidence.status = "FAILED";
  evidence.failure = String(error);
  throw error;
} finally {
  await fs.writeFile(
    path.join(out, "acceptance.json"),
    JSON.stringify(evidence, null, 2) + "\n",
  );
  await browser?.close();
  for (const proc of processes) proc.kill("SIGTERM");
  console.log("Acceptance artifacts: " + out);
}

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { createHash } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
const ref = {
  kind: "strategy",
  entity_id: "synthetic:one",
  entity_type: "StrategyVariant",
  definition_revision: "v1",
  name: "合成策略",
  native_ids: ["M9999"],
  definition_hash: createHash("sha256")
    .update(
      JSON.stringify({ definition: null, formula: null, original_rule: null }),
    )
    .digest("hex"),
};
const seed = {
  batch_id: "bundled-test",
  refs: [ref],
  results: [
    {
      origin_run_id: "run1",
      variant_id: "v1",
      manifest_sha256: "a".repeat(64),
      record_id: "M9999",
    },
  ],
};
const source = readFileSync(
  new URL("../worker/index.mjs", import.meta.url),
  "utf8",
).replace(
  /import seed from [^;]+;/,
  "const seed=" + JSON.stringify(seed) + ";",
);
const {
  default: worker,
  hash,
  canonical,
} = await import(
  "data:text/javascript;base64," + Buffer.from(source).toString("base64")
);
function environment() {
  const sqlite = new DatabaseSync(":memory:");
  for (const name of readdirSync(new URL("../drizzle/", import.meta.url))
    .filter((n) => n.endsWith(".sql"))
    .sort())
    sqlite.exec(
      readFileSync(new URL("../drizzle/" + name, import.meta.url), "utf8"),
    );
  const DB = {
    prepare(sql) {
      return {
        bind(...args) {
          const s = sqlite.prepare(sql);
          return {
            first: async () => s.get(...args) || null,
            all: async () => ({ results: s.all(...args) }),
            run: async () => s.run(...args),
            execute: () => s.run(...args),
          };
        },
      };
    },
    async batch(statements) {
      sqlite.exec("BEGIN");
      try {
        const out = statements.map((s) => s.execute());
        sqlite.exec("COMMIT");
        return out;
      } catch (e) {
        sqlite.exec("ROLLBACK");
        throw e;
      }
    },
  };
  const blobs = new Map();
  const BUCKET = {
    async put(k, b) {
      blobs.set(k, Uint8Array.from(b));
    },
    async get(k) {
      const b = blobs.get(k);
      return b ? { body: new Response(b).body } : null;
    },
  };
  return { DB, BUCKET, sqlite, blobs };
}
function browser(
  path,
  method = "GET",
  payload,
  owner = "owner-one",
  headers = {},
) {
  return new Request("https://test.chatgpt.site" + path, {
    method,
    headers: {
      "oai-authenticated-user-id": owner,
      ...(method === "GET"
        ? {}
        : {
            Origin: "https://test.chatgpt.site",
            "Content-Type": "application/json",
            "X-QuantGraph-Request": "1",
          }),
      ...headers,
    },
    ...(payload !== undefined ? { body: JSON.stringify(payload) } : {}),
  });
}
function service(path, method = "GET", payload) {
  return new Request("https://test.chatgpt.site" + path, {
    method,
    headers: { "X-QuantGraph-Sync": "1" },
    ...(payload !== undefined ? { body: JSON.stringify(payload) } : {}),
  });
}
const path =
  "/v1/personal/items/strategy/synthetic%3Aone?definition_revision=v1";
const save = (id = "m1", revision = 0, patch = { note: "先补证" }) => ({
  mutation_id: id,
  expected_record_revision: revision,
  patch,
});
test("owner note survives a separate request and another session, is isolated and immutable", async () => {
  const env = environment();
  let r = await worker.fetch(browser(path, "PUT", save()), env);
  assert.equal(r.status, 200);
  assert.equal((await r.json()).record_revision, 1);
  assert.equal(
    (await (await worker.fetch(browser(path), env)).json()).note,
    "先补证",
  );
  assert.equal(
    (
      await (
        await worker.fetch(browser(path, "GET", undefined, "owner-two"), env)
      ).json()
    ).note,
    "",
  );
  assert.throws(() =>
    env.sqlite.exec("UPDATE qg_feedback SET payload_json='{}'"),
  );
  assert.throws(() => env.sqlite.exec("DELETE FROM qg_feedback"));
});
test("CSRF and absent identity cannot save; service cannot manufacture browser identity", async () => {
  const env = environment();
  for (const req of [
    new Request("https://test.chatgpt.site" + path, {
      method: "PUT",
      body: JSON.stringify(save()),
    }),
    browser(path, "PUT", save(), "owner-one", {
      Origin: "https://evil.example",
    }),
    browser(path, "PUT", save(), "owner-one", {
      "Sec-Fetch-Site": "cross-site",
    }),
  ])
    assert.ok([401, 403].includes((await worker.fetch(req, env)).status));
  assert.equal(
    (await worker.fetch(browser("/v1/sync/feedback"), env)).status,
    403,
  );
});
test("same mutation replay is exact; different content or stale revision is rejected", async () => {
  const env = environment();
  assert.equal(
    (await worker.fetch(browser(path, "PUT", save()), env)).status,
    200,
  );
  assert.equal(
    (await worker.fetch(browser(path, "PUT", save()), env)).status,
    200,
  );
  assert.equal(
    (
      await worker.fetch(
        browser(path, "PUT", save("m1", 0, { note: "changed" })),
        env,
      )
    ).status,
    409,
  );
  assert.equal(
    (await worker.fetch(browser(path, "PUT", save("m2", 0)), env)).status,
    409,
  );
  assert.equal(
    (
      await worker.fetch(
        browser(path, "PUT", save("m3", 1, { questions: "下一步" })),
        env,
      )
    ).status,
    200,
  );
  const f = await (
    await worker.fetch(service("/v1/sync/feedback"), env)
  ).json();
  assert.deepEqual(
    f.events.map((e) => e.seq),
    [1, 2],
  );
  assert.equal(f.next_cursor, 2);
  assert.equal(
    await hash(
      canonical({ target: f.events[0].target, payload: f.events[0].payload }),
    ),
    f.events[0].payload_sha256,
  );
});
test("concurrent saves never overwrite a newer edit", async () => {
  const env = environment();
  const rs = await Promise.all([
    worker.fetch(browser(path, "PUT", save("a", 0, { note: "A" })), env),
    worker.fetch(browser(path, "PUT", save("b", 0, { note: "B" })), env),
  ]);
  assert.deepEqual(rs.map((r) => r.status).sort(), [200, 409]);
});
test("result identity includes run, variant and manifest", async () => {
  const env = environment();
  assert.equal(
    (
      await worker.fetch(
        browser(
          path +
            "&origin_run_id=run1&variant_id=v1&manifest_sha256=" +
            "a".repeat(64),
          "PUT",
          save(),
        ),
        env,
      )
    ).status,
    200,
  );
  assert.equal(
    (await (await worker.fetch(browser(path), env)).json()).note,
    "",
  );
  assert.equal(
    (
      await worker.fetch(
        browser(
          path +
            "&origin_run_id=wrong&variant_id=v1&manifest_sha256=" +
            "a".repeat(64),
        ),
        env,
      )
    ).status,
    409,
  );
});
test("empty and duplicate-key request fail without events", async () => {
  const env = environment();
  const req = browser(path, "PUT", save());
  const dup = new Request(req.url, {
    method: "PUT",
    headers: req.headers,
    body: '{"mutation_id":"x","mutation_id":"y","expected_record_revision":0,"patch":{}}',
  });
  assert.equal((await worker.fetch(dup, env)).status, 422);
  assert.equal(
    (await worker.fetch(browser(path + "-missing"), env)).status,
    409,
  );
  assert.equal(
    (await (await worker.fetch(service("/v1/sync/feedback"), env)).json())
      .events.length,
    0,
  );
});
test("batch bytes must match pins, activation is atomic/idempotent and history remains accessible", async () => {
  const env = environment();
  const bytes = new TextEncoder().encode(
    JSON.stringify({
      ...ref,
      knowledge: { reader_brief: { purpose: "新增补证" } },
    }),
  );
  const digest = await hash(bytes);
  const m = {
    schema_version: "quantgraph-site-sync/v1",
    parent_batch_id: seed.batch_id,
    files: [
      {
        path: "/catalog/details/test.json",
        sha256: digest,
        bytes: bytes.length,
      },
    ],
    entities: [{ ...ref, detail_path: "/catalog/details/test.json" }],
    results: [],
  };
  const begin = await (
    await worker.fetch(service("/v1/sync/batches", "POST", m), env)
  ).json();
  assert.equal(
    (
      await worker.fetch(
        service("/v1/sync/activate/" + begin.batch_id, "POST", {}),
        env,
      )
    ).status,
    409,
  );
  assert.equal(
    (
      await worker.fetch(
        new Request("https://test.chatgpt.site/v1/sync/objects/" + digest, {
          method: "PUT",
          headers: { "X-QuantGraph-Sync": "1" },
          body: "invalid",
        }),
        env,
      )
    ).status,
    422,
  );
  const upload = new Request(
    "https://test.chatgpt.site/v1/sync/objects/" + digest,
    { method: "PUT", headers: { "X-QuantGraph-Sync": "1" }, body: bytes },
  );
  assert.equal((await worker.fetch(upload, env)).status, 200);
  assert.equal(
    (
      await worker.fetch(
        service("/v1/sync/activate/" + begin.batch_id, "POST", {}),
        env,
      )
    ).status,
    200,
  );
  assert.equal(
    (
      await worker.fetch(
        service("/v1/sync/activate/" + begin.batch_id, "POST", {}),
        env,
      )
    ).status,
    200,
  );
  const served = await worker.fetch(
    browser("/v1/snapshot/assets?path=/catalog/details/test.json"),
    env,
  );
  assert.equal(await served.text(), new TextDecoder().decode(bytes));
  assert.equal(
    (
      await worker.fetch(
        browser(
          "/v1/snapshot/assets?path=/catalog/details/test.json&batch_id=" +
            seed.batch_id,
        ),
        env,
      )
    ).status,
    307,
  );
});
test("feedback acknowledgement cannot outrun retained events and MCP is private read-only", async () => {
  const env = environment();
  assert.equal(
    (await worker.fetch(service("/v1/sync/ack", "POST", { cursor: 1 }), env))
      .status,
    409,
  );
  await worker.fetch(browser(path, "PUT", save()), env);
  assert.equal(
    (await worker.fetch(service("/v1/sync/ack", "POST", { cursor: 1 }), env))
      .status,
    200,
  );
  const stat = await (
    await worker.fetch(browser("/v1/sync/status"), env)
  ).json();
  assert.equal(stat.cloud_received_cursor, 1);
  const discover = await (
    await worker.fetch(
      service("/mcp", "POST", { jsonrpc: "2.0", id: 1, method: "tools/list" }),
      env,
    )
  ).json();
  assert.equal(discover.result.tools.length, 2);
  const read = await worker.fetch(
    service("/mcp", "POST", {
      jsonrpc: "2.0",
      id: 1,
      method: "tools/call",
      params: { name: "quantgraph_feedback", arguments: {} },
    }),
    env,
  );
  assert.equal(read.status, 401);
});

test("duplicate immutable references and definition content changes are rejected", async () => {
  const env = environment();
  const data = { ...ref, formula: "changed" };
  const bytes = new TextEncoder().encode(JSON.stringify(data));
  const digest = await hash(bytes);
  const newref = {
    ...ref,
    definition_hash: await hash(
      canonical({ definition: null, formula: "changed", original_rule: null }),
    ),
    detail_path: "/catalog/details/changed.json",
  };
  const manifest = {
    schema_version: "quantgraph-site-sync/v1",
    parent_batch_id: seed.batch_id,
    files: [{ path: newref.detail_path, sha256: digest, bytes: bytes.length }],
    entities: [newref, newref],
    results: [],
  };
  assert.equal(
    (await worker.fetch(service("/v1/sync/batches", "POST", manifest), env))
      .status,
    422,
  );
  manifest.entities = [newref];
  const b = await (
    await worker.fetch(service("/v1/sync/batches", "POST", manifest), env)
  ).json();
  await worker.fetch(
    new Request("https://test.chatgpt.site/v1/sync/objects/" + digest, {
      method: "PUT",
      headers: { "X-QuantGraph-Sync": "1" },
      body: bytes,
    }),
    env,
  );
  assert.equal(
    (
      await worker.fetch(
        service("/v1/sync/activate/" + b.batch_id, "POST", {}),
        env,
      )
    ).status,
    409,
  );
  assert.equal(
    (await (await worker.fetch(browser("/v1/sync/status"), env)).json())
      .active_batch,
    seed.batch_id,
  );
});
test("broken or overlong history never silently falls back to bundled data", async () => {
  const env = environment();
  env.sqlite
    .prepare("INSERT INTO qg_batches VALUES(?,?,?,?,?,?,?)")
    .run("bad", "missing", "a".repeat(64), "{}", "ACTIVE", "now", "now");
  env.sqlite
    .prepare("INSERT INTO qg_settings VALUES(?,?)")
    .run("active_batch", "bad");
  assert.equal(
    (
      await worker.fetch(
        browser("/v1/snapshot/assets?path=/catalog/meta.json"),
        env,
      )
    ).status,
    503,
  );
});
test("browser context is rejected by every service mutation route", async () => {
  const env = environment();
  for (const [path, method] of [
    ["/v1/sync/batches", "POST"],
    ["/v1/sync/objects/" + "a".repeat(64), "PUT"],
    ["/v1/sync/activate/missing", "POST"],
    ["/v1/sync/ack", "POST"],
  ])
    assert.equal(
      (
        await worker.fetch(
          browser(path, method, {}, "owner-one", { "X-QuantGraph-Sync": "1" }),
          env,
        )
      ).status,
      403,
    );
});

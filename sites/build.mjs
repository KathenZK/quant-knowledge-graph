import { build as viteBuild } from "vite";
import react from "@vitejs/plugin-react";
import { build as bundle } from "esbuild";
import { readFile, writeFile, mkdir, cp, rm } from "node:fs/promises";
import { resolve } from "node:path";
const root = process.cwd();
await rm(resolve(root, "dist"), { recursive: true, force: true });
await viteBuild({
  configFile: false,
  root: resolve(root, "web"),
  publicDir: resolve(root, "public"),
  plugins: [react()],
  define: {
    "import.meta.env.VITE_QUANTGRAPH_DEPLOYMENT": JSON.stringify("sites"),
  },
  build: {
    outDir: resolve(root, "dist/client"),
    emptyOutDir: false,
    sourcemap: false,
  },
});
await bundle({
  entryPoints: [resolve(root, "sites/worker/index.mjs")],
  bundle: true,
  format: "esm",
  platform: "browser",
  target: "es2022",
  outfile: resolve(root, "dist/server/index.js"),
  minify: true,
});
await mkdir(resolve(root, "dist/.openai"), { recursive: true });
const hosting = JSON.parse(
  await readFile(resolve(root, ".openai/hosting.json"), "utf8"),
);
if (hosting.static || hosting.d1 !== "DB" || hosting.r2 !== "BUCKET")
  throw new Error("Expected logical Worker DB/BUCKET bindings");
await writeFile(
  resolve(root, "dist/.openai/hosting.json"),
  JSON.stringify(hosting, null, 2),
);
await cp(
  resolve(root, "sites/drizzle"),
  resolve(root, "dist/.openai/drizzle"),
  { recursive: true },
);
console.log(
  "Built existing QuantGraph React + lightweight Worker; private data is deployment input only",
);
await writeFile(
  resolve(root, "dist/server/wrangler.json"),
  JSON.stringify(
    {
      name: "quantgraph-sites",
      main: "index.js",
      compatibility_date: "2026-09-01",
      assets: { directory: "../client", binding: "ASSETS" },
    },
    null,
    2,
  ),
);

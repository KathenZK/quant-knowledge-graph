import { defineConfig } from "drizzle-kit";
export default defineConfig({
  out: "./sites/drizzle",
  schema: "./sites/db/schema.ts",
  dialect: "sqlite",
});

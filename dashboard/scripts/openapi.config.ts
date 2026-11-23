import { fileURLToPath } from "node:url";
import { defineConfig } from "@hey-api/openapi-ts/config";

export default defineConfig({
  input: fileURLToPath(new URL("../../openspec/openapi-v1.yaml", import.meta.url)),
  output: {
    path: fileURLToPath(new URL("../src/api/generated/openapi-v1", import.meta.url)),
    postProcess: ["biome:check"],
  },
  plugins: ["@hey-api/typescript", "@hey-api/sdk", "@hey-api/client-axios"],
});

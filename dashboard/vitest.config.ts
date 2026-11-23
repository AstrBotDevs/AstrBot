import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    server: { deps: { inline: ["vuetify"] } },
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://localhost:3000/" } },
    include: ["tests/**/*.test.mjs"],
    setupFiles: ["./tests/setup.mjs"],
    clearMocks: true,
    restoreMocks: false,
    unstubGlobals: true,
    unstubEnvs: true,
    isolate: true,
    pool: "forks",
    maxWorkers: 1,
    fileParallelism: false,
  },
});

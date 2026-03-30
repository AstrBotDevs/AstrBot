import { fileURLToPath, URL } from "url";
import { createRequire } from "module";
import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";
import vuetify from "vite-plugin-vuetify";
import webfontDl from "vite-plugin-webfont-dl";
import { cpSync, mkdirSync, existsSync } from "fs";
import { join, resolve } from "path";

const require = createRequire(import.meta.url);

// Conditional import for Cloudflare Workers (ESM-only package)
let cloudflarePlugin: (() => any) | null = null;
try {
  const mod = require("@cloudflare/vite-plugin");
  cloudflarePlugin = mod.cloudflare;
} catch {
  // Cloudflare plugin not available, skip
}

// Vite plugin: download MDI font to public/ at build time (no git binary)
function mdiFontDownload() {
  return {
    name: "vite-plugin-mdi-font-download",
    async buildStart() {
      const configDir = fileURLToPath(new URL(".", import.meta.url));
      const mdiSource = resolve(
        configDir,
        "node_modules/.pnpm/@mdi+font@7.4.47/node_modules/@mdi/font/fonts",
      );
      const mdiDest = resolve(configDir, "public/fonts");
      if (!existsSync(mdiSource)) {
        console.warn("[mdi-font] @mdi/font not found in node_modules, skipping download");
        return;
      }
      mkdirSync(mdiDest, { recursive: true });
      cpSync(mdiSource, mdiDest, { recursive: true });
      console.log("[mdi-font] Downloaded MDI fonts to public/fonts/");
    },
  };
}

// https://vitejs.dev/config/
export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const basePath = env.VITE_BASE_PATH || process.env.BASE_PATH || "/";
  const devApiProxyTarget =
    env.VITE_DEV_API_PROXY_TARGET ||
    process.env.VITE_DEV_API_PROXY_TARGET ||
    "";

  return {
    base: command === "build" ? basePath : "/",

    plugins: [
      mdiFontDownload(),
      vue({
        template: {
          compilerOptions: {
            isCustomElement: (tag) => ["v-list-recognize-title"].includes(tag),
          },
        },
      }),
      vuetify({
        autoImport: true,
      }),
      webfontDl(),
      ...(cloudflarePlugin ? [cloudflarePlugin()] : []),
    ],
    resolve: {
      alias: {
        mermaid: "mermaid/dist/mermaid.js",
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    css: {
      preprocessorOptions: {
        scss: {},
      },
    },
    build: {
      sourcemap: false,
      chunkSizeWarningLimit: 1024 * 1024, // Set the limit to 1 MB
    },
    optimizeDeps: {
      exclude: ["vuetify"],
      entries: ["./src/**/*.vue"],
    },
    server: {
      host: "::",
      port: 3000,
      proxy: devApiProxyTarget
        ? {
            "/api": {
              target: devApiProxyTarget,
              changeOrigin: true,
            },
          }
        : undefined,
    },
  };
});

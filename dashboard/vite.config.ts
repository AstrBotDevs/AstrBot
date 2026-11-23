import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";
import { defineConfig, loadEnv, type Plugin } from "vite";
import vue from "@vitejs/plugin-vue";
import vuetify from "vite-plugin-vuetify";
import webfontDl from "vite-plugin-webfont-dl";
import { runMdiSubset } from "./scripts/subset-mdi-font.mjs";

const require = createRequire(import.meta.url);
let cloudflarePlugin: (() => Plugin | Plugin[]) | undefined;
try {
  cloudflarePlugin = require("@cloudflare/vite-plugin").cloudflare;
} catch {
  // The optional deployment adapter is absent in ordinary dashboard builds.
}

const t2iShikiRuntimePath = fileURLToPath(
  new URL("../astrbot/core/utils/t2i/template/shiki_runtime.iife.js", import.meta.url),
);

function mdiSubset(): Plugin {
  return {
    name: "vite-plugin-mdi-subset",
    async buildStart() {
      await runMdiSubset();
    },
  };
}

function t2iShikiRuntimeAsset(): Plugin {
  return {
    name: "vite-plugin-t2i-shiki-runtime",
    configureServer(server) {
      server.middlewares.use("/t2i/shiki_runtime.iife.js", (_req, res) => {
        try {
          res.statusCode = 200;
          res.setHeader("Content-Type", "text/javascript; charset=utf-8");
          res.end(readFileSync(t2iShikiRuntimePath));
        } catch (error) {
          res.statusCode = 404;
          res.end(`T2I Shiki runtime not found: ${error instanceof Error ? error.message : String(error)}`);
        }
      });
    },
    generateBundle() {
      try {
        this.emitFile({
          type: "asset",
          fileName: "t2i/shiki_runtime.iife.js",
          source: readFileSync(t2iShikiRuntimePath),
        });
      } catch (error) {
        this.warn(`Skipping unavailable T2I Shiki runtime: ${error instanceof Error ? error.message : String(error)}`);
      }
    },
  };
}

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const basePath = env.VITE_BASE_PATH || process.env.BASE_PATH || "/";
  const proxyTarget =
    env.VITE_DEV_API_PROXY_TARGET || process.env.VITE_DEV_API_PROXY_TARGET || "http://127.0.0.1:6185";

  return {
    base: command === "build" ? basePath : "/",
    plugins: [
      ...(command === "build" ? [mdiSubset()] : []),
      t2iShikiRuntimeAsset(),
      {
        name: "katex-woff2-only",
        enforce: "pre",
        transform(source, id) {
          if (!/\/katex\/dist\/katex(?:\.min)?\.css$/.test(id.split("?")[0])) return;
          return source.replace(/src:[^;}]+/g, (declaration) => {
            const woff2 = declaration.match(/url\([^)]*\.woff2\)\s*format\(["']woff2["']\)/);
            return woff2 ? `src:${woff2[0]}` : declaration;
          });
        },
      },
      vue({
        template: {
          compilerOptions: {
            isCustomElement: (tag) => ["v-list-recognize-title"].includes(tag),
          },
        },
      }),
      vuetify({ autoImport: true }),
      webfontDl(),
      ...(cloudflarePlugin ? [cloudflarePlugin()] : []),
    ],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
        mermaid: "mermaid/dist/mermaid.js",
      },
    },
    css: {
      preprocessorOptions: {
        scss: {
          api: "modern-compiler",
          silenceDeprecations: ["import", "global-builtin", "if-function"],
        },
        sass: {
          api: "modern-compiler",
          silenceDeprecations: ["import", "global-builtin", "if-function"],
        },
      },
    },
    build: {
      sourcemap: false,
      chunkSizeWarningLimit: 1024,
    },
    optimizeDeps: {
      exclude: ["vuetify"],
      entries: ["./src/**/*.vue"],
    },
    server: {
      host: "0.0.0.0",
      port: 3000,
      proxy: {
        "/api": { target: proxyTarget, changeOrigin: true, ws: true },
      },
    },
  };
});

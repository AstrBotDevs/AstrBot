import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const indexHtml = await readFile(new URL("../index.html", import.meta.url), "utf8");
const viteConfig = await readFile(new URL("../vite.config.ts", import.meta.url), "utf8");
const vadComposable = await readFile(
  new URL("../src/composables/useVADRecording.ts", import.meta.url),
  "utf8",
);
const dashboardEntry = await readFile(new URL("../src/main.ts", import.meta.url), "utf8");
const t2iEditor = await readFile(
  new URL("../src/components/shared/T2ITemplateEditor.vue", import.meta.url),
  "utf8",
);
const dashboardStaticRoutes = await readFile(
  new URL("../../astrbot/dashboard/api/static_files.py", import.meta.url),
  "utf8",
);

test("loads VAD and fonts from local build assets", () => {
  assert.doesNotMatch(indexHtml, /https:\/\/(?:cdn\.jsdelivr\.net|fonts\.googleapis\.com)/);
  assert.match(indexHtml, /%BASE_URL%vad\/onnx\/ort\.wasm\.min\.js/);
  assert.match(indexHtml, /%BASE_URL%vad\/bundle\.min\.js/);
  assert.match(vadComposable, /import\.meta\.env\.BASE_URL}vad\//);
  assert.match(viteConfig, /vite-plugin-vad-runtime-assets/);
  assert.match(viteConfig, /silero_vad_v5\.onnx/);
  assert.match(viteConfig, /ort-wasm-simd-threaded\.wasm/);
  assert.match(dashboardEntry, /@fontsource\/outfit\/400\.css/);
  assert.match(dashboardEntry, /@fontsource\/noto-sans\/400\.css/);
  assert.match(t2iEditor, /DOMPurify\.sanitize/);
  assert.match(t2iEditor, /sandbox=""/);
  assert.doesNotMatch(t2iEditor, /sandbox="allow-scripts"/);
  assert.doesNotMatch(t2iEditor, /src=["']\/t2i\/shiki_runtime\.iife\.js/);
});

test("adds a dashboard CSP that keeps local assets and browser workers usable", () => {
  assert.match(dashboardStaticRoutes, /Content-Security-Policy/);
  assert.match(dashboardStaticRoutes, /script-src 'self'/);
  assert.match(dashboardStaticRoutes, /worker-src 'self' blob:/);
  assert.match(dashboardStaticRoutes, /img-src 'self' data: blob: https:/);
  assert.match(dashboardStaticRoutes, /connect-src 'self' https: ws: wss:/);
});

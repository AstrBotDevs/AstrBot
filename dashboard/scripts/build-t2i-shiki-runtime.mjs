import { createRequire } from "node:module";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { build } from "vite";

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(__dirname, "..");
const runtimeOutputFile = path.resolve(
  dashboardRoot,
  "..",
  "astrbot",
  "core",
  "utils",
  "t2i",
  "template",
  "shiki_runtime.iife.js",
);
const shikiRequire = createRequire(require.resolve("shiki/package.json"));

const languageSpecs = [
  ["bash", "bash"],
  ["css", "css"],
  ["html", "html"],
  ["javascript", "javascript"],
  ["json", "json"],
  ["jsx", "jsx"],
  ["markdown", "markdown"],
  ["powershell", "powershell"],
  ["python", "python"],
  ["sql", "sql"],
  ["tsx", "tsx"],
  ["typescript", "typescript"],
  ["xml", "xml"],
  ["yaml", "yaml"],
];

const themeSpecs = [
  ["github-light", "github-light"],
  ["github-dark", "github-dark"],
];

const languageAliases = {
  bat: "powershell",
  cjs: "javascript",
  console: "bash",
  cts: "typescript",
  dockerfile: "bash",
  env: "bash",
  htm: "html",
  js: "javascript",
  md: "markdown",
  mjs: "javascript",
  mts: "typescript",
  plain: "text",
  plaintext: "text",
  ps1: "powershell",
  pwsh: "powershell",
  py: "python",
  shell: "bash",
  shellscript: "bash",
  sh: "bash",
  svg: "xml",
  text: "text",
  ts: "typescript",
  txt: "text",
  vue: "html",
  xhtml: "html",
  xml: "xml",
  yml: "yaml",
  zsh: "bash",
};

function resolveShikiModule(specifier) {
  return pathToFileURL(shikiRequire.resolve(specifier)).href;
}

function buildVirtualSource() {
  const shikiImport = JSON.stringify(
    pathToFileURL(require.resolve("shiki")).href,
  );
  const languageImports = languageSpecs
    .map(
      ([, packageName], index) =>
        `import lang${index} from ${JSON.stringify(resolveShikiModule(`@shikijs/langs/${packageName}`))};`,
    )
    .join("\n");

  const themeImports = themeSpecs
    .map(
      ([, packageName], index) =>
        `import theme${index} from ${JSON.stringify(resolveShikiModule(`@shikijs/themes/${packageName}`))};`,
    )
    .join("\n");

  const supportedLanguages = languageSpecs.map(([runtimeName]) => runtimeName);

  return `import { createHighlighterCoreSync, createJavaScriptRegexEngine } from ${shikiImport};
${languageImports}
${themeImports}

const highlighter = createHighlighterCoreSync({
  engine: createJavaScriptRegexEngine(),
  langs: [${languageSpecs.map((_, index) => `...lang${index}`).join(", ")}],
  themes: [${themeSpecs.map((_, index) => `theme${index}`).join(", ")}],
});

const supportedLanguages = new Set(${JSON.stringify(supportedLanguages)});
const languageAliases = ${JSON.stringify(languageAliases)};
const supportedThemes = new Set(${JSON.stringify(themeSpecs.map(([theme]) => theme))});

function normalizeLanguage(language) {
  const normalized = String(language || "").trim().toLowerCase();
  if (!normalized) {
    return "text";
  }

  if (normalized in languageAliases) {
    return languageAliases[normalized];
  }

  return supportedLanguages.has(normalized) ? normalized : "text";
}

function normalizeTheme(theme) {
  const normalized = String(theme || "").trim();
  return supportedThemes.has(normalized) ? normalized : "github-light";
}

function extractLanguage(codeElement) {
  const className = codeElement.className || "";
  const match = className.match(/language-([\\w+#.-]+)/i);
  return match ? match[1] : "";
}

function renderCodeToHtml(code, language, theme) {
  const normalizedTheme = normalizeTheme(theme);

  try {
    return highlighter.codeToHtml(String(code || ""), {
      lang: normalizeLanguage(language),
      theme: normalizedTheme,
    });
  } catch (error) {
    console.warn("Failed to render T2I code block with Shiki.", error);
    return highlighter.codeToHtml(String(code || ""), {
      lang: "text",
      theme: normalizedTheme,
    });
  }
}

function highlightAllCodeBlocks(root, theme) {
  if (!root) {
    return;
  }

  root.querySelectorAll("pre > code").forEach((codeElement) => {
    const preElement = codeElement.parentElement;
    if (!preElement || preElement.classList.contains("shiki")) {
      return;
    }

    preElement.outerHTML = renderCodeToHtml(
      codeElement.textContent || "",
      extractLanguage(codeElement),
      theme,
    );
  });
}

window.AstrBotT2IShiki = Object.freeze({
  highlightAllCodeBlocks,
  normalizeLanguage,
  renderCodeToHtml,
});
`;
}

async function main() {
  const tempDir = mkdtempSync(path.join(tmpdir(), "astrbot-t2i-shiki-runtime-"));
  const entryPath = path.join(tempDir, "entry.mjs");

  writeFileSync(entryPath, buildVirtualSource(), "utf-8");

  try {
    await build({
      configFile: false,
      logLevel: "info",
      publicDir: false,
      build: {
        chunkSizeWarningLimit: 1500,
        cssCodeSplit: false,
        emptyOutDir: false,
        lib: {
          entry: entryPath,
          fileName: () => path.basename(runtimeOutputFile),
          formats: ["iife"],
          name: "AstrBotT2IShikiRuntime",
        },
        minify: "esbuild",
        outDir: path.dirname(runtimeOutputFile),
        rollupOptions: {
          output: {
            inlineDynamicImports: true,
          },
        },
        sourcemap: false,
        target: "es2018",
      },
    });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }

  console.log(`Built ${runtimeOutputFile}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

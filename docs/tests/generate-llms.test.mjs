import assert from "node:assert/strict";
import {
  mkdtemp,
  mkdir,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";

import {
  canonicalPathFor,
  generateLlms,
  rawMarkdownPathForPage,
} from "../scripts/generate-llms.mjs";

async function writeFixture(root, relativePath, content) {
  const absolutePath = join(root, ...relativePath.split("/"));
  await mkdir(dirname(absolutePath), { recursive: true });
  await writeFile(absolutePath, content);
}

async function createFixtureProject() {
  const temporaryRoot = await mkdtemp(join(tmpdir(), "astrbot-llms-"));
  const docsRoot = join(temporaryRoot, "docs");

  await writeFixture(
    docsRoot,
    "zh/index.md",
    `---
layout: home
---

# AstrBot

Agentic AI assistant documentation.
`,
  );
  await writeFixture(
    docsRoot,
    "zh/dev/star/plugin-new.md",
    `---
outline: deep
---

# AstrBot 插件开发指南

本章节介绍插件开发，并从最小示例开始。

## 开始

::: tip 注意事项
继续阅读[下一篇](./next.md)。
:::

\`\`\`text
<script setup>
# This heading is inside a code block.
</script>
\`\`\`

<script setup>
import { onMounted } from "vue"
</script>
`,
  );
  await writeFixture(
    docsRoot,
    "zh/dev/star/next.md",
    `# 下一篇

更多内容。
`,
  );
  await writeFixture(
    docsRoot,
    "zh/dev/star/index.md",
    `# 插件开发目录

目录内容。
`,
  );
  await writeFixture(
    docsRoot,
    "zh/redirect.md",
    `---
layout: false
head:
  - - meta
    - name: robots
      content: noindex
---

# Redirect
`,
  );
  await writeFixture(
    docsRoot,
    "zh/draft.md",
    `---
draft: true
---

# Draft
`,
  );
  await writeFixture(
    docsRoot,
    "zh/platform/windows.md",
    "---\r\noutline: deep\r\n---\r\n\r\n# Windows\r\n\r\nCRLF content.\r\n",
  );
  await writeFixture(
    docsRoot,
    "en/index.md",
    `# AstrBot

English documentation.
`,
  );
  await writeFixture(
    docsRoot,
    "en/dev/star/plugin-new.md",
    `# Plugin Guide

Build an AstrBot plugin.

## Requirements

### Details

[Local anchor](#details)

[Clean root document](/dev/star/next)

[Root Markdown document](/dev/star/next.md)

[Root asset](/logo.png)

[Encoded document](/dev/star/guide%20page.md)

[Reserved filename](/dev/star/name%23part.md)
`,
  );

  return {
    docsRoot,
    publicDir: join(docsRoot, "public"),
    temporaryRoot,
  };
}

test("maps localized Markdown paths to clean canonical routes", () => {
  assert.equal(canonicalPathFor("zh", "index.md"), "/");
  assert.equal(canonicalPathFor("zh", "what-is-astrbot.md"), "/what-is-astrbot");
  assert.equal(
    canonicalPathFor("zh", "dev/plugin-market/index.md"),
    "/dev/plugin-market/",
  );
  assert.equal(canonicalPathFor("en", "index.md"), "/en/");
  assert.equal(
    canonicalPathFor("en", "dev/star/plugin-new.md"),
    "/en/dev/star/plugin-new",
  );
});

test("maps VitePress page paths to raw Markdown routes", () => {
  assert.equal(
    rawMarkdownPathForPage("zh/dev/star/plugin-new.md"),
    "/raw/zh/dev/star/plugin-new.md",
  );
  assert.equal(
    rawMarkdownPathForPage("en/use/plugin page.md"),
    "/raw/en/use/plugin%20page.md",
  );
  assert.equal(
    rawMarkdownPathForPage("en/use/guide%20page.md"),
    "/raw/en/use/guide%20page.md",
  );
  assert.equal(
    rawMarkdownPathForPage("zh/dev/star/name#part?.md"),
    "/raw/zh/dev/star/name%23part%3F.md",
  );
  assert.equal(rawMarkdownPathForPage("README.md"), null);
});

test("generates raw, index, and full Markdown outputs", async (t) => {
  const project = await createFixtureProject();
  t.after(() => rm(project.temporaryRoot, { recursive: true, force: true }));

  await mkdir(join(project.publicDir, "raw", "zh"), { recursive: true });
  await writeFile(join(project.publicDir, "raw", "zh", "stale.md"), "stale");

  const result = await generateLlms({
    docsRoot: project.docsRoot,
    publicDir: project.publicDir,
  });

  assert.equal(result.sourceDocuments, 9);
  assert.equal(result.canonicalDocuments, 7);
  assert.equal(result.rawDocuments, 8);

  const index = await readFile(join(project.publicDir, "llms.txt"), "utf8");
  assert.match(index, /^# AstrBot Documentation/m);
  assert.match(
    index,
    /\[AstrBot 插件开发指南\]\(https:\/\/docs\.astrbot\.app\/dev\/star\/plugin-new\)/,
  );
  assert.match(
    index,
    /https:\/\/docs\.astrbot\.app\/raw\/zh\/dev\/star\/plugin-new\.md/,
  );
  assert.match(index, /https:\/\/docs\.astrbot\.app\/llms-full\.txt/);
  assert.match(index, /https:\/\/docs\.astrbot\.app\/llms-zh\.txt/);
  assert.match(index, /https:\/\/docs\.astrbot\.app\/llms-en\.txt/);
  assert.doesNotMatch(index, /\/redirect/);
  assert.doesNotMatch(index, /\/draft/);
  assert.doesNotMatch(index, /\): >/);
  assert.doesNotMatch(index, /Generated at/);

  const englishIndex = await readFile(
    join(project.publicDir, "llms-en.txt"),
    "utf8",
  );
  assert.match(englishIndex, /# AstrBot Documentation - Complete Markdown/);
  assert.doesNotMatch(englishIndex, /AstrBot 插件开发指南/);

  const combinedFullText = await readFile(
    join(project.publicDir, "llms-full.txt"),
    "utf8",
  );
  assert.match(combinedFullText, /AstrBot 插件开发指南/);
  assert.match(combinedFullText, /Plugin Guide/);
  assert.match(
    combinedFullText,
    /\[下一篇\]\(https:\/\/docs\.astrbot\.app\/dev\/star\/next\)/,
  );
  assert.match(
    combinedFullText,
    /\[Local anchor\]\(https:\/\/docs\.astrbot\.app\/en\/dev\/star\/plugin-new#details\)/,
  );
  assert.match(
    combinedFullText,
    /\[Clean root document\]\(https:\/\/docs\.astrbot\.app\/en\/dev\/star\/next\)/,
  );
  assert.match(
    combinedFullText,
    /\[Root Markdown document\]\(https:\/\/docs\.astrbot\.app\/en\/dev\/star\/next\)/,
  );
  assert.match(
    combinedFullText,
    /\[Root asset\]\(https:\/\/docs\.astrbot\.app\/logo\.png\)/,
  );
  assert.match(
    combinedFullText,
    /\[Encoded document\]\(https:\/\/docs\.astrbot\.app\/en\/dev\/star\/guide%20page\)/,
  );
  assert.match(
    combinedFullText,
    /\[Reserved filename\]\(https:\/\/docs\.astrbot\.app\/en\/dev\/star\/name%23part\)/,
  );
  assert.doesNotMatch(combinedFullText, /%2520/);
  assert.match(combinedFullText, /\*\*Tip: 注意事项\*\*/);
  assert.match(combinedFullText, /<script setup>\n# This heading is inside/);
  assert.doesNotMatch(combinedFullText, /import \{ onMounted \}/);
  assert.doesNotMatch(combinedFullText, /^outline: deep$/m);
  assert.doesNotMatch(combinedFullText, /^::: tip/m);

  const rawPlugin = await readFile(
    join(project.publicDir, "raw", "zh", "dev", "star", "plugin-new.md"),
    "utf8",
  );
  assert.match(rawPlugin, /^---\noutline: deep\n---/);
  assert.match(rawPlugin, /import \{ onMounted \}/);

  const rawCrlf = await readFile(
    join(project.publicDir, "raw", "zh", "platform", "windows.md"),
  );
  assert.equal(
    rawCrlf.toString("utf8"),
    "---\r\noutline: deep\r\n---\r\n\r\n# Windows\r\n\r\nCRLF content.\r\n",
  );

  await assert.rejects(
    readFile(join(project.publicDir, "raw", "zh", "stale.md")),
    { code: "ENOENT" },
  );
  await assert.rejects(
    readFile(join(project.publicDir, "raw", "zh", "draft.md")),
    { code: "ENOENT" },
  );
  assert.match(
    await readFile(join(project.publicDir, "raw", "zh", "redirect.md"), "utf8"),
    /layout: false/,
  );

  const firstOutput = await readFile(
    join(project.publicDir, "llms-full.txt"),
  );
  await generateLlms({
    docsRoot: project.docsRoot,
    publicDir: project.publicDir,
  });
  assert.deepEqual(
    await readFile(join(project.publicDir, "llms-full.txt")),
    firstOutput,
  );
});

test("rejects full-text output that exceeds the configured limit", async (t) => {
  const project = await createFixtureProject();
  t.after(() => rm(project.temporaryRoot, { recursive: true, force: true }));

  await mkdir(project.publicDir, { recursive: true });
  await writeFile(join(project.publicDir, "llms.txt"), "previous output");

  await assert.rejects(
    generateLlms({
      docsRoot: project.docsRoot,
      publicDir: project.publicDir,
      maxLanguageBytes: 10,
    }),
    /Chinese full documentation .* exceeding the 10-byte limit/,
  );
  assert.equal(
    await readFile(join(project.publicDir, "llms.txt"), "utf8"),
    "previous output",
  );
});

test("serializes concurrent generator runs without temporary output", async (t) => {
  const project = await createFixtureProject();
  t.after(() => rm(project.temporaryRoot, { recursive: true, force: true }));

  await Promise.all([
    generateLlms({
      docsRoot: project.docsRoot,
      publicDir: project.publicDir,
    }),
    generateLlms({
      docsRoot: project.docsRoot,
      publicDir: project.publicDir,
    }),
  ]);

  const outputs = await readdir(project.publicDir);
  assert.equal(
    outputs.filter((filename) => filename.startsWith(".llms-")).length,
    0,
  );
  assert.match(
    await readFile(join(project.publicDir, "llms.txt"), "utf8"),
    /^# AstrBot Documentation/m,
  );
  assert.match(
    await readFile(
      join(project.publicDir, "raw", "en", "dev", "star", "plugin-new.md"),
      "utf8",
    ),
    /Plugin Guide/,
  );
});

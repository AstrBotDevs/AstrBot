import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

test("history pages retain reasoning boundaries and complete tool results", () => {
  const source = readFileSync(
    new URL("../src/composables/useMessages.ts", import.meta.url),
    "utf8",
  );
  const ast = ts.createSourceFile(
    "messages.ts",
    source,
    ts.ScriptTarget.Latest,
    true,
  );
  const names = new Set([
    "normalizeHistoryRecord",
    "normalizeMessageParts",
    "normalizePartsInternal",
    "extractReasoningText",
    "messageBlocks",
    "isEmptyPlainPart",
    "isThinkingPart",
  ]);
  const functions = [];
  const visit = (node) => {
    if (ts.isFunctionDeclaration(node) && names.has(node.name?.text)) {
      functions.push(node.getText(ast));
    }
    ts.forEachChild(node, visit);
  };
  visit(ast);
  assert.equal(functions.length, names.size);
  let locale = "en-US";
  const translations = Object.fromEntries(
    ["en-US", "zh-CN", "ja-JP", "ru-RU"].map((language) => [
      language,
      JSON.parse(readFileSync(new URL(`../src/i18n/locales/${language}/features/chat.json`, import.meta.url), "utf8").replace(/^\uFEFF/, "")),
    ]),
  );
  const context = vm.createContext({
    exports: {},
    useModuleI18n: () => ({ tm: (key) => key.split(".").reduce((value, part) => value[part], translations[locale]) }),
  });
  vm.runInContext(ts.transpile(functions.join("\n")), context);

  for (const language of Object.keys(translations)) {
    locale = language;
    for (const code of ["ffmpegNotFound", "messageProcessingFailed"]) {
      const content = { type: "bot", message: [{ type: "plain", text: "stored fallback", error_code: code }] };
      const restored = context.normalizeHistoryRecord({ id: 2, content });
      assert.equal(context.messageBlocks(restored.content)[0].parts[0].text, translations[locale].errors[code]);
      assert.equal(content.message[0].text, "stored fallback");
    }
  }

  const parts = [
    { type: "think", think: "Before the tool" },
    {
      type: "tool_call",
      tool_calls: [{ id: "tool-1", name: "search", result: "Complete result" }],
    },
    { type: "plain", text: "Intermediate answer" },
    { type: "think", think: "After the tool" },
    { type: "plain", text: "Final answer" },
  ];
  const record = context.normalizeHistoryRecord({
    id: 1,
    content: { type: "bot", message: parts },
  });
  assert.deepEqual(JSON.parse(JSON.stringify(record.content.message)), parts);
  const blocks = context.messageBlocks(record.content);
  assert.deepEqual(JSON.parse(JSON.stringify(blocks)), [
    { kind: "thinking", parts: parts.slice(0, 2) },
    { kind: "content", parts: parts.slice(2, 3) },
    { kind: "thinking", parts: parts.slice(3, 4) },
    { kind: "content", parts: parts.slice(4) },
  ]);
});

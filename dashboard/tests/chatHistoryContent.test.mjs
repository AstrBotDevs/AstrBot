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
  const context = vm.createContext({ exports: {} });
  vm.runInContext(ts.transpile(functions.join("\n")), context);

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

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

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
  "processStreamPayload",
  "appendError",
  "appendPlain",
  "markMessageStarted",
  "payloadText",
  "hasPlainText",
  "normalizeMessageParts",
  "normalizePartsInternal",
  "messageBlocks",
  "isThinkingPart",
  "isEmptyPlainPart",
]);
const functions = [];
function visit(node) {
  if (ts.isFunctionDeclaration(node) && names.has(node.name?.text))
    functions.push(node.getText(ast));
  ts.forEachChild(node, visit);
}
visit(ast);
assert.equal(functions.length, names.size);

for (const transport of ["sse", "websocket"]) {
  test(`${transport} retains error identity and partial output through completion and history`, () => {
    const context = vm.createContext({
      exports: {},
      messageContent: (record) => record.content,
    });
    vm.runInContext(ts.transpile(functions.join("\n")), context);
    const record = { content: { type: "bot", message: [], isLoading: true } };
    const frames = [
      { type: "plain", data: "Partial answer", streaming: true },
      {
        type: "error",
        data: { code: "noProvider", message: "No available model" },
      },
      { type: "complete", data: "Partial answer", streaming: true },
      { type: "end" },
    ];
    for (const frame of frames)
      context.processStreamPayload(
        record,
        transport === "sse" ? frame : { ...frame, ct: "chat", t: frame.type },
      );
    const expected = [
      { type: "plain", text: "Partial answer" },
      { type: "error", code: "noProvider", message: "No available model" },
    ];
    assert.deepEqual(
      JSON.parse(JSON.stringify(record.content.message)),
      expected,
    );
    assert.equal(record.content.isLoading, false);
    const restored = context.normalizeMessageParts(
      JSON.parse(JSON.stringify(record.content.message)),
    );
    assert.deepEqual(JSON.parse(JSON.stringify(restored)), expected);
    assert.equal(
      context.messageBlocks({ ...record.content, message: restored })[0].kind,
      "content",
    );
  });
}

test("legacy error events and unknown error codes remain error parts", () => {
  const context = vm.createContext({ exports: {} });
  vm.runInContext(ts.transpile(functions.join("\n")), context);
  const record = { content: { message: [] } };
  context.processStreamPayload(record, {
    type: "error",
    data: "Legacy failure",
  });
  context.processStreamPayload(record, {
    type: "error",
    data: { code: "future_error", message: "Unknown failure" },
  });
  context.appendError(record, new Error("Disconnected"), "connection_error");
  assert.deepEqual(JSON.parse(JSON.stringify(record.content.message)), [
    { type: "error", code: "agent_error", message: "Legacy failure" },
    { type: "error", code: "future_error", message: "Unknown failure" },
    { type: "error", code: "connection_error", message: "Disconnected" },
  ]);
});

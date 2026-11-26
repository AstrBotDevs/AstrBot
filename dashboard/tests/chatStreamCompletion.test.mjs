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
  "startSseStream",
  "processStreamPayload",
  "isSessionRunning",
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

for (const scenario of ["missing end", "complete", "aborted", "another run"]) {
  test(`SSE completion reconciles only an interrupted idle session: ${scenario}`, async () => {
    const bot = { content: { type: "bot", message: [] } };
    const connections = {};
    const reloads = [];
    const context = vm.createContext({
      AbortController,
      activeConnections: connections,
      messagesBySession: { session: [bot] },
      deferredBotAnchors: new WeakMap(),
      locale: { value: "en-US" },
      chatApi: { sendStreamUrl: () => "/chat/send" },
      buildChatRequestFlags: () => ({}),
      readChatSessionPrefs: () => ({}),
      processToolStreamPayload: () => false,
      fetchWithAuth: async () => ({ ok: true, body: {} }),
      readSseStream: async (_body, onPayload) => {
        if (scenario === "complete") onPayload({ type: "end" });
        if (scenario === "aborted") connections.message.abort.abort();
        if (scenario === "another run") {
          connections.other = { sessionId: "session" };
        }
      },
      markMessageStarted: () => {},
      partToPayload: (part) => part,
      loadSessionMessages: async (...args) => reloads.push(args),
      options: { onSessionsChanged: async () => {} },
    });
    vm.runInContext(ts.transpile(functions.join("\n")), context);
    context.startSseStream(
      "session",
      "message",
      [],
      bot,
      undefined,
      true,
      true,
      "",
      "",
    );
    await new Promise(setImmediate);
    assert.equal(connections.message, undefined);
    assert.deepEqual(
      reloads,
      scenario === "missing end" ? [["session", true, false, true]] : [],
    );
  });
}

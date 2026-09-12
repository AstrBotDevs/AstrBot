import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

test("failed history loading pauses scroll requests until an explicit retry", async () => {
  const chat = readFileSync(
    new URL("../src/components/chat/Chat.vue", import.meta.url),
    "utf8",
  )
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const messages = readFileSync(
    new URL("../src/composables/useMessages.ts", import.meta.url),
    "utf8",
  );
  const names = new Set([
    "maybeLoadEarlierOnScroll",
    "loadEarlierWithAnchor",
    "retryCurrentSessionLoad",
    "loadEarlierMessages",
  ]);
  const functions = [];
  for (const source of [chat, messages]) {
    const ast = ts.createSourceFile(
      "source.ts",
      source,
      ts.ScriptTarget.Latest,
      true,
    );
    const visit = (node) => {
      if (ts.isFunctionDeclaration(node) && names.has(node.name?.text)) {
        functions.push(node.getText(ast));
      }
      ts.forEachChild(node, visit);
    };
    visit(ast);
  }
  assert.equal(functions.length, names.size);
  const state = {
    page: 1,
    page_size: 50,
    total: 101,
    has_more: true,
    loading: false,
  };
  const current = { id: 51, content: { message: [] } };
  const records = { session: [current] };
  const container = {
    scrollHeight: 1000,
    clientHeight: 400,
    scrollTop: 0,
    querySelector: () => null,
  };
  const requests = [];
  const context = vm.createContext({
    currSessionId: { value: "session" },
    activeSessionPagination: { value: state },
    activeMessages: { value: records.session },
    messagesContainer: { value: container },
    suppressAutoScroll: { value: false },
    LOAD_EARLIER_SCROLL_THRESHOLD: 120,
    CSS: { escape: (value) => value },
    nextTick: async () => {},
    paginationBySession: { session: state },
    messagesBySession: records,
    sessionLoadEpochs: { session: 1 },
    console: { error: () => {} },
    normalizeHistoryRecord: (record) => record,
    attachThreads: () => {},
    resolveRecordMedia: async () => {},
    chatApi: {
      getSession: (sessionId, params) =>
        new Promise((resolve, reject) => {
          requests.push({ sessionId, params, resolve, reject });
        }),
    },
  });
  vm.runInContext(ts.transpile(functions.join("\n")), context);
  context.maybeLoadEarlierOnScroll(container);
  assert.equal(requests.length, 1);
  assert.equal(state.loading, true);
  for (let i = 0; i < 10; i++) context.maybeLoadEarlierOnScroll(container);
  assert.equal(requests.length, 1, "pending requests must be deduplicated");
  requests[0].reject(new Error("Network Error"));
  await new Promise(setImmediate);
  assert.equal(state.error, "Network Error");
  assert.equal(state.loading, false);
  assert.equal(state.page, 1);
  assert.deepEqual(records.session, [current]);
  for (let i = 0; i < 10; i++) context.maybeLoadEarlierOnScroll(container);
  assert.equal(
    requests.length,
    1,
    "scroll events must not retry a failed page",
  );

  const retry = context.retryCurrentSessionLoad();
  assert.equal(requests.length, 2);
  assert.equal(
    requests[1].params.page,
    2,
    "retry must request the failed page again",
  );
  assert.equal(state.error, undefined);
  context.maybeLoadEarlierOnScroll(container);
  assert.equal(requests.length, 2);
  requests[1].resolve({
    data: {
      status: "ok",
      data: {
        history: [{ id: 1, content: { message: [] } }],
        page: 2,
        total: 101,
        has_more: true,
      },
    },
  });
  await retry;
  assert.equal(state.page, 2);
  assert.equal(state.error, undefined);
  assert.equal(records.session.length, 2);
  context.maybeLoadEarlierOnScroll(container);
  assert.equal(
    requests.length,
    3,
    "successful retry must restore automatic pagination",
  );
  requests[2].reject(new Error("Network Error"));
  await new Promise(setImmediate);
});

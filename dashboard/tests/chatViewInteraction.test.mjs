import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { computed, reactive, ref } from "vue";

for (const reply of [false, true]) {
  test(`view actions preserve the source message and refresh sessions only for a saved reply: ${reply}`, async () => {
    let sendFrame;
    let finish;
    let action;
    let refreshes = 0;
    let scrolls = 0;
    const requests = [];
    const encoder = new TextEncoder();
    const response = new Response(
      new ReadableStream({
        start(controller) {
          sendFrame = (payload) =>
            controller.enqueue(
              encoder.encode(`data: ${JSON.stringify(payload)}\n\n`),
            );
          finish = () => controller.close();
        },
      }),
      { headers: { "content-type": "text/event-stream" } },
    );
    const context = vm.createContext({
      exports: {},
      reactive,
      ref,
      computed,
      provide: (_key, handler) => {
        action = handler;
      },
      onBeforeUnmount() {},
      useI18n: () => ({ locale: ref("zh-CN") }),
      viewActionKey: Symbol(),
      fetchWithAuth: async (url) => {
        requests.push(url);
        return response;
      },
      TextDecoder,
      console,
    });
    for (const path of [
      "../src/utils/chatViews.ts",
      "../src/composables/useMessages.ts",
    ]) {
      const source = readFileSync(new URL(path, import.meta.url), "utf8");
      const ast = ts.createSourceFile(
        "source.ts",
        source,
        ts.ScriptTarget.Latest,
        true,
      );
      const code = ast.statements
        .filter(
          (node) =>
            !ts.isImportDeclaration(node) &&
            !(
              ts.isVariableStatement(node) &&
              node.getText(ast).includes('Symbol("chat-view-action")')
            ),
        )
        .map((node) => node.getText(ast))
        .join("\n");
      vm.runInContext(
        ts.transpile(code, { module: ts.ModuleKind.CommonJS }),
        context,
      );
    }
    const messages = context.exports.useMessages({
      currentSessionId: ref("session"),
      onSessionsChanged: () => {
        refreshes++;
      },
      onStreamUpdate: () => {
        scrolls++;
      },
    });
    messages.messagesBySession.session = [
      {
        id: "original",
        created_at: "2026-11-16T01:00:00Z",
        content: {
          type: "bot",
          message: [{ type: "view", id: "reading" }],
          agentStats: { duration: 3 },
        },
      },
    ];
    const original = messages.messagesBySession.session[0];
    const before = JSON.stringify(original);
    const pending = action("reading", {
      interaction_id: "click-1",
      action_id: "reading:set_read",
      expected_revision: 1,
      data: {},
    });
    assert.equal(messages.isSessionRunning("session"), false);
    sendFrame({ type: "run_started", data: { run_id: "action-run" } });
    sendFrame({
      type: "ui_action_result",
      data: { snapshot: { revision: 2, data: { read: true } } },
    });
    assert.equal((await pending).snapshot.revision, 2);
    assert.equal(messages.isSessionRunning("session"), false);
    assert.equal(messages.isMessageStreaming(original, 0), false);
    assert.equal(scrolls, 0);
    if (reply) {
      sendFrame({ type: "plain", data: "A new reply", streaming: true });
      await new Promise(setImmediate);
      const records = messages.messagesBySession.session;
      assert.equal(records.length, 2);
      assert.equal(messages.isSessionRunning("session"), true);
      assert.equal(messages.isMessageStreaming(original, 0), false);
      assert.equal(messages.isMessageStreaming(records[1], 1), true);
      sendFrame({ type: "message_saved", data: { id: "saved-reply" } });
    }
    sendFrame({ type: "end" });
    finish();
    await new Promise(setImmediate);
    assert.equal(refreshes, reply ? 1 : 0);
    assert.equal(messages.isSessionRunning("session"), false);
    assert.equal(messages.isMessageStreaming(original, 0), false);
    assert.equal(JSON.stringify(original), before);
    assert.deepEqual(requests, ["/api/v1/chat/views/reading/actions"]);
    if (!reply) {
      assert.equal(scrolls, 0);
      assert.equal(messages.messagesBySession.session.length, 1);
    }
  });
}

test("message list uses the specific streaming message even when another request is active", () => {
  const source = readFileSync(
    new URL("../src/components/chat/ChatMessageList.vue", import.meta.url),
    "utf8",
  );
  const script = source
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const ast = ts.createSourceFile(
    "component.ts",
    script,
    ts.ScriptTarget.Latest,
    true,
  );
  const predicate = ast.statements.find(
    (node) =>
      ts.isFunctionDeclaration(node) &&
      node.name?.text === "isMessageStreaming",
  );
  const original = { id: "original" };
  const reply = { id: "reply" };
  const props = {
    messages: [original],
    isStreaming: true,
    isMessageStreaming: () => false,
  };
  const context = vm.createContext({ props, isUserMessage: () => false });
  vm.runInContext(ts.transpile(predicate.getText(ast)), context);
  assert.equal(context.isMessageStreaming(original, 0), false);
  props.messages.push(reply);
  props.isMessageStreaming = (message) => message === reply;
  assert.equal(context.isMessageStreaming(original, 0), false);
  assert.equal(context.isMessageStreaming(reply, 1), true);
});

test("thread view callbacks keep the original message idle and do not scroll for an acknowledgement", () => {
  const source = readFileSync(
    new URL("../src/components/chat/ThreadPanel.vue", import.meta.url),
    "utf8",
  );
  const script = source
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const ast = ts.createSourceFile(
    "thread.ts",
    script,
    ts.ScriptTarget.Latest,
    true,
  );
  const registration = ast.statements.find(
    (node) =>
      ts.isExpressionStatement(node) &&
      ts.isCallExpression(node.expression) &&
      node.expression.expression.getText(ast) === "provide" &&
      node.expression.arguments[0].getText(ast) === "viewActionKey",
  );
  const original = { id: "original", content: { agentStats: { duration: 3 } } };
  const messages = ref([original]);
  const sending = ref(false);
  const activeBotRecord = ref(null);
  let action;
  let payload;
  let end;
  let scrolls = 0;
  const context = vm.createContext({
    ref,
    messages,
    sending,
    activeBotRecord,
    viewActionKey: Symbol(),
    provide: (_key, handler) => {
      action = handler;
    },
    streamViewAction: (_id, _input, onPayload, onEnd) => {
      payload = onPayload;
      end = onEnd;
    },
    processPayload() {},
    scrollToBottom: () => {
      scrolls++;
    },
  });
  vm.runInContext(ts.transpile(registration.getText(ast)), context);
  action("reading", { interaction_id: "click-1" });
  assert.notEqual(activeBotRecord.value, messages.value[0]);
  payload({ type: "run_started" });
  payload({ type: "end" });
  end();
  assert.equal(scrolls, 0);
  assert.equal(messages.value.length, 1);
  assert.equal(activeBotRecord.value, null);
  assert.equal(sending.value, false);

  action("reading", { interaction_id: "click-2" });
  payload({ type: "plain", data: "New reply" });
  assert.equal(messages.value.length, 2);
  assert.equal(activeBotRecord.value, messages.value[1]);
  assert.notEqual(activeBotRecord.value, messages.value[0]);
  assert.equal(scrolls, 1);
  end();
  assert.equal(original.content.agentStats.duration, 3);
});

test("views remain outside collapsed work before and after restoring tool history", () => {
  const source = readFileSync(
    new URL(
      "../src/components/chat/message_list_comps/MessageWork.vue",
      import.meta.url,
    ),
    "utf8",
  );
  const script = source
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const ast = ts.createSourceFile(
    "work.ts",
    script,
    ts.ScriptTarget.Latest,
    true,
  );
  const names = new Set(["workBlocks", "processBlocks", "finalBlocks"]);
  const declarations = ast.statements.filter(
    (node) =>
      ts.isVariableStatement(node) &&
      node.declarationList.declarations.some((decl) =>
        names.has(decl.name.getText(ast)),
      ),
  );
  const view = { type: "view", id: "reading" };
  const thinking = {
    kind: "thinking",
    parts: [{ type: "think", think: "Open a list" }],
  };
  const tools = {
    kind: "thinking",
    parts: [{ type: "tool_call", tool_calls: [{ id: "tool-1" }] }],
  };
  const props = reactive({
    isUser: false,
    blocks: [thinking, { kind: "content", parts: [view] }],
  });
  const context = vm.createContext({ props, computed, exports: {} });
  vm.runInContext(
    ts.transpile(
      declarations.map((node) => node.getText(ast)).join("\n") +
        "\nexports.process = processBlocks; exports.final = finalBlocks;",
      { target: ts.ScriptTarget.ES2022 },
    ),
    context,
  );
  assert.equal(context.exports.final.value[0].parts[0].id, "reading");
  props.blocks.push(tools);
  const original = JSON.stringify(props.blocks);
  assert.equal(context.exports.process.value.length, 1);
  assert.equal(context.exports.process.value[0].parts.length, 2);
  assert.equal(context.exports.final.value[0].parts[0].id, "reading");
  assert.equal(JSON.stringify(props.blocks), original);
  props.blocks.push({
    kind: "content",
    parts: [{ type: "plain", text: "Your list is ready." }],
  });
  assert.deepEqual(JSON.parse(JSON.stringify(context.exports.final.value)), [
    {
      kind: "content",
      parts: [view, { type: "plain", text: "Your list is ready." }],
    },
  ]);
  props.blocks = JSON.parse(JSON.stringify(props.blocks));
  assert.equal(context.exports.final.value[0].parts[0].id, "reading");
  assert.ok(
    context.exports.process.value.every((block) =>
      block.parts.every((part) => part.type !== "view"),
    ),
  );
  props.isUser = true;
  assert.equal(context.exports.process.value.length, 0);
  assert.equal(context.exports.final.value.length, props.blocks.length);
});

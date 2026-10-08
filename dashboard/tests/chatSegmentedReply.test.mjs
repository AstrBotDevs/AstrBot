import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { reactive } from "vue";

const messages = readFileSync(
  new URL("../src/composables/useMessages.ts", import.meta.url),
  "utf8",
);
const thread = readFileSync(
  new URL("../src/components/chat/ThreadPanel.vue", import.meta.url),
  "utf8",
)
  .split('<script setup lang="ts">')[1]
  .split("</script>")[0];
const names = new Set([
  "processStreamPayload",
  "processPayload",
  "appendPlain",
  "markMessageStarted",
  "hasPlainText",
  "payloadText",
  "normalizeHistoryRecord",
  "normalizeMessageParts",
  "normalizePartsInternal",
  "extractReasoningText",
  "ensureBotRecordVisible",
  "regenerateMessage",
  "buildChatRequestFlags",
  "messageContent",
  "createLocalExchange",
  "isSessionRunning",
  "stripUploadOnlyFields",
]);
const functions = [];
for (const source of [messages, thread]) {
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
const compiledFunctions = ts.transpile(functions.join("\n"));

for (const { accepted, segmented } of [
  { accepted: true, segmented: true },
  { accepted: true, segmented: false },
  { accepted: false },
]) {
  test(`regeneration: ${
    accepted
      ? segmented
        ? "segmented reply"
        : "single reply"
      : "rejected request"
  }`, async () => {
    const user = {
      id: 1,
      llm_checkpoint_id: "old",
      content: { type: "user", message: [] },
    };
    const unrelated = {
      id: 2,
      llm_checkpoint_id: "earlier",
      content: {
        type: "bot",
        message: [{ type: "plain", text: "Earlier turn" }],
      },
    };
    const records = reactive([
      unrelated,
      user,
      ...[10, 11, 12].map((id) => ({
        id,
        llm_checkpoint_id: "old",
        content: {
          type: "bot",
          message: [{ type: "plain", text: `Old ${id}` }],
        },
      })),
    ]);
    const target = records[records.length - 1];
    const context = vm.createContext({
      exports: {},
      reactive,
      AbortController,
      messagesBySession: reactive({ session: records }),
      activeConnections: {},
      options: {},
      console: { error() {} },
      chatApi: {
        regenerateMessageUrl: (_session, id) => {
          assert.equal(id, 12);
          return "/regenerate";
        },
      },
      fetchWithAuth: async () => ({
        ok: accepted,
        status: accepted ? 200 : 400,
        body: {},
        headers: { get: () => "text/event-stream" },
      }),
      readSseStream: async (_body, receive) => {
        assert.equal(
          context.messagesBySession.session.filter(
            (record) => record.content.type === "bot",
          ).length,
          2,
        );
        for (let index = 0; index < (segmented ? 3 : 1); index++) {
          receive({ type: "plain", data: `New ${index}`, streaming: false });
          receive({
            type: "message_saved",
            data: { id: 20 + index, llm_checkpoint_id: "new" },
          });
        }
        receive({ type: "end", data: "" });
      },
    });
    vm.runInContext(compiledFunctions, context);
    await context.regenerateMessage("session", target);
    const bots = context.messagesBySession.session.filter(
      (record) => record.content.type === "bot",
    );
    assert.deepEqual(
      bots.map((record) => record.id),
      accepted ? (segmented ? [2, 20, 21, 22] : [2, 20]) : [2, 10, 11, 12],
    );
    assert.ok(
      context.messagesBySession.session.some((record) => record.id === user.id),
    );
    assert.equal(Object.keys(context.activeConnections).length, 0);
  });
}

for (const resume of [false, true]) {
  test(`queued reply follows all segments${
    resume ? " after a snapshot" : ""
  }`, () => {
    const records = reactive([
      { content: { type: "user", message: [] } },
      { content: { type: "bot", message: [] } },
    ]);
    const first = {
      sessionId: "session",
      messageId: "a",
      botRecord: records[1],
      userRecord: records[0],
      botVisible: true,
    };
    const anchors = new WeakMap();
    const context = vm.createContext({
      exports: {},
      reactive,
      messagesBySession: reactive({ session: records }),
      activeConnections: reactive({ a: first }),
      loadedSessions: {},
      deferredBotAnchors: anchors,
      resolveRecordMedia: async () => {},
    });
    vm.runInContext(compiledFunctions, context);
    const receiveFirst = (type, data) =>
      context.processStreamPayload(
        first.botRecord,
        { type, data, streaming: false },
        first.userRecord,
        first,
      );
    receiveFirst("plain", "A1");
    receiveFirst("message_saved", {
      id: 10,
      llm_checkpoint_id: "checkpoint-a",
    });
    const next = context.createLocalExchange({
      sessionId: "session",
      messageId: "b",
      parts: [{ type: "plain", text: "Question B" }],
    });
    const second = {
      ...next,
      sessionId: "session",
      messageId: "b",
      botVisible: false,
      deferredBeforeBot: anchors.get(next.botRecord),
    };
    context.activeConnections.b = second;
    receiveFirst("plain", "A2");
    receiveFirst("message_saved", {
      id: 11,
      llm_checkpoint_id: "checkpoint-a",
    });
    if (resume) {
      receiveFirst("run_snapshot", {
        run_id: "a",
        llm_checkpoint_id: "checkpoint-a",
        status: "running",
        messages: JSON.parse(
          JSON.stringify(
            context.messagesBySession.session.filter(
              (record) => record.content.type === "bot",
            ),
          ),
        ),
      });
    }
    context.processStreamPayload(
      next.botRecord,
      { type: "run_started", data: { run_id: "b" } },
      next.userRecord,
      second,
    );
    receiveFirst("plain", "A3");
    receiveFirst("message_saved", {
      id: 12,
      llm_checkpoint_id: "checkpoint-a",
    });
    receiveFirst("end", "");
    delete context.activeConnections.a;
    context.processStreamPayload(
      next.botRecord,
      { type: "plain", data: "B reply", streaming: false },
      next.userRecord,
      second,
    );
    const botText = context.messagesBySession.session
      .filter((record) => record.content.type === "bot")
      .map((record) =>
        record.content.message.map((part) => part.text).join(""),
      );
    assert.deepEqual(botText, ["A1", "A2", "A3", "B reply"]);
  });
}

for (const handler of ["sse", "thread"]) {
  for (const mediaType of ["image", "file"]) {
    test(`${handler}: text and ${mediaType} share a message until complete`, async () => {
      const bot = { content: { type: "bot", message: [] } };
      const user = { content: { type: "user", message: [] } };
      const records = reactive([user, bot]);
      const connection = {
        sessionId: "session",
        messageId: "run",
        botRecord: records[1],
        userRecord: records[0],
      };
      const context = vm.createContext({
        exports: {},
        reactive,
        messagesBySession: { session: records },
        messages: { value: records },
        activeConnections: { run: connection },
        resolvePartMedia: async () => {},
      });
      vm.runInContext(compiledFunctions, context);
      for (const payload of [
        { type: "plain", data: "Caption.", streaming: false },
        {
          type: mediaType,
          data:
            mediaType === "file"
              ? "[FILE]stored.txt|report.txt"
              : "[IMAGE]result.png",
          streaming: false,
        },
        { type: "complete", data: "", streaming: false },
        {
          type: "message_saved",
          data: { id: 1, llm_checkpoint_id: "checkpoint" },
        },
        { type: "plain", data: "Next message.", streaming: false },
        { type: "complete", data: "", streaming: false },
        {
          type: "message_saved",
          data: { id: 2, llm_checkpoint_id: "checkpoint" },
        },
      ]) {
        if (handler === "thread")
          context.processPayload(connection, user, payload);
        else context.processStreamPayload(bot, payload, user, connection);
      }
      await Promise.resolve();
      const bots = records.filter((record) => record.content.type === "bot");
      assert.deepEqual(
        bots.map((record) => record.id),
        [1, 2],
      );
      assert.deepEqual(
        bots[0].content.message.map((part) => part.type),
        ["plain", mediaType],
      );
      assert.equal(bots[1].content.message[0].text, "Next message.");
    });
  }
  for (const scenario of [
    {
      name: "non-streaming segments become separate messages, including repeated segments",
      chunks: ["First.", "Second.", "Second.", "Third."],
      streaming: false,
    },
    {
      name: "a single non-streaming reply remains intact",
      chunks: ["Complete reply."],
      streaming: false,
    },
    {
      name: "streaming deltas and the final full text do not duplicate content",
      chunks: ["First.", "Second.", "Third."],
      streaming: true,
    },
  ]) {
    test(`${handler}: ${scenario.name}`, () => {
      const bot = { content: { type: "bot", message: [], isLoading: true } };
      const user = { content: { type: "user", message: [] } };
      const records = [user, bot];
      const connection = {
        botRecord: bot,
        userRecord: user,
        sessionId: "session",
        messageId: "run",
        messageSaved: false,
      };
      const context = vm.createContext({
        exports: {},
        reactive: (value) => value,
        messagesBySession: { session: records },
        messages: { value: records },
        activeConnections: { run: connection },
        resolveRecordMedia: async () => {},
      });
      vm.runInContext(compiledFunctions, context);
      const getBots = () =>
        (handler === "thread"
          ? context.messages.value
          : context.messagesBySession.session
        ).filter((record) => record.content.type === "bot");
      const receive = (payload) => {
        if (handler === "thread") {
          context.processPayload(connection, user, payload);
        } else {
          context.processStreamPayload(bot, payload, user, connection);
        }
      };
      let expected = "";
      for (const [index, data] of scenario.chunks.entries()) {
        receive({ type: "plain", data, streaming: scenario.streaming });
        assert.equal(getBots().length, scenario.streaming ? 1 : index + 1);
        if (!scenario.streaming) {
          receive({
            type: "message_saved",
            data: { id: index + 1, llm_checkpoint_id: "checkpoint" },
          });
          assert.deepEqual(
            getBots().map((record) => record.id),
            scenario.chunks.slice(0, index + 1).map((_, i) => i + 1),
          );
        }
        expected += data;
        assert.deepEqual(
          JSON.parse(
            JSON.stringify(
              getBots().flatMap((record) => record.content.message),
            ),
          ),
          scenario.streaming
            ? [{ type: "plain", text: expected }]
            : scenario.chunks
                .slice(0, index + 1)
                .map((text) => ({ type: "plain", text })),
        );
        if (handler !== "thread" && index === 1) {
          const snapshotMessages = JSON.parse(JSON.stringify(getBots()));
          const snapshot = {
            type: "run_snapshot",
            data: {
              run_id: "run",
              status: "running",
              llm_checkpoint_id: "checkpoint",
              messages: snapshotMessages,
            },
          };
          receive(snapshot);
          receive(snapshot);
          assert.equal(
            getBots().length,
            scenario.streaming ? 1 : 2,
            "reconnection must not duplicate saved messages",
          );
        }
      }
      if (scenario.streaming) {
        receive({ type: "complete", data: expected, streaming: true });
      }
      receive({ type: "end", data: "", streaming: false });
      assert.equal(
        getBots()
          .flatMap((record) => record.content.message)
          .map((part) => part.text)
          .join(""),
        expected,
      );
      assert.ok(getBots().every((record) => !record.content.isLoading));
      assert.equal(
        getBots().length,
        scenario.streaming ? 1 : scenario.chunks.length,
        "end events must not add empty message bubbles",
      );
    });
  }
}

test("websocket: legacy event envelopes preserve separate reply messages", () => {
  const bot = { content: { type: "bot", message: [] } };
  const records = reactive([bot]);
  const connection = {
    sessionId: "session",
    messageId: "run",
    botRecord: records[0],
  };
  const context = vm.createContext({
    exports: {},
    reactive,
    messagesBySession: { session: records },
    activeConnections: { run: connection },
  });
  vm.runInContext(compiledFunctions, context);
  for (const [index, text] of ["First.", "Second."].entries()) {
    context.processStreamPayload(
      bot,
      {
        ct: "chat",
        t: "plain",
        data: text,
        streaming: false,
      },
      undefined,
      connection,
    );
    context.processStreamPayload(
      bot,
      {
        ct: "chat",
        t: "message_saved",
        data: { id: index + 1 },
      },
      undefined,
      connection,
    );
  }
  assert.deepEqual(
    records.map((record) => ({
      id: record.id,
      text: record.content.message[0].text,
    })),
    [
      { id: 1, text: "First." },
      { id: 2, text: "Second." },
    ],
  );
});

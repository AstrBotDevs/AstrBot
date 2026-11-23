import assert from "node:assert/strict";
import { flushPromises } from "@vue/test-utils";
import { test, vi } from "vitest";
import { messageBlocks } from "../src/composables/useMessages.ts";
import { historyResponse, mountMessages } from "./helpers/messages.mjs";
import { createSseStream } from "./helpers/streams.mjs";

test("history pages retain reasoning boundaries and complete tool results", async () => {
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
  const h = mountMessages();
  h.getSession.mockResolvedValue(historyResponse([{ id: 1, content: { type: "bot", message: parts } }]));
  await h.messages.loadSessionMessages("session", false);
  const record = h.messages.activeMessages.value[0];
  assert.deepEqual(JSON.parse(JSON.stringify(record.content.message)), parts);
  const blocks = messageBlocks(record.content);
  assert.deepEqual(JSON.parse(JSON.stringify(blocks)), [
    { kind: "thinking", parts: parts.slice(0, 2) },
    { kind: "content", parts: parts.slice(2, 3) },
    { kind: "thinking", parts: parts.slice(3, 4) },
    { kind: "content", parts: parts.slice(4) },
  ]);
});

test("late initial history cannot overwrite a newly sent local exchange", async () => {
  const h = mountMessages();
  let finishHistory;
  h.getSession.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finishHistory = resolve;
      }),
  );
  const pending = h.messages.loadSessionMessages("session", false);
  const stream = createSseStream();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(stream.response));
  const exchange = h.messages.createLocalExchange({
    sessionId: "session",
    messageId: "new",
    parts: [{ type: "plain", text: "New question" }],
  });
  h.messages.sendMessageStream({ sessionId: "session", messageId: "new", parts: [], transport: "sse", ...exchange });
  stream.send({ type: "plain", data: "Live answer", streaming: true });
  await flushPromises();
  finishHistory(
    historyResponse([{ id: "older", content: { type: "bot", message: [{ type: "plain", text: "Old answer" }] } }]),
  );
  await pending;
  const records = h.messages.messagesBySession.session;
  assert.equal(records.includes(exchange.userRecord), true);
  assert.equal(records.includes(exchange.botRecord), true);
  assert.equal(exchange.botRecord.content.message[0].text, "Live answer");
  stream.send({ type: "end" });
  stream.close();
  await flushPromises();
});

test("history loading indicators remain owned by their session when tabs finish out of order", async () => {
  const h = mountMessages();
  const pending = new Map();
  h.getSession.mockImplementation((id) => new Promise((resolve) => pending.set(id, resolve)));
  h.currentSessionId.value = "A";
  const first = h.messages.loadSessionMessages("A", false);
  assert.equal(h.messages.loadingMessages.value, true);
  h.currentSessionId.value = "B";
  const second = h.messages.loadSessionMessages("B", false);
  assert.equal(h.messages.loadingMessages.value, true);
  pending.get("B")(historyResponse());
  await second;
  assert.equal(h.messages.loadingMessages.value, false);
  h.currentSessionId.value = "A";
  assert.equal(h.messages.loadingMessages.value, true);
  pending.get("A")(historyResponse());
  await first;
  assert.equal(h.messages.loadingMessages.value, false);
});

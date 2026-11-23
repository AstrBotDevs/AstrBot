import assert from "node:assert/strict";
import { flushPromises } from "@vue/test-utils";
import { test, vi } from "vitest";
import { appendError, messageBlocks, normalizeMessageParts } from "../src/composables/useMessages.ts";
import { historyResponse, mountMessages } from "./helpers/messages.mjs";
import { createSseStream, TestWebSocket } from "./helpers/streams.mjs";

for (const transport of ["sse", "websocket"]) {
  test(`${transport} retains error identity and partial output through completion and history`, async () => {
    const h = mountMessages();
    const stream = createSseStream();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(stream.response));
    TestWebSocket.instances.length = 0;
    vi.stubGlobal("WebSocket", TestWebSocket);
    const exchange = h.messages.createLocalExchange({ sessionId: "session", messageId: "message", parts: [] });
    h.messages.sendMessageStream({ sessionId: "session", messageId: "message", parts: [], transport, ...exchange });
    const frames = [
      { type: "plain", data: "Partial answer", streaming: true },
      { type: "error", data: { code: "noProvider", message: "No available model" } },
      { type: "complete", data: "Partial answer", streaming: true },
      { type: "end" },
    ];
    if (transport === "websocket") {
      const socket = TestWebSocket.instances[0];
      socket.open();
      for (const frame of frames) socket.receive({ ...frame, ct: "chat", t: frame.type, message_id: "message" });
    } else {
      for (const frame of frames) stream.send(frame);
      stream.close();
    }
    await flushPromises();
    const expected = [
      { type: "plain", text: "Partial answer" },
      { type: "error", code: "noProvider", message: "No available model" },
    ];
    assert.deepEqual(exchange.botRecord.content.message, expected);
    assert.equal(exchange.botRecord.content.isLoading, false);
    assert.equal(h.messages.isSessionRunning("session"), false);
    assert.deepEqual(normalizeMessageParts(JSON.parse(JSON.stringify(expected))), expected);
    h.getSession.mockResolvedValue(historyResponse([{ id: 1, content: { type: "bot", message: expected } }]));
    await h.messages.loadSessionMessages("session", false);
    const restored = h.messages.activeMessages.value[0];
    assert.deepEqual(restored.content.message, expected);
    assert.equal(messageBlocks(restored.content)[0].kind, "content");
  });
}

test("legacy error events and unknown error codes remain error parts", async () => {
  const h = mountMessages();
  const stream = createSseStream();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(stream.response));
  const exchange = h.messages.createLocalExchange({ sessionId: "session", messageId: "legacy", parts: [] });
  h.messages.sendMessageStream({ sessionId: "session", messageId: "legacy", parts: [], transport: "sse", ...exchange });
  stream.send({ type: "error", data: "Legacy failure" });
  stream.send({ type: "error", data: { code: "future_error", message: "Unknown failure" } });
  stream.send({ type: "end" });
  stream.close();
  await flushPromises();
  appendError(exchange.botRecord, new Error("Disconnected"), "connection_error");
  assert.deepEqual(exchange.botRecord.content.message, [
    { type: "error", code: "agent_error", message: "Legacy failure" },
    { type: "error", code: "future_error", message: "Unknown failure" },
    { type: "error", code: "connection_error", message: "Disconnected" },
  ]);
});

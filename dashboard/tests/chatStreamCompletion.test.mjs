import assert from "node:assert/strict";
import { flushPromises } from "@vue/test-utils";
import { test, vi } from "vitest";
import { mountMessages } from "./helpers/messages.mjs";
import { createSseStream, TestWebSocket } from "./helpers/streams.mjs";

for (const scenario of ["missing end", "complete", "aborted", "another run"]) {
  test(`SSE completion reconciles only an interrupted idle session: ${scenario}`, async () => {
    const h = mountMessages();
    const stream = createSseStream();
    const other = createSseStream();
    const fetch = vi.fn().mockResolvedValueOnce(stream.response).mockResolvedValueOnce(other.response);
    vi.stubGlobal("fetch", fetch);
    const send = (messageId) => {
      const exchange = h.messages.createLocalExchange({ sessionId: "session", messageId, parts: [] });
      h.messages.sendMessageStream({ sessionId: "session", messageId, parts: [], transport: "sse", ...exchange });
    };
    send("message");
    await flushPromises();
    assert.equal(h.messages.isSessionRunning("session"), true);
    if (scenario === "complete") stream.send({ type: "end" });
    if (scenario === "aborted") {
      h.messages.cleanupConnections();
      assert.equal(fetch.mock.calls[0][1].signal.aborted, true);
      await flushPromises();
      assert.equal(stream.stats.cancelled, 1);
      assert.equal(stream.body.locked, false);
    }
    if (scenario === "another run") send("other");
    stream.close();
    await flushPromises();
    assert.equal(h.getSession.mock.calls.length, scenario === "missing end" ? 1 : 0);
    if (scenario === "missing end")
      assert.deepEqual(h.getSession.mock.calls[0], ["session", { page: 1, page_size: 50 }]);
    assert.equal(h.messages.isSessionRunning("session"), scenario === "another run");
    if (scenario === "another run") {
      other.send({ type: "end" });
      other.close();
      await flushPromises();
      assert.equal(h.messages.isSessionRunning("session"), false);
      assert.equal(h.getSession.mock.calls.length, 0);
    }
  });
}

test("a CRLF terminal frame completes SSE and releases its reader without waiting for socket EOF", async () => {
  const h = mountMessages();
  const stream = createSseStream({ newline: "\r\n" });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(stream.response));
  const exchange = h.messages.createLocalExchange({ sessionId: "session", messageId: "terminal", parts: [] });
  h.messages.sendMessageStream({
    sessionId: "session",
    messageId: "terminal",
    parts: [],
    transport: "sse",
    ...exchange,
  });
  stream.send({ type: "plain", data: "Finished", streaming: true });
  stream.send({ type: "end" });
  await flushPromises();
  assert.equal(h.messages.isSessionRunning("session"), false);
  assert.equal(exchange.botRecord.content.message[0].text, "Finished");
  assert.equal(stream.body.locked, false);
  assert.equal(stream.stats.cancelled, 1);
  assert.equal(h.getSession.mock.calls.length, 0);
});

test("unknown or cross-session WebSocket message IDs cannot mutate another active turn", async () => {
  const h = mountMessages();
  TestWebSocket.instances.length = 0;
  vi.stubGlobal("WebSocket", TestWebSocket);
  const send = (sessionId, messageId) => {
    const exchange = h.messages.createLocalExchange({ sessionId, messageId, parts: [] });
    h.messages.sendMessageStream({ sessionId, messageId, parts: [], transport: "websocket", ...exchange });
    return exchange.botRecord;
  };
  const first = send("A", "a");
  const second = send("B", "b");
  const [socketA, socketB] = TestWebSocket.instances;
  socketA.open();
  socketB.open();
  const frame = (message_id) => ({ ct: "chat", t: "plain", message_id, data: "foreign", streaming: true });
  socketA.receive(frame("unknown-old-id"));
  socketA.receive(frame("b"));
  socketB.receive(frame("a"));
  assert.deepEqual(first.content.message, []);
  assert.deepEqual(second.content.message, []);
  socketA.receive({ ...frame("a"), data: "A reply" });
  socketB.receive({ ...frame("b"), data: "B reply" });
  assert.equal(first.content.message[0].text, "A reply");
  assert.equal(second.content.message[0].text, "B reply");
  socketA.receive({ ct: "chat", t: "end", message_id: "a" });
  assert.equal(h.messages.isSessionRunning("A"), false);
  assert.equal(h.messages.isSessionRunning("B"), true);
  socketB.receive({ ct: "chat", t: "end", message_id: "b" });
  assert.equal(h.messages.isSessionRunning("B"), false);
});

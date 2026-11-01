import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../../astrbot/dashboard/plugin_page_bridge.js", import.meta.url), "utf8");

test("SSE terminal states notify once and unsubscribe stays silent", async () => {
  const sent = [];
  let receive;
  const parent = { postMessage: (message) => sent.push(message) };
  const window = {
    location: { origin: "https://example.com" },
    parent,
    addEventListener: (type, handler) => { if (type === "message") receive = handler; },
  };
  runInNewContext(source, { window });
  const deliver = (message) => receive({
    source: parent,
    origin: window.location.origin,
    data: { channel: "astrbot-plugin-page", ...message },
  });
  const subscribe = async (handlers) => {
    const promise = window.AstrBotPluginView.subscribeSSE("events", handlers);
    const request = sent.at(-1);
    deliver({ kind: "response", requestId: request.requestId, ok: true });
    return promise;
  };
  const calls = [];
  const handlers = {
    onOpen: () => calls.push("open"),
    onClose: () => calls.push("close"),
    onError: () => calls.push("error"),
  };
  const closedId = await subscribe(handlers);
  deliver({ kind: "sse_state", subscriptionId: closedId, state: "open" });
  deliver({ kind: "sse_state", subscriptionId: closedId, state: "closed" });
  deliver({ kind: "sse_state", subscriptionId: closedId, state: "error" });
  const errorId = await subscribe(handlers);
  deliver({ kind: "sse_state", subscriptionId: errorId, state: "error" });
  deliver({ kind: "sse_state", subscriptionId: errorId, state: "closed" });
  const cancelledId = await subscribe(handlers);
  const unsubscribe = window.AstrBotPluginView.unsubscribeSSE(cancelledId);
  const request = sent.at(-1);
  deliver({ kind: "sse_state", subscriptionId: cancelledId, state: "closed" });
  deliver({ kind: "response", requestId: request.requestId, ok: true });
  await unsubscribe;
  assert.deepEqual(calls, ["open", "close", "error"]);
});

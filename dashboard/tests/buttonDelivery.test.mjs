import assert from "node:assert/strict";
import test from "node:test";
import { messagesHarness } from "./helpers/messagesHarness.mjs";

for (const [name, fail] of [
  [
    "a rejected request",
    (request) => request.resolve({ ok: false, status: 503 }),
  ],
  ["a request without a body", (request) => request.resolve({ ok: true })],
]) {
  test(`${name} clears the remembered choice for a retry`, async () => {
    const h = messagesHarness();
    try {
      h.choices.rememberChosenCallback("keep");
      h.choices.rememberChosenCallback("retry");
      h.messages.sendButtonInteraction({
        sessionId: "one",
        sourceMessageId: 1,
        callbackData: "retry",
      });
      const body = JSON.parse(h.requests[0].request.body);
      assert.equal(body.message[0].type, "button_interaction");
      assert.equal(body.message[0].callback_data, "retry");
      fail(h.requests[0]);
      await new Promise((resolve) => setImmediate(resolve));
      assert.deepEqual([...h.choices.chosenCallbacks.value], ["keep"]);
      assert.deepEqual(
        JSON.parse(h.storage.get("chat.chosenButtonCallbacks")),
        ["keep"],
      );
    } finally {
      h.stop();
    }
  });
}

import assert from "node:assert/strict";
import test from "node:test";
import { loadSource } from "./helpers/vueHarness.mjs";
import { messagesHarness } from "./helpers/messagesHarness.mjs";

const card = (key, extra = {}) => ({
  type: "actionrow",
  title: "Approve",
  single_use: true,
  buttons: [
    {
      id: "approve",
      label: "Allow",
      action: { type: "callback", callback_data: key },
    },
  ],
  ...extra,
});

test("a streamed remaining time becomes a local deadline once", () => {
  const h = messagesHarness();
  try {
    const before = Date.now() / 1000;
    // The server clock is far off: only expires_in counts.
    const [part] = h.api.normalizeMessageParts([
      card("skew", { expires_at: 100, expires_in: 60 }),
    ]);
    assert.ok(part.expires_at >= before + 60);
    assert.ok(part.expires_at <= Date.now() / 1000 + 60);
    assert.equal("expires_in" in part, false);
    h.choices.approvalNow.value = Date.now();
    assert.equal(h.choices.approvalCardState(part).expired, false);
    const [again] = h.api.normalizeMessageParts([part]);
    assert.equal(again.expires_at, part.expires_at);
    // History keeps only expires_at, which is left as it is.
    const [stored] = h.api.normalizeMessageParts([
      card("old", { expires_at: 100 }),
    ]);
    assert.equal(stored.expires_at, 100);
  } finally {
    h.stop();
  }
});

test("card state: choices, expiry and outcomes lock it; only titled single-use rows dock", () => {
  const h = messagesHarness();
  try {
    const { approvalCardState } = h.choices;
    const part = card("first", { expires_at: 10 });
    h.choices.approvalNow.value = 0;
    assert.equal(approvalCardState(part).open, true);
    for (const outcome of ["approved", "rejected", "expired"]) {
      const state = approvalCardState({ ...part, outcome });
      assert.equal(state.locked, true);
      assert.equal(state.outcome, outcome);
    }
    assert.equal(approvalCardState({ ...part, title: "" }).open, false);
    h.choices.rememberChosenCallback("first");
    assert.equal(approvalCardState(part).chosen, "first");
    assert.equal(approvalCardState(part).locked, true);
    // A reusable row never locks on a choice.
    assert.equal(
      approvalCardState({ ...part, single_use: false }).locked,
      false,
    );
  } finally {
    h.stop();
  }
});

test("chosen callbacks deduplicate, keep the newest 200 and tolerate storage failures", () => {
  let fail = false;
  let saved;
  const choices = loadSource(
    new URL("../src/composables/useActionRowChoices.ts", import.meta.url),
    {},
    {
      localStorage: {
        getItem: () => '["stored", 1]',
        setItem: (_, value) => {
          if (fail) throw Error("blocked");
          saved = value;
        },
      },
    },
  );
  assert.deepEqual([...choices.chosenCallbacks.value], ["stored"]);
  for (let i = 0; i < 205; i++) choices.rememberChosenCallback(String(i));
  choices.rememberChosenCallback("10");
  assert.equal(choices.chosenCallbacks.value.length, 200);
  assert.equal(new Set(choices.chosenCallbacks.value).size, 200);
  assert.equal(choices.chosenCallbacks.value.at(-1), "10");
  assert.equal(JSON.parse(saved)[0], "5");
  fail = true;
  assert.doesNotThrow(() => choices.rememberChosenCallback("first"));
  assert.doesNotThrow(() => choices.forgetChosenCallback("first"));
  assert.equal(choices.chosenCallbacks.value.includes("first"), false);
});

for (const transport of ["sse", "websocket", "regenerate"]) {
  test(`${transport} requests carry the stored permission mode`, async () => {
    const h = messagesHarness({ permission_mode: "workspace" });
    try {
      if (transport === "regenerate")
        void h.messages.regenerateMessage("one", h.bot);
      else h.send(transport);
      await new Promise((resolve) => setImmediate(resolve));
      const payload =
        transport === "websocket"
          ? h.sockets[0].sent
          : JSON.parse(h.requests[0].request.body);
      assert.equal(payload.permission_mode, "workspace");
    } finally {
      h.stop();
    }
  });
}

test("approval waits, answers and turn interruption only affect the matching unfinished calls", async () => {
  const h = messagesHarness();
  try {
    h.send("websocket");
    for (const id of ["a", "b", "done"]) {
      h.api.upsertToolCall(h.bot, {
        id,
        finished_ts: id === "done" ? 5 : undefined,
      });
    }
    await h.emit({
      type: "actionrow",
      data: { ...card("answer"), tool_call_id: "a" },
    });
    const calls = h.bot.content.message.flatMap(
      (part) => part.tool_calls || [],
    );
    assert.deepEqual(
      calls.map((call) => call.phase),
      ["awaiting_approval", undefined, undefined],
    );
    h.messages.sendButtonInteraction({
      sessionId: "one",
      callbackData: "answer",
    });
    assert.equal(calls[0].phase, undefined);
    await h.emit({
      type: "actionrow",
      data: { ...card("late"), tool_call_id: "done" },
    });
    assert.equal(calls[2].phase, undefined);
    await h.emit({ type: "end" });
    assert.deepEqual(
      calls.map((call) => call.phase),
      ["unknown", "unknown", undefined],
    );
  } finally {
    h.stop();
  }
});

test("an approval result sets the card outcome and ends the wait without adding text", async () => {
  const h = messagesHarness();
  try {
    h.send("websocket");
    await h.emit({
      type: "plain",
      chain_type: "tool_call",
      data: JSON.stringify({ id: "call", name: "write" }),
    });
    await h.emit({
      type: "actionrow",
      data: { ...card("allow"), tool_call_id: "call", expires_in: 120 },
    });
    await h.emit({
      type: "actionrow",
      data: { ...card("other"), tool_call_id: "other" },
    });
    const [tools, row, other] = h.bot.content.message;
    assert.equal(tools.tool_calls[0].phase, "awaiting_approval");
    assert.ok(row.expires_at > Date.now() / 1000);
    await h.emit({
      type: "plain",
      chain_type: "approval_result",
      data: JSON.stringify({ tool_call_id: "call", outcome: "rejected" }),
    });
    assert.equal(row.outcome, "rejected");
    assert.equal(other.outcome, undefined);
    assert.equal(tools.tool_calls[0].phase, undefined);
    assert.equal(h.bot.content.message.length, 3);
    assert.equal(
      h.bot.content.message.some((part) => part.type === "plain"),
      false,
    );
  } finally {
    h.stop();
  }
});

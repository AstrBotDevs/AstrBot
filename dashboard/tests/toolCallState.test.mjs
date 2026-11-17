import assert from "node:assert/strict";
import test from "node:test";
import { nextTick, reactive } from "vue";
import { loadSource, mountTemplate } from "./helpers/vueHarness.mjs";
import { messagesHarness } from "./helpers/messagesHarness.mjs";

function loadToolCallCard(timers) {
  return loadSource(
    new URL(
      "../src/components/chat/message_list_comps/ToolCallCard.vue",
      import.meta.url,
    ),
    { "@/i18n/composables": { useModuleI18n: () => ({ tm: (key) => key }) } },
    {
      setInterval: (fn) => {
        timers.add(fn);
        return fn;
      },
      clearInterval: (fn) => timers.delete(fn),
    },
    true,
  ).default;
}

test("a turn ending before a call returns marks only that call interrupted", async () => {
  const h = messagesHarness();
  try {
    h.send("websocket");
    for (const call of [
      { id: "done", name: "read", ts: 1 },
      { id: "open", name: "shell", ts: 2 },
    ]) {
      await h.emit({ type: "plain", chain_type: "tool_call", data: JSON.stringify(call) });
    }
    await h.emit({
      type: "plain",
      chain_type: "tool_call_result",
      data: JSON.stringify({ id: "done", result: "ok", ts: 3 }),
    });
    await h.emit({ type: "end", data: "" });
    const calls = h.bot.content.message.flatMap((part) => part.tool_calls || []);
    assert.deepEqual(
      calls.map((call) => [call.id, call.phase]),
      [
        ["done", undefined],
        ["open", "unknown"],
      ],
    );
  } finally {
    h.stop();
  }
});

test("a failed run marks the unreturned call interrupted without an end event", async () => {
  const h = messagesHarness();
  try {
    h.send("websocket");
    await h.emit({
      type: "plain",
      chain_type: "tool_call",
      data: JSON.stringify({ id: "open", name: "shell", ts: 1 }),
    });
    await h.emit({
      type: "error",
      data: { code: "agent_error", message: "WebChat run failed" },
    });
    const calls = h.bot.content.message.flatMap((part) => part.tool_calls || []);
    assert.deepEqual(
      calls.map((call) => [call.id, call.phase]),
      [["open", "unknown"]],
    );
  } finally {
    h.stop();
  }
});

for (const phase of ["awaiting_approval", "unknown"]) {
  test(`a late result clears the ${phase} mark`, () => {
    const h = messagesHarness();
    try {
      h.api.upsertToolCall(h.bot, { id: "tool", phase });
      h.api.finishToolCall(h.bot, { id: "tool", result: "done", ts: 10 });
      const call = h.bot.content.message[0].tool_calls[0];
      assert.equal(call.finished_ts, 10);
      assert.equal(call.phase, undefined);
    } finally {
      h.stop();
    }
  });
}

test("the elapsed timer follows running, awaiting, interrupted and finished states", async () => {
  const timers = new Set();
  const call = reactive({ name: "shell", ts: 1 });
  const h = mountTemplate(loadToolCallCard(timers), {
    toolCall: call,
    initialExpanded: true,
  });
  const text = () =>
    h
      .findAll((node) => node.type === "text")
      .map((node) => node.text)
      .join(" ");
  try {
    assert.equal(timers.size, 1);
    call.phase = "awaiting_approval";
    await nextTick();
    assert.equal(timers.size, 0);
    assert.match(text(), /toolStatus\.awaitingApproval/);
    call.phase = undefined;
    await nextTick();
    assert.equal(timers.size, 1);
    assert.doesNotMatch(text(), /toolStatus\.awaitingApproval/);
    call.phase = "unknown";
    await nextTick();
    assert.equal(timers.size, 0);
    assert.match(text(), /toolStatus\.interrupted/);
    call.phase = undefined;
    await nextTick();
    assert.equal(timers.size, 1);
    call.finished_ts = 2;
    await nextTick();
    assert.equal(timers.size, 0);
    assert.doesNotMatch(text(), /toolStatus\.interrupted/);
  } finally {
    h.stop();
  }
  assert.equal(timers.size, 0);
});

for (const phase of ["awaiting_approval", "unknown"]) {
  test(`a card mounted while ${phase} starts no elapsed timer`, () => {
    const timers = new Set();
    const h = mountTemplate(loadToolCallCard(timers), {
      toolCall: reactive({ name: "shell", ts: 1, phase }),
    });
    try {
      assert.equal(timers.size, 0);
    } finally {
      h.stop();
    }
  });
}

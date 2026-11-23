import assert from "node:assert/strict";
import { flushPromises } from "@vue/test-utils";
import { test, vi } from "vitest";
import { defineComponent, h, inject, nextTick, reactive } from "vue";
import { chatApi } from "../src/api/v1.ts";
import ChatMessageList from "../src/components/chat/ChatMessageList.vue";
import MessageWork from "../src/components/chat/message_list_comps/MessageWork.vue";
import ThreadPanel from "../src/components/chat/ThreadPanel.vue";
import { viewActionKey } from "../src/utils/chatViews.ts";
import { mountDashboard } from "./helpers/components.mjs";
import { mountMessages } from "./helpers/messages.mjs";
import { createSseStream } from "./helpers/streams.mjs";

for (const reply of [false, true]) {
  test(`view actions preserve the source message and refresh sessions only for a saved reply: ${reply}`, async () => {
    let refreshes = 0;
    let scrolls = 0;
    const requests = [];
    const stream = createSseStream();
    const sendFrame = stream.send;
    const finish = stream.close;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        requests.push(url);
        return stream.response;
      }),
    );
    const fixture = mountMessages({
      onSessionsChanged: () => {
        refreshes++;
      },
      onStreamUpdate: () => {
        scrolls++;
      },
    });
    const { messages, action } = fixture;
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
      await flushPromises();
      const records = messages.messagesBySession.session;
      assert.equal(records.length, 2);
      assert.equal(messages.isSessionRunning("session"), true);
      assert.equal(messages.isMessageStreaming(original, 0), false);
      assert.equal(messages.isMessageStreaming(records[1], 1), true);
      sendFrame({ type: "message_saved", data: { id: "saved-reply" } });
    }
    sendFrame({ type: "end" });
    finish();
    await flushPromises();
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

test("message list uses the specific streaming message even when another request is active", async () => {
  const original = { id: "original", content: { type: "bot", message: [] } };
  const reply = { id: "reply", content: { type: "bot", message: [] } };
  const { wrapper, vm } = await mountDashboard(ChatMessageList, {
    props: { messages: [original], isMessageStreaming: () => false },
  });
  assert.equal(vm.isMessageStreaming(original, 0), false);
  await wrapper.setProps({ messages: [original, reply], isMessageStreaming: (message) => message === reply });
  assert.equal(vm.isMessageStreaming(original, 0), false);
  assert.equal(vm.isMessageStreaming(reply, 1), true);
});

test("thread view callbacks keep the original message idle and do not scroll for an acknowledgement", async () => {
  const original = { id: "original", content: { type: "bot", message: [], agentStats: { duration: 3 } } };
  vi.spyOn(chatApi, "getThread").mockResolvedValue({ data: { data: { history: [original] } } });
  let action;
  const Probe = defineComponent({
    setup() {
      action = inject(viewActionKey);
      return () => h("div");
    },
  });
  const ack = createSseStream();
  const reply = createSseStream();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(ack.response).mockResolvedValueOnce(reply.response));
  const { vm } = await mountDashboard(ThreadPanel, {
    props: {
      modelValue: true,
      thread: { thread_id: "thread", selected_text: "source" },
      isDark: false,
      getProviderSelection: () => ({ providerId: "", modelName: "" }),
    },
    global: { stubs: { ChatMessageList: Probe } },
  });
  await flushPromises();
  let scrolls = 0;
  Object.defineProperty(vm.messagesEl, "scrollTop", {
    configurable: true,
    get: () => 0,
    set: () => {
      scrolls++;
    },
  });
  const source = vm.messages[0];
  const pending = action("reading", { interaction_id: "click-1", action_id: "set", expected_revision: 1, data: {} });
  assert.notEqual(vm.activeBotRecord, source);
  ack.send({ type: "run_started" });
  ack.send({ type: "ui_action_result", data: { snapshot: { revision: 2, data: {} } } });
  await pending;
  ack.send({ type: "end" });
  ack.close();
  await flushPromises();
  assert.equal(scrolls, 0);
  assert.equal(vm.messages.length, 1);
  assert.equal(vm.activeBotRecord, null);
  assert.equal(vm.sending, false);

  const response = action("reading", { interaction_id: "click-2", action_id: "set", expected_revision: 2, data: {} });
  reply.send({ type: "ui_action_result", data: { snapshot: { revision: 3, data: {} } } });
  await response;
  reply.send({ type: "plain", data: "New reply" });
  await flushPromises();
  assert.equal(vm.messages.length, 2);
  assert.equal(vm.activeBotRecord, vm.messages[1]);
  assert.notEqual(vm.activeBotRecord, source);
  assert.equal(scrolls, 1);
  reply.send({ type: "end" });
  reply.close();
  await flushPromises();
  assert.equal(vm.messages[0].content.agentStats.duration, 3);
});

test("views remain outside collapsed work before and after restoring tool history", async () => {
  const view = { type: "view", id: "reading" };
  const thinking = { kind: "thinking", parts: [{ type: "think", think: "Open a list" }] };
  const tools = { kind: "thinking", parts: [{ type: "tool_call", tool_calls: [{ id: "tool-1" }] }] };
  const props = reactive({ isUser: false, isStreaming: false, blocks: [thinking, { kind: "content", parts: [view] }] });
  const { wrapper, vm } = await mountDashboard(MessageWork, {
    props,
    slots: {
      default: ({ blocks }) =>
        blocks.flatMap((block) =>
          block.parts.map((part) =>
            h(
              "span",
              { "data-part-type": part.type, "data-view-id": part.id || "" },
              part.text || part.think || part.id || part.type,
            ),
          ),
        ),
    },
  });
  const visibleView = () => wrapper.get('[data-view-id="reading"]').element;
  assert.equal(vm.finalBlocks[0].parts[0].id, "reading");
  assert.equal(visibleView().closest(".process-collapse"), null);
  props.blocks.push(tools);
  await nextTick();
  const original = JSON.stringify(props.blocks);
  assert.equal(vm.processBlocks.length, 1);
  assert.equal(vm.processBlocks[0].parts.length, 2);
  assert.equal(vm.finalBlocks[0].parts[0].id, "reading");
  assert.equal(JSON.stringify(props.blocks), original);
  props.blocks.push({ kind: "content", parts: [{ type: "plain", text: "Your list is ready." }] });
  await nextTick();
  assert.deepEqual(JSON.parse(JSON.stringify(vm.finalBlocks)), [
    { kind: "content", parts: [view, { type: "plain", text: "Your list is ready." }] },
  ]);
  await wrapper.setProps({ blocks: JSON.parse(JSON.stringify(props.blocks)) });
  assert.equal(vm.finalBlocks[0].parts[0].id, "reading");
  assert.ok(vm.processBlocks.every((block) => block.parts.every((part) => part.type !== "view")));
  await wrapper.get(".process-toggle").trigger("click");
  assert.equal(visibleView().closest(".process-collapse"), null);
  await wrapper.setProps({ isUser: true });
  assert.equal(vm.processBlocks.length, 0);
  assert.equal(vm.finalBlocks.length, props.blocks.length);
});

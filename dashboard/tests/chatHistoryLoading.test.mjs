import assert from "node:assert/strict";
import { flushPromises } from "@vue/test-utils";
import { test, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { chatApi } from "../src/api/v1.ts";
import { deferredRequests, geometry, mountChat } from "./helpers/chat.mjs";
import { historyResponse } from "./helpers/messages.mjs";

test("failed history loading pauses scroll requests until an explicit retry", async () => {
  const Rows = defineComponent({
    props: ["messages"],
    setup(props) {
      return () =>
        h(
          "div",
          props.messages.map((record) => h("article", { key: record.id, "data-message-id": String(record.id) })),
        );
    },
  });
  const { state: context, wrapper } = await mountChat({ global: { stubs: { ChatMessageList: Rows } } });
  context.currSessionId = "session";
  chatApi.getSession.mockResolvedValue(
    historyResponse([{ id: 51, content: { type: "bot", message: [] } }], {
      total: 101,
      has_more: true,
    }),
  );
  await context.loadSessionMessages("session", false);
  await nextTick();
  const current = context.activeMessages[0];
  const state = context.activeSessionPagination;
  let anchorTop = 100;
  const container = geometry(context.messagesContainer, { scrollHeight: 1000, clientHeight: 400, scrollTop: 0 });
  const anchor = wrapper.get('[data-message-id="51"]').element;
  vi.spyOn(anchor, "getBoundingClientRect").mockImplementation(() => ({ top: anchorTop }));
  const { requests } = deferredRequests("getSession");
  context.maybeLoadEarlierOnScroll(container);
  assert.equal(requests.length, 1);
  assert.equal(state.loading, true);
  for (let i = 0; i < 10; i++) context.maybeLoadEarlierOnScroll(container);
  assert.equal(requests.length, 1, "pending requests must be deduplicated");
  requests[0].reject(new Error("Network Error"));
  await flushPromises();
  assert.equal(state.error, "Network Error");
  assert.equal(state.loading, false);
  assert.equal(state.page, 1);
  assert.deepEqual(context.activeMessages, [current]);
  for (let i = 0; i < 10; i++) context.maybeLoadEarlierOnScroll(container);
  assert.equal(requests.length, 1, "scroll events must not retry a failed page");

  container.scrollTop = 80;
  const retry = context.retryCurrentSessionLoad();
  assert.equal(requests.length, 2);
  assert.equal(requests[1].params.page, 2, "retry must request the failed page again");
  assert.equal(state.error, undefined);
  container.scrollTop = 20;
  anchorTop = 360;
  context.maybeLoadEarlierOnScroll(container);
  assert.equal(requests.length, 2);
  requests[1].resolve({
    data: {
      status: "ok",
      data: {
        history: [{ id: 1, content: { message: [] } }],
        page: 2,
        total: 101,
        has_more: true,
      },
    },
  });
  await retry;
  assert.equal(container.scrollTop, 220, "prepending history must preserve scrolling that continues during loading");
  assert.equal(state.page, 2);
  assert.equal(state.error, undefined);
  assert.equal(context.activeMessages.length, 2);
  container.scrollTop = 0;
  context.maybeLoadEarlierOnScroll(container);
  assert.equal(requests.length, 3, "successful retry must restore automatic pagination");
  requests[2].reject(new Error("Network Error"));
  await flushPromises();
});

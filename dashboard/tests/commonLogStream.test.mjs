import assert from "node:assert/strict";
import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { test, vi } from "vitest";
import { useCommonStore } from "@/stores/common";

vi.mock("@/api/v1", () => ({ pluginApi: {}, statsApi: {} }));

vi.mock("@/utils/request", () => ({
  default: { get: vi.fn() },
  resolveApiUrl: (path) => path,
}));

function controlledStream() {
  let controller;
  const cancel = vi.fn();
  const body = new ReadableStream({
    start(value) {
      controller = value;
    },
    cancel,
  });
  return { body, controller, cancel, response: { ok: true, status: 200, body } };
}

function prepare(...responses) {
  vi.useFakeTimers();
  setActivePinia(createPinia());
  const store = useCommonStore();
  const fetch = vi.fn();
  for (const response of responses) fetch.mockResolvedValueOnce(response);
  vi.stubGlobal("fetch", fetch);
  vi.spyOn(console, "info").mockImplementation(() => undefined);
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  return { store, fetch };
}

test("a rejected read clears connection state, releases the lock, and schedules one retry", async () => {
  const first = controlledStream();
  const second = controlledStream();
  const { store, fetch } = prepare(first.response, second.response);
  const running = store.createEventSource();
  await flushPromises();
  assert.equal(store.sse_connected, true);
  const payload = new TextEncoder().encode('data: {"type":"log","level":"INFO","time":1,"data":"消息"}\n\n');
  const split = payload.length - 6;
  first.controller.enqueue(payload.slice(0, split));
  first.controller.enqueue(payload.slice(split));
  await flushPromises();
  assert.equal(store.log_cache[0].data, "消息");
  assert.ok(store.log_cache[0].uuid);

  first.controller.error(new Error("connection dropped while reading"));
  await running;
  assert.equal(store.sse_connected, false);
  assert.equal(store.eventSource, null);
  assert.equal(first.body.locked, false);
  assert.equal(store.log_cache.at(-1).level, "ERROR");
  assert.equal(vi.getTimerCount(), 1);
  assert.equal(fetch.mock.calls.length, 1);

  await vi.advanceTimersByTimeAsync(1000);
  assert.equal(fetch.mock.calls.length, 2);
  assert.equal(store.sse_connected, true);
  assert.equal(vi.getTimerCount(), 0);
  store.closeEventSourcet();
  await flushPromises();
  assert.equal(second.body.locked, false);
  assert.equal(second.cancel.mock.calls.length, 1);
  assert.equal(store.sse_connected, false);
  assert.equal(vi.getTimerCount(), 0);
});

test("closing an active reader is expected cancellation without an error log or retry", async () => {
  const stream = controlledStream();
  const { store, fetch } = prepare(stream.response);
  const running = store.createEventSource();
  await flushPromises();
  const signal = fetch.mock.calls[0][1].signal;
  store.closeEventSourcet();
  await running;
  assert.equal(signal.aborted, true);
  assert.equal(stream.cancel.mock.calls.length, 1);
  assert.equal(stream.body.locked, false);
  assert.equal(store.eventSource, null);
  assert.equal(store.sse_connected, false);
  assert.deepEqual(store.log_cache, []);
  assert.equal(vi.getTimerCount(), 0);
  await store.createEventSource();
  assert.equal(fetch.mock.calls.length, 1);
});

test("closing after a read is fulfilled discards its queued log event", async () => {
  const stream = controlledStream();
  const { store } = prepare(stream.response);
  const running = store.createEventSource();
  await flushPromises();
  stream.controller.enqueue(
    new TextEncoder().encode('data: {"type":"log","level":"INFO","time":1,"data":"late event"}\n\n'),
  );
  store.closeEventSourcet();
  await running;

  assert.deepEqual(store.log_cache, []);
  assert.equal(store.sse_connected, false);
  assert.equal(store.eventSource, null);
  assert.equal(stream.cancel.mock.calls.length, 1);
  assert.equal(stream.body.locked, false);
  assert.equal(vi.getTimerCount(), 0);
});

test("a clean end releases its reader and close cancels the pending reconnect", async () => {
  const stream = controlledStream();
  const { store, fetch } = prepare(stream.response);
  const running = store.createEventSource();
  await flushPromises();
  stream.controller.close();
  await running;
  assert.equal(stream.body.locked, false);
  assert.equal(store.sse_connected, false);
  assert.equal(vi.getTimerCount(), 1);
  store.closeEventSourcet();
  await vi.advanceTimersByTimeAsync(3000);
  assert.equal(vi.getTimerCount(), 0);
  assert.equal(fetch.mock.calls.length, 1);
});

test("a response arriving after close is cancelled and never marks the store connected", async () => {
  const stream = controlledStream();
  const { store, fetch } = prepare();
  let resolveFetch;
  fetch.mockReturnValueOnce(
    new Promise((resolve) => {
      resolveFetch = resolve;
    }),
  );
  const running = store.createEventSource();
  store.closeEventSourcet();
  resolveFetch(stream.response);
  await running;
  assert.equal(stream.cancel.mock.calls.length, 1);
  assert.equal(stream.body.locked, false);
  assert.equal(store.sse_connected, false);
  assert.deepEqual(store.log_cache, []);
  assert.equal(vi.getTimerCount(), 0);
});

test("failed responses release their bodies and error entries obey the cache bound", async () => {
  const stream = controlledStream();
  const { store } = prepare({ ...stream.response, ok: false, status: 503 });
  store.log_cache_max_len = 1;
  store.log_cache.push({ uuid: "old", type: "log", level: "INFO", time: 0, data: "old" });
  await store.createEventSource();
  assert.equal(stream.body.locked, false);
  assert.equal(stream.cancel.mock.calls.length, 1);
  assert.equal(store.log_cache.length, 1);
  assert.equal(store.log_cache[0].level, "ERROR");
  assert.equal(store.sse_connected, false);
  assert.equal(vi.getTimerCount(), 1);
  store.closeEventSourcet();
  assert.equal(vi.getTimerCount(), 0);
});

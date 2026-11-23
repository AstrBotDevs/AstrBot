import { flushPromises } from "@vue/test-utils";
import { vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { chatApi, providerApi } from "../../src/api/v1.ts";
import Chat from "../../src/components/chat/Chat.vue";
import { useProviderModelSelection } from "../../src/composables/useProviderModelSelection.ts";
import { useSessions } from "../../src/composables/useSessions.ts";
import request from "../../src/utils/request.ts";
import { mountDashboard } from "./components.mjs";
import { historyResponse } from "./messages.mjs";
import { mountComposable } from "./mountComposable.mjs";

export function deferredRequests(method = "listSessions") {
  const requests = [];
  const spy = vi.spyOn(chatApi, method).mockImplementation(
    (...args) =>
      new Promise((resolve, reject) =>
        requests.push({
          args,
          params: args[method === "getSession" ? 1 : 0],
          sessionId: method === "getSession" ? args[0] : undefined,
          resolve,
          reject,
        }),
      ),
  );
  return { requests, spy };
}

export function mountSessions() {
  const transport = deferredRequests();
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/:pathMatch(.*)*", component: { render: () => null } }],
  });
  const app = mountComposable(() => useSessions(), { global: { plugins: [router] } });
  return { ...app, state: app.result, ...transport };
}

export function geometry(element, values) {
  for (const [name, initial] of Object.entries(values)) {
    let value = initial;
    Object.defineProperty(element, name, {
      configurable: true,
      get: () => value,
      set: (next) => {
        value = next;
      },
    });
  }
  return element;
}

export async function mountChat(options = {}) {
  localStorage.setItem("user", "alice");
  vi.stubGlobal("innerWidth", 1400);
  useProviderModelSelection().resetSelection();
  const observers = [];
  const frames = new Map();
  let frameId = 0;
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback) {
        this.callback = callback;
        this.targets = new Set();
        observers.push(this);
      }
      observe(target) {
        this.targets.add(target);
      }
      unobserve(target) {
        this.targets.delete(target);
      }
      disconnect() {
        this.targets.clear();
      }
    },
  );
  vi.stubGlobal("requestAnimationFrame", (callback) => {
    frames.set(++frameId, callback);
    return frameId;
  });
  vi.stubGlobal("cancelAnimationFrame", (id) => frames.delete(id));
  if (!globalThis.CSS?.escape) vi.stubGlobal("CSS", { ...globalThis.CSS, escape: (value) => String(value) });
  vi.spyOn(chatApi, "listSessions").mockResolvedValue({
    data: { status: "ok", data: { sessions: [], page: 1, page_size: 30, total: 0 } },
  });
  vi.spyOn(chatApi, "getSession").mockResolvedValue(historyResponse());
  vi.spyOn(chatApi, "listProjects").mockResolvedValue({ data: { status: "ok", data: [] } });
  vi.spyOn(providerApi, "listByProviderType").mockResolvedValue({ data: { status: "ok", data: [] } });
  vi.spyOn(request, "get").mockImplementation(async (url) => {
    if (url === "/api/chatui_project/list") return { data: { status: "ok", data: [] } };
    throw new Error(`Unexpected chat setup request: ${url}`);
  });
  const app = await mountDashboard(Chat, { route: "/chat", ...options });
  await flushPromises();
  app.vuetify.display.update();
  app.vm.shouldStickToBottom = false;
  app.vm.autoScrollPaused = true;
  await flushPromises();
  const transport = deferredRequests();
  return {
    ...app,
    state: app.vm,
    context: app.vm,
    observers,
    frames,
    ...transport,
    scroll: (event) => event.currentTarget.dispatchEvent(new Event("scroll")),
  };
}

export function resolvePage(request, start, end, total) {
  request.resolve({
    data: {
      status: "ok",
      data: {
        sessions: Array.from({ length: end - start }, (_, index) => ({
          session_id: String(start + index),
          display_name: `Session ${start + index}`,
        })),
        page: request.params.page,
        page_size: 30,
        total,
      },
    },
  });
}

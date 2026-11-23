import assert from "node:assert/strict";
import { flushPromises } from "@vue/test-utils";
import { test, vi } from "vitest";
import { nextTick } from "vue";
import { chatApi } from "../src/api/v1.ts";
import { geometry, mountChat, mountSessions, resolvePage } from "./helpers/chat.mjs";
import { historyResponse } from "./helpers/messages.mjs";

test("load every session beyond 100, deduplicate requests, and stop at the last page", async () => {
  const { state, requests } = mountSessions();
  let pending = state.getSessions();
  resolvePage(requests[0], 0, 30, 125);
  await pending;
  for (let page = 2; page <= 5; page++) {
    pending = state.getSessions(true);
    await state.getSessions(true);
    assert.equal(requests.length, page);
    resolvePage(requests[page - 1], (page - 1) * 30, Math.min(page * 30, 125), 125);
    await pending;
  }
  assert.equal(state.sessions.value.length, 125);
  assert.equal(state.sessionsPagination.hasMore, false);
  await state.getSessions(true);
  assert.equal(requests.length, 5);
});

test("failure keeps loaded sessions and retries the same page; overlap does not duplicate rows", async () => {
  const { state, requests } = mountSessions();
  let pending = state.getSessions();
  requests[0].reject(new Error("Offline"));
  await pending;
  assert.equal(state.sessionsPagination.error, true);
  pending = state.getSessions(state.sessionsPagination.append);
  resolvePage(requests[1], 0, 30, 61);
  await pending;
  pending = state.getSessions(true);
  requests[2].resolve({ data: { status: "error", message: "Unavailable" } });
  await pending;
  assert.equal(state.sessions.value.length, 30);
  assert.equal(state.sessionsPagination.page, 1);
  assert.equal(state.sessionsPagination.error, true);
  pending = state.getSessions(state.sessionsPagination.append);
  assert.equal(requests[3].params.page, 2);
  resolvePage(requests[3], 29, 59, 61);
  await pending;
  assert.equal(state.sessions.value.length, 59);
  assert.equal(state.sessionsPagination.error, false);
});

test("refresh preserves the loaded range and ignores an older in-flight append", async () => {
  const { state, requests } = mountSessions();
  let pending = state.getSessions();
  resolvePage(requests[0], 0, 30, 100);
  await pending;
  pending = state.getSessions(true);
  resolvePage(requests[1], 30, 60, 100);
  await pending;
  const stale = state.getSessions(true);
  const refresh = state.getSessions();
  resolvePage(requests[3], 1, 31, 99);
  await flushPromises();
  assert.equal(requests[4].params.page, 2);
  resolvePage(requests[4], 31, 61, 99);
  await refresh;
  resolvePage(requests[2], 60, 90, 100);
  await stale;
  assert.equal(state.sessions.value.length, 60);
  assert.equal(state.sessions.value[0].session_id, "1");
  assert.equal(state.sessionsPagination.page, 2);
  assert.equal(state.sessionsPagination.loading, false);
});

test("sidebar scrolling pauses after failure until retry, matching message history loading", async () => {
  const { state, requests, scroll } = await mountChat();
  const initial = state.getSessions();
  resolvePage(requests[0], 0, 30, 65);
  await initial;
  const container = geometry(state.sidebarContent, { scrollTop: 0, scrollHeight: 1000, clientHeight: 400 });
  const event = { currentTarget: container };
  scroll(event);
  assert.equal(requests.length, 1, "scrolling away from the bottom does not fetch");
  container.scrollTop = 481;
  scroll(event);
  assert.equal(requests.length, 2);
  for (let i = 0; i < 10; i++) scroll(event);
  assert.equal(requests.length, 2, "scrolling during loading does not duplicate requests");
  requests[1].reject(new Error("Offline"));
  await flushPromises();
  for (let i = 0; i < 10; i++) scroll(event);
  assert.equal(requests.length, 2, "failed requests require an explicit retry");
  assert.equal(state.sessions.length, 30);
  const retry = state.getSessions(state.sessionsPagination.append);
  assert.equal(requests[2].params.page, 2);
  resolvePage(requests[2], 30, 60, 65);
  await retry;
  scroll(event);
  assert.equal(requests[3].params.page, 3, "automatic loading resumes after retry");
  resolvePage(requests[3], 60, 65, 65);
  await flushPromises();
  scroll(event);
  assert.equal(requests.length, 4, "the last page stops automatic requests");
  assert.equal(state.sessions.length, 65);
});

test("an underfilled sidebar loads after rendering, pauses on failure, and skips hidden containers", async () => {
  const { state, requests, vuetify } = await mountChat();
  const container = geometry(state.sidebarContent, { scrollTop: 0, scrollHeight: 1260, clientHeight: 1260 });
  const initial = state.getSessions();
  resolvePage(requests[0], 0, 30, 125);
  await initial;
  await nextTick();
  assert.equal(requests.length, 2, "first render must load without a scroll event");
  requests[1].reject(new Error("Offline"));
  await flushPromises();
  await nextTick();
  assert.equal(requests.length, 2, "underfill must not repeatedly retry a failed request");
  const retry = state.getSessions(true);
  container.scrollHeight = 2400;
  resolvePage(requests[2], 30, 60, 125);
  await retry;
  await nextTick();
  assert.equal(requests.length, 3, "stop filling once content overflows");
  container.clientHeight = 0;
  state.loadMoreSessions();
  state.sidebarContent = null;
  state.loadMoreSessions();
  assert.equal(requests.length, 3, "collapsed or unmounted sidebar must not load");
  state.sidebarContent = container;
  container.scrollHeight = 2500;
  container.clientHeight = 2500;
  vi.stubGlobal("innerWidth", 500);
  vuetify.display.update();
  await nextTick();
  assert.equal(state.isMobile, true);
  state.loadMoreSessions();
  assert.equal(requests.length, 3, "closed mobile drawer must not load");
  state.sessionsExpanded = false;
  state.mobileDrawer.open = true;
  await nextTick();
  state.loadMoreSessions();
  assert.equal(requests.length, 3, "collapsed conversations must not load");
  state.sessionsExpanded = true;
  await nextTick();
  assert.equal(requests[3].params.page, 3, "expanding conversations in an underfilled drawer resumes pagination");
  resolvePage(requests[3], 60, 90, 90);
  await flushPromises();
  await nextTick();
  assert.equal(requests.length, 4, "hasMore prevents further requests");
});

test("deep-linked session metadata restores title and selection without fetching intervening pages", async () => {
  const { state, requests, wrapper } = await mountChat();
  const older = { session_id: "90", display_name: "Older session", platform_id: "webchat", is_group: 0 };
  state.sessions = [{ session_id: "1", display_name: "First session" }];
  state.currSessionId = "90";
  chatApi.getSession.mockResolvedValue(historyResponse([], { session: older }));
  await state.loadSessionMessages("90");
  await nextTick();
  assert.equal(state.currentSession.display_name, "Older session");
  assert.equal(state.sidebarSessions[0].session_id, "90");
  assert.equal(wrapper.find(".session-item.active .session-title").text(), "Older session");
  assert.equal(state.sessions.length, 1, "metadata must not change the paginated list");
  assert.equal(requests.length, 0, "metadata loading must not fetch intervening session-list pages");
  state.sessions.push(older);
  assert.equal(state.sidebarSessions.length, 2, "the loaded page must not duplicate the selected row");
  state.sessions.pop();
  state.sessionProjects["90"] = { project_id: "project" };
  assert.equal(state.sidebarSessions.length, 1, "project sessions stay out of the ordinary list");
  state.currSessionId = "";
  assert.equal(state.currentSession, null);
});

test("collapsing project content fills the sidebar without resizing its container", async () => {
  const { state, requests, observers } = await mountChat();
  const container = geometry(state.sidebarContent, { clientHeight: 1260, scrollHeight: 1595, scrollTop: 0 });
  const projectElement = state.sidebarProjectElement;
  const observer = observers.find((item) => item.targets.has(projectElement));
  assert.ok(observer, "the mounted project list must be observed");
  const initial = state.getSessions();
  resolvePage(requests[0], 0, 30, 100);
  await initial;
  await nextTick();
  assert.equal(requests.length, 1);
  container.scrollHeight = 1260;
  observer.callback([{ target: projectElement }]);
  assert.equal(requests.length, 2, "project collapse must request the next page");
  assert.equal(requests[1].params.page, 2);
  observer.callback([{ target: projectElement }]);
  assert.equal(requests.length, 2, "resize notifications must not duplicate the pending request");
  container.scrollHeight = 2000;
  resolvePage(requests[1], 30, 60, 100);
  await flushPromises();
  await nextTick();
  assert.equal(requests.length, 2);
});

test("renaming an unloaded session refreshes page boundaries so traversal loses no sessions", async () => {
  const { state } = await mountChat();
  let rows = Array.from({ length: 100 }, (_, i) => ({ session_id: String(i + 1), display_name: `Session ${i + 1}` }));
  const pages = [];
  chatApi.listSessions.mockImplementation(async ({ page, page_size }) => {
    pages.push(page);
    return {
      data: {
        status: "ok",
        data: {
          sessions: structuredClone(rows.slice((page - 1) * page_size, page * page_size)),
          page,
          page_size,
          total: rows.length,
        },
      },
    };
  });
  vi.spyOn(chatApi, "updateSession").mockImplementation(async (id, body) => {
    const renamed = rows.find((row) => row.session_id === id);
    Object.assign(renamed, body);
    rows = [renamed, ...rows.filter((row) => row !== renamed)];
  });
  state.editingSessionTitleId = "90";
  state.sessionTitleDraft = "Renamed 90";
  state.sessionTitleDialogOpen = true;
  state.sessionDetails["90"] = structuredClone(rows[89]);
  await state.getSessions();
  await state.getSessions(true);
  state.currSessionId = "90";
  await state.saveSessionTitleDialog();
  assert.deepEqual(pages, [1, 2, 1, 2], "rename must refresh the loaded range");
  assert.equal(state.sessions.length, 60);
  assert.equal(state.sessions[0].session_id, "90");
  assert.equal(state.sessions[0].display_name, "Renamed 90");
  state.currSessionId = "1";
  while (state.sessionsPagination.hasMore) await state.getSessions(true);
  assert.equal(state.sessions.length, 100);
  assert.equal(new Set(state.sessions.map((row) => row.session_id)).size, 100);
  assert.equal(
    state.sessions.some((row) => row.session_id === "90"),
    true,
  );
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { computed, nextTick, reactive, ref, watch } from "vue";

function setup() {
  const requests = [];
  const source = readFileSync(new URL("../src/composables/useSessions.ts", import.meta.url), "utf8");
  const ast = ts.createSourceFile("sessions.ts", source, ts.ScriptTarget.Latest, true);
  const definition = ast.statements.find((node) => ts.isFunctionDeclaration(node) && node.name.text === "useSessions");
  const context = vm.createContext({
    exports: {},
    ref,
    reactive,
    computed,
    watch,
    sidebarContent: ref(null),
    sidebarProjectElement: ref(null),
    messagesContainer: ref(null),
    chatResizeObserver: null,
    ResizeObserver: class {
      constructor(callback) {
        this.callback = callback;
      }
    },
    isMobile: ref(false),
    mobileDrawer: reactive({ open: false }),
    useRouter: () => ({ push() {} }),
    console: { error() {} },
    chatApi: {
      listSessions: (params) => new Promise((resolve, reject) => requests.push({ params, resolve, reject })),
    },
  });
  vm.runInContext(
    ts.transpile(definition.getText(ast), {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
    }),
    context,
  );
  const state = context.exports.useSessions();
  context.sessionsPagination = state.sessionsPagination;
  context.getSessions = state.getSessions;
  const chat = readFileSync(new URL("../src/components/chat/Chat.vue", import.meta.url), "utf8")
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const chatAst = ts.createSourceFile("chat.ts", chat, ts.ScriptTarget.Latest, true);
  for (const name of ["loadMoreSessions", "saveSessionTitleDialog"]) {
    const handler = chatAst.statements.find((node) => ts.isFunctionDeclaration(node) && node.name.text === name);
    vm.runInContext(ts.transpile(handler.getText(chatAst)), context);
  }
  const visit = (node) => {
    if (ts.isBinaryExpression(node) && node.left.getText(chatAst) === "chatResizeObserver") {
      vm.runInContext(ts.transpile(node.getText(chatAst)), context);
    }
    ts.forEachChild(node, visit);
  };
  visit(chatAst);
  const loadingWatcher = chatAst.statements.find(
    (node) =>
      ts.isExpressionStatement(node) &&
      node.getText(chatAst).startsWith("watch(") &&
      node.getText(chatAst).includes("() => loadMoreSessions()"),
  );
  const stopWatching = vm.runInContext(ts.transpile(loadingWatcher.getText(chatAst)), context);
  return {
    state,
    requests,
    context,
    stopWatching,
    scroll: (event) => {
      context.sidebarContent.value = event.currentTarget;
      context.loadMoreSessions();
    },
  };
}

function resolvePage(request, start, end, total) {
  request.resolve({
    data: {
      status: "ok",
      data: {
        sessions: Array.from({ length: end - start }, (_, index) => ({
          session_id: String(start + index),
        })),
        page: request.params.page,
        page_size: 30,
        total,
      },
    },
  });
}

test("load every session beyond 100, deduplicate requests, and stop at the last page", async () => {
  const { state, requests } = setup();
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
  const { state, requests } = setup();
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
  const { state, requests } = setup();
  let pending = state.getSessions();
  resolvePage(requests[0], 0, 30, 100);
  await pending;
  pending = state.getSessions(true);
  resolvePage(requests[1], 30, 60, 100);
  await pending;
  const stale = state.getSessions(true);
  const refresh = state.getSessions();
  resolvePage(requests[3], 1, 31, 99);
  await new Promise(setImmediate);
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
  const { state, requests, scroll } = setup();
  const initial = state.getSessions();
  resolvePage(requests[0], 0, 30, 65);
  await initial;
  const container = { scrollTop: 0, scrollHeight: 1000, clientHeight: 400 };
  const event = { currentTarget: container };
  scroll(event);
  assert.equal(requests.length, 1, "scrolling away from the bottom does not fetch");
  container.scrollTop = 481;
  scroll(event);
  assert.equal(requests.length, 2);
  for (let i = 0; i < 10; i++) scroll(event);
  assert.equal(requests.length, 2, "scrolling during loading does not duplicate requests");
  requests[1].reject(new Error("Offline"));
  await new Promise(setImmediate);
  for (let i = 0; i < 10; i++) scroll(event);
  assert.equal(requests.length, 2, "failed requests require an explicit retry");
  assert.equal(state.sessions.value.length, 30);
  const retry = state.getSessions(state.sessionsPagination.append);
  assert.equal(requests[2].params.page, 2);
  resolvePage(requests[2], 30, 60, 65);
  await retry;
  scroll(event);
  assert.equal(requests[3].params.page, 3, "automatic loading resumes after retry");
  resolvePage(requests[3], 60, 65, 65);
  await new Promise(setImmediate);
  scroll(event);
  assert.equal(requests.length, 4, "the last page stops automatic requests");
  assert.equal(state.sessions.value.length, 65);
});

test("an underfilled sidebar loads after rendering, pauses on failure, and skips hidden containers", async (t) => {
  const { state, requests, context, stopWatching } = setup();
  t.after(stopWatching);
  context.sidebarContent.value = {
    scrollTop: 0,
    scrollHeight: 1260,
    clientHeight: 1260,
  };
  const initial = state.getSessions();
  resolvePage(requests[0], 0, 30, 125);
  await initial;
  await nextTick();
  assert.equal(requests.length, 2, "first render must load without a scroll event");
  requests[1].reject(new Error("Offline"));
  await new Promise(setImmediate);
  await nextTick();
  assert.equal(requests.length, 2, "underfill must not repeatedly retry a failed request");
  const retry = state.getSessions(true);
  context.sidebarContent.value.scrollHeight = 2400;
  resolvePage(requests[2], 30, 60, 125);
  await retry;
  await nextTick();
  assert.equal(requests.length, 3, "stop filling once content overflows");
  context.sidebarContent.value.clientHeight = 0;
  context.loadMoreSessions();
  context.sidebarContent.value = null;
  context.loadMoreSessions();
  assert.equal(requests.length, 3, "collapsed or unmounted sidebar must not load");
  context.sidebarContent.value = {
    scrollTop: 0,
    scrollHeight: 2500,
    clientHeight: 2500,
  };
  context.isMobile.value = true;
  context.loadMoreSessions();
  assert.equal(requests.length, 3, "closed mobile drawer must not load");
  context.mobileDrawer.open = true;
  await nextTick();
  assert.equal(requests[3].params.page, 3, "opening an underfilled drawer resumes pagination");
  resolvePage(requests[3], 60, 90, 90);
  await new Promise(setImmediate);
  await nextTick();
  assert.equal(requests.length, 4, "hasMore prevents further requests");
});

test("deep-linked session metadata restores title and selection without fetching intervening pages", async () => {
  const messages = readFileSync(new URL("../src/composables/useMessages.ts", import.meta.url), "utf8");
  const chat = readFileSync(new URL("../src/components/chat/Chat.vue", import.meta.url), "utf8")
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const definitions = [];
  for (const source of [messages, chat]) {
    const ast = ts.createSourceFile("source.ts", source, ts.ScriptTarget.Latest, true);
    const visit = (node) => {
      if (ts.isFunctionDeclaration(node) && node.name?.text === "loadSessionMessages") {
        definitions.push(node.getText(ast));
      }
      if (
        ts.isVariableStatement(node) &&
        node.declarationList.declarations.some((declaration) =>
          ["currentSession", "sessionProject", "sidebarSessions"].includes(declaration.name.getText(ast)),
        )
      )
        definitions.push(node.getText(ast));
      ts.forEachChild(node, visit);
    };
    visit(ast);
  }
  const older = {
    session_id: "90",
    display_name: "Older session",
    platform_id: "webchat",
    is_group: 0,
  };
  const context = vm.createContext({
    computed,
    sessions: ref([{ session_id: "1" }]),
    currSessionId: ref("90"),
    projectSessions: ref([]),
    projectSessionsById: ref({}),
    sessionDetails: reactive({}),
    sessionProjects: reactive({}),
    loadingMessagesState: ref(false),
    loadingSessionId: ref(null),
    sessionLoadEpochs: {},
    messagesBySession: {},
    paginationBySession: {},
    loadedSessions: {},
    attachThreads() {},
    resolveRecordMedia: async () => {},
    normalizeSessionProject: (project) => project || null,
    chatApi: {
      getSession: async () => ({
        data: { status: "ok", data: { session: older, history: [], total: 0 } },
      }),
    },
  });
  vm.runInContext(ts.transpile(definitions.join("\n")), context);
  await context.loadSessionMessages("90");
  assert.equal(vm.runInContext("currentSession.value.display_name", context), "Older session");
  assert.equal(vm.runInContext("sidebarSessions.value[0].session_id", context), "90");
  assert.equal(context.sessions.value.length, 1, "metadata must not change the paginated list");
  context.sessions.value.push(older);
  assert.equal(
    vm.runInContext("sidebarSessions.value.length", context),
    2,
    "the loaded page must not duplicate the selected row",
  );
  context.sessions.value.pop();
  context.sessionProjects["90"] = { project_id: "project" };
  assert.equal(
    vm.runInContext("sidebarSessions.value.length", context),
    1,
    "project sessions stay out of the ordinary list",
  );
  context.currSessionId.value = "";
  assert.equal(vm.runInContext("currentSession.value", context), null);
});

test("collapsing project content fills the sidebar without resizing its container", async (t) => {
  const { state, requests, context, stopWatching } = setup();
  t.after(stopWatching);
  context.sidebarContent.value = {
    clientHeight: 1260,
    scrollHeight: 1595,
    scrollTop: 0,
  };
  context.sidebarProjectElement.value = {};
  const initial = state.getSessions();
  resolvePage(requests[0], 0, 30, 100);
  await initial;
  await nextTick();
  assert.equal(requests.length, 1);
  context.sidebarContent.value.scrollHeight = 1260;
  context.chatResizeObserver.callback([{ target: context.sidebarProjectElement.value }]);
  assert.equal(requests.length, 2, "project collapse must request the next page");
  assert.equal(requests[1].params.page, 2);
  context.chatResizeObserver.callback([{ target: context.sidebarProjectElement.value }]);
  assert.equal(requests.length, 2, "resize notifications must not duplicate the pending request");
  context.sidebarContent.value.scrollHeight = 2000;
  resolvePage(requests[1], 30, 60, 100);
  await new Promise(setImmediate);
  await nextTick();
  assert.equal(requests.length, 2);
});

test("renaming an unloaded session refreshes page boundaries so traversal loses no sessions", async (t) => {
  const { state, context, stopWatching } = setup();
  t.after(stopWatching);
  let rows = Array.from({ length: 100 }, (_, i) => ({
    session_id: String(i + 1),
    display_name: `Session ${i + 1}`,
  }));
  const pages = [];
  context.chatApi.listSessions = async ({ page, page_size }) => {
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
  };
  context.chatApi.updateSession = async (id, body) => {
    const renamed = rows.find((row) => row.session_id === id);
    Object.assign(renamed, body);
    rows = [renamed, ...rows.filter((row) => row !== renamed)];
  };
  Object.assign(context, {
    updateSessionTitle: state.updateSessionTitle,
    editingSessionTitleId: ref("90"),
    savingSessionTitle: ref(false),
    sessionTitleDraft: ref("Renamed 90"),
    sessionTitleDialogOpen: ref(true),
    sessionDetails: reactive({ 90: structuredClone(rows[89]) }),
    projectSessions: ref([]),
    projectSessionsById: ref({}),
    refreshProjectSessionsAfterTitleSave: ref(false),
  });
  await state.getSessions();
  await state.getSessions(true);
  state.currSessionId.value = "90";
  await context.saveSessionTitleDialog();
  assert.deepEqual(pages, [1, 2, 1, 2], "rename must refresh the loaded range");
  assert.equal(state.sessions.value.length, 60);
  assert.equal(state.sessions.value[0].session_id, "90");
  assert.equal(state.sessions.value[0].display_name, "Renamed 90");
  state.currSessionId.value = "1";
  while (state.sessionsPagination.hasMore) await state.getSessions(true);
  assert.equal(state.sessions.value.length, 100);
  assert.equal(new Set(state.sessions.value.map((row) => row.session_id)).size, 100);
  assert.equal(
    state.sessions.value.some((row) => row.session_id === "90"),
    true,
  );
});

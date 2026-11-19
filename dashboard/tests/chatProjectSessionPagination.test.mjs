import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { nextTick, reactive, ref, watch } from "vue";

function setup() {
  const requests = [];
  const source = readFileSync(
    new URL("../src/composables/useProjects.ts", import.meta.url),
    "utf8",
  );
  const ast = ts.createSourceFile(
    "projects.ts",
    source,
    ts.ScriptTarget.Latest,
    true,
  );
  const definition = ast.statements.find(
    (node) =>
      ts.isFunctionDeclaration(node) && node.name.text === "useProjects",
  );
  const context = vm.createContext({
    exports: {},
    ref,
    reactive,
    console: { error() {} },
    chatApi: {
      listProjectSessions: (projectId, params) =>
        new Promise((resolve, reject) =>
          requests.push({ projectId, params, resolve, reject }),
        ),
      deleteProject: async () => ({ data: { status: "ok" } }),
      listProjects: async () => ({ data: { status: "ok", data: [] } }),
    },
  });
  vm.runInContext(
    ts.transpile(definition.getText(ast), {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
    }),
    context,
  );
  return { state: context.exports.useProjects(), requests };
}

function resolvePage(request, start, end, total) {
  request.resolve({
    data: {
      status: "ok",
      data: {
        sessions: Array.from({ length: end - start }, (_, i) => ({
          session_id: `${request.projectId}-${start + i}`,
        })),
        page: request.params.page,
        page_size: 30,
        total,
      },
    },
  });
}

test("both project lists share pages and reach all 125 sessions without duplicate requests", async () => {
  const { state, requests } = setup();
  let pending = state.getProjectSessions("p");
  resolvePage(requests[0], 0, 30, 125);
  await pending;
  for (let page = 2; page <= 5; page++) {
    pending = state.getProjectSessions("p", true);
    await state.getProjectSessions("p", true);
    assert.equal(requests.length, page);
    assert.equal(requests.at(-1).params.page, page);
    resolvePage(
      requests.at(-1),
      (page - 1) * 30,
      Math.min(page * 30, 125),
      125,
    );
    await pending;
  }
  assert.equal(state.projectSessionsById.value.p.length, 125);
  assert.equal(
    new Set(state.projectSessionsById.value.p.map((s) => s.session_id)).size,
    125,
  );
  assert.equal(state.projectSessionsPagination.p.hasMore, false);
  await state.getProjectSessions("p", true);
  assert.equal(requests.length, 5);
});

test("failed page retains rows and retries the same page, deduplicating overlap", async () => {
  const { state, requests } = setup();
  let pending = state.getProjectSessions("p");
  requests[0].reject(new Error("Offline"));
  await pending;
  assert.equal(state.projectSessionsPagination.p.error, true);
  pending = state.getProjectSessions(
    "p",
    state.projectSessionsPagination.p.append,
  );
  resolvePage(requests[1], 0, 30, 125);
  await pending;
  pending = state.getProjectSessions("p", true);
  requests[2].resolve({ data: { status: "error", message: "Unavailable" } });
  await pending;
  assert.equal(state.projectSessionsById.value.p.length, 30);
  assert.equal(state.projectSessionsPagination.p.page, 1);
  pending = state.getProjectSessions(
    "p",
    state.projectSessionsPagination.p.append,
  );
  assert.equal(requests[3].params.page, 2);
  resolvePage(requests[3], 29, 59, 125);
  await pending;
  assert.equal(state.projectSessionsById.value.p.length, 59);
  assert.equal(state.projectSessionsPagination.p.error, false);
});

test("mutation refresh retains loaded pages and ignores a stale append", async () => {
  const { state, requests } = setup();
  let pending = state.getProjectSessions("p");
  resolvePage(requests[0], 0, 30, 125);
  await pending;
  pending = state.getProjectSessions("p", true);
  resolvePage(requests[1], 30, 60, 125);
  await pending;
  const stale = state.getProjectSessions("p", true);
  pending = state.getProjectSessions("p");
  resolvePage(requests[3], 1, 31, 125);
  await new Promise(setImmediate);
  assert.equal(requests[4].params.page, 2);
  resolvePage(requests[4], 31, 61, 125);
  await pending;
  resolvePage(requests[2], 60, 90, 125);
  await stale;
  assert.equal(state.projectSessionsById.value.p.length, 60);
  assert.equal(state.projectSessionsById.value.p[0].session_id, "p-1");
  assert.equal(state.projectSessionsPagination.p.page, 2);
  assert.equal(state.projectSessionsPagination.p.loading, false);
});

test("switching projects during loading keeps each cache and pagination independent", async () => {
  const { state, requests } = setup();
  const first = state.getProjectSessions("first");
  const second = state.getProjectSessions("second");
  resolvePage(requests[1], 0, 2, 2);
  await second;
  resolvePage(requests[0], 0, 30, 125);
  await first;
  assert.equal(state.projectSessionsById.value.second.length, 2);
  assert.equal(state.projectSessionsById.value.first.length, 30);
  assert.equal(state.projectSessionsPagination.second.hasMore, false);
  assert.equal(state.projectSessionsPagination.first.hasMore, true);
});

test("deleting a project invalidates pending requests and its cache", async () => {
  const { state, requests } = setup();
  state.selectedProjectId.value = "p";
  const pending = state.getProjectSessions("p");
  await state.deleteProject("p");
  resolvePage(requests[0], 0, 30, 125);
  await pending;
  assert.equal(state.projectSessionsById.value.p, undefined);
  assert.equal(state.projectSessionsPagination.p, undefined);
  assert.equal(state.selectedProjectId.value, null);
});

test("renaming a sidebar project session refreshes its own project", async () => {
  const source = readFileSync(
    new URL("../src/components/chat/Chat.vue", import.meta.url),
    "utf8",
  )
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const ast = ts.createSourceFile(
    "chat.ts",
    source,
    ts.ScriptTarget.Latest,
    true,
  );
  const handler = ast.statements.find(
    (node) =>
      ts.isFunctionDeclaration(node) &&
      node.name.text === "saveSessionTitleDialog",
  );
  const refreshed = [];
  const context = vm.createContext({
    editingSessionTitleId: ref("p-1"),
    savingSessionTitle: ref(false),
    sessionTitleDraft: ref("Renamed"),
    sessionTitleDialogOpen: ref(true),
    refreshProjectSessionsAfterTitleSave: ref(true),
    sessionDetails: {},
    projectSessions: ref([]),
    projectSessionsById: ref({
      p: [{ session_id: "p-1", display_name: "Original" }],
    }),
    chatApi: { updateSession: async () => {} },
    updateSessionTitle() {},
    loadProjectSessions: async (id) => refreshed.push(id),
  });
  vm.runInContext(ts.transpile(handler.getText(ast)), context);
  await context.saveSessionTitleDialog();
  assert.deepEqual(refreshed, ["p"]);
  assert.equal(context.projectSessionsById.value.p[0].display_name, "Renamed");
});

test("an exact 120-session total stops without requesting an empty page", async () => {
  const { state, requests } = setup();
  for (let page = 1; page <= 4; page++) {
    const pending = state.getProjectSessions("p", page > 1);
    resolvePage(requests.at(-1), (page - 1) * 30, page * 30, 120);
    await pending;
  }
  assert.equal(state.projectSessionsById.value.p.length, 120);
  assert.equal(state.projectSessionsPagination.p.hasMore, false);
  await state.getProjectSessions("p", true);
  assert.equal(requests.length, 4);
});

test("sidebar projects load near the bottom and skip errors, collapsed lists, and lists above the viewport", () => {
  const source = readFileSync(
    new URL("../src/components/chat/ProjectList.vue", import.meta.url),
    "utf8",
  )
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const ast = ts.createSourceFile(
    "list.ts",
    source,
    ts.ScriptTarget.Latest,
    true,
  );
  const handler = ast.statements.find(
    (node) =>
      ts.isFunctionDeclaration(node) && node.name.text === "loadMoreSessions",
  );
  const calls = [];
  const pagination = {
    a: { hasMore: true, loading: false, error: false },
    b: { hasMore: true, loading: false, error: false },
  };
  const collapsed = new Set();
  const context = vm.createContext({
    props: { pagination },
    isProjectExpanded: (id) => !collapsed.has(id),
    emit: (...args) => calls.push(args),
  });
  vm.runInContext(ts.transpile(handler.getText(ast)), context);
  let bottomA = 721;
  let bottomB = 900;
  const container = {
    clientHeight: 500,
    getBoundingClientRect: () => ({ top: 100 }),
    querySelectorAll: () => [
      {
        dataset: { projectId: "a" },
        getBoundingClientRect: () => ({ bottom: bottomA }),
      },
      {
        dataset: { projectId: "b" },
        getBoundingClientRect: () => ({ bottom: bottomB }),
      },
    ],
  };
  context.loadMoreSessions(container);
  assert.equal(calls.length, 0);
  bottomA = 720;
  context.loadMoreSessions(container);
  assert.deepEqual(calls.pop(), ["loadSessions", "a", true]);
  pagination.a.loading = true;
  bottomB = 650;
  context.loadMoreSessions(container);
  assert.deepEqual(calls.pop(), ["loadSessions", "b", true]);
  pagination.a.loading = false;
  pagination.a.error = true;
  collapsed.add("b");
  context.loadMoreSessions(container);
  assert.equal(calls.length, 0);
  pagination.a.error = false;
  bottomA = 99;
  context.loadMoreSessions(container);
  context.loadMoreSessions(container);
  assert.equal(calls.length, 0, "an offscreen project must not keep loading");
  bottomA = 101;
  context.loadMoreSessions(container);
  assert.deepEqual(calls.pop(), ["loadSessions", "a", true]);
  pagination.a.hasMore = false;
  context.loadMoreSessions(container);
  assert.equal(calls.length, 0);
});

test("project page fills after rendering, uses 120px threshold and ignores hidden or failed lists", async () => {
  const source = readFileSync(
    new URL("../src/components/chat/ProjectView.vue", import.meta.url),
    "utf8",
  )
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const ast = ts.createSourceFile(
    "view.ts",
    source,
    ts.ScriptTarget.Latest,
    true,
  );
  const handler = ast.statements.find(
    (node) =>
      ts.isFunctionDeclaration(node) && node.name.text === "loadMoreSessions",
  );
  const watcher = ast.statements.find(
    (node) =>
      ts.isExpressionStatement(node) && node.getText(ast).startsWith("watch("),
  );
  const calls = [];
  const props = reactive({
    project: { project_id: "a" },
    pagination: { hasMore: true, loading: false, error: false },
  });
  const container = { clientHeight: 500, scrollHeight: 1000, scrollTop: 379 };
  const context = vm.createContext({
    props,
    sessionsContainer: ref(container),
    watch,
    emit: (...args) => calls.push(args),
  });
  vm.runInContext(ts.transpile(handler.getText(ast)), context);
  const stop = vm.runInContext(ts.transpile(watcher.getText(ast)), context);
  try {
    context.loadMoreSessions();
    assert.equal(calls.length, 0);
    container.scrollTop = 380;
    context.loadMoreSessions();
    assert.deepEqual(calls.pop(), ["loadSessions", true]);
    props.pagination.loading = true;
    await nextTick();
    assert.equal(calls.length, 0);
    container.scrollHeight = 400;
    container.scrollTop = 0;
    props.pagination.loading = false;
    await nextTick();
    assert.deepEqual(calls.pop(), ["loadSessions", true]);
    props.pagination.error = true;
    context.loadMoreSessions();
    assert.equal(calls.length, 0);
    props.pagination.error = false;
    container.clientHeight = 0;
    context.loadMoreSessions();
    assert.equal(calls.length, 0);
    container.clientHeight = 500;
    props.project = { project_id: "b" };
    await nextTick();
    assert.deepEqual(calls.pop(), ["loadSessions", true]);
    props.pagination.hasMore = false;
    context.loadMoreSessions();
    assert.equal(calls.length, 0);
  } finally {
    stop();
  }
});

test("project API wrapper accepts either pagination parameter without weakening their types", () => {
  const source = readFileSync(
    new URL("../src/api/v1.ts", import.meta.url),
    "utf8",
  );
  const ast = ts.createSourceFile(
    "api.ts",
    source,
    ts.ScriptTarget.Latest,
    true,
  );
  const statement = ast.statements.find(
    (node) =>
      ts.isVariableStatement(node) &&
      node.declarationList.declarations.some(
        (declaration) => declaration.name.getText(ast) === "chatApi",
      ),
  );
  const api = statement.declarationList.declarations.find(
    (node) => node.name.getText(ast) === "chatApi",
  );
  const method = api.initializer.properties.find(
    (node) => node.name.getText(ast) === "listProjectSessions",
  );
  const filename = "project-pagination-types.ts";
  const fixture = `
    declare function typed<T>(value: unknown): T;
    declare const openApiV1: any;
    const chatApi = { ${method.getText(ast)} };
    chatApi.listProjectSessions("p");
    chatApi.listProjectSessions("p", {});
    chatApi.listProjectSessions("p", { page: 2 });
    chatApi.listProjectSessions("p", { page_size: 30 });
    chatApi.listProjectSessions("p", { page: 2, page_size: 30 });
    // @ts-expect-error Pagination parameters must remain numeric.
    chatApi.listProjectSessions("p", { page: "2" });
    // @ts-expect-error Pagination parameters must remain numeric.
    chatApi.listProjectSessions("p", { page_size: "30" });
  `;
  const options = {
    noEmit: true,
    strict: true,
    skipLibCheck: true,
    types: [],
    target: ts.ScriptTarget.ES2020,
  };
  const host = ts.createCompilerHost(options);
  const getSourceFile = host.getSourceFile.bind(host);
  host.getSourceFile = (name, ...args) =>
    name === filename
      ? ts.createSourceFile(name, fixture, ts.ScriptTarget.ES2020, true)
      : getSourceFile(name, ...args);
  const program = ts.createProgram([filename], options, host);
  const diagnostics = ts.getPreEmitDiagnostics(program);
  assert.deepEqual(
    diagnostics.map((d) =>
      ts.flattenDiagnosticMessageText(d.messageText, "\n"),
    ),
    [],
  );
});

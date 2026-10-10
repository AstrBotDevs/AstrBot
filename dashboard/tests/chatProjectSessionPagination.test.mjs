import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { reactive, ref } from "vue";

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

function resolvePage(request, start, end, hasMore) {
  request.resolve({
    data: {
      status: "ok",
      data: {
        sessions: Array.from({ length: end - start }, (_, i) => ({
          session_id: `${request.projectId}-${start + i}`,
        })),
        page: request.params.page,
        page_size: 30,
        has_more: hasMore,
      },
    },
  });
}

test("both project lists share pages and reach all 125 sessions without duplicate requests", async () => {
  const { state, requests } = setup();
  let pending = state.getProjectSessions("p");
  resolvePage(requests[0], 0, 30, true);
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
      page < 5,
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
  resolvePage(requests[1], 0, 30, true);
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
  resolvePage(requests[3], 29, 59, true);
  await pending;
  assert.equal(state.projectSessionsById.value.p.length, 59);
  assert.equal(state.projectSessionsPagination.p.error, false);
});

test("mutation refresh retains loaded pages and ignores a stale append", async () => {
  const { state, requests } = setup();
  let pending = state.getProjectSessions("p");
  resolvePage(requests[0], 0, 30, true);
  await pending;
  pending = state.getProjectSessions("p", true);
  resolvePage(requests[1], 30, 60, true);
  await pending;
  const stale = state.getProjectSessions("p", true);
  pending = state.getProjectSessions("p");
  resolvePage(requests[3], 1, 31, true);
  await new Promise(setImmediate);
  assert.equal(requests[4].params.page, 2);
  resolvePage(requests[4], 31, 61, true);
  await pending;
  resolvePage(requests[2], 60, 90, true);
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
  resolvePage(requests[1], 0, 2, false);
  await second;
  resolvePage(requests[0], 0, 30, true);
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
  resolvePage(requests[0], 0, 30, true);
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

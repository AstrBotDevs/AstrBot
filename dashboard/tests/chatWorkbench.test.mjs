import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { parse } from "vue/compiler-sfc";
import { computed, reactive, ref, watch, nextTick, effectScope } from "vue";

function setup(storage = new Map(), username = "alice") {
  const scope = effectScope();
  const source = readFileSync(
    new URL("../src/composables/useChatWorkbench.ts", import.meta.url),
    "utf8",
  );
  const ast = ts.createSourceFile(
    "workbench.ts",
    source,
    ts.ScriptTarget.Latest,
    true,
  );
  let host;
  const context = vm.createContext({
    exports: {},
    computed,
    reactive,
    ref,
    watch,
    workbenchKey: Symbol(),
    getStoredDashboardUsername: () => username,
    chatPreferences: (update) => {
      const prefs = JSON.parse(
        storage.get(username) || '{"global":{},"sessions":{}}',
      );
      if (update) {
        update(prefs);
        storage.set(username, JSON.stringify(prefs));
      }
      return prefs;
    },
    provide: (_key, value) => {
      host = value;
    },
  });
  vm.runInContext(
    ts.transpile(
      ast.statements
        .filter((node) => !ts.isImportDeclaration(node))
        .map((node) => node.getText(ast))
        .join("\n"),
      { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    ),
    context,
  );
  const session = ref("one");
  const width = ref(null);
  const workbench = scope.run(() =>
    context.exports.useChatWorkbench(session, width),
  );
  return {
    ...workbench,
    session,
    width,
    host,
    storage,
    stop: () => scope.stop(),
  };
}

test("workbench tabs stay in their session and closed tabs do not reopen on message remount", () => {
  const { state, closeTab, openPage, session, host, stop } = setup();
  const first = {
    id: "pdf",
    title: "Plan.pdf",
    type: "view",
    target: "chat_workbench",
  };
  const second = { ...first, id: "markdown", title: "Notes.md" };
  const action = () => {};
  host.open(first, action, "live");
  host.open(second, action, "live");
  assert.equal(state.value.tabs.length, 2);
  assert.equal(state.value.activeId, "markdown");
  assert.equal(state.value.tabs[0].action, action);
  host.open(first, action, "live");
  assert.equal(state.value.activeId, "markdown");
  closeTab("markdown");
  assert.equal(state.value.activeId, "pdf");
  host.open(second, action, "live");
  assert.equal(state.value.tabs.length, 1);
  host.open(second, action);
  assert.equal(state.value.tabs.length, 2);
  state.value.open = false;
  session.value = "two";
  assert.equal(state.value, undefined);
  host.open({ ...first, id: "other" }, action, "live");
  assert.equal(state.value.tabs.length, 1);
  session.value = "one";
  assert.equal(state.value.tabs.length, 2);
  assert.equal(state.value.open, false);
  closeTab("pdf");
  closeTab("markdown");
  assert.equal(state.value.activeId, "");
  assert.equal(state.value.open, false);
  openPage();
  assert.equal(state.value.tabs[0].launcher, true);
  openPage({ plugin_name: "demo", name: "context", title: "Context" });
  assert.equal(state.value.tabs.length, 1);
  assert.equal(state.value.tabs[0].page.name, "context");
  session.value = "new-session";
  assert.equal(state.value, undefined);
  openPage({ plugin_name: "demo", name: "context", title: "Context" });
  assert.equal(state.value.tabs.length, 1);
  closeTab(state.value.activeId);
  assert.equal(state.value.tabs.length, 0);
  assert.equal(state.value.open, false);
  stop();
});

test("reload restores open tabs, order, active selection, hidden state, and width without reviving closed tabs", async () => {
  let app = setup();
  for (const id of ["first", "second", "closed"])
    app.host.open(
      {
        type: "view",
        id,
        name: "preview",
        title: id,
        data: { secret: "never persist" },
        html: "never persist",
        base_url: "token",
      },
      () => {},
      "live",
    );
  app.closeTab("closed");
  app.state.value.activeId = "first";
  app.state.value.open = false;
  app.width.value = 650;
  await nextTick();
  const { storage } = app;
  assert.ok(!storage.get("alice").includes("never persist"));
  assert.ok(!storage.get("alice").includes("token"));
  app.stop();
  app = setup(storage);
  assert.deepEqual(
    Array.from(app.state.value.tabs, (tab) => tab.part.id),
    ["first", "second"],
  );
  assert.equal(app.state.value.activeId, "first");
  assert.equal(app.state.value.open, false);
  assert.equal(app.width.value, 650);
  const action = () => {};
  for (const id of ["closed", "second", "first", "older-history"])
    app.host.open({ type: "view", id, title: id }, action, "history");
  assert.equal(app.state.value.tabs.length, 2);
  assert.equal(app.state.value.activeId, "first");
  assert.equal(app.state.value.open, false);
  assert.equal(app.state.value.tabs[0].action, action);
  app.host.open({ type: "view", id: "closed" }, action, "live");
  assert.equal(app.state.value.tabs.length, 2);
  app.host.open({ type: "view", id: "closed" }, action);
  assert.equal(app.state.value.activeId, "closed");
  assert.equal(app.state.value.open, true);
  app.host.open({ type: "view", id: "new-result" }, action, "live");
  assert.equal(app.state.value.activeId, "new-result");
  await nextTick();
  app.stop();
});

test("resident pages and launcher tabs restore independently for each session", async () => {
  let app = setup();
  const context = { plugin_name: "demo", name: "context", title: "Context" };
  app.host.open(
    { type: "view", id: "file", title: "Plan.pdf" },
    () => {},
    "live",
  );
  app.openPage(context);
  app.openPage({ plugin_name: "demo", name: "notes", title: "Notes" });
  app.closeTab("page:demo:notes");
  app.state.value.open = false;
  app.session.value = "two";
  assert.equal(app.state.value, undefined);
  app.openPage(context);
  app.openPage();
  assert.equal(app.state.value.activeId, "workbench:new");
  assert.equal(app.state.value.open, true);
  app.session.value = "one";
  assert.equal(app.state.value.activeId, "page:demo:context");
  assert.equal(app.state.value.open, false);
  await nextTick();
  const { storage } = app;
  app.stop();
  app = setup(storage);
  assert.deepEqual(
    Array.from(app.state.value.tabs, (tab) => tab.part.id),
    ["file", "page:demo:context"],
  );
  assert.equal(app.state.value.tabs[1].page.name, "context");
  assert.equal(app.state.value.activeId, "page:demo:context");
  assert.equal(app.state.value.open, false);
  app.closeTab("page:demo:context");
  assert.equal(app.state.value.activeId, "file");
  app.session.value = "two";
  assert.equal(app.state.value.tabs.length, 2);
  assert.equal(app.state.value.tabs[0].page.name, "context");
  assert.equal(app.state.value.tabs[1].launcher, true);
  assert.equal(app.state.value.activeId, "workbench:new");
  assert.equal(app.state.value.open, true);
  await nextTick();
  app.stop();
  app = setup(storage);
  assert.equal(app.state.value.tabs.length, 1);
  assert.equal(app.state.value.activeId, "file");
  app.stop();
  const other = setup(storage, "bob");
  assert.equal(other.state.value, undefined);
  other.stop();
});

test("legacy global pages belong only to the new-chat workspace", async () => {
  const storage = new Map([
    [
      "alice",
      JSON.stringify({
        global: {
          workbench: {
            tabs: [
              {
                id: "page:demo:context",
                plugin_name: "demo",
                name: "context",
                title: "Context",
              },
            ],
            activeId: "page:demo:context",
            open: true,
            width: 600,
          },
        },
        sessions: {},
      }),
    ],
  ]);
  let app = setup(storage);
  assert.equal(app.state.value, undefined);
  app.session.value = "";
  assert.equal(app.state.value.tabs[0].page.name, "context");
  assert.equal(app.state.value.open, true);
  app.closeTab("page:demo:context");
  app.openPage();
  app.session.value = "two";
  assert.equal(app.state.value, undefined);
  await nextTick();
  app.stop();
  app = setup(storage);
  app.session.value = "";
  assert.equal(app.state.value.tabs.length, 1);
  assert.equal(app.state.value.tabs[0].launcher, true);
  assert.equal(app.state.value.activeId, "workbench:new");
  assert.equal(app.width.value, 600);
  app.stop();
});

test("only the latest view list request updates the workbench", async () => {
  const { descriptor } = parse(
    readFileSync(
      new URL("../src/components/chat/ChatWorkbench.vue", import.meta.url),
      "utf8",
    ),
  );
  const block = descriptor.scriptSetup.content.match(
    /const views = ref[\s\S]*?\r?\n}\r?\n/,
  )[0];
  const responses = [];
  const context = vm.createContext({
    ref,
    fetchWithAuth: () => new Promise((resolve) => responses.push(resolve)),
  });
  vm.runInContext(
    ts.transpile(`${block}\nthis.state = { views, viewsLoading, viewsFailed, loadViews };`, {
      target: ts.ScriptTarget.ES2022,
    }),
    context,
  );
  const { views, viewsLoading, loadViews } = context.state;
  const reply = (data) => ({ ok: true, json: async () => ({ data }) });
  // Open, close and reopen the workbench: the first request answers last.
  const first = loadViews();
  const second = loadViews();
  responses[1](reply([{ name: "context" }]));
  await second;
  responses[0](reply([]));
  await first;
  assert.equal(views.value.length, 1, "an older empty list does not hide +");
  assert.equal(viewsLoading.value, false);
});

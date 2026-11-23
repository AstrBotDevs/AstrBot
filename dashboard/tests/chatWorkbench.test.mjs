import assert from "node:assert/strict";
import { test } from "vitest";
import { inject, nextTick, ref } from "vue";
import { useChatWorkbench } from "../src/composables/useChatWorkbench.ts";
import { CHAT_PREFERENCES_KEY } from "../src/utils/chatPreferences.ts";
import { workbenchKey } from "../src/utils/chatViews.ts";
import { mountComposable } from "./helpers/mountComposable.mjs";

function setup(storage = new Map(), username = "alice") {
  localStorage.clear();
  localStorage.setItem("user", username);
  localStorage.setItem(
    CHAT_PREFERENCES_KEY,
    JSON.stringify({
      version: 1,
      users: Object.fromEntries([...storage].map(([user, value]) => [user, JSON.parse(value)])),
    }),
  );
  const session = ref("one");
  const width = ref(null);
  const app = mountComposable(() => useChatWorkbench(session, width), {
    childSetup: () => inject(workbenchKey),
  });
  function syncStorage() {
    const preferences = JSON.parse(localStorage.getItem(CHAT_PREFERENCES_KEY));
    storage.clear();
    for (const [user, value] of Object.entries(preferences.users)) storage.set(user, JSON.stringify(value));
    return storage;
  }
  return {
    ...app.result,
    session,
    width,
    host: app.child,
    get storage() {
      return syncStorage();
    },
    stop: () => {
      app.unmount();
      syncStorage();
    },
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
  app.host.open({ type: "view", id: "file", title: "Plan.pdf" }, () => {}, "live");
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

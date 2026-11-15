import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { registerHooks } from "node:module";
import { compileScript, parse } from "vue/compiler-sfc";
import ts from "typescript";
import * as vue from "vue";
import * as pinia from "pinia";

// CSS is irrelevant to timer tests; keep the actual Vuetify component logic.
registerHooks({
  load(url, context, nextLoad) {
    if (url.endsWith(".css"))
      return { format: "module", source: "", shortCircuit: true };
    return nextLoad(url, context);
  },
});
const { VSnackbar } = await import("vuetify/components/VSnackbar");
const { createVuetify } = await import("vuetify");

const read = (path) =>
  readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");
const documentsPath = "views/knowledge-base/components/DocumentsTab.vue";
const detailPath = "views/knowledge-base/KBDetail.vue";

function evaluate(source, imports) {
  const exports = {};
  vm.runInNewContext(
    ts.transpile(source, {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
    }),
    {
      exports,
      require: (name) => {
        assert.ok(name in imports, `Unexpected import: ${name}`);
        return name.endsWith(".vue")
          ? { default: imports[name] }
          : imports[name];
      },
      console: { error() {}, warn() {} },
      FormData,
      window: imports.window,
      clearInterval: imports.window?.clearInterval,
    },
  );
  return exports;
}

function component(path, imports, exposed = "") {
  const source = read(path).replace(
    "</script>",
    `\ndefineExpose({ ${exposed} })\n</script>`,
  );
  const { descriptor } = parse(source, { filename: path });
  return evaluate(
    compileScript(descriptor, { id: path, inlineTemplate: true }).content,
    imports,
  ).default;
}

// Use Vue's real renderer/lifecycle with an in-memory host; no server or user data is touched.
function host() {
  const node = (type, text = "") => ({
    type,
    text,
    children: [],
    props: {},
    parent: null,
  });
  const renderer = vue.createRenderer({
    createElement: (type) => node(type),
    createText: (text) => node("text", text),
    createComment: (text) => node("comment", text),
    setText: (el, text) => {
      el.text = text;
    },
    setElementText: (el, text) => {
      el.text = text;
      el.children = [];
    },
    parentNode: (el) => el.parent,
    nextSibling: (el) =>
      el.parent?.children[el.parent.children.indexOf(el) + 1] || null,
    patchProp: (el, key, _old, value) => {
      el.props[key] = value;
    },
    insert(el, parent, anchor = null) {
      if (el.parent)
        el.parent.children.splice(el.parent.children.indexOf(el), 1);
      el.parent = parent;
      const index = anchor ? parent.children.indexOf(anchor) : -1;
      parent.children.splice(index < 0 ? parent.children.length : index, 0, el);
    },
    remove(el) {
      if (el.parent)
        el.parent.children.splice(el.parent.children.indexOf(el), 1);
      el.parent = null;
    },
  });
  return { renderer, root: node("root") };
}

async function setup(t, overrides = {}, realSnackbar = false) {
  let poll,
    finishRefresh,
    kbRequests = 0,
    documentState,
    documentInstance,
    appState;
  const calls = [];
  const ok = (data) => ({ data: { status: "ok", data } });
  const api = {
    get: () =>
      ++kbRequests === 1
        ? Promise.resolve(ok({ kb_name: "Test" }))
        : new Promise((resolve) => {
            finishRefresh = () => resolve(ok({ kb_name: "Test" }));
          }),
    documents: async () => ok({ items: [], total: 0 }),
    uploadDocument: async (...args) => {
      calls.push(args);
      return ok({ task_id: "task", file_count: 1 });
    },
    importDocumentFromUrl: async (...args) => {
      calls.push(args);
      return ok({ task_id: "task", url: "https://example.test" });
    },
    task: async () =>
      ok({
        status: "completed",
        result: { success_count: 1, failed_count: 0 },
      }),
    deleteDocument: async (...args) => {
      calls.push(args);
      return ok({});
    },
    ...overrides,
  };
  let now = 0,
    nextTimer = 0;
  const timeouts = new Map();
  const oldWindow = globalThis.window;
  const oldShadowRoot = globalThis.ShadowRoot;
  if (realSnackbar) {
    globalThis.ShadowRoot = class {};
    globalThis.window = {
      setTimeout(callback, delay) {
        timeouts.set(++nextTimer, { callback, at: now + delay });
        return nextTimer;
      },
      clearTimeout(id) {
        timeouts.delete(id);
      },
      setInterval() {
        return -1;
      },
    };
  }
  const empty = { render: () => null };
  const timers = {
    setInterval: (callback) => {
      poll = callback;
      return 1;
    },
    clearInterval: () => {
      poll = undefined;
    },
    setTimeout: () => 1,
    clearTimeout() {},
  };
  const imports = {
    vue,
    pinia,
    window: timers,
    "@/api/v1": {
      knowledgeApi: api,
      providerApi: { listByProviderType: async () => ok([]) },
      configProfileApi: { get: async () => ok({ config: {} }) },
    },
    "vue-router": {
      useRouter: () => ({ push() {} }),
      useRoute: () => ({ params: { kbId: "test" } }),
    },
    "@/i18n/composables": {
      useI18n: () => ({ locale: vue.ref("en-US") }),
      useModuleI18n: () => ({ tm: (key) => key }),
    },
    "./TavilyKeyDialog.vue": empty,
    "./components/RetrievalTab.vue": empty,
    "./components/SettingsTab.vue": empty,
    "@/components/shared/WaitingForRestart.vue": empty,
    "@/components/shared/UpgradeRecoveryDialog.vue": empty,
  };
  imports["@/stores/toast"] = evaluate(read("stores/toast.js"), imports);
  imports["@/utils/toast"] = evaluate(read("utils/toast.js"), imports);
  const Documents = component(
    documentsPath,
    imports,
    "selectedFiles, uploadUrl, uploadFiles, uploadFromUrl, loadDocuments, onTavilyKeySet, deleteTarget, deleteDocument",
  );
  const setupDocuments = Documents.setup;
  Documents.setup = (props, context) => {
    documentInstance = vue.getCurrentInstance();
    return setupDocuments(props, {
      ...context,
      expose: (value) => {
        documentState = value;
        context.expose(value);
      },
    });
  };
  imports["./components/DocumentsTab.vue"] = Documents;
  const Detail = component(detailPath, imports);
  imports["vue-router"].RouterView = { render: () => vue.h(Detail) };
  const App = component("App.vue", imports, "snackbarShow");
  const setupApp = App.setup;
  App.setup = (props, context) =>
    setupApp(props, {
      ...context,
      expose: (value) => {
        appState = value;
        context.expose(value);
      },
    });
  const { renderer, root } = host();
  const app = renderer.createApp(App);
  const storePlugin = pinia.createPinia();
  app.use(storePlugin);
  if (realSnackbar) app.use(createVuetify({ components: { VSnackbar } }));
  // Vuetify controls are slot stubs; actual App, KBDetail and DocumentsTab templates run.
  const template = read(documentsPath) + read(detailPath) + read("App.vue");
  for (const tag of new Set(template.match(/v-[a-z-]+(?=[\s>])/g))) {
    if (realSnackbar && tag === "v-snackbar") continue;
    app.component(tag, {
      props: ["modelValue"],
      setup:
        (props, { slots }) =>
        () =>
          tag === "v-snackbar" && !props.modelValue
            ? null
            : vue.h(tag, {}, slots.default?.()),
    });
  }
  app.mount(root);
  t.after(() => {
    // Restore the clock only after actual Vuetify unmount hooks have run.
    app.unmount();
    if (realSnackbar) {
      globalThis.window = oldWindow;
      globalThis.ShadowRoot = oldShadowRoot;
    }
  });
  const flush = async () => {
    for (let i = 0; i < 8; i++) {
      await Promise.resolve();
      await vue.nextTick();
    }
  };
  await flush();
  const store = imports["@/stores/toast"].useToastStore(storePlugin);
  return {
    api,
    calls,
    store,
    flush,
    root,
    realSnackbar,
    async advance(ms) {
      const end = now + ms;
      while (true) {
        const due = [...timeouts.entries()]
          .filter(([, timer]) => timer.at <= end)
          .sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        const [id, timer] = due;
        now = timer.at;
        timeouts.delete(id);
        timer.callback();
        await flush();
      }
      now = end;
      await flush();
    },
    get state() {
      return documentState;
    },
    get instance() {
      return documentInstance;
    },
    poll: async () => {
      assert.ok(poll, "Upload polling is active");
      await poll();
      await flush();
    },
    refresh: async () => {
      assert.ok(finishRefresh);
      finishRefresh();
      await flush();
    },
    dismiss: async () => {
      appState.snackbarShow.value = false;
      await flush();
    },
  };
}

function expectToast(env, message, color) {
  assert.equal(env.store.current?.message, message);
  assert.equal(env.store.current?.color, color);
  assert.equal(env.store.current?.location, "top center");
  assert.equal(env.store.current?.timeout, 3000);
  assert.equal(env.store.current?.closable, true);
  if (env.realSnackbar) return;
  const text = (el) => [el.text, ...el.children.map(text)].join(" ");
  const snackbars = (el) => [
    ...(el.type === "v-snackbar" ? [el] : []),
    ...el.children.flatMap(snackbars),
  ];
  assert.ok(
    snackbars(env.root).some((el) => text(el).includes(message)),
    "App renders the notification",
  );
}

async function selectUpload(env, mode) {
  if (mode === "file") {
    const file = new Blob(["temporary test document"]);
    file.name = "test.txt";
    env.state.selectedFiles.value = [file];
    await env.state.uploadFiles();
  } else {
    env.state.uploadUrl.value = "https://example.test";
    await env.state.uploadFromUrl();
  }
  await env.flush();
}

for (const mode of ["file", "url"]) {
  test(`${mode}: validation warns before making a request`, async (t) => {
    const env = await setup(t);
    await env.state[mode === "file" ? "uploadFiles" : "uploadFromUrl"]();
    await env.flush();
    expectToast(
      env,
      mode === "file" ? "upload.fileRequired" : "upload.urlRequired",
      "warning",
    );
    assert.equal(env.calls.length, 0);
  });

  for (const failedCount of [0, 1]) {
    test(`${mode}: completion survives KBDetail refresh unmount/remount (failures=${failedCount})`, async (t) => {
      const env = await setup(t, {
        task: async () => ({
          data: {
            status: "ok",
            data: {
              status: "completed",
              result: { success_count: 1, failed_count: failedCount },
            },
          },
        }),
      });
      await selectUpload(env, mode);
      expectToast(
        env,
        mode === "file"
          ? "正在后台上传 1 个文件..."
          : "正在从 URL 后台提取内容...",
        "primary",
      );
      const oldInstance = env.instance;
      await env.poll();
      assert.equal(
        oldInstance.isUnmounted,
        true,
        "Real parent loading branch unmounts DocumentsTab",
      );
      const message = failedCount
        ? "上传完成: 1 个成功, 1 个失败"
        : "成功上传 1 个文档";
      expectToast(env, message, failedCount ? "warning" : "success");
      await env.refresh();
      assert.notEqual(env.instance, oldInstance);
      assert.equal(env.instance.isUnmounted, false);
      expectToast(env, message, failedCount ? "warning" : "success");
      await env.dismiss();
      assert.equal(env.store.current, undefined);
    });
  }

  for (const failure of ["response", "fallback", "network"]) {
    test(`${mode}: upload ${failure} keeps original error message`, async (t) => {
      const env = await setup(t, {
        [mode === "file" ? "uploadDocument" : "importDocumentFromUrl"]:
          async () => {
            if (failure === "network")
              throw Object.assign(new Error("offline"), {
                response: { data: { message: "URL request failed" } },
              });
            return {
              data: {
                status: "error",
                message: failure === "response" ? "Upload rejected" : undefined,
              },
            };
          },
      });
      await selectUpload(env, mode);
      expectToast(
        env,
        failure === "response"
          ? "Upload rejected"
          : mode === "url" && failure === "network"
          ? "URL request failed"
          : "documents.uploadFailed",
        "error",
      );
    });
  }
}

for (const error of ["Task failed", undefined]) {
  test(`background task failure keeps error details (${error})`, async (t) => {
    const env = await setup(t, {
      task: async () => ({
        data: { status: "ok", data: { status: "failed", error } },
      }),
    });
    await selectUpload(env, "file");
    await env.dismiss();
    await env.poll();
    expectToast(env, `上传失败: ${error || "未知错误"}`, "error");
  });
}

test("list exception and Tavily configuration use global feedback", async (t) => {
  const env = await setup(t);
  env.api.documents = async () => {
    throw new Error("offline");
  };
  await env.state.loadDocuments();
  await env.flush();
  expectToast(env, "加载文档列表失败", "error");
  await env.dismiss();
  env.state.onTavilyKeySet();
  await env.flush();
  expectToast(env, "Tavily API Key 配置成功", "success");
});

for (const outcome of ["ok", "error", "network"]) {
  test(`single deletion retains feedback and refresh behavior (${outcome})`, async (t) => {
    const env = await setup(t, {
      deleteDocument: async (...args) => {
        env.calls.push(args);
        if (outcome === "network") throw new Error("offline");
        return { data: { status: outcome, message: "Delete rejected" } };
      },
    });
    const oldInstance = env.instance;
    env.state.deleteTarget.value = { doc_id: "temporary-test" };
    await env.state.deleteDocument();
    await env.flush();
    expectToast(
      env,
      outcome === "ok"
        ? "documents.deleteSuccess"
        : outcome === "error"
        ? "Delete rejected"
        : "documents.deleteFailed",
      outcome === "ok" ? "success" : "error",
    );
    assert.equal(env.calls.length, 1);
    assert.equal(oldInstance.isUnmounted, outcome === "ok");
  });
}

for (const mode of ["file", "url"]) {
  for (const outcome of ["success", "partial", "failed"]) {
    test(`${mode}: actual Vuetify immediately replaces the start toast and times out (${outcome})`, async (t) => {
      const env = await setup(
        t,
        {
          task: async () => ({
            data: {
              status: "ok",
              data:
                outcome === "failed"
                  ? { status: "failed", error: "Task failed" }
                  : {
                      status: "completed",
                      result: {
                        success_count: 1,
                        failed_count: outcome === "partial" ? 1 : 0,
                      },
                    },
            },
          }),
        },
        true,
      );
      await selectUpload(env, mode);
      await env.advance(1000);
      await env.poll();
      const message =
        outcome === "failed"
          ? "上传失败: Task failed"
          : outcome === "partial"
          ? "上传完成: 1 个成功, 1 个失败"
          : "成功上传 1 个文档";
      expectToast(
        env,
        message,
        outcome === "failed"
          ? "error"
          : outcome === "partial"
          ? "warning"
          : "success",
      );
      if (outcome !== "failed") await env.refresh();
      // The replaced start toast's old timer must not close the completion toast.
      await env.advance(2000);
      assert.equal(env.store.current.message, message);
      await env.advance(999);
      assert.equal(env.store.current.message, message);
      await env.advance(1);
      assert.equal(env.store.current, undefined);
    });
  }
}

test("actual Vuetify gives queued identical messages their own timeout", async (t) => {
  const env = await setup(t, {}, true);
  env.store.add({ message: "Same message" });
  env.store.add({ message: "Same message" });
  await env.flush();
  const firstId = env.store.current.id;
  await env.advance(3000);
  assert.equal(env.store.current.message, "Same message");
  assert.notEqual(env.store.current.id, firstId);
  await env.advance(2999);
  assert.ok(env.store.current);
  await env.advance(1);
  assert.equal(env.store.current, undefined);
});

test("actual Vuetify restarts timing after manual dismissal", async (t) => {
  const env = await setup(t, {}, true);
  env.store.add({ message: "First" });
  env.store.add({ message: "Second" });
  await env.flush();
  await env.advance(1000);
  await env.dismiss();
  assert.equal(env.store.current.message, "Second");
  await env.advance(2000);
  assert.equal(env.store.current.message, "Second");
  await env.advance(1000);
  assert.equal(env.store.current, undefined);
});

test("an expired start toast still allows a later completion message", async (t) => {
  const env = await setup(t, {}, true);
  await selectUpload(env, "file");
  await env.advance(3000);
  assert.equal(env.store.current, undefined);
  await env.poll();
  expectToast(env, "成功上传 1 个文档", "success");
  await env.advance(3000);
  assert.equal(env.store.current, undefined);
});

test("notification groups preserve unrelated queue entries", async (t) => {
  const env = await setup(t, {}, true);
  env.store.add({ message: "Unrelated" });
  env.store.add({ message: "Upload A", group: "a" });
  env.store.add({ message: "Upload B", group: "b" });
  env.store.add({ message: "Completed A", group: "a" });
  await env.flush();
  assert.equal(env.store.current.message, "Unrelated");
  await env.advance(3000);
  assert.equal(env.store.current.message, "Completed A");
  await env.advance(3000);
  assert.equal(env.store.current.message, "Upload B");
  await env.advance(3000);
  assert.equal(env.store.current, undefined);
});

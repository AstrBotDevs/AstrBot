import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { compileScript, parse } from "vue/compiler-sfc";
import * as vue from "vue";

test("chat model reset respects session boundaries and survives unavailable storage", async (t) => {
  const storage = new Map([
    ["selectedProvider", "provider-a"],
    ["selectedProviderModel", "model-a"],
    [
      "chat.sessionProvider.a",
      JSON.stringify({ providerId: "provider-a", modelName: "model-a" }),
    ],
    [
      "chat.sessionProvider.b",
      JSON.stringify({ providerId: "provider-b", modelName: "model-b" }),
    ],
    ["astrbot-locale", "en-US"],
    ["token", "test-token"],
  ]);
  let storageUnavailable = false;
  const requests = [];
  const routes = [];
  const context = vm.createContext({
    exports: {},
    require: (id) => {
      if (id === "vue") return vue;
      if (id.includes("useProviderModelSelection")) return context.exports;
      return { default: menuStub };
    },
    window: { clearTimeout() {} },
    console,
    ...vue,
    currSessionId: vue.ref("a"),
    selectedTokenProviderId: vue.ref(""),
    // Deliberately emulate child props that have not updated in the same tick.
    inputRef: {
      value: {
        getCurrentSelection: () => ({
          providerId: "provider-a",
          modelName: "model-a",
        }),
      },
    },
    router: {
      push: async (path) => {
        routes.push(path);
      },
    },
    authApi: { logout: async () => {} },
    showChatWorkspace() {},
    selectedProjectId: vue.ref(null),
    selectedProject: vue.ref(null),
    replyTarget: vue.ref(null),
    route: { path: "/chat/a" },
    basePath: () => "/chat",
    loadedSessions: { a: true, b: true },
    scrollToBottom() {},
    focusChatInput: async () => {},
    canSend: { value: true },
    activeDraftSessionId: "a",
    draft: vue.ref("Hello"),
    buildOutgoingParts: (text) => [{ type: "plain", text }],
    sending: vue.ref(false),
    crypto: { randomUUID: () => "message-id" },
    createLocalExchange: () => ({ userRecord: {}, botRecord: {} }),
    updateTitleFromText() {},
    draftSaveTimer: null,
    writeChatDraft() {},
    clearStaged() {},
    sendMessageStream: (payload) => {
      requests.push(payload);
    },
    transportMode: { value: "sse" },
    enableStreaming: { value: true },
    enableReasoning: { value: false },
  });
  Object.defineProperty(context, "localStorage", {
    get() {
      if (storageUnavailable) throw new Error("Storage access denied");
      return {
        getItem: (key) => storage.get(key) ?? null,
        setItem: (key, value) => storage.set(key, value),
        removeItem: (key) => storage.delete(key),
        key: (index) => [...storage.keys()][index] ?? null,
        get length() {
          return storage.size;
        },
      };
    },
  });
  const composable = readFileSync(
    new URL("../src/composables/useProviderModelSelection.ts", import.meta.url),
    "utf8",
  );
  vm.runInContext(
    ts.transpile(composable, { module: ts.ModuleKind.CommonJS }),
    context,
  );
  const selection = context.exports.useProviderModelSelection();
  Object.assign(context, {
    useProviderModelSelection: context.exports.useProviderModelSelection,
    currentProviderId: selection.selectedProviderId,
    currentModelName: selection.selectedModelName,
    setProviderSelection: selection.setSelection,
  });

  const chat = parse(
    readFileSync(
      new URL("../src/components/chat/Chat.vue", import.meta.url),
      "utf8",
    ),
  ).descriptor.scriptSetup.content;
  const ast = ts.createSourceFile(
    "Chat.ts",
    chat,
    ts.ScriptTarget.Latest,
    true,
  );
  const names = new Set([
    "getSelectedProviderSelection",
    "readSessionProviderSelection",
    "writeSessionProviderSelection",
    "selectSession",
    "sendCurrentMessage",
  ]);
  const statements = ast.statements.filter((node) => {
    if (ts.isFunctionDeclaration(node)) return names.has(node.name?.text);
    const text = node.getText(ast);
    return (
      text.startsWith("const SESSION_PROVIDER_STORAGE_PREFIX =") ||
      text.startsWith("watch([currentProviderId, currentModelName]")
    );
  });
  assert.equal(statements.length, names.size + 2);
  vm.runInContext(
    ts.transpile(statements.map((node) => node.getText(ast)).join("\n")),
    context,
  );

  const auth = ts.createSourceFile(
    "auth.ts",
    readFileSync(new URL("../src/stores/auth.ts", import.meta.url), "utf8"),
    ts.ScriptTarget.Latest,
    true,
  );
  let logout;
  const visit = (node) => {
    if (ts.isMethodDeclaration(node) && node.name.getText(auth) === "logout")
      logout = node;
    ts.forEachChild(node, visit);
  };
  visit(auth);
  assert.ok(logout);
  vm.runInContext(
    ts.transpile(`function logout() ${logout.body.getText(auth)}`),
    context,
  );

  let menuProps;
  let menuEmit;
  const menuStub = vue.defineComponent({
    props: ["modelValue", "fallbackModel", "allowEmpty"],
    emits: ["update:modelValue", "select"],
    setup(props, { emit, expose }) {
      menuProps = props;
      menuEmit = emit;
      expose({
        getCurrentSelection: () => ({
          providerId: props.modelValue,
          modelName: props.fallbackModel,
        }),
      });
      return () => null;
    },
  });
  const descriptor = parse(
    readFileSync(
      new URL("../src/components/chat/ProviderModelMenu.vue", import.meta.url),
      "utf8",
    ),
  ).descriptor;
  const component = compileScript(descriptor, {
    id: "model-reset-test",
    inlineTemplate: true,
  });
  const componentContext = vm.createContext({
    exports: {},
    require: context.require,
  });
  vm.runInContext(
    ts.transpile(component.content, { module: ts.ModuleKind.CommonJS }),
    componentContext,
  );
  const renderer = vue.createRenderer({
    createComment: () => ({}),
    insert() {},
    remove() {},
    parentNode() {},
    nextSibling() {},
  });
  const app = renderer.createApp(componentContext.exports.default);
  app.mount({});
  t.after(() => app.unmount());

  await t.test(
    "selecting and clearing updates the active session without sending",
    async () => {
      menuEmit("update:modelValue", "provider-c");
      menuEmit("select", { id: "provider-c", model: "model-c" });
      await vue.nextTick();
      assert.equal(
        JSON.parse(storage.get("chat.sessionProvider.a")).modelName,
        "model-c",
      );
      menuEmit("update:modelValue", "");
      menuEmit("select", null);
      await vue.nextTick();
      assert.equal(storage.has("chat.sessionProvider.a"), false);
      assert.equal(storage.has("selectedProvider"), false);
      assert.equal(storage.has("selectedProviderModel"), false);
      assert.equal(
        JSON.parse(storage.get("chat.sessionProvider.b")).providerId,
        "provider-b",
      );
      menuEmit("update:modelValue", "provider-a");
      menuEmit("select", { id: "provider-a", model: "model-a" });
      await vue.nextTick();
    },
  );

  await t.test(
    "the rendered chat menu enables clearing; immediate send uses the configured default",
    async () => {
      assert.equal(menuProps.allowEmpty, true);
      assert.equal(menuProps.modelValue, "provider-a");
      menuEmit("update:modelValue", "");
      menuEmit("select", null);
      // Send before Vue has flushed child props or the persistence watcher.
      await context.sendCurrentMessage();
      assert.equal(requests[0].selectedProvider, "");
      assert.equal(requests[0].selectedModel, "");
      assert.equal(selection.selectedModelName.value, "");
      assert.equal(storage.has("selectedProvider"), false);
      assert.equal(storage.has("selectedProviderModel"), false);
      assert.equal(storage.has("chat.sessionProvider.a"), false);
      assert.equal(
        JSON.parse(storage.get("chat.sessionProvider.b")).providerId,
        "provider-b",
      );
      assert.equal(menuProps.modelValue, "");
    },
  );

  await t.test(
    "switching B to cleared A restores the default and preserves B",
    async () => {
      await context.selectSession("b");
      await vue.nextTick();
      assert.equal(selection.selectedProviderId.value, "provider-b");
      assert.equal(selection.selectedModelName.value, "model-b");
      await context.selectSession("a");
      await vue.nextTick();
      assert.equal(selection.selectedProviderId.value, "");
      assert.equal(selection.selectedModelName.value, "");
      assert.equal(storage.has("chat.sessionProvider.a"), false);
      assert.equal(
        JSON.parse(storage.get("chat.sessionProvider.b")).providerId,
        "provider-b",
      );
      // A fresh module reads the same cleared selection after a page reload.
      const reloadContext = vm.createContext({
        exports: {},
        require: context.require,
        window: {},
        localStorage: context.localStorage,
      });
      vm.runInContext(
        ts.transpile(composable, { module: ts.ModuleKind.CommonJS }),
        reloadContext,
      );
      assert.equal(
        reloadContext.exports.useProviderModelSelection().selectedProviderId
          .value,
        "",
      );
    },
  );

  await t.test(
    "logout clears every session and shared refs without touching unrelated preferences",
    async () => {
      selection.setSelection("provider-b", "model-b");
      await vue.nextTick();
      context.logout.call({ username: "test-user" });
      await vue.nextTick();
      assert.equal(selection.selectedProviderId.value, "");
      assert.equal(selection.selectedModelName.value, "");
      assert.equal(menuProps.modelValue, "");
      assert.deepEqual([...storage], [["astrbot-locale", "en-US"]]);
      assert.equal(routes.at(-1), "/auth/login");
    },
  );

  await t.test(
    "a throwing localStorage getter cannot block reset, sending, or logout",
    async () => {
      selection.setSelection("provider-a", "model-a");
      storageUnavailable = true;
      assert.doesNotThrow(() => selection.setSelection("", "stale-model"));
      assert.equal(selection.selectedProviderId.value, "");
      assert.equal(selection.selectedModelName.value, "");
      await context.sendCurrentMessage();
      assert.equal(requests.at(-1).selectedProvider, "");
      assert.equal(requests.at(-1).selectedModel, "");
      assert.doesNotThrow(() => context.logout.call({ username: "test-user" }));
      assert.equal(routes.at(-1), "/auth/login");
      const restrictedContext = vm.createContext({
        exports: {},
        require: context.require,
        window: {},
      });
      Object.defineProperty(restrictedContext, "localStorage", {
        get() {
          throw new Error("Storage access denied");
        },
      });
      vm.runInContext(
        ts.transpile(composable, { module: ts.ModuleKind.CommonJS }),
        restrictedContext,
      );
      assert.doesNotThrow(() =>
        restrictedContext.exports.useProviderModelSelection(),
      );
    },
  );
});

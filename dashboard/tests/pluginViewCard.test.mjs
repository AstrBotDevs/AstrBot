import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { ref } from "vue";

for (const authorized of [true, false]) {
  test(`card loads the shared SDK through host authentication: ${authorized}`, async () => {
    let mount;
    const requests = [];
    const elements = [];
    const sdk = readFileSync(
      new URL("../../astrbot/dashboard/plugin_page_bridge.js", import.meta.url),
      "utf8",
    );
    const context = vm.createContext({
      exports: {},
      axios: { create: () => ({}) },
      localStorage: {
        getItem: (key) => (key === "token" ? "test-dashboard-token" : null),
      },
      window: {
        location: new URL("https://dashboard.test/"),
        addEventListener() {},
        async fetch(url, init) {
          requests.push({ url, headers: init?.headers });
          if (
            !authorized ||
            init?.headers?.get("Authorization") !==
              "Bearer test-dashboard-token"
          ) {
            return new Response("Unauthorized", { status: 401 });
          }
          return url.endsWith("bridge-sdk.js")
            ? new Response(sdk)
            : Response.json({
                data: {
                  html: "<html><head></head><body>Reading list</body></html>",
                  base_url: "/scoped-view-assets/",
                  data: { books: [{ title: "Example" }] },
                  revision: 1,
                },
              });
        },
      },
      DOMParser: class {
        parseFromString() {
          return {
            querySelectorAll: () => [],
            createElement: (tag) => ({ tag }),
            head: { prepend: (...nodes) => elements.push(...nodes) },
            documentElement: {
              get outerHTML() {
                return JSON.stringify(elements);
              },
            },
          };
        }
      },
      URL,
      Request,
      Headers,
      crypto: { randomUUID: () => "test-session" },
      ref,
      defineProps: () => ({ part: { id: "test-view", name: "reading" } }),
      inject() {},
      watch() {},
      onMounted: (callback) => (mount = callback),
      onBeforeUnmount() {},
      useI18n: () => ({ locale: ref("zh-CN") }),
      useModuleI18n: () => ({ tm: (key) => key }),
      useTheme: () => ({
        global: { current: ref({ dark: false, colors: {} }) },
      }),
      viewActionKey: Symbol(),
    });
    for (const path of [
      "../src/api/http.ts",
      "../src/utils/pluginI18n.js",
      "../src/components/chat/message_list_comps/PluginViewCard.vue",
    ]) {
      let source = readFileSync(new URL(path, import.meta.url), "utf8");
      if (path.endsWith(".vue")) {
        source = source.match(
          /<script setup lang="ts">([\s\S]*?)<\/script>/,
        )[1];
      }
      const ast = ts.createSourceFile(
        "source.ts",
        source,
        ts.ScriptTarget.Latest,
        true,
      );
      const code = ast.statements
        .filter((node) => !ts.isImportDeclaration(node))
        .map((node) => node.getText(ast))
        .join("\n");
      vm.runInContext(
        ts.transpile(code, {
          module: ts.ModuleKind.CommonJS,
          target: ts.ScriptTarget.ES2022,
        }),
        context,
      );
    }
    await mount();
    assert.deepEqual(
      requests.map(({ url }) => url),
      ["/api/v1/chat/views/test-view", "/api/plugin/page/bridge-sdk.js"],
    );
    for (const request of requests) {
      assert.equal(
        request.headers.get("Authorization"),
        "Bearer test-dashboard-token",
      );
    }
    assert.equal(vm.runInContext("error.value", context), !authorized);
    if (authorized) {
      assert.equal(
        elements[0].href,
        "https://dashboard.test/scoped-view-assets/",
      );
      assert.equal(elements[1].tag, "script");
      assert.equal(elements[1].textContent, sdk);
      assert.equal(elements[1].src, undefined);
      assert.ok(
        !vm
          .runInContext("srcdoc.value", context)
          .includes("test-dashboard-token"),
      );
    } else {
      assert.equal(vm.runInContext("srcdoc.value", context), "");
      assert.equal(elements.length, 0);
    }
  });
}

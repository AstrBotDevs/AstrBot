import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import * as vue from "vue";
import { compileScript, parse } from "vue/compiler-sfc";
import { renderToString } from "vue/server-renderer";

const source = readFileSync(
  new URL(
    "../src/components/chat/message_list_comps/ReasoningBlock.vue",
    import.meta.url,
  ),
  "utf8",
);
const { descriptor } = parse(source);

test("reasoning loading and failures are visible without replacing the activity title", async () => {
  const script = compileScript(descriptor, {
    id: "reasoning",
    inlineTemplate: true,
  });
  const context = vm.createContext({
    exports: {},
    require: (name) => {
      if (name === "vue") return vue;
      if (name === "@/i18n/composables") {
        return { useModuleI18n: () => ({ tm: (key) => key }) };
      }
      if (name === "@/composables/useMessages") {
        return {
          reasoningActivityCounts: () => ({}),
          reasoningActivityTitle: () => "Activity summary",
        };
      }
      if (name === "@lucide/vue") return { ChevronRight: () => vue.h("span") };
      if (name.endsWith(".vue")) return { default: () => vue.h("div") };
      throw new Error(`Unexpected import: ${name}`);
    },
  });
  vm.runInContext(
    ts.transpile(script.content, { module: ts.ModuleKind.CommonJS }),
    context,
  );
  for (const status of ["unloaded", "loading", "error", "loaded"]) {
    const app = vue.createSSRApp(context.exports.default, {
      hasReasoning: true,
      reasoningStatus: status,
      openInSidebar: true,
    });
    app.component("VProgressCircular", {
      setup:
        (_, { attrs }) =>
        () =>
          vue.h("progress", attrs),
    });
    app.component("VBtn", {
      setup:
        (_, { attrs, slots }) =>
        () =>
          vue.h("button", attrs, slots.default?.()),
    });
    const html = await renderToString(app);
    assert.match(html, /Activity summary/);
    assert.equal(html.includes("<progress"), status === "loading");
    assert.equal(/<button[^>]* disabled/.test(html), status === "loading");
    assert.equal(html.includes('aria-busy="true"'), status === "loading");
    assert.equal(html.includes('role="alert"'), status === "error");
    assert.equal(html.includes("reasoning.loadFailed"), status === "error");
    assert.equal(html.includes("actions.retry"), status === "error");
  }
});

test("reasoning actions ignore pending loads and allow retry after failure", () => {
  const ast = ts.createSourceFile(
    "ReasoningBlock.ts",
    descriptor.scriptSetup.content,
    ts.ScriptTarget.Latest,
    true,
  );
  const action = ast.statements.find(
    (node) =>
      ts.isFunctionDeclaration(node) &&
      node.name?.text === "handlePrimaryAction",
  );
  assert.ok(action);
  const events = [];
  const props = { hasReasoning: true, reasoningStatus: "unloaded" };
  const context = vm.createContext({
    props,
    emit: (event) => events.push(event),
    openInSidebar: { value: true },
    isExpanded: { value: false },
  });
  vm.runInContext(ts.transpile(action.getText(ast)), context);
  context.handlePrimaryAction();
  assert.deepEqual(events, ["load-reasoning"]);
  props.reasoningStatus = "loading";
  context.handlePrimaryAction();
  assert.deepEqual(events, ["load-reasoning"]);
  props.reasoningStatus = "error";
  context.handlePrimaryAction();
  assert.deepEqual(events, ["load-reasoning", "load-reasoning"]);
  props.reasoningStatus = "loaded";
  context.handlePrimaryAction();
  assert.equal(events.at(-1), "open");
  context.openInSidebar.value = false;
  context.handlePrimaryAction();
  assert.equal(context.isExpanded.value, true);
});

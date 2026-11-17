import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { computed, reactive, ref } from "vue";

test("workbench tabs stay in their session and closed tabs do not reopen on message remount", () => {
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
    workbenchKey: Symbol(),
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
      {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    ),
    context,
  );
  const session = ref("one");
  const { state, closeTab, openPage } = context.exports.useChatWorkbench(session);
  const first = {
    id: "pdf",
    title: "Plan.pdf",
    type: "view",
    target: "chat_workbench",
  };
  const second = { ...first, id: "markdown", title: "Notes.md" };
  const action = () => {};
  host.open(first, action, true);
  host.open(second, action, true);
  assert.equal(state.value.tabs.length, 2);
  assert.equal(state.value.activeId, "markdown");
  assert.equal(state.value.tabs[0].action, action);
  host.open(first, action, true);
  assert.equal(state.value.activeId, "markdown");
  closeTab("markdown");
  assert.equal(state.value.activeId, "pdf");
  host.open(second, action, true);
  assert.equal(state.value.tabs.length, 1);
  host.open(second, action);
  assert.equal(state.value.tabs.length, 2);
  state.value.open = false;
  session.value = "two";
  assert.equal(state.value, undefined);
  host.open({ ...first, id: "other" }, action, true);
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
  openPage({plugin_name: "demo", name: "context", title: "Context"});
  assert.equal(state.value.tabs.length, 1);
  assert.equal(state.value.tabs[0].page.name, "context");
  session.value = "new-session";
  assert.equal(state.value.tabs.length, 1);
  assert.equal(state.value.open, true);
  openPage({plugin_name: "demo", name: "context", title: "Context"});
  assert.equal(state.value.tabs.length, 1);
  closeTab(state.value.activeId);
  assert.equal(state.value, undefined);
});

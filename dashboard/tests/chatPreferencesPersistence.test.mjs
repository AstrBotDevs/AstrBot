import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { effectScope, nextTick, reactive, ref, watch } from "vue";

const components = ["Chat.vue", "StandaloneChat.vue"];
const preferences = ["enableStreaming", "enableReasoning", "sendShortcut"];

function mountPreferences(component, storage, t) {
  const source = readFileSync(
    new URL(`../src/components/chat/${component}`, import.meta.url),
    "utf8",
  )
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const ast = ts.createSourceFile(
    component,
    source,
    ts.ScriptTarget.Latest,
    true,
  );
  const statements = ast.statements.filter((node) => {
    if (ts.isVariableStatement(node)) {
      return node.declarationList.declarations.some((declaration) =>
        preferences.includes(declaration.name.getText(ast)),
      );
    }
    return (
      ts.isExpressionStatement(node) &&
      ts.isCallExpression(node.expression) &&
      node.expression.expression.getText(ast) === "watch" &&
      (preferences.includes(node.expression.arguments[0]?.getText(ast)) ||
        (node.expression.arguments[0]?.getText(ast) === "() => props.active" &&
          node.expression.arguments[1]
            ?.getText(ast)
            .includes("enableStreaming.value")))
    );
  });
  const context = vm.createContext({
    ref,
    watch,
    props: reactive({ active: true }),
    localStorage: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
    },
  });
  const scope = effectScope();
  t.after(() => scope.stop());
  return scope.run(() =>
    vm.runInContext(
      ts.transpile(
        statements.map((node) => node.getText(ast)).join("\n") +
          "\n({ enableStreaming, enableReasoning, sendShortcut, props });",
      ),
      context,
    ),
  );
}

test("retained Chat.vue refreshes preferences when it becomes active again", async (t) => {
  const storage = new Map([["chat.transportMode", "websocket"]]);
  const mainChat = mountPreferences("Chat.vue", storage, t);
  for (const [streaming, reasoning, shortcut] of [
    [false, false, "shift_enter"],
    [true, true, "enter"],
  ]) {
    mainChat.props.active = false;
    await nextTick();
    const testChat = mountPreferences("StandaloneChat.vue", storage, t);
    testChat.enableStreaming.value = streaming;
    testChat.enableReasoning.value = reasoning;
    testChat.sendShortcut.value = shortcut;
    await nextTick();

    mainChat.props.active = true;
    await nextTick();
    assert.equal(mainChat.enableStreaming.value, streaming);
    assert.equal(mainChat.enableReasoning.value, reasoning);
    assert.equal(mainChat.sendShortcut.value, shortcut);
    assert.equal(storage.get("chat.transportMode"), "websocket");
  }
});

for (const component of components) {
  test(`${component} preserves the default chat preferences`, (t) => {
    const state = mountPreferences(component, new Map(), t);
    assert.equal(state.enableStreaming.value, true);
    assert.equal(state.enableReasoning.value, true);
    assert.equal(state.sendShortcut.value, "enter");
  });

  test(`${component} saves and restores chat preferences across entry points`, async (t) => {
    const storage = new Map([["chat.transportMode", "websocket"]]);
    const state = mountPreferences(component, storage, t);
    for (const [streaming, reasoning, shortcut] of [
      [false, false, "shift_enter"],
      [true, true, "enter"],
    ]) {
      state.enableStreaming.value = streaming;
      state.enableReasoning.value = reasoning;
      state.sendShortcut.value = shortcut;
      await nextTick();
      assert.equal(storage.get("chat.enableStreaming"), String(streaming));
      assert.equal(storage.get("chat.enableReasoning"), String(reasoning));
      assert.equal(storage.get("chat.sendShortcut"), shortcut);
      assert.equal(storage.get("chat.transportMode"), "websocket");
      for (const entryPoint of components) {
        const restored = mountPreferences(entryPoint, storage, t);
        assert.equal(restored.enableStreaming.value, streaming);
        assert.equal(restored.enableReasoning.value, reasoning);
        assert.equal(restored.sendShortcut.value, shortcut);
      }
    }
  });
}

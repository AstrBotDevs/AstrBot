import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";
import { effectScope, nextTick, ref, watch } from "vue";

// Runs Chat.vue's permission mode watcher on its own.
function harness() {
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
  const statements = ast.statements.filter(
    (node) =>
      ts.isExpressionStatement(node) &&
      /^watch\(\s*permissionMode,/.test(node.getText(ast)),
  );
  assert.equal(statements.length, 1);
  const permissionMode = ref("ask");
  const currSessionId = ref("a");
  const requests = [];
  const errors = [];
  const saved = [];
  const scope = effectScope();
  scope.run(() =>
    vm.runInNewContext(ts.transpile(statements[0].getText(ast)), {
      watch,
      permissionMode,
      currSessionId,
      Error,
      String,
      writeChatSessionPref: (...args) => saved.push(args),
      chatApi: {
        setPermissionMode: (...args) =>
          new Promise((resolve, reject) =>
            requests.push({ args, resolve, reject }),
          ),
      },
      toast: { error: (message) => errors.push(message) },
      tm: (key, params) => `${key}: ${params?.error}`,
    }),
  );
  return {
    permissionMode,
    currSessionId,
    requests,
    errors,
    saved,
    stop: () => scope.stop(),
  };
}

test("a mode change is saved and applied to the conversation that owned it", async () => {
  const h = harness();
  try {
    h.permissionMode.value = "full";
    h.currSessionId.value = "b";
    await nextTick();
    assert.deepEqual(
      h.requests.map((r) => r.args),
      [["a", "full"]],
    );
    assert.deepEqual(h.saved, [["a", "permission_mode", "full"]]);
    h.requests[0].reject(new Error("stale failure"));
    await new Promise(setImmediate);
    assert.deepEqual(h.errors, []);
  } finally {
    h.stop();
  }
});

test("a new conversation keeps the mode for its first send without a request", () => {
  const h = harness();
  try {
    h.currSessionId.value = "";
    h.permissionMode.value = "full";
    assert.deepEqual(h.saved, [["", "permission_mode", "full"]]);
    assert.equal(h.requests.length, 0);
  } finally {
    h.stop();
  }
});

for (const transport of [true, false]) {
  test(`a failed mode update is shown: transport error=${transport}`, async () => {
    const h = harness();
    try {
      h.permissionMode.value = "full";
      await nextTick();
      if (transport) h.requests[0].reject(new Error("offline"));
      else
        h.requests[0].resolve({ data: { status: "error", message: "denied" } });
      await new Promise(setImmediate);
      assert.equal(h.errors.length, 1);
      assert.match(h.errors[0], /permissionMode\.saveFailed: (offline|denied)/);
    } finally {
      h.stop();
    }
  });
}

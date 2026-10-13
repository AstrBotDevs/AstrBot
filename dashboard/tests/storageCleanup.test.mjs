import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { computed, ref } from "vue";
import { parse } from "vue/compiler-sfc";

const { descriptor } = parse(readFileSync(new URL("../src/components/shared/StorageCleanupPanel.vue", import.meta.url), "utf8"));
const ast = ts.createSourceFile("cleanup.js", descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true);

function setup({ confirmed = true, removedTraces = 3 } = {}) {
  const prompts = [];
  const requests = [];
  const notifications = [];
  const status = { logs: { size_bytes: 10 }, cache: { size_bytes: 20 }, traces: { size_bytes: 30 }, total_bytes: 60 };
  const context = vm.createContext({
    ref, computed, tm: (key, values) => ({ key, ...values }),
    confirmDialog: {},
    askForConfirmation: async (message) => { prompts.push(message); return confirmed; },
    toastStore: { add: (notification) => notifications.push(notification) },
    statsApi: { cleanupStorage: async (target) => {
      requests.push(target);
      return { data: { status: "ok", data: { removed_bytes: 128, processed_files: 2, removed_traces: removedTraces, status } } };
    } },
  });
  const names = new Set(["storageStatus", "storageCards", "cleaningTarget", "showToast", "formatBytes", "cleanupStorage"]);
  const statements = ast.statements.filter((node) => ts.isVariableStatement(node) &&
    names.has(node.declarationList.declarations[0]?.name.getText(ast)));
  assert.equal(statements.length, names.size);
  vm.runInContext(statements.map((node) => node.getText(ast)).join("\n"), context);
  const state = vm.runInContext("({ storageStatus, storageCards, cleaningTarget, cleanupStorage })", context);
  state.storageStatus.value = status;
  return { ...state, prompts, requests, notifications };
}

test("cleanup menu includes trace data and its separately reported disk usage", () => {
  const state = setup();
  assert.deepEqual(Array.from(state.storageCards.value, (item) => item.key), ["cache", "logs", "traces"]);
  assert.equal(state.storageCards.value[2].sizeBytes, 30);
  assert.equal(state.storageStatus.value.total_bytes, 60);
});

test("trace cleanup warns about irreversible history removal and reports message traces, not files", async () => {
  const state = setup();
  await state.cleanupStorage("traces");
  assert.equal(state.prompts[0].key, "system.cleanup.confirmWithTraces");
  assert.deepEqual(state.requests, ["traces"]);
  assert.equal(state.notifications[0].message.key, "system.cleanup.messages.cleanupTracesSuccess");
  assert.equal(state.notifications[0].message.count, 3);
  assert.equal(state.notifications[0].message.size, "128 B");
  assert.equal(state.cleaningTarget.value, "");
});

test("all cleanup includes trace confirmation and separate file/trace counts", async () => {
  const state = setup();
  await state.cleanupStorage("all");
  assert.equal(state.prompts[0].key, "system.cleanup.confirmWithTraces");
  assert.equal(state.notifications[0].message.key, "system.cleanup.messages.cleanupWithTracesSuccess");
  assert.equal(state.notifications[0].message.count, 2);
  assert.equal(state.notifications[0].message.traces, 3);
});

test("cancelling cleanup does not send a destructive request", async () => {
  const state = setup({ confirmed: false });
  await state.cleanupStorage("traces");
  assert.equal(state.requests.length, 0);
  assert.equal(state.notifications.length, 0);
});

test("ordinary log cleanup retains its existing confirmation and success message", async () => {
  const state = setup({ removedTraces: 0 });
  await state.cleanupStorage("logs");
  assert.equal(state.prompts[0].key, "system.cleanup.confirm");
  assert.equal(state.notifications[0].message.key, "system.cleanup.messages.cleanupSuccess");
});

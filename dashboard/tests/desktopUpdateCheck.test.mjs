import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

test("desktop update checks recover from failures and stalled bridge calls", async (t) => {
  const script = readFileSync(
    new URL(
      "../src/layouts/full/vertical-header/VerticalHeader.vue",
      import.meta.url,
    ),
    "utf8",
  )
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const source = ts.createSourceFile(
    "header.ts",
    script,
    ts.ScriptTarget.Latest,
    true,
  );
  const check = source.statements.find(
    (node) =>
      ts.isFunctionDeclaration(node) &&
      node.name?.text === "checkDesktopUpdate",
  );
  assert.ok(check);

  const timers = new Map();
  const warnings = [];
  const errors = [];
  let timerId = 0;
  let bridge;
  const context = vm.createContext({
    desktopUpdateInstalling: { value: false },
    desktopUpdateDialog: { value: false },
    desktopUpdateChecking: { value: false },
    desktopDownloadProgress: { value: null },
    desktopUpdateHasNewVersion: { value: false },
    desktopUpdateCurrentVersion: { value: "-" },
    desktopUpdateLatestVersion: { value: "-" },
    desktopUpdateStatus: { value: "" },
    getAppUpdaterBridge: () => bridge,
    t: (key) => key,
    console: {
      warn: (...args) => warnings.push(args),
      error: (...args) => errors.push(args),
    },
    setTimeout: (callback, delay) => {
      assert.equal(delay, 30_000);
      timers.set(++timerId, callback);
      return timerId;
    },
    clearTimeout: (id) => timers.delete(id),
  });
  vm.runInContext(
    ts.transpileModule(check.getText(source), {
      compilerOptions: { target: ts.ScriptTarget.ES2022 },
    }).outputText,
    context,
  );

  await t.test(
    "non-OK automatic checks log the failure reason without opening a dialog",
    async () => {
      bridge = {
        checkForAppUpdate: async () => ({ ok: false, reason: "Offline" }),
      };
      await context.checkDesktopUpdate();
      assert.equal(warnings.at(-1)[1], "Offline");
      assert.equal(context.desktopUpdateStatus.value, "Offline");
      assert.equal(context.desktopUpdateDialog.value, false);
      assert.equal(context.desktopUpdateChecking.value, false);
      assert.equal(timers.size, 0);
    },
  );

  await t.test(
    "missing bridges are logged and release the checking state",
    async () => {
      bridge = null;
      await context.checkDesktopUpdate();
      assert.match(warnings.at(-1)[0], /bridge is unavailable/);
      assert.equal(context.desktopUpdateChecking.value, false);
      assert.equal(timers.size, 0);
    },
  );

  await t.test(
    "rejected checks log the error and clear their timer",
    async () => {
      const failure = new Error("Bridge disconnected");
      bridge = {
        checkForAppUpdate: async () => {
          throw failure;
        },
      };
      await context.checkDesktopUpdate();
      assert.equal(errors.at(-1)[1], failure);
      assert.equal(context.desktopUpdateChecking.value, false);
      assert.equal(timers.size, 0);
    },
  );

  await t.test(
    "timeouts allow retries and late results cannot overwrite a newer check",
    async () => {
      let resolveStalled;
      let calls = 0;
      bridge = {
        checkForAppUpdate: () => {
          calls++;
          return new Promise((resolve) => {
            resolveStalled = resolve;
          });
        },
      };
      const stalled = context.checkDesktopUpdate();
      await context.checkDesktopUpdate(true);
      assert.equal(calls, 1);
      assert.equal(context.desktopUpdateDialog.value, true);
      assert.equal(context.desktopUpdateChecking.value, true);
      timers.values().next().value();
      await stalled;
      assert.match(errors.at(-1)[1].message, /timed out/);
      assert.equal(context.desktopUpdateChecking.value, false);
      assert.equal(
        context.desktopUpdateStatus.value,
        "core.header.updateDialog.desktopApp.checkFailed",
      );
      assert.equal(timers.size, 0);

      let resolveRetry;
      bridge = {
        checkForAppUpdate: () =>
          new Promise((resolve) => {
            resolveRetry = resolve;
          }),
      };
      const retry = context.checkDesktopUpdate(true);
      assert.equal(context.desktopUpdateChecking.value, true);
      resolveStalled({ ok: true, hasUpdate: true, latestVersion: "stale" });
      await Promise.resolve();
      await Promise.resolve();
      assert.equal(context.desktopUpdateChecking.value, true);
      assert.equal(context.desktopUpdateLatestVersion.value, "-");
      assert.equal(context.desktopUpdateHasNewVersion.value, false);
      resolveRetry({
        ok: true,
        hasUpdate: true,
        currentVersion: "1.0.0",
        latestVersion: "1.1.0",
      });
      await retry;
      assert.equal(context.desktopUpdateChecking.value, false);
      assert.equal(context.desktopUpdateHasNewVersion.value, true);
      assert.equal(context.desktopUpdateLatestVersion.value, "1.1.0");
      assert.equal(timers.size, 0);
    },
  );

  await t.test(
    "successful checks clear their timers and do not log failures",
    async () => {
      const warningCount = warnings.length;
      const errorCount = errors.length;
      bridge = {
        checkForAppUpdate: async () => ({ ok: true, hasUpdate: false }),
      };
      await context.checkDesktopUpdate();
      assert.equal(context.desktopUpdateChecking.value, false);
      assert.equal(context.desktopUpdateHasNewVersion.value, false);
      assert.equal(warnings.length, warningCount);
      assert.equal(errors.length, errorCount);
      assert.equal(timers.size, 0);
    },
  );
});

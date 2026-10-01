import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const source = readFileSync(
  new URL(
    "../src/layouts/full/vertical-header/VerticalHeader.vue",
    import.meta.url,
  ),
  "utf8",
)
  .split('<script setup lang="ts">')[1]
  .split("</script>")[0];
const names = new Set([
  "stopUpdateProgressPolling",
  "stopRestartPolling",
  "stopRestartReloadTimer",
  "resetRestartFeedbackState",
  "fetchAstrBotStartTime",
  "showRestartCompleted",
  "waitForAstrBotRestart",
  "applyUpdateProgress",
  "retryRestartCheck",
  "showRestartUnconfirmed",
  "startUpdateProgressPolling",
]);
const ast = ts.createSourceFile(
  "header.ts",
  source,
  ts.ScriptTarget.Latest,
  true,
);
const functions = ast.statements
  .filter(
    (node) => ts.isFunctionDeclaration(node) && names.has(node.name?.text),
  )
  .map((node) => node.getText(ast));
const dialogWatcher = ast.statements.find(
  (node) =>
    ts.isExpressionStatement(node) &&
    ts.isCallExpression(node.expression) &&
    node.expression.expression.getText(ast) === "watch" &&
    node.expression.arguments[0]?.getText(ast) === "updateStatusDialog",
);

function setup(response) {
  let now = 0;
  let nextId = 0;
  const timers = new Map();
  const schedule = (callback, delay, interval = false) => {
    const id = ++nextId;
    timers.set(id, { callback, due: now + delay, delay, interval });
    return id;
  };
  const context = vm.createContext({
    restartCompleted: { value: false },
    restartWaiting: { value: false },
    restartUnconfirmed: { value: false },
    restartStartTime: { value: null },
    restartReloadCountdown: { value: 3 },
    updateProgress: { value: { id: "update" } },
    updateStatusDialog: { value: true },
    installLoading: { value: false },
    commonStore: {},
    restartPollTimer: null,
    restartReloadTimer: null,
    updateProgressTimer: null,
    restartTimeoutTimer: null,
    restartPollGeneration: 0,
    updateProgressGeneration: 0,
    RESTART_FEEDBACK_DELAY_SECONDS: 3,
    RESTART_START_TIME_POLL_INTERVAL_MS: 2000,
    RESTART_CONFIRMATION_TIMEOUT_MS: 90000,
    statsApi: {
      startTime: async () => ({
        data: { data: { start_time: await response() } },
      }),
    },
    updatesApi: {
      progress: async () => ({
        data: {
          data: {
            id: "update",
            stage: "core",
            status: "running",
            stages: {},
          },
        },
      }),
    },
    watch: (_ref, callback) => {
      context.setDialogOpen = callback;
    },
    t: (key) => key,
    createEmptyUpdateProgress: () => ({ stages: {} }),
    reloadAfterUpdate: () => {},
    setInterval: (fn, delay) => schedule(fn, delay, true),
    setTimeout: (fn, delay) => schedule(fn, delay),
    clearInterval: (id) => timers.delete(id),
    clearTimeout: (id) => timers.delete(id),
  });
  vm.runInContext(
    ts.transpileModule(functions.join("\n"), {
      compilerOptions: { target: ts.ScriptTarget.ES2022 },
    }).outputText,
    context,
  );
  vm.runInContext(dialogWatcher.getText(ast), context);
  async function settle() {
    await new Promise(setImmediate);
  }
  async function advance(ms) {
    const target = now + ms;
    await settle();
    while (true) {
      const entry = [...timers.entries()]
        .filter(([, timer]) => timer.due <= target)
        .sort((a, b) => a[1].due - b[1].due)[0];
      if (!entry) break;
      const [id, timer] = entry;
      now = timer.due;
      if (timer.interval) timer.due += timer.delay;
      else timers.delete(id);
      timer.callback();
      await settle();
    }
    now = target;
  }
  return { context, timers, advance, settle };
}

test("a healthy backend with an unknown baseline eventually offers recovery", async () => {
  const { context: c, timers, advance } = setup(() => 200);
  c.waitForAstrBotRestart(null);
  await advance(90000);
  assert.equal(c.restartCompleted.value, false);
  assert.equal(c.restartWaiting.value, false);
  assert.equal(c.restartUnconfirmed.value, true);
  assert.equal(timers.size, 0);
});

test("a response arriving after timeout cannot trigger automatic refresh", async () => {
  let resolve;
  const pending = new Promise((done) => {
    resolve = done;
  });
  const { context: c, advance, settle } = setup(() => pending);
  c.waitForAstrBotRestart(100);
  await advance(90000);
  resolve(200);
  await settle();
  assert.equal(c.restartCompleted.value, false);
  assert.equal(c.restartUnconfirmed.value, true);
  c.applyUpdateProgress({ id: "update", stage: "restart", status: "success" });
  assert.equal(c.restartWaiting.value, false);
});

test("unchanged numeric strings and invalid timestamps cannot confirm a restart", async () => {
  for (const response of [100, "100", null, 0, "invalid", -1]) {
    const { context: c, advance } = setup(() => response);
    c.waitForAstrBotRestart("100");
    await advance(90000);
    assert.equal(c.restartCompleted.value, false, String(response));
    assert.equal(c.restartUnconfirmed.value, true);
  }
});

test("normal restart survives temporary disconnects and confirms a new timestamp", async () => {
  let ready = false;
  const { context: c, advance } = setup(() => {
    if (!ready) throw new Error("offline");
    return 200;
  });
  c.waitForAstrBotRestart(100);
  await advance(4000);
  assert.equal(c.restartCompleted.value, false);
  ready = true;
  await advance(2000);
  assert.equal(c.restartCompleted.value, true);
  assert.equal(c.restartWaiting.value, false);
  assert.equal(c.restartUnconfirmed.value, false);
});

test("checking again after timeout observes recovery without submitting an update", async () => {
  let timestamp = 100;
  const { context: c, advance, settle } = setup(() => timestamp);
  c.waitForAstrBotRestart(100);
  await advance(90000);
  assert.equal(c.restartUnconfirmed.value, true);
  timestamp = 200;
  c.retryRestartCheck();
  await settle();
  assert.equal(c.restartCompleted.value, true);
  assert.equal(c.restartUnconfirmed.value, false);
});

test("downloads do not use the restart deadline and repeated progress cannot extend it", async () => {
  const { context: c, advance } = setup(() => 100);
  c.waitForAstrBotRestart(100, false);
  await advance(120000);
  assert.equal(c.restartUnconfirmed.value, false);
  c.waitForAstrBotRestart(100);
  await advance(88000);
  c.waitForAstrBotRestart(100);
  await advance(2000);
  assert.equal(c.restartUnconfirmed.value, true);
});

test("continuous network errors still end the waiting state", async () => {
  const {
    context: c,
    timers,
    advance,
  } = setup(() => {
    throw new Error("offline");
  });
  c.waitForAstrBotRestart(100);
  await advance(90000);
  assert.equal(c.restartWaiting.value, false);
  assert.equal(c.restartUnconfirmed.value, true);
  assert.equal(timers.size, 0);
});

test("cleanup invalidates a pending response and clears the deadline", async () => {
  let resolve;
  const {
    context: c,
    timers,
    settle,
  } = setup(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  c.waitForAstrBotRestart(100);
  c.resetRestartFeedbackState();
  resolve(200);
  await settle();
  assert.equal(c.restartCompleted.value, false);
  assert.equal(c.restartUnconfirmed.value, false);
  assert.equal(timers.size, 0);
});

test("closing and reopening the dialog resumes download observation", async () => {
  const { context: c, timers, settle } = setup(() => 100);
  c.waitForAstrBotRestart(100, false);
  c.startUpdateProgressPolling("update");
  await settle();
  c.setDialogOpen(false);
  assert.equal(timers.size, 0);
  c.setDialogOpen(true);
  await settle();
  assert.notEqual(c.updateProgressTimer, null);
  assert.notEqual(c.restartPollTimer, null);
  assert.equal(c.restartTimeoutTimer, null);
});

test("closing during restart ignores late replies and reopening resumes checks", async () => {
  let resolve;
  let timestamp;
  const {
    context: c,
    timers,
    settle,
  } = setup(
    () =>
      timestamp ??
      new Promise((done) => {
        resolve = done;
      }),
  );
  c.waitForAstrBotRestart(100);
  c.setDialogOpen(false);
  resolve(200);
  await settle();
  assert.equal(c.restartCompleted.value, false);
  assert.equal(timers.size, 0);
  timestamp = 200;
  c.setDialogOpen(true);
  await settle();
  assert.equal(c.restartCompleted.value, true);
});

test("an explicit update error stops restart waiting and preserves the error", async () => {
  const { context: c, timers } = setup(() => 100);
  c.waitForAstrBotRestart(100);
  c.applyUpdateProgress({
    id: "update",
    stage: "restart",
    status: "error",
    message: "restart failed",
  });
  assert.equal(c.restartWaiting.value, false);
  assert.equal(c.updateProgress.value.status, "error");
  assert.equal(c.updateProgress.value.message, "restart failed");
  assert.equal(timers.size, 0);
});

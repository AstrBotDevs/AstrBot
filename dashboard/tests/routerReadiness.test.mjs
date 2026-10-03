import assert from "node:assert/strict";
import test from "node:test";

test("waitForRouterReadyInBackground returns immediately and logs failures", async () => {
  const module = await import("../src/utils/routerReadiness.mjs").catch(() => null);

  assert.ok(module?.waitForRouterReadyInBackground);

  const error = new Error("router blocked");
  let warned;
  const readyPromise = Promise.reject(error);
  const logger = {
    warn: (message, cause) => {
      warned = { message, cause };
    },
  };

  const result = module.waitForRouterReadyInBackground({ isReady: () => readyPromise }, logger);

  assert.equal(result, undefined);
  await Promise.resolve();
  assert.deepEqual(warned, {
    message: "Router did not become ready after fallback mount:",
    cause: error,
  });
});

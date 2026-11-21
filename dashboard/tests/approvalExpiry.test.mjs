import assert from "node:assert/strict";
import test from "node:test";
import { loadSource } from "./helpers/vueHarness.mjs";

const DAY = 24 * 60 * 60 * 1000;

function clock() {
  const state = { now: 0, timers: new Map() };
  const choices = loadSource(
    new URL("../src/composables/useActionRowChoices.ts", import.meta.url),
    {},
    {
      localStorage: { getItem: () => null, setItem() {} },
      Date: { now: () => state.now },
      setTimeout: (fn, delay) => {
        state.timers.set(fn, delay);
        return fn;
      },
      clearTimeout: (fn) => state.timers.delete(fn),
    },
  );
  const fire = () => {
    const [fn] = state.timers.keys();
    state.timers.delete(fn);
    fn();
  };
  return { ...state, state, choices, fire };
}

test("long approval deadlines are woken in bounded steps of one day", () => {
  const h = clock();
  const deadline = 90 * DAY;
  h.choices.wakeApprovalClockAt(deadline);
  assert.deepEqual([...h.timers.values()], [DAY + 50]);
  h.state.now = DAY + 50;
  h.fire();
  assert.equal(h.choices.approvalNow.value, DAY + 50);
  // A card re-arms the clock when it reads the new time.
  h.choices.wakeApprovalClockAt(deadline);
  assert.deepEqual([...h.timers.values()], [DAY + 50]);
});

test("the shared clock keeps one timer for the earliest deadline", () => {
  const h = clock();
  h.choices.wakeApprovalClockAt(5000);
  h.choices.wakeApprovalClockAt(9000);
  assert.deepEqual([...h.timers.values()], [5050]);
  h.choices.wakeApprovalClockAt(2000);
  assert.deepEqual([...h.timers.values()], [2050]);
  for (const ignored of [0, -1, Number.NaN])
    h.choices.wakeApprovalClockAt(ignored);
  assert.equal(h.timers.size, 1);
});

test("expiry follows the shared clock and the newest open card is docked", () => {
  const h = clock();
  const card = (key, extra = {}) => ({
    type: "actionrow",
    title: "Approve",
    single_use: true,
    expires_at: 10,
    buttons: [{ action: { type: "callback", callback_data: key } }],
    ...extra,
  });
  const { approvalCardState, latestOpenApproval, approvalCardKey } = h.choices;
  const first = card("first");
  const messages = [first, card("second")].map((part) => ({
    content: { message: [part] },
  }));
  h.choices.approvalNow.value = 9999;
  assert.equal(approvalCardState(first).open, true);
  assert.equal(approvalCardKey(latestOpenApproval(messages).part), "second");
  h.choices.rememberChosenCallback("second");
  assert.equal(approvalCardKey(latestOpenApproval(messages).part), "first");
  h.choices.approvalNow.value = 10000;
  assert.equal(approvalCardState(first).expired, true);
  assert.equal(latestOpenApproval(messages), null);
  assert.equal(approvalCardKey(undefined), "");
});

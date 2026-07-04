// Author: elecvoid243
// Date: 2026-07-03
// Spec: docs/superpowers/specs/2026-07-02-blocking-interactive-choice-design.md §5.1
//
// Regression: SSE `interactive_choice` events must surface the part in
// the bot message's `content.message` array, not only in the Pinia
// store. `ChatMessageList.vue` renders `<InteractiveChoiceBox>` only
// when iterating `messageParts(message)`, so a part that lives only in
// the store will never appear on screen even though submit handlers
// work end-to-end.
//
// This test pins both halves of the contract:
//   1. `botRecord.content.message` contains the part → UI renders the box
//   2. `useInteractiveChoiceStore().activeChoices[request_id]` exists →
//      hydrate / reconcile / tab-switch can recover it
//
// Run: cd dashboard && pnpm exec node --test src/composables/useMessages.interactiveChoice.test.ts

import assert from "node:assert/strict";
import { test, beforeEach } from "node:test";
import { setActivePinia, createPinia } from "pinia";

import {
  applyInteractiveChoiceSse,
  type BotMessageLike,
} from "./dispatchInteractiveChoice.ts";
import { abandonPendingInteractiveChoices } from "./abandonPendingInteractiveChoices.ts";
import type { InteractiveChoicePart } from "./parseInteractiveChoice.ts";
import { useInteractiveChoiceStore } from "../stores/interactiveChoice.ts";
// Bug Y1 fix: dispatcher now requires an explicit UMO so the store
// write cannot accidentally pool two sessions together.
const TEST_UMO = "webchat:sse-test!1!sess";

const SPEC_PART: InteractiveChoicePart = {
  type: "interactive_choice",
  request_id: "11111111-2222-3333-4444-555555555555",
  prompt: "Pick a color",
  options: [
    { id: "A", label: "Red" },
    { id: "B", label: "Blue" },
  ],
  expires_at: 9_999_999_999,
};

const VALID_SSE_PAYLOAD = {
  type: "interactive_choice",
  data: {
    request_id: SPEC_PART.request_id,
    spec: {
      type: "interactive_choice",
      prompt: SPEC_PART.prompt,
      options: SPEC_PART.options,
    },
    expires_at: SPEC_PART.expires_at,
  },
};

function makeBotRecord(): BotMessageLike {
  return {
    content: {
      message: [],
      isLoading: true,
    },
  };
}

beforeEach(() => {
  setActivePinia(createPinia());
});

test("applyInteractiveChoiceSse pushes the part into botRecord.content.message", () => {
  const botRecord = makeBotRecord();
  applyInteractiveChoiceSse(TEST_UMO, botRecord, VALID_SSE_PAYLOAD);

  assert.equal(botRecord.content.message.length, 1);
  const part = botRecord.content.message[0] as InteractiveChoicePart;
  assert.equal(part.type, "interactive_choice");
  assert.equal(part.request_id, SPEC_PART.request_id);
  assert.equal(part.prompt, SPEC_PART.prompt);
  assert.deepEqual(part.options, SPEC_PART.options);
  assert.equal(part.expires_at, SPEC_PART.expires_at);
});

test("applyInteractiveChoiceSse clears the loading state", () => {
  const botRecord = makeBotRecord();
  assert.equal(botRecord.content.isLoading, true);

  applyInteractiveChoiceSse(TEST_UMO, botRecord, VALID_SSE_PAYLOAD);

  assert.equal(botRecord.content.isLoading, false);
});

test("applyInteractiveChoiceSse mirrors the part into the Pinia store", () => {
  const botRecord = makeBotRecord();
  const store = useInteractiveChoiceStore();

  applyInteractiveChoiceSse(TEST_UMO, botRecord, VALID_SSE_PAYLOAD);

  const stored = store.activeChoices[TEST_UMO]?.[SPEC_PART.request_id];
  assert.ok(stored, "store must contain an entry keyed by TEST_UMO.request_id");
  assert.equal(stored.request_id, SPEC_PART.request_id);
});

test("applyInteractiveChoiceSse is a no-op when the payload fails validation", () => {
  const botRecord = makeBotRecord();
  const badPayload = { type: "interactive_choice", data: {} };

  applyInteractiveChoiceSse(TEST_UMO, botRecord, badPayload);

  assert.equal(botRecord.content.message.length, 0);
  assert.equal(
    Object.keys(useInteractiveChoiceStore().activeChoices[TEST_UMO] ?? {})
      .length,
    0,
  );
});

test("applyInteractiveChoiceSse throws when umo is missing (Bug Y1)", () => {
  const botRecord = makeBotRecord();
  assert.throws(
    () => applyInteractiveChoiceSse("", botRecord, VALID_SSE_PAYLOAD),
    /missing required 'umo'/,
  );
});

test("applyInteractiveChoiceSse writes under the supplied UMO bucket, not a global pool (Bug Y1)", () => {
  const botRecord = makeBotRecord();
  const SSO_UMO = "webchat:sso!1!sess";
  applyInteractiveChoiceSse(SSO_UMO, botRecord, VALID_SSE_PAYLOAD);

  const store = useInteractiveChoiceStore();
  // The part lives in the supplied bucket only — not in any other
  // session's bucket and not at the top level.
  assert.ok(store.activeChoices[SSO_UMO]?.[SPEC_PART.request_id]);
  assert.equal(store.activeChoices[TEST_UMO], undefined);
});

// Bug 3 fix: when the user types a chat-input message while an
// ask_user_choice prompt is pending, the prompt must be marked
// ignored. The deterministic trigger is
// `abandonPendingInteractiveChoices(umo)`, which
// `useMessages.createLocalExchange` calls before pushing the new
// user_msg. The old approach — a runtime reverse-walk of
// `props.messages` on every SSE mutation — could mis-classify a
// follow-up Q2 (emitted in the same bot record as the response to
// the typed input) as ignored, because the walk's `hasUserAfter`
// reset was satisfied by the typed-input user message itself.
// Tested in isolation here so the regression suite can run under
// the raw `node --test` runner without resolving the `@/api`
// aliases that `useMessages.ts` pulls in.
test("abandonPendingInteractiveChoices flags every active request_id (Bug 3)", () => {
  const store = useInteractiveChoiceStore();
  store.hydrate(TEST_UMO);
  store.addChoice(TEST_UMO, {
    type: "interactive_choice",
    request_id: "req-pending-1",
    prompt: "Pick a color",
    options: [
      { id: "A", label: "Red" },
      { id: "B", label: "Blue" },
    ],
    expires_at: 9_999_999_999,
  });
  store.addChoice(TEST_UMO, {
    type: "interactive_choice",
    request_id: "req-pending-2",
    prompt: "Pick a fruit",
    options: [
      { id: "A", label: "Apple" },
      { id: "B", label: "Banana" },
    ],
    expires_at: 9_999_999_999,
  });
  assert.equal(store.isIgnored(TEST_UMO, "req-pending-1"), false);
  assert.equal(store.isIgnored(TEST_UMO, "req-pending-2"), false);

  // The chat-input send path calls this before pushing the new
  // user_msg.
  abandonPendingInteractiveChoices(TEST_UMO);

  // Both pending prompts are now flagged ignored. A follow-up Q2
  // emitted by the LLM after the typed reply will arrive in a
  // later bot record and will *not* be in this set — it has not
  // been "passed over" by a typed message yet.
  assert.equal(store.isIgnored(TEST_UMO, "req-pending-1"), true);
  assert.equal(store.isIgnored(TEST_UMO, "req-pending-2"), true);
});

test("abandonPendingInteractiveChoices is a no-op when no choice is active (Bug 3)", () => {
  const store = useInteractiveChoiceStore();
  store.hydrate(TEST_UMO);
  // No addChoice — activeChoices[TEST_UMO] is undefined.
  abandonPendingInteractiveChoices(TEST_UMO);
  // No ignored bucket is created, so the in-memory state stays
  // empty (the `persist` call would warn "localStorage is not
  // defined" under the raw `node --test` runner, but it must not
  // throw and must not write into the store).
  const ignoredStates = (
    store as unknown as { ignoredStates: Record<string, unknown> }
  ).ignoredStates;
  assert.equal(ignoredStates[TEST_UMO], undefined);
});

test("abandonPendingInteractiveChoices is a no-op for an empty umo (Bug 3)", () => {
  const store = useInteractiveChoiceStore();
  store.hydrate(TEST_UMO);
  store.addChoice(TEST_UMO, {
    type: "interactive_choice",
    request_id: "req-still-active",
    prompt: "Pick",
    options: [
      { id: "A", label: "a" },
      { id: "B", label: "b" },
    ],
    expires_at: 9_999_999_999,
  });
  // An empty umo is treated as a no-op (defensive — useMessages
  // always has a real sessionId by this point, but the helper must
  // not blow up if a future caller forgets to guard).
  abandonPendingInteractiveChoices("");
  assert.equal(store.isIgnored(TEST_UMO, "req-still-active"), false);
});

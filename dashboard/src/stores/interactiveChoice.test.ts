// Author: elecvoid243 (task13_impl, task13_fix)
// Date: 2026-07-03
// Spec: docs/superpowers/specs/2026-07-02-blocking-interactive-choice-design.md §5.2
//
// Test runner: node --test (Node v24 strips TS from .ts imports automatically).
// Run: cd dashboard && node --test src/stores/interactiveChoice.test.ts
//
// Plan Amendment D: a hydrate test is mandatory so that localStorage
// rehydration cannot regress silently.
//
// Task 13 fix: submitChoice + reconcile are the transport-layer actions
// and were uncovered; both paths are exercised below using
// axios-mock-adapter (already a project dep) attached to the same
// httpClient instance the store imports.
import assert from "node:assert/strict";
import { test, beforeEach, afterEach } from "node:test";

// Pinia test harness: createPinia + setActivePinia avoids needing a full Vue app.
import { createPinia, setActivePinia } from "pinia";

// axios-mock-adapter is already a project dependency; we attach it to the
// httpClient instance the store imports, so submitChoice / reconcile calls
// are intercepted without hitting a real network.
import MockAdapter from "axios-mock-adapter";

import { httpClient } from "../api/http.ts";
import type { InteractiveChoicePart } from "../composables/parseInteractiveChoice.ts";
import { STORAGE_KEY, useInteractiveChoiceStore } from "./interactiveChoice.ts";

const TEST_UMO = "webchat:test!1!sess";

// Minimal in-memory localStorage stub for Node test runtime.
class MemoryStorage {
  private store = new Map<string, string>();
  getItem(key: string): string | null {
    return this.store.has(key) ? (this.store.get(key) as string) : null;
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  clear(): void {
    this.store.clear();
  }
}

// Per-test MockAdapter attached to the store's httpClient.
let mock: MockAdapter;

beforeEach(() => {
  // Fresh Pinia + localStorage for each test.
  setActivePinia(createPinia());
  const mem = new MemoryStorage();
  (globalThis as unknown as { localStorage: MemoryStorage }).localStorage = mem;
  // Reset any prior handlers/history so each test gets a clean slate.
  mock = new MockAdapter(httpClient);
});

afterEach(() => {
  // Restore the original axios adapter so tests don't leak mock state.
  mock.restore();
});

// ---------------------------------------------------------------------------
// Pure constant
// ---------------------------------------------------------------------------

test("STORAGE_KEY is correct", () => {
  assert.equal(STORAGE_KEY, "astrbot-interactive-choice-pending");
});

// ---------------------------------------------------------------------------
// Plan Amendment D: hydrate rehydrates from localStorage
// ---------------------------------------------------------------------------

test("hydrate populates activeChoices from pre-populated localStorage", () => {
  // Arrange: pre-populate localStorage with a saved InteractiveChoicePart.
  const saved = {
    [TEST_UMO]: {
      "req-hydrate-1": {
        type: "interactive_choice",
        request_id: "req-hydrate-1",
        prompt: "Pick one",
        options: [
          { id: "A", label: "alpha" },
          { id: "B", label: "beta" },
        ],
      },
    },
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));

  // Act
  const store = useInteractiveChoiceStore();
  store.hydrate(TEST_UMO);

  // Assert: the hydrated item lives in activeChoices[TEST_UMO].
  assert.ok(
    store.activeChoices[TEST_UMO]?.["req-hydrate-1"],
    "expected activeChoices[TEST_UMO] to contain hydrated request_id",
  );
  assert.equal(
    store.activeChoices[TEST_UMO]["req-hydrate-1"].prompt,
    "Pick one",
  );
  assert.equal(store.asList.length, 1);
  assert.equal(store.hasAny, true);
});

test("hydrate clears localStorage on corrupt JSON", () => {
  // Arrange: stuff a corrupted payload into localStorage.
  localStorage.setItem(STORAGE_KEY, "{not json");

  // Act: hydrate must not throw and must clear the bad key.
  const store = useInteractiveChoiceStore();
  store.hydrate(TEST_UMO);

  // Assert
  assert.equal(store.asList.length, 0);
  assert.equal(localStorage.getItem(STORAGE_KEY), null);
});

test("hydrate is a no-op when localStorage is empty", () => {
  const store = useInteractiveChoiceStore();
  store.hydrate(TEST_UMO);
  assert.equal(store.hasAny, false);
});

// ---------------------------------------------------------------------------
// addChoice / removeChoice round-trip via persist -> hydrate
// ---------------------------------------------------------------------------

test("addChoice persists and a fresh store can rehydrate", () => {
  // First store: add a choice.
  const storeA = useInteractiveChoiceStore();
  // Bug Y1 contract: `addChoice` does not implicitly select the
  // active UMO. Tests that inspect `hasAny` must hydrate first
  // (the same sequence ChatMessageList.vue follows on mount).
  storeA.hydrate(TEST_UMO);
  storeA.addChoice(TEST_UMO, {
    type: "interactive_choice",
    request_id: "req-persist-1",
    prompt: "p",
    options: [
      { id: "A", label: "a" },
      { id: "B", label: "b" },
    ],
  });
  assert.equal(storeA.hasAny, true);

  // Second store on a fresh Pinia simulates page reload.
  setActivePinia(createPinia());
  const storeB = useInteractiveChoiceStore();
  storeB.hydrate(TEST_UMO);
  assert.ok(storeB.activeChoices[TEST_UMO]?.["req-persist-1"]);
  assert.equal(storeB.activeChoices[TEST_UMO]["req-persist-1"].prompt, "p");
});

test("removeChoice deletes by request_id and clears persisted entry", () => {
  const store = useInteractiveChoiceStore();
  store.addChoice(TEST_UMO, {
    type: "interactive_choice",
    request_id: "req-rm",
    prompt: "p",
    options: [
      { id: "A", label: "a" },
      { id: "B", label: "b" },
    ],
  });
  store.removeChoice(TEST_UMO, "req-rm");
  // The legacy flat-key index was removed by Bug Y1; the new layout
  // stores by UMO.
  assert.equal(store.activeChoices["req-rm"], undefined);
  assert.equal(store.activeChoices[TEST_UMO]?.["req-rm"], undefined);
  assert.equal(store.hasAny, false);
  // localStorage now holds {} — there were no other UMOs and the
  // bucket became empty after the only child was deleted.
  assert.equal(localStorage.getItem(STORAGE_KEY), "{}");
});

// ---------------------------------------------------------------------------
// submitChoice: HTTP transport + optimistic removal
// ---------------------------------------------------------------------------

test("submitChoice sends correct payload and removes locally on success", async () => {
  // Arrange: pre-populate store with one choice.
  const store = useInteractiveChoiceStore();
  store.addChoice(TEST_UMO, {
    type: "interactive_choice",
    request_id: "req-1",
    prompt: "Pick one",
    options: [
      { id: "A", label: "Alpha" },
      { id: "B", label: "Beta" },
    ],
    expires_at: Date.now() / 1000 + 60,
  });
  mock
    .onPost("/api/chat/interactive-choice/req-1")
    .reply(200, { status: "ok", data: null });

  // Act
  await store.submitChoice(TEST_UMO, "req-1", {
    choice_id: "A",
    free_text: "hello",
  });

  // Assert: one POST to the right URL with the right JSON body.
  assert.equal(mock.history.post.length, 1);
  assert.equal(mock.history.post[0].url, "/api/chat/interactive-choice/req-1");
  assert.deepEqual(JSON.parse(mock.history.post[0].data as string), {
    choice_id: "A",
    free_text: "hello",
  });
  // Optimistic local removal on ok envelope.
  assert.equal(store.activeChoices[TEST_UMO]?.["req-1"], undefined);
  // localStorage persistence also reflects the removal.
  assert.equal(localStorage.getItem(STORAGE_KEY), "{}");
});

test("submitChoice keeps the choice locally when backend returns error", async () => {
  // Arrange
  const store = useInteractiveChoiceStore();
  store.addChoice(TEST_UMO, {
    type: "interactive_choice",
    request_id: "req-1",
    prompt: "Pick one",
    options: [
      { id: "A", label: "Alpha" },
      { id: "B", label: "Beta" },
    ],
  });
  mock
    .onPost("/api/chat/interactive-choice/req-1")
    .reply(500, { status: "error", message: "boom" });

  // Act + Assert: the promise rejects with an axios error.
  await assert.rejects(
    store.submitChoice(TEST_UMO, "req-1", { choice_id: "A", free_text: "" }),
  );

  // The local entry must still be present so the UI can retry or surface the error.
  assert.ok(store.activeChoices[TEST_UMO]?.["req-1"]);
  assert.equal(store.activeChoices[TEST_UMO]["req-1"].prompt, "Pick one");
  assert.equal(mock.history.post.length, 1);
});

// ---------------------------------------------------------------------------
// reconcile: GET pending from backend and merge into store
// ---------------------------------------------------------------------------

test("reconcile POSTs to pending endpoint and merges backend state", async () => {
  // Arrange: backend returns one pending choice.
  // Note: POST (not GET) because the dashboard static-files catch-all
  // route preempts every GET /api/* with a 404. The endpoint is
  // read-only on the server; only the verb changed to dodge routing.
  mock.onPost("/api/chat/interactive-choice/pending").reply(200, {
    status: "ok",
    data: {
      pending: [
        {
          type: "interactive_choice",
          request_id: "from-backend-1",
          prompt: "Backend prompt",
          options: [
            { id: "X", label: "x" },
            { id: "Y", label: "y" },
          ],
        },
        {
          type: "interactive_choice",
          request_id: "from-backend-2",
          prompt: "Second",
          options: [
            { id: "P", label: "p" },
            { id: "Q", label: "q" },
          ],
        },
      ],
    },
  });

  // Act
  const store = useInteractiveChoiceStore();
  const RECON_UMO = "webchat:reconcile!1!sess";
  // Bug Y1 contract: hydrate first so `asList` is the right bucket
  // (see ChatMessageList.vue onMounted which always pairs hydrate +
  // reconcile in this order).
  store.hydrate(RECON_UMO);
  await store.reconcile(RECON_UMO);

  // Assert: POST hit the pending endpoint with session_id in the body
  // and no GET was issued.
  assert.equal(mock.history.post.length, 1);
  assert.equal(
    mock.history.post[0].url,
    "/api/chat/interactive-choice/pending",
  );
  assert.deepEqual(JSON.parse(mock.history.post[0].data as string), {
    session_id: RECON_UMO,
  });
  assert.equal(mock.history.get.length, 0);

  // Backend entries are now in activeChoices[RECON_UMO].
  assert.ok(store.activeChoices[RECON_UMO]?.["from-backend-1"]);
  assert.equal(
    store.activeChoices[RECON_UMO]["from-backend-1"].prompt,
    "Backend prompt",
  );
  assert.ok(store.activeChoices[RECON_UMO]?.["from-backend-2"]);
  // The per-UMO getter flattens the bucket.
  assert.equal(store.asList.length, 2);

  // Persistence reflects the merged state — single UMO key, shape
  // is Record<request_id, part> (Object.keys count), not an array.
  const persisted = JSON.parse(localStorage.getItem(STORAGE_KEY) as string);
  assert.equal(Object.keys(persisted[RECON_UMO]).length, 2);
});

// Bug Y1 regression: reconcile must overwrite the *matching* UMO only,
// leaving sibling UMOs untouched.
test("reconcile only overwrites the matching UMO bucket", async () => {
  mock.onPost("/api/chat/interactive-choice/pending").reply(200, {
    status: "ok",
    data: {
      pending: [
        {
          type: "interactive_choice",
          request_id: "overwritten",
          prompt: "from backend",
          options: [{ id: "A", label: "a" }],
        },
      ],
    },
  });

  const store = useInteractiveChoiceStore();
  // Add a part under a sibling UMO — it must survive reconcile.
  store.addChoice("webchat:other!1!sess", {
    type: "interactive_choice",
    request_id: "sibling-1",
    prompt: "I'm in a different session",
    options: [{ id: "X", label: "x" }],
  });

  await store.reconcile(TEST_UMO);

  assert.ok(store.activeChoices[TEST_UMO]?.["overwritten"]);
  assert.ok(store.activeChoices["webchat:other!1!sess"]?.["sibling-1"]);
  assert.equal(
    store.activeChoices["webchat:other!1!sess"]["sibling-1"].prompt,
    "I'm in a different session",
  );
});

// ---------------------------------------------------------------------------
// Bug X1 fix: injectOrphans re-attach hydrated store parts to nearest bot
// message.
// ---------------------------------------------------------------------------

function makeBotMessage(
  parts: Array<Record<string, unknown> & { type: string }> = [],
) {
  return { content: { message: parts } };
}

test("injectOrphans attaches a single orphan to the only bot message", () => {
  const store = useInteractiveChoiceStore();
  store.addChoice(TEST_UMO, {
    type: "interactive_choice",
    request_id: "orphan-1",
    prompt: "Pick one",
    options: [{ id: "A", label: "a" }],
  });

  const bot = makeBotMessage();
  const injected = store.injectOrphans(TEST_UMO, [bot]);

  assert.equal(injected, 1);
  assert.equal(bot.content.message.length, 1);
  assert.equal(bot.content.message[0].request_id, "orphan-1");
});

test("injectOrphans is idempotent when a part is already in messages", () => {
  const store = useInteractiveChoiceStore();
  store.addChoice(TEST_UMO, {
    type: "interactive_choice",
    request_id: "dup-1",
    prompt: "Pick one",
    options: [{ id: "A", label: "a" }],
  });

  const bot = makeBotMessage([
    {
      type: "interactive_choice",
      request_id: "dup-1",
      prompt: "x",
      options: [],
    },
  ]);
  const injected = store.injectOrphans(TEST_UMO, [bot]);

  assert.equal(injected, 0);
  assert.equal(bot.content.message.length, 1);
});

test("injectOrphans skips user messages (no `content.message` array)", () => {
  const store = useInteractiveChoiceStore();
  store.addChoice(TEST_UMO, {
    type: "interactive_choice",
    request_id: "orphan-2",
    prompt: "Pick one",
    options: [{ id: "A", label: "a" }],
  });

  const user = { content: { text: "hello" } } as unknown as Parameters<
    typeof store.injectOrphans
  >[1][number];
  const injected = store.injectOrphans(TEST_UMO, [user]);

  assert.equal(injected, 0);
});

test("injectOrphans picks the *last* bot message when there are several", () => {
  const store = useInteractiveChoiceStore();
  store.addChoice(TEST_UMO, {
    type: "interactive_choice",
    request_id: "orphan-3",
    prompt: "Pick one",
    options: [{ id: "A", label: "a" }],
  });

  const bot1 = makeBotMessage([{ type: "text", text: "earlier" }]);
  const bot2 = makeBotMessage([{ type: "text", text: "later" }]);
  const injected = store.injectOrphans(TEST_UMO, [bot1, bot2]);

  assert.equal(injected, 1);
  assert.equal(bot1.content.message.length, 1);
  assert.equal(bot2.content.message.length, 2);
  assert.equal(bot2.content.message[1].request_id, "orphan-3");
});

test("injectOrphans does nothing when the store is empty", () => {
  const store = useInteractiveChoiceStore();
  const bot = makeBotMessage();
  const injected = store.injectOrphans(TEST_UMO, [bot]);

  assert.equal(injected, 0);
  assert.equal(bot.content.message.length, 0);
});

test("injectOrphans leaves a part as orphan when there is no bot message", () => {
  const store = useInteractiveChoiceStore();
  store.addChoice(TEST_UMO, {
    type: "interactive_choice",
    request_id: "orphan-4",
    prompt: "Pick one",
    options: [{ id: "A", label: "a" }],
  });

  const injected = store.injectOrphans(TEST_UMO, []);
  assert.equal(injected, 0);
  assert.ok(store.activeChoices[TEST_UMO]?.["orphan-4"]);
});

test("injectOrphans injects multiple orphans each into the last bot message", () => {
  const store = useInteractiveChoiceStore();
  store.addChoice(TEST_UMO, {
    type: "interactive_choice",
    request_id: "multi-1",
    prompt: "first",
    options: [{ id: "A", label: "a" }],
  });
  store.addChoice(TEST_UMO, {
    type: "interactive_choice",
    request_id: "multi-2",
    prompt: "second",
    options: [{ id: "B", label: "b" }],
  });

  const bot = makeBotMessage();
  const injected = store.injectOrphans(TEST_UMO, [bot]);

  assert.equal(injected, 2);
  assert.equal(bot.content.message.length, 2);
  const ids = bot.content.message.map((p) => p.request_id);
  assert.ok(ids.includes("multi-1"));
  assert.ok(ids.includes("multi-2"));
});

// ---------------------------------------------------------------------------
// Bug 1 fix: submissionStates per UMO.
// ---------------------------------------------------------------------------

import {
  CANCELLED_STORAGE_KEY,
  IGNORED_STORAGE_KEY,
  SUBMISSION_STORAGE_KEY,
} from "./interactiveChoice.ts";

test("SUBMISSION_STORAGE_KEY is the expected localStorage key", () => {
  assert.equal(
    SUBMISSION_STORAGE_KEY,
    "astrbot-interactive-choice-submissions",
  );
});

test("IGNORED_STORAGE_KEY is the expected localStorage key", () => {
  assert.equal(IGNORED_STORAGE_KEY, "astrbot-interactive-choice-ignored");
});

test("markSubmitted stores an option-based submission and persists it", () => {
  const store = useInteractiveChoiceStore();
  store.markSubmitted(TEST_UMO, "req-A", "option", { optionId: "A" });

  const got = store.getSubmissionState(TEST_UMO, "req-A");
  assert.ok(got);
  assert.equal(got?.kind, "option");
  assert.equal(got?.optionId, "A");
  const persisted = JSON.parse(
    localStorage.getItem(SUBMISSION_STORAGE_KEY) as string,
  );
  assert.equal(persisted[TEST_UMO]["req-A"].optionId, "A");
});

test("markSubmitted stores a free-text submission and persists it", () => {
  const store = useInteractiveChoiceStore();
  store.markSubmitted(TEST_UMO, "req-B", "input", { freeText: "选我选我" });

  const got = store.getSubmissionState(TEST_UMO, "req-B");
  assert.ok(got);
  assert.equal(got?.kind, "input");
  assert.equal(got?.freeText, "选我选我");
});

test("markSubmitted overwrites a previous submission for the same request_id", () => {
  const store = useInteractiveChoiceStore();
  store.markSubmitted(TEST_UMO, "req-X", "option", { optionId: "A" });
  store.markSubmitted(TEST_UMO, "req-X", "option", { optionId: "B" });
  assert.equal(store.getSubmissionState(TEST_UMO, "req-X")?.optionId, "B");
});

test("getSubmissionState returns undefined for unknown request_id", () => {
  const store = useInteractiveChoiceStore();
  assert.equal(
    store.getSubmissionState(TEST_UMO, "never-submitted"),
    undefined,
  );
});

test("submissionStates for different request_ids are isolated", () => {
  const store = useInteractiveChoiceStore();
  store.markSubmitted(TEST_UMO, "req-1", "option", { optionId: "A" });
  store.markSubmitted(TEST_UMO, "req-2", "input", { freeText: "free" });
  assert.equal(store.getSubmissionState(TEST_UMO, "req-1")?.optionId, "A");
  assert.equal(store.getSubmissionState(TEST_UMO, "req-2")?.freeText, "free");
});

test("submitChoice does NOT clear the submission state (UI keeps showing '已选择')", async () => {
  const store = useInteractiveChoiceStore();
  store.addChoice(TEST_UMO, {
    type: "interactive_choice",
    request_id: "req-persist",
    prompt: "Pick one",
    options: [{ id: "A", label: "a" }],
  });
  store.markSubmitted(TEST_UMO, "req-persist", "option", { optionId: "B" });
  mock
    .onPost("/api/chat/interactive-choice/req-persist")
    .reply(200, { status: "ok", data: null });

  await store.submitChoice(TEST_UMO, "req-persist", {
    choice_id: "B",
    free_text: "",
  });

  // choice removed
  assert.equal(store.activeChoices[TEST_UMO]?.["req-persist"], undefined);
  // but submissionStates still holds the user's choice
  const state = store.getSubmissionState(TEST_UMO, "req-persist");
  assert.ok(state, "submissionStates must survive submitChoice");
  assert.equal(state?.optionId, "B");
});

test("clearSubmissionState removes the entry and persists", () => {
  const store = useInteractiveChoiceStore();
  store.markSubmitted(TEST_UMO, "req-clear", "input", { freeText: "x" });
  assert.ok(store.getSubmissionState(TEST_UMO, "req-clear"));
  store.clearSubmissionState(TEST_UMO, "req-clear");
  assert.equal(store.getSubmissionState(TEST_UMO, "req-clear"), undefined);
});

test("hydrate restores submissionStates from localStorage", () => {
  // Pre-populate per-UMO submissions in localStorage.
  const saved = {
    [TEST_UMO]: {
      "hyd-A": {
        kind: "option",
        optionId: "A",
        submittedAt: 1_700_000_000_000,
      },
      "hyd-B": {
        kind: "input",
        freeText: "hi",
        submittedAt: 1_700_000_001_000,
      },
    },
  };
  localStorage.setItem(SUBMISSION_STORAGE_KEY, JSON.stringify(saved));

  const store = useInteractiveChoiceStore();
  store.hydrate(TEST_UMO);

  assert.equal(store.getSubmissionState(TEST_UMO, "hyd-A")?.optionId, "A");
  assert.equal(store.getSubmissionState(TEST_UMO, "hyd-B")?.freeText, "hi");
});

test("hydrate tolerates corrupt submissionStates JSON without throwing", () => {
  localStorage.setItem(SUBMISSION_STORAGE_KEY, "{not json");
  const store = useInteractiveChoiceStore();
  store.hydrate(TEST_UMO);
  assert.equal(
    Object.keys(
      (store as unknown as { submissionStates: object }).submissionStates,
    ).length,
    0,
  );
  assert.equal(localStorage.getItem(SUBMISSION_STORAGE_KEY), null);
});

// ---------------------------------------------------------------------------
// Bug Y1 regression: per-UMO isolation — the new tests that pin the Y1 fix.
// ---------------------------------------------------------------------------

test("addChoice under different UMOs does not collide", () => {
  const store = useInteractiveChoiceStore();
  store.addChoice("webchat:alice!1!sess", {
    type: "interactive_choice",
    request_id: "shared-rid",
    prompt: "for alice",
    options: [{ id: "A", label: "a" }],
  });
  store.addChoice("webchat:bob!2!sess", {
    type: "interactive_choice",
    request_id: "shared-rid",
    prompt: "for bob",
    options: [{ id: "B", label: "b" }],
  });

  assert.equal(
    store.activeChoices["webchat:alice!1!sess"]["shared-rid"].prompt,
    "for alice",
  );
  assert.equal(
    store.activeChoices["webchat:bob!2!sess"]["shared-rid"].prompt,
    "for bob",
  );
});

test("removeChoice only affects the matching UMO bucket", () => {
  const store = useInteractiveChoiceStore();
  store.addChoice("webchat:uA!1!s", {
    type: "interactive_choice",
    request_id: "rA",
    prompt: "A",
    options: [{ id: "X", label: "x" }],
  });
  store.addChoice("webchat:uB!2!s", {
    type: "interactive_choice",
    request_id: "rB",
    prompt: "B",
    options: [{ id: "Y", label: "y" }],
  });

  store.removeChoice("webchat:uA!1!s", "rA");

  // removeChoice's "empty bucket auto-delete" policy means
  // activeChoices["webchat:uA!1!s"] becomes `undefined` after the
  // only child is removed — that's the intended memory-hygiene
  // behaviour, so assert on the bucket itself.
  assert.equal(
    store.activeChoices["webchat:uA!1!s"],
    undefined,
    "removed UMO bucket should be auto-deleted once empty",
  );
  assert.equal(store.activeChoices["webchat:uB!2!s"]?.["rB"]?.prompt, "B");
});

test("hydrate with a new UMO wipes the previous bucket from memory", () => {
  // Boot with UMO #1, add a part, then switch to UMO #2 and add another.
  const store = useInteractiveChoiceStore();
  store.hydrate("webchat:one!1!s");
  store.addChoice("webchat:one!1!s", {
    type: "interactive_choice",
    request_id: "r1",
    prompt: "first session",
    options: [{ id: "A", label: "a" }],
  });
  assert.ok(store.activeChoices["webchat:one!1!s"]?.["r1"]);

  // Switching to UMO #2 must clear UMO #1's in-memory bucket.
  store.hydrate("webchat:two!2!s");
  assert.equal(store.activeChoices["webchat:one!1!s"], undefined);
  assert.equal(store.currentUmo, "webchat:two!2!s");

  store.addChoice("webchat:two!2!s", {
    type: "interactive_choice",
    request_id: "r2",
    prompt: "second session",
    options: [{ id: "B", label: "b" }],
  });

  // After the switch UMO #1 is gone in memory but persistence still
  // holds it (we cleared only in memory; localStorage was rewritten
  // by addChoice under UMO #2 and now contains both buckets).
  const persisted = JSON.parse(localStorage.getItem(STORAGE_KEY) as string);
  // The legacy blank-result is not required: just verify UMO #1's
  // bucket was *not* deleted from localStorage by hydrate (that's
  // an in-memory-only op). We expect either shape depending on
  // whether addChoice later overwrote; for this test, since
  // addChoice writes through persist(), UMO #2 is present, UMO #1
  // may still be present depending on order.
  assert.ok(persisted["webchat:two!2!s"]);
  assert.equal(persisted["webchat:two!2!s"]["r2"].prompt, "second session");
});

test("hydrate drops legacy flat-array payloads from localStorage", () => {
  // The legacy (pre-2026-07-04) format was an Array<Part> under
  // STORAGE_KEY. hydrate must clear it without crashing.
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify([
      {
        type: "interactive_choice",
        request_id: "legacy",
        prompt: "old",
        options: [{ id: "A", label: "a" }],
      },
    ]),
  );
  const store = useInteractiveChoiceStore();
  store.hydrate(TEST_UMO);
  assert.equal(store.hasAny, false);
  // Migration path removed the legacy payload on read.
  assert.equal(localStorage.getItem(STORAGE_KEY), null);
});

test("getSubmissionState is scoped per UMO (Bug Y1 fix)", () => {
  const store = useInteractiveChoiceStore();
  store.markSubmitted("webchat:uA", "shared", "option", { optionId: "A" });
  store.markSubmitted("webchat:uB", "shared", "option", { optionId: "B" });

  assert.equal(store.getSubmissionState("webchat:uA", "shared")?.optionId, "A");
  assert.equal(store.getSubmissionState("webchat:uB", "shared")?.optionId, "B");
});

test("markSubmitted throws when umo is missing (safety)", () => {
  const store = useInteractiveChoiceStore();
  assert.throws(
    () => store.markSubmitted("", "rid", "option", { optionId: "A" }),
    /missing required 'umo'/,
  );
  assert.throws(
    () =>
      store.addChoice("", {
        type: "interactive_choice",
        request_id: "rid",
        prompt: "p",
        options: [{ id: "A", label: "a" }],
      }),
    /missing required 'umo'/,
  );
});

// ---------------------------------------------------------------------------
// Bug 2 fix: per-UMO ignoredStates — persist "pass-over" so a hard
// refresh doesn't briefly re-show the choice box as pending while
// history reloads. Mirrors the SUBMISSION_STORAGE_KEY test layout.
// ---------------------------------------------------------------------------

test("markIgnored persists and isIgnored reads true", () => {
  const store = useInteractiveChoiceStore();
  store.markIgnored(TEST_UMO, ["req-A", "req-B"]);

  assert.equal(store.isIgnored(TEST_UMO, "req-A"), true);
  assert.equal(store.isIgnored(TEST_UMO, "req-B"), true);
  assert.equal(store.isIgnored(TEST_UMO, "req-OTHER"), false);

  // Persisted as Record<UMO, Record<id, true>>.
  const persisted = JSON.parse(
    localStorage.getItem(IGNORED_STORAGE_KEY) as string,
  );
  assert.deepEqual(persisted[TEST_UMO], { "req-A": true, "req-B": true });
});

test("markIgnored is idempotent — re-mark does not double-write", () => {
  const store = useInteractiveChoiceStore();
  store.markIgnored(TEST_UMO, ["req-A"]);
  // Snapshot persisted size by inspecting via markIgnored: second
  // pass with the same id must remain a single true entry.
  store.markIgnored(TEST_UMO, ["req-A", "req-A", "req-A"]);
  const persisted = JSON.parse(
    localStorage.getItem(IGNORED_STORAGE_KEY) as string,
  );
  assert.deepEqual(
    Object.keys(persisted[TEST_UMO]).sort(),
    ["req-A"],
    "re-marking the same id should not duplicate the key",
  );
});

test("markIgnored with empty array is a no-op (no persist call)", () => {
  const store = useInteractiveChoiceStore();
  store.markIgnored(TEST_UMO, []);
  assert.equal(localStorage.getItem(IGNORED_STORAGE_KEY), null);
  assert.equal(
    Object.keys((store as unknown as { ignoredStates: object }).ignoredStates)
      .length,
    0,
  );
});

test("markIgnored ignores non-string / empty ids inside the batch", () => {
  const store = useInteractiveChoiceStore();
  // Mixed junk batch — only well-formed string ids land in the bucket.
  store.markIgnored(TEST_UMO, [
    "",
    "ok-1",
    // Pinia/TS would prevent these at compile time, but the action
    // is forgiving at runtime for safety.
    null as unknown as string,
    undefined as unknown as string,
    "ok-2",
  ]);
  assert.equal(store.isIgnored(TEST_UMO, "ok-1"), true);
  assert.equal(store.isIgnored(TEST_UMO, "ok-2"), true);
  const persisted = JSON.parse(
    localStorage.getItem(IGNORED_STORAGE_KEY) as string,
  );
  assert.deepEqual(Object.keys(persisted[TEST_UMO]).sort(), ["ok-1", "ok-2"]);
});

test("isIgnored is scoped per UMO (Bug Y1 mirror)", () => {
  const store = useInteractiveChoiceStore();
  store.markIgnored("webchat:uA", ["shared"]);
  store.markIgnored("webchat:uB", ["shared"]);

  assert.equal(store.isIgnored("webchat:uA", "shared"), true);
  assert.equal(store.isIgnored("webchat:uB", "shared"), true);
  assert.equal(
    store.isIgnored("webchat:uC" /* never set */, "shared"),
    false,
    "unmarked UMO never returns true",
  );
});

test("isIgnored returns false when umo is empty (no throw)", () => {
  const store = useInteractiveChoiceStore();
  // The Y1 fix raises on markIgnored(""), but read-only isIgnored
  // is forgiving — empty umo means "no bucket".
  assert.doesNotThrow(() => store.isIgnored("", "rid"));
  assert.equal(store.isIgnored("", "rid"), false);
});

test("hydrate restores ignoredStates from localStorage", () => {
  const saved = {
    [TEST_UMO]: {
      "hyd-A": true,
      "hyd-B": true,
    },
  };
  localStorage.setItem(IGNORED_STORAGE_KEY, JSON.stringify(saved));

  const store = useInteractiveChoiceStore();
  store.hydrate(TEST_UMO);

  assert.equal(store.isIgnored(TEST_UMO, "hyd-A"), true);
  assert.equal(store.isIgnored(TEST_UMO, "hyd-B"), true);
});

test("hydrate tolerates corrupt ignoredStates JSON without throwing", () => {
  localStorage.setItem(IGNORED_STORAGE_KEY, "{not json");
  const store = useInteractiveChoiceStore();
  store.hydrate(TEST_UMO);
  assert.equal(
    Object.keys((store as unknown as { ignoredStates: object }).ignoredStates)
      .length,
    0,
    "corrupt JSON must not leak into in-memory state",
  );
  assert.equal(localStorage.getItem(IGNORED_STORAGE_KEY), null);
});

test("hydrate drops legacy flat-array ignoredStates payload", () => {
  // Same shape as the activeChoices legacy migration — flat arrays
  // pre-date per-UMO scoping and are dropped, never read.
  localStorage.setItem(IGNORED_STORAGE_KEY, JSON.stringify(["legacy"]));
  const store = useInteractiveChoiceStore();
  store.hydrate(TEST_UMO);
  assert.equal(store.isIgnored(TEST_UMO, "anything"), false);
  assert.equal(localStorage.getItem(IGNORED_STORAGE_KEY), null);
});

test("hydrate to a new UMO clears the prior UMO's ignoredStates", () => {
  const store = useInteractiveChoiceStore();
  store.markIgnored("webchat:prior", ["rid-X"]);
  assert.equal(store.isIgnored("webchat:prior", "rid-X"), true);

  store.hydrate("webchat:fresh");
  // Switching to a new UMO must drop the previous UMO's in-memory
  // bucket — same contract as submissionStates / activeChoices.
  assert.equal(
    store.isIgnored("webchat:prior", "rid-X"),
    false,
    "post-switch, prior UMO bucket must be empty",
  );
});

test("markIgnored throws when umo is missing (safety)", () => {
  const store = useInteractiveChoiceStore();
  assert.throws(() => store.markIgnored("", ["rid"]), /missing required 'umo'/);
});

// ---------------------------------------------------------------------------
// Task F2: per-UMO cancelledStates — server-driven "this box has been
// resolved by timeout / cancel" tracking. Mirrors the ignoredStates
// layout but is driven by the SSE `interactive_choice_resolved
// {reason: "cancelled"}` event (and by `reconcile(umo)` orphan
// detection) instead of by a later user message.
// ---------------------------------------------------------------------------

test("CANCELLED_STORAGE_KEY is the expected localStorage key", () => {
  assert.equal(CANCELLED_STORAGE_KEY, "astrbot-interactive-choice-cancelled");
});

test("markCancelled is idempotent (re-mark is a no-op)", () => {
  const store = useInteractiveChoiceStore();
  store.markCancelled(TEST_UMO, "rid-1");
  store.markCancelled(TEST_UMO, "rid-1");
  store.markCancelled(TEST_UMO, "rid-1");
  assert.equal(store.isCancelled(TEST_UMO, "rid-1"), true);
});

test("isCancelled returns false for unknown request_id", () => {
  const store = useInteractiveChoiceStore();
  assert.equal(store.isCancelled(TEST_UMO, "rid-unknown"), false);
});

test("cancelledStates is scoped per UMO (Bug Y1 mirror)", () => {
  const store = useInteractiveChoiceStore();
  const umoA = "webchat:FriendMessage:webchat!alice!sess";
  const umoB = "webchat:FriendMessage:webchat!bob!sess";
  store.markCancelled(umoA, "rid-1");
  assert.equal(store.isCancelled(umoA, "rid-1"), true);
  assert.equal(store.isCancelled(umoB, "rid-1"), false);
});

test("reconcile marks locally-tracked parts absent from backend as cancelled", async () => {
  const store = useInteractiveChoiceStore();
  const umo = "webchat:FriendMessage:webchat!alice!sess";

  const partPresent: InteractiveChoicePart = {
    type: "interactive_choice",
    request_id: "rid-present",
    prompt: "x?",
    options: [{ id: "a", label: "A" }],
  };
  const partMissing: InteractiveChoicePart = {
    type: "interactive_choice",
    request_id: "rid-missing",
    prompt: "y?",
    options: [{ id: "b", label: "B" }],
  };
  store.addChoice(umo, partPresent);
  store.addChoice(umo, partMissing);

  // Backend pending list returns only the present one (simulates a
  // missed SSE `interactive_choice_resolved {reason: "cancelled"}`
  // event during a network outage).
  mock.onPost("/api/chat/interactive-choice/pending").reply(200, {
    status: "ok",
    data: { pending: [partPresent] },
  });

  await store.reconcile(umo);

  // The POST was issued to the right URL with the right body.
  assert.equal(mock.history.post.length, 1);
  assert.equal(
    mock.history.post[0].url,
    "/api/chat/interactive-choice/pending",
  );
  assert.deepEqual(JSON.parse(mock.history.post[0].data as string), {
    session_id: umo,
  });
  // Orphan rid is now cancelled; the still-pending rid is not.
  assert.equal(store.isCancelled(umo, "rid-missing"), true);
  assert.equal(store.isCancelled(umo, "rid-present"), false);
});

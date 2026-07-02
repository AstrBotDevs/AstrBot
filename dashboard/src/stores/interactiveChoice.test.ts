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
import {
  STORAGE_KEY,
  useInteractiveChoiceStore,
} from "./interactiveChoice.ts";

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
  const saved = [
    {
      type: "interactive_choice",
      request_id: "req-hydrate-1",
      prompt: "Pick one",
      options: [
        { id: "A", label: "alpha" },
        { id: "B", label: "beta" },
      ],
    },
  ];
  localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));

  // Act
  const store = useInteractiveChoiceStore();
  store.hydrate();

  // Assert: the hydrated item lives in activeChoices.
  assert.ok(
    store.activeChoices["req-hydrate-1"],
    "expected activeChoices to contain hydrated request_id",
  );
  assert.equal(store.activeChoices["req-hydrate-1"].prompt, "Pick one");
  assert.equal(store.asList.length, 1);
  assert.equal(store.hasAny, true);
});

test("hydrate clears localStorage on corrupt JSON", () => {
  // Arrange: stuff a corrupted payload into localStorage.
  localStorage.setItem(STORAGE_KEY, "{not json");

  // Act: hydrate must not throw and must clear the bad key.
  const store = useInteractiveChoiceStore();
  store.hydrate();

  // Assert
  assert.equal(store.asList.length, 0);
  assert.equal(localStorage.getItem(STORAGE_KEY), null);
});

test("hydrate is a no-op when localStorage is empty", () => {
  const store = useInteractiveChoiceStore();
  store.hydrate();
  assert.equal(store.hasAny, false);
});

// ---------------------------------------------------------------------------
// addChoice / removeChoice round-trip via persist -> hydrate
// ---------------------------------------------------------------------------

test("addChoice persists and a fresh store can rehydrate", () => {
  // First store: add a choice.
  const storeA = useInteractiveChoiceStore();
  storeA.addChoice({
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
  storeB.hydrate();
  assert.ok(storeB.activeChoices["req-persist-1"]);
  assert.equal(storeB.activeChoices["req-persist-1"].prompt, "p");
});

test("removeChoice deletes by request_id and clears persisted entry", () => {
  const store = useInteractiveChoiceStore();
  store.addChoice({
    type: "interactive_choice",
    request_id: "req-rm",
    prompt: "p",
    options: [
      { id: "A", label: "a" },
      { id: "B", label: "b" },
    ],
  });
  store.removeChoice("req-rm");
  assert.equal(store.activeChoices["req-rm"], undefined);
  assert.equal(store.hasAny, false);
  assert.equal(localStorage.getItem(STORAGE_KEY), "[]");
});

// ---------------------------------------------------------------------------
// submitChoice: HTTP transport + optimistic removal
// ---------------------------------------------------------------------------

test("submitChoice sends correct payload and removes locally on success", async () => {
  // Arrange: pre-populate store with one choice.
  const store = useInteractiveChoiceStore();
  store.addChoice({
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
  await store.submitChoice("req-1", { choice_id: "A", free_text: "hello" });

  // Assert: one POST to the right URL with the right JSON body.
  assert.equal(mock.history.post.length, 1);
  assert.equal(
    mock.history.post[0].url,
    "/api/chat/interactive-choice/req-1",
  );
  assert.deepEqual(
    JSON.parse(mock.history.post[0].data as string),
    { choice_id: "A", free_text: "hello" },
  );
  // Optimistic local removal on ok envelope.
  assert.equal(store.activeChoices["req-1"], undefined);
  // localStorage persistence also reflects the removal.
  assert.equal(localStorage.getItem(STORAGE_KEY), "[]");
});

test("submitChoice keeps the choice locally when backend returns error", async () => {
  // Arrange
  const store = useInteractiveChoiceStore();
  store.addChoice({
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
    store.submitChoice("req-1", { choice_id: "A", free_text: "" }),
  );

  // The local entry must still be present so the UI can retry or surface the error.
  assert.ok(store.activeChoices["req-1"]);
  assert.equal(store.activeChoices["req-1"].prompt, "Pick one");
  assert.equal(mock.history.post.length, 1);
});

// ---------------------------------------------------------------------------
// reconcile: GET pending from backend and merge into store
// ---------------------------------------------------------------------------

test("reconcile merges backend pending into store", async () => {
  // Arrange: backend returns one pending choice.
  mock
    .onGet("/api/chat/interactive-choice/pending")
    .reply(200, {
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
  await store.reconcile("webchat:FriendMessage:webchat!alice!sess");

  // Assert: GET hit the pending endpoint with the session_id query param.
  assert.equal(mock.history.get.length, 1);
  assert.equal(
    mock.history.get[0].url,
    "/api/chat/interactive-choice/pending",
  );
  assert.deepEqual(mock.history.get[0].params, {
    session_id: "webchat:FriendMessage:webchat!alice!sess",
  });

  // Backend entries are now in activeChoices.
  assert.ok(store.activeChoices["from-backend-1"]);
  assert.equal(
    store.activeChoices["from-backend-1"].prompt,
    "Backend prompt",
  );
  assert.ok(store.activeChoices["from-backend-2"]);
  assert.equal(store.asList.length, 2);

  // Persistence reflects the merged state.
  const persisted = JSON.parse(localStorage.getItem(STORAGE_KEY) as string);
  assert.equal(persisted.length, 2);
});
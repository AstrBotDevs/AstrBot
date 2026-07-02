// Author: elecvoid243 (task13_impl)
// Date: 2026-07-03
// Spec: docs/superpowers/specs/2026-07-02-blocking-interactive-choice-design.md §5.2
//
// Test runner: node --test (Node v24 strips TS from .ts imports automatically).
// Run: cd dashboard && pnpm exec node --test --import tsx src/stores/interactiveChoice.test.ts
//
// Plan Amendment D: a hydrate test is mandatory so that localStorage
// rehydration cannot regress silently.
import assert from "node:assert/strict";
import { test, beforeEach } from "node:test";

// Pinia test harness: createPinia + setActivePinia avoids needing a full Vue app.
import { createPinia, setActivePinia } from "pinia";

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

beforeEach(() => {
  // Fresh Pinia + localStorage for each test.
  setActivePinia(createPinia());
  const mem = new MemoryStorage();
  (globalThis as unknown as { localStorage: MemoryStorage }).localStorage = mem;
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
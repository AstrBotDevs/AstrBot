// Author: elecvoid243 (task12_impl)
// Date: 2026-07-03
// Spec: docs/superpowers/specs/2026-07-02-blocking-interactive-choice-design.md §5.1
//
// Test runner: node --test (Node v24 strips TS from .ts imports automatically).
// Run: cd dashboard && pnpm exec node --test --import tsx src/composables/parseInteractiveChoice.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  isInteractiveChoicePayload,
  validateInteractiveChoice,
  truncateInteractiveChoice,
  getOptionSubmitText,
} from "./parseInteractiveChoice.ts";

test("isInteractiveChoicePayload accepts valid type", () => {
  assert.equal(isInteractiveChoicePayload({ type: "interactive_choice" }), true);
});

test("isInteractiveChoicePayload rejects null", () => {
  assert.equal(isInteractiveChoicePayload(null), false);
});

test("validateInteractiveChoice accepts request_id", () => {
  const valid = {
    type: "interactive_choice",
    request_id: "r1",
    prompt: "test",
    options: [{ id: "A", label: "a" }, { id: "B", label: "b" }],
  };
  assert.equal(validateInteractiveChoice(valid), true);
});

test("validateInteractiveChoice rejects missing request_id", () => {
  const invalid = {
    type: "interactive_choice",
    prompt: "test",
    options: [{ id: "A", label: "a" }, { id: "B", label: "b" }],
  };
  assert.equal(validateInteractiveChoice(invalid), false);
});

test("validateInteractiveChoice rejects empty request_id", () => {
  const invalid = {
    type: "interactive_choice",
    request_id: "  ",
    prompt: "test",
    options: [{ id: "A", label: "a" }, { id: "B", label: "b" }],
  };
  assert.equal(validateInteractiveChoice(invalid), false);
});

test("validateInteractiveChoice rejects duplicate option ids", () => {
  const invalid = {
    type: "interactive_choice",
    request_id: "r1",
    prompt: "test",
    options: [{ id: "A", label: "a" }, { id: "A", label: "b" }],
  };
  assert.equal(validateInteractiveChoice(invalid), false);
});

test("truncateInteractiveChoice preserves request_id", () => {
  const input = {
    type: "interactive_choice" as const,
    request_id: "r1",
    prompt: "x".repeat(300),
    options: [{ id: "A", label: "a" }],
  };
  const out = truncateInteractiveChoice(input);
  assert.equal(out.request_id, "r1");
  assert.equal(out.prompt.length, 200);
});

test("getOptionSubmitText returns id+label when no value", () => {
  const opt = { id: "A", label: "alpha" };
  assert.equal(getOptionSubmitText(opt), "A. alpha");
});

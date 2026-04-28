import assert from "node:assert/strict";
import test from "node:test";

import { isComposingEnter } from "../src/utils/imeInput.mjs";

test("detects Enter while an IME composition is active", () => {
  assert.equal(isComposingEnter({ key: "Enter", isComposing: true }, false), true);
  assert.equal(isComposingEnter({ key: "Enter", isComposing: false }, true), true);
});

test("does not treat normal Enter as IME composition", () => {
  assert.equal(isComposingEnter({ key: "Enter", isComposing: false }, false), false);
  assert.equal(isComposingEnter({ key: "a", isComposing: true }, true), false);
});

test("detects Enter fired immediately after composition ended", () => {
  assert.equal(
    isComposingEnter(
      { key: "Enter", isComposing: false, timeStamp: 105 },
      false,
      100,
    ),
    true,
  );
});

test("does not treat delayed Enter after composition ended as IME composition", () => {
  assert.equal(
    isComposingEnter(
      { key: "Enter", isComposing: false, timeStamp: 250 },
      false,
      100,
    ),
    false,
  );
});

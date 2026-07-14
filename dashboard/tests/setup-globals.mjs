// Author: implementer1, 2026-07-12
// Purpose: Register happy-dom's globals (document, HTMLElement, etc.) so
// node:test can run DOM-dependent tests against composables/components that
// import DOMPurify + markdown-it.
//
// Usage:
//   cd dashboard && node --import tsx --import ./tests/setup-globals.mjs \
//     --test tests/markdownPipeline.test.mjs
//
// This file is INTENTIONALLY NOT imported from any production code. It only
// runs as a `--import` argument to the test runner.

import { Window } from "happy-dom";

const window = new Window();

for (const name of [
  "document",
  "HTMLElement",
  "HTMLAnchorElement",
  "HTMLDivElement",
  "Node",
  "Element",
  "CSS",
  "navigator",
  "getComputedStyle",
  "MutationObserver",
  "DOMParser",
  "Text",
]) {
  if (name in window) {
    try {
      globalThis[name] = window[name];
    } catch {
      /* some props are read-only; skip */
    }
  }
}

globalThis.window = window;

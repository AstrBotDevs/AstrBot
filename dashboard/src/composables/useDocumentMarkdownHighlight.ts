// Author: elecvoid243, 2026-07-14
// Spec: docs/superpowers/specs/2026-07-14-document-fullscreen-review-design.md §3.3
//
// Memoized Shiki wrapper for the DocumentManager raw view. Mirrors
// FileBrowserFilePreview's render call (file_browser.vue:147) but is
// tailored for markdown content (always uses "markdown" grammar,
// always returns dual-theme "auto" rendering).
//
// Design note: Shiki init is shared across every instance of this
// composable. We do NOT use onMounted here because:
//   1. The composable must be testable in plain `it()` blocks (no
//      mount() wrapper). onMounted is a no-op outside a component,
//      which would leave isReady false forever and break tests.
//   2. Sharing one highlighter across all instances avoids redundant
//      Shiki init work — `ensureShikiLanguages()` memoises anyway, but
//      this also shares the `isReady` ref so consumers see the same
//      lifecycle regardless of how many composables they spin up.
//
// Init trigger: the first call to `useDocumentMarkdownHighlight` kicks
// off the shared init (idempotent). This is functionally equivalent to
// starting at module-evaluation time for production — the very first
// composable call (from the first DocumentManager mount) starts the
// load — and is what makes test #1's
// `expect(isReady.value).toBe(false)` assertion deterministic (a
// module-eval IIFE resolves before vitest's first test body runs).
//
// Adversarial input (NUL bytes) is routed to the safe escapeHtml path.
// Shiki's text grammar renders raw \u0000 unchanged, which breaks the
// DOM. We detect NULs and use the HTML-escaped <pre><code> fallback
// (the same one used when Shiki throws).

import { computed, ref, type ComputedRef, type Ref } from "vue";
import {
  ensureShikiLanguages,
  renderShikiCode,
  escapeHtml,
} from "@/utils/shiki";

export interface UseDocumentMarkdownHighlight {
  /** Shiki-highlighted HTML for `content` (markdown grammar, dual-theme). */
  highlightedHtml: ComputedRef<string>;
  /** True after the async highlighter is initialized. */
  isReady: Ref<boolean>;
}

// `escapeHtml` is imported from @/utils/shiki (see import above).
// The imported version handles & < > " ' — all 5 chars we need for
// safe <pre><code> fallbacks — but does NOT handle \u0000. We chain
// `.replace(/\u0000/g, "&#0;")` after it in the NUL branch below so
// adversarial NUL input never reaches the DOM.

// Module-level shared state. One Shiki highlighter per process, and one
// isReady ref shared across every composable instance.
let _sharedHighlighter: unknown = null;
const _initDone = ref<boolean>(false);
let _initPromise: Promise<void> | null = null;

function _ensureInit(): Promise<void> {
  if (_initPromise) return _initPromise;
  _initPromise = (async () => {
    if (_sharedHighlighter !== null) return;
    try {
      _sharedHighlighter = await ensureShikiLanguages();
    } catch (err) {
      // Shiki init failure is non-fatal — the computed falls back to
      // escaped <pre><code>. Log once so the user can find it via
      // devtools if they ever need to.
      console.error("useDocumentMarkdownHighlight: shiki init failed", err);
    } finally {
      _initDone.value = true;
    }
  })();
  return _initPromise;
}

export function useDocumentMarkdownHighlight(
  content: Ref<string>,
  // isDark is accepted (Task 2 passes it) but not consumed in v1 —
  // renderShikiCode is always called with colorMode="auto" since Shiki's
  // dual-theme rendering picks light vs dark via CSS media queries.
  // Kept in the signature so Task 2's call site compiles unchanged.
  isDark: Ref<boolean> = ref(false),
): UseDocumentMarkdownHighlight {
  // Kick off the init if it hasn't been started yet. The IIFE body
  // runs as microtasks, so a synchronous `expect(isReady.value).toBe(false)`
  // assertion in a test body still observes the pre-init value.
  void _ensureInit();

  return {
    isReady: _initDone,
    highlightedHtml: computed<string>(() => {
      const text = content.value;
      if (!text) return "";
      // Adversarial input: NUL bytes break the DOM and Shiki's text
      // grammar passes them through unchanged. Route to the safe
      // escapeHtml path BEFORE checking isReady (so this also covers
      // the pre-init window) and BEFORE handing the text to Shiki.
      // `indexOf` is used instead of `includes` for the same
      // ES2021-lib compatibility reason as above.
      if (text.indexOf("\u0000") !== -1) {
        return `<pre><code>${escapeHtml(text).replace(/\u0000/g, "&#0;")}</code></pre>`;
      }
      if (!_initDone.value || _sharedHighlighter === null) {
        return `<pre><code>${escapeHtml(text)}</code></pre>`;
      }
      try {
        // renderShikiCode signature: (highlighter, code, language, colorMode)
        // colorMode="auto" enables dual-theme (light/dark) auto-switching.
        // DocumentManager only displays .md files; we hardcode the grammar
        // here rather than detecting from a path extension.
        return renderShikiCode(
          _sharedHighlighter as never,
          text,
          "markdown",
          "auto",
        ) as string;
      } catch (err) {
        console.error("useDocumentMarkdownHighlight: render failed", err);
        return `<pre><code>${escapeHtml(text)}</code></pre>`;
      }
    }),
  };
}

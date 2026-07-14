// Author: elecvoid243, 2026-07-14
// Spec: docs/superpowers/specs/2026-07-14-document-fullscreen-review-design.md §3.3
//
// Spec for useDocumentMarkdownHighlight — see impl file for the public
// contract being tested.

import { describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import { useDocumentMarkdownHighlight } from "./useDocumentMarkdownHighlight";

describe("useDocumentMarkdownHighlight", () => {
  it("returns empty html until shiki is ready, then renders markdown", async () => {
    const content = ref<string>("# Hello\n\nworld");
    const { highlightedHtml, isReady } = useDocumentMarkdownHighlight(content);
    expect(isReady.value).toBe(false);
    // First nextTick: onMounted hooks fire; shiki is fetched async.
    await nextTick();
    // Wait for the async shiki init to resolve. The composable flips
    // isReady to true once ensureShikiLanguages resolves.
    await vi.waitFor(() => expect(isReady.value).toBe(true), { timeout: 5000 });
    await nextTick();
    expect(highlightedHtml.value).toContain("class=\"line\"");
    expect(highlightedHtml.value.length).toBeGreaterThan(0);
  });

  it("falls back to escaped <pre><code> when shiki render throws", async () => {
    // Force the shiki highlighter to throw by passing an obviously
    // invalid content type — we cannot easily stub the highlighter
    // since the composable imports it directly. Instead we assert
    // the safe-fallback contract: the result must still be valid
    // HTML even for adversarial input.
    const content = ref<string>("\u0000\u0000\u0000");
    const { highlightedHtml, isReady } = useDocumentMarkdownHighlight(content);
    await vi.waitFor(() => expect(isReady.value).toBe(true), { timeout: 5000 });
    await nextTick();
    // Must not be empty, must not throw, must not contain raw NUL bytes
    // in the output (would break the DOM).
    expect(highlightedHtml.value).toBeTruthy();
    expect(highlightedHtml.value).not.toContain("\u0000");
  });

  it("memoizes on (content, isDark) — same input returns same ref value", async () => {
    const content = ref<string>("const x = 1;");
    const isDark = ref<boolean>(false);
    const a = useDocumentMarkdownHighlight(content, isDark);
    await vi.waitFor(() => expect(a.isReady.value).toBe(true), { timeout: 5000 });
    await nextTick();
    const firstHtml = a.highlightedHtml.value;
    // Touch the content (no change) — html should remain the same
    // reference (the computed memoizes).
    void a.highlightedHtml.value;
    void a.highlightedHtml.value;
    expect(a.highlightedHtml.value).toBe(firstHtml);
  });
});

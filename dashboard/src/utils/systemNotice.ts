/**
 * Utilities for detecting and extracting system-injected suffixes from
 * tool call results.  Two kinds of suffixes are recognised:
 *
 * 1. **[SYSTEM NOTICE]** — repeated-tool warnings, follow-up notices, etc.
 *    Always prefixed with the literal marker `[SYSTEM NOTICE]` followed by
 *    one of the known SYSTEM_NOTICE_PREFIXES.
 *
 * 2. **Tool-result overflow notice** — emitted when a tool output is too
 *    large and gets spilled to a file.  The notice text starts with
 *    `"Truncated tool output preview shown above."` and does NOT carry the
 *    `[SYSTEM NOTICE]` marker (it is a plain-text suffix).
 *
 * Both suffixes are always appended at the very end of the tool result by
 * the backend, possibly as a chain of multiple notices (e.g. repeated-tool
 * warning + follow-up notice).  When the tool output itself contains text
 * that looks like a system notice (e.g. reading a log file), the algorithm
 * must correctly ignore those false positives.
 *
 * **Key invariant**: the real system notice chain starts at the EARLIEST
 * valid candidate where everything from that position to end-of-text is
 * exclusively notice-chain content (no file content mixed in).
 *
 * Known message prefixes produced by the AstrBot system (not file content).
 * Used to distinguish genuine system notices from text that happens to
 * contain the literal string "[SYSTEM NOTICE]".
 */
export const SYSTEM_NOTICE_PREFIXES = [
  "By the way,",
  "Important:",
  "User sent",
];

const MARKER = "[SYSTEM NOTICE]";

/** Distinctive opening of the tool-result overflow notice. */
const OVERFLOW_NOTICE_PREFIX = "Truncated tool output preview shown above.";

// ── Helpers ─────────────────────────────────────────────────────────────

/**
 * Check whether the text starting at `idx` begins with a genuine
 * `[SYSTEM NOTICE]` marker followed by one of the known prefixes.
 */
function isGenuineSystemNotice(text: string, idx: number): boolean {
  const suffix = text.slice(idx).trim();
  return SYSTEM_NOTICE_PREFIXES.some((p) =>
    suffix.startsWith(`${MARKER} ${p}`),
  );
}

/**
 * Check whether the entire region from `fromPos` to end-of-text contains
 * ONLY notice-chain content (no real file content).
 *
 * Allowed line types within the notice chain:
 *   - Blank lines (separators between notices)
 *   - Lines containing `[SYSTEM NOTICE]` (notice markers and their bodies)
 *   - Lines starting with the overflow notice prefix
 *   - Numbered list items (`N. …`) — but ONLY when preceded by a
 *     `[SYSTEM NOTICE] User sent` (follow-up notice) in the chain.
 *     This prevents file content like `1. item` from being mistaken for
 *     notice content.
 *   - Continuation lines of a notice paragraph (non-blank, directly after
 *     a notice marker line, before any blank line gap).
 */
function isNoticeChainRegion(text: string, fromPos: number): boolean {
  const region = text.slice(fromPos);
  const lines = region.split("\n");
  let inFollowUp = false;
  let sawBlankAfterNotice = false;

  for (const rawLine of lines) {
    const trimmed = rawLine.trim();

    // Blank lines are separators between notices — always allowed.
    if (trimmed === "") {
      if (!inFollowUp) sawBlankAfterNotice = true;
      continue;
    }

    // [SYSTEM NOTICE] marker — starts a new notice in the chain.
    if (trimmed.includes(MARKER)) {
      // Track whether this is a follow-up notice (allows numbered items).
      const markerIdx = trimmed.indexOf(MARKER);
      const afterMarker = trimmed.slice(markerIdx).trim();
      if (afterMarker.startsWith(`${MARKER} User sent`)) {
        inFollowUp = true;
      }
      sawBlankAfterNotice = false;
      continue;
    }

    // Overflow notice prefix — part of the chain.
    if (trimmed.startsWith(OVERFLOW_NOTICE_PREFIX)) {
      inFollowUp = false;
      sawBlankAfterNotice = false;
      continue;
    }

    // Numbered list items — only valid after a "User sent" follow-up notice.
    if (inFollowUp && /^\d+\.\s/.test(trimmed)) continue;

    // Continuation lines:
    // - In follow-up mode: free-form instruction text is part of the notice body.
    // - Outside follow-up: continuation of an overflow notice paragraph
    //   (before any blank line gap).
    if (inFollowUp || !sawBlankAfterNotice) {
      continue;
    }

    // Anything else is real file content — not a valid notice chain.
    return false;
  }

  return true;
}

// ── Public API ──────────────────────────────────────────────────────────

/**
 * Find the character index where the system notice suffix begins.
 *
 * Returns the EARLIEST position where a genuine notice candidate starts
 * and everything from that position to end-of-text is exclusively
 * notice-chain content.  This ensures that when multiple notices are
 * chained (e.g. repeated-tool warning + follow-up notice), ALL of them
 * are captured in the suffix.
 *
 * For tools whose result may contain file content (e.g. astrbot_file_read_tool,
 * astrbot_file_edit_tool), the raw result can include literal
 * `[SYSTEM NOTICE]` strings or overflow-notice-like text that are part of
 * the file being read/edited, not a system message.  These are rejected
 * because the region from the fake notice to end-of-text contains real
 * file content.
 *
 * **Strategy** (first valid candidate wins):
 *   1. Find all `[SYSTEM NOTICE]` markers in the text (in order).
 *   2. For each genuine marker (earliest first), check if the region from
 *      that position to end-of-text is a valid notice chain.
 *   3. Return the first position that passes.
 *   4. If no `[SYSTEM NOTICE]` passes, check for overflow notice.
 *   5. If nothing passes, return -1.
 *
 * @returns The character index where the notice suffix begins, or -1.
 */
export function findSystemNoticeIndex(text: string): number {
  // ── Collect all candidates and sort by position ascending ─────────
  const positions: { pos: number; type: "system" | "overflow" }[] = [];

  let searchFrom = 0;
  while (searchFrom < text.length) {
    const idx = text.indexOf(MARKER, searchFrom);
    if (idx < 0) break;
    positions.push({ pos: idx, type: "system" });
    searchFrom = idx + MARKER.length;
  }

  searchFrom = 0;
  while (searchFrom < text.length) {
    const idx = text.indexOf(OVERFLOW_NOTICE_PREFIX, searchFrom);
    if (idx < 0) break;
    positions.push({ pos: idx, type: "overflow" });
    searchFrom = idx + OVERFLOW_NOTICE_PREFIX.length;
  }

  positions.sort((a, b) => a.pos - b.pos);

  // ── Check each candidate (earliest first) ────────────────────────
  for (const { pos, type } of positions) {
    // Quick prefix check — skip non-genuine candidates.
    if (type === "system" && !isGenuineSystemNotice(text, pos)) continue;

    if (isNoticeChainRegion(text, pos)) {
      return pos;
    }
  }

  return -1;
}

/**
 * Split tool result text into the main content and the optional
 * system notice suffix.
 *
 * @param text  The raw tool result text.
 * @returns An object with `content` (the main result) and `notice`
 *          (the system notice string, or null if none).
 */
export function splitSystemNotice(
  text: string,
): { content: string; notice: string | null } {
  const idx = findSystemNoticeIndex(text);
  if (idx < 0) return { content: text, notice: null };
  return {
    content: text.slice(0, idx).trim(),
    notice: text.slice(idx).trim(),
  };
}

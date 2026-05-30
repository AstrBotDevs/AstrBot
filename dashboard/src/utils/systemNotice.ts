/**
 * Utilities for detecting and extracting the genuine AstrBot
 * [SYSTEM NOTICE] suffix from tool call results.
 *
 * @author AstrBot Agent Harness
 * @since 2026-05-30
 */

/**
 * Known message prefixes produced by the AstrBot system (not file content).
 * Used by findRealSystemNoticeIndex() to distinguish genuine system notices
 * from [SYSTEM NOTICE] text that happens to appear inside file content
 * (e.g. when reading AstrBot log files or editing files that contain the
 * literal string "[SYSTEM NOTICE]").
 */
export const SYSTEM_NOTICE_PREFIXES = [
  "By the way,",
  "Important:",
  "This is a",
];

const MARKER = "[SYSTEM NOTICE]";

/**
 * Find the index of the genuine AstrBot system notice in the text.
 *
 * For tools whose result may contain file content (e.g. astrbot_file_read_tool,
 * astrbot_file_edit_tool), the raw result can include literal "[SYSTEM NOTICE]"
 * strings that are part of the file being read/edited, not a system message.
 *
 * Key invariant: the REAL [SYSTEM NOTICE] is ALWAYS the very last thing in
 * the tool result — there is NO content after it.  Any "[SYSTEM NOTICE]"
 * that has non-empty lines following it is necessarily part of the file
 * content, not a system message.
 *
 * Strategy:
 *   1. Find all occurrences of [SYSTEM NOTICE] in the text.
 *   2. Scan from the LAST occurrence backward (most likely to be real).
 *   3. For each candidate:
 *      a. Check it matches a known system prefix.
 *      b. Check there are NO non-empty lines after the notice line.
 *         If there are, this [SYSTEM NOTICE] is embedded in file
 *         content — skip it and try the previous occurrence.
 *   4. If no candidate passes both checks, there is no real notice.
 *
 * @returns The character index of the real [SYSTEM NOTICE], or -1 if none.
 */
export function findRealSystemNoticeIndex(text: string): number {
  // Collect all occurrences so we can scan from last to first.
  const occurrences: number[] = [];
  let searchFrom = 0;
  while (searchFrom < text.length) {
    const idx = text.indexOf(MARKER, searchFrom);
    if (idx < 0) break;
    occurrences.push(idx);
    searchFrom = idx + MARKER.length;
  }
  if (occurrences.length === 0) return -1;

  // Scan from the last occurrence backward.
  for (let i = occurrences.length - 1; i >= 0; i--) {
    const idx = occurrences[i];
    const suffix = text.slice(idx).trim();

    // Must match a known system prefix pattern.
    if (
      !SYSTEM_NOTICE_PREFIXES.some((p) =>
        suffix.startsWith(`${MARKER} ${p}`),
      )
    ) {
      continue;
    }

    // The real system notice is always at the very end of the tool
    // result with NO content after it.  Check if there are any
    // non-empty lines following the notice line — if so, this is
    // file content that happens to contain [SYSTEM NOTICE], not a
    // genuine system message.
    const afterText = text.slice(idx);
    const lines = afterText.split("\n");
    let hasContentAfter = false;
    for (let j = 1; j < lines.length; j++) {
      if (lines[j].trim() !== "") {
        hasContentAfter = true;
        break;
      }
    }
    if (hasContentAfter) {
      // This [SYSTEM NOTICE] has file content after it — it's fake.
      // Continue checking earlier occurrences.
      continue;
    }

    // No content after this notice — it's the real one.
    return idx;
  }

  return -1;
}

/**
 * Split tool result text into the main content and the optional
 * [SYSTEM NOTICE] suffix.
 *
 * @param text  The raw tool result text.
 * @returns An object with `content` (the main result) and `notice`
 *          (the system notice string, or null if none).
 */
export function splitSystemNotice(
  text: string,
): { content: string; notice: string | null } {
  const idx = findRealSystemNoticeIndex(text);
  if (idx < 0) return { content: text, notice: null };
  return {
    content: text.slice(0, idx).trim(),
    notice: text.slice(idx).trim(),
  };
}

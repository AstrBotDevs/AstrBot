// Author: elecvoid243
// Date: 2026-07-07
// Spec: docs/superpowers/specs/2026-07-07-hunk-discard-design.md §5.2
//
// Pure helpers extracted from DiffPreview.vue so they are unit-testable
// without spinning up a Vue SFC. No reactive / Vue dependencies — every
// parameter is passed in explicitly.
//
// Public surface kept minimal:
//   - DiffLine / DiffHunk   — line & hunk shape (replaces inline interfaces
//                             in DiffPreview.vue).
//   - extractDiffContent()  — strip ```diff``` fences / leading preamble.
//   - parseUnifiedDiff()    — full parser used by both the preview renderer
//                             and buildHunkPatchText() (so they parse the
//                             same way).
//   - buildHunkPatchText()  — reconstruct a git-applyable unified-diff
//                             patch for a single hunk, used by the discard
//                             hunk feature. **Output is guaranteed to end
//                             with a single trailing `\n`** so `git apply
//                             --check --reverse` does not reject it as
//                             "corrupt patch".

export interface DiffLine {
  type: "add" | "del" | "ctx" | "header-file";
  prefix: string;
  content: string;
  oldNo: string;
  newNo: string;
}

export interface DiffHunk {
  header: string;
  lines: DiffLine[];
  /** Index in the full parse (maxLines=Infinity). Stable across maxLines
   *  variants (truncation only drops the trailing hunk's tail, never
   *  reshuffles). Used to cross-reference the hunk in the full parse
   *  when buildHunkPatchText() needs the complete body. */
  hunkIndex: number;
}

export function extractDiffContent(raw: string): string {
  // If the text contains a ```diff ... ``` block, extract its content
  const blockMatch = raw.match(/```diff\s*\n?([\s\S]*?)```/);
  if (blockMatch) return blockMatch[1];

  // Otherwise, try to strip leading "Diff:" / "Edited ..." lines
  const diffIdx = raw.indexOf("@@");
  if (diffIdx >= 0) return raw.slice(diffIdx);

  return raw;
}

export function parseUnifiedDiff(text: string, maxLines: number): DiffHunk[] {
  const lines = text.split("\n");
  const hunks: DiffHunk[] = [];
  let currentHunk: DiffHunk | null = null;
  let totalLines = 0;
  let oldNo = 0;
  let newNo = 0;

  // Try to parse --- / +++ file headers to get old/new line numbers
  for (const rawLine of lines) {
    if (totalLines >= maxLines) break;

    const hunkMatch = rawLine.match(
      /^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$/,
    );
    if (hunkMatch) {
      // Flush previous hunk
      if (currentHunk) hunks.push(currentHunk);

      oldNo = parseInt(hunkMatch[1], 10);
      newNo = parseInt(hunkMatch[3], 10);

      currentHunk = {
        header: rawLine,
        lines: [],
        hunkIndex: hunks.length,   // pre-push index; same as final `i` in the v-for
      };
      continue;
    }

    if (!currentHunk) continue;

    const ch = rawLine[0];
    let type: DiffLine["type"];
    let prefix: string;
    let content: string;

    if (ch === "+") {
      type = "add";
      prefix = "+";
      content = rawLine.slice(1);
    } else if (ch === "-") {
      type = "del";
      prefix = "−";
      content = rawLine.slice(1);
    } else if (ch === " ") {
      type = "ctx";
      prefix = " ";
      content = rawLine.slice(1);
    } else if (rawLine === "\\ No newline at end of file") {
      type = "ctx";
      prefix = " ";
      content = rawLine;
    } else {
      // Could be --- or +++ header lines; skip or treat as ctx
      if (rawLine.startsWith("---") || rawLine.startsWith("+++")) continue;
      type = "ctx";
      prefix = " ";
      content = rawLine;
    }

    const line: DiffLine = {
      type,
      prefix,
      content,
      oldNo: type === "add" ? "" : String(oldNo),
      newNo: type === "del" ? "" : String(newNo),
    };

    if (type !== "add") oldNo++;
    if (type !== "del") newNo++;

    currentHunk.lines.push(line);
    totalLines++;
  }

  if (currentHunk) hunks.push(currentHunk);
  return hunks;
}

export function buildHunkPatchText(
  diffContent: string,
  filePath: string,
  hunkIndex: number,
): string {
  // Spec §2 decision #10 + §5.2: use full parse (maxLines=Infinity) to
  // avoid truncation, then look up the hunk by hunkIndex. Use ASCII
  // '-'/'+'/' ' prefixes — the parser's display prefix is U+2212
  // (visual minus) which git apply rejects.
  if (!filePath) return "";
  const fullText = extractDiffContent(diffContent);
  const fullHunks = parseUnifiedDiff(fullText, Infinity);
  const target =
    fullHunks.find((h) => h.hunkIndex === hunkIndex) ??
    fullHunks[hunkIndex];
  if (!target) return "";
  const lines: string[] = [
    `diff --git a/${filePath} b/${filePath}`,
    `--- a/${filePath}`,
    `+++ b/${filePath}`,
    target.header,
  ];
  for (const line of target.lines) {
    const prefix = line.type === "del" ? "-" : line.type === "add" ? "+" : " ";
    lines.push(prefix + line.content);
  }
  // git apply requires every body line — including the last — to be
  // terminated by `\n`. Without the trailing `\n` the parser reports
  // "error: corrupt patch at line N" where N is the index of the last
  // body line (regression hit on 2026-07-07 in production). The
  // corresponding backend reason code is `patch_malformed` and the
  // discard silently fails. See hunk-discard-design.md §5.4 for the
  // invariant contract.
  return lines.join("\n") + "\n";
}

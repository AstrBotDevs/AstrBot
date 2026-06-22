// Author: elecvoid243, 2026-06-21
// Spec: docs/superpowers/specs/2026-06-21-file-browser-inline-comments-design.md §4.1
// In-memory comment store + content cache for the file-browser inline
// comments feature. See spec §1, §2 (decisions), §4.1, §5 for context.

import { reactive, computed } from "vue";

/**
 * Single file comment, anchored to a line at comment-creation time.
 * `lineContent` and `contextBefore`/`contextAfter` are frozen snapshots
 * so the LLM can use `lineContent` as a content-fingerprint to relocate
 * the line even if the file has been edited since the comment was made.
 */
export interface FileComment {
  /** UUID, stable across edits/deletes. */
  id: string;
  /** Absolute path. Comments are partitioned by this. */
  filePath: string;
  /** 1-based line number at comment time. May drift if file is edited. */
  line: number;
  /** Exact line content at comment time. The LLM uses this as a fingerprint. */
  lineContent: string;
  /** Line above (null if line === 1). */
  contextBefore: string | null;
  /** Line below (null if line === last line). */
  contextAfter: string | null;
  /** User's comment text. Multi-line allowed. */
  text: string;
  createdAt: number;
  updatedAt: number;
}

/** Single source of truth for line context extraction. Used by both
 *  useFileComments (to freeze the snapshot in addComment) and by
 *  FileBrowserFilePreview (to populate the editor preview). Keeping
 *  the two call sites in lockstep via one helper means the editor
 *  preview is always consistent with what the comment will store. */
export interface LineContext {
  lineContent: string;
  contextBefore: string | null;
  contextAfter: string | null;
}

export function extractLineContext(content: string, line: number): LineContext | null {
  const lines = content.split("\n");
  const idx = line - 1;
  if (idx < 0 || idx >= lines.length) return null;
  return {
    lineContent: lines[idx],
    contextBefore: idx > 0 ? lines[idx - 1] : null,
    contextAfter: idx < lines.length - 1 ? lines[idx + 1] : null,
  };
}

/** UUID generator matching the pattern used in StandaloneChat.vue:311. */
function newId(): string {
  return (
    (globalThis.crypto?.randomUUID?.() as string | undefined) ??
    `${Date.now()}-${Math.random()}`
  );
}

/**
 * In-memory comment store + content cache for the file-browser.
 *
 *   comments[filePath] = FileComment[]
 *   contentCache[filePath] = string
 *
 * Comments are cleared on session switch via `resetForSession()`. The
 * content cache survives session switches and is auto-rebuilt by
 * FileBrowserFilePreview's `immediate: true` watch whenever a file
 * is opened. addComment freezes the line snapshot from the cache;
 * returns null if the cache is empty (caller decides UX).
 *
 * Module-level singleton: every component that calls `useFileComments()`
 * gets the SAME store instance. This is required because the file
 * browser (`FileBrowserFilePreview`, rendered inside `Chat.vue`) and
 * the chat input's `sendCurrentMessage` (also in `Chat.vue`) live in
 * the SAME component tree, but the legacy plan assumed they were both
 * inside `StandaloneChat.vue` — which is only rendered on the config
 * page, NOT the main chat. Provide/inject via a parent does not work
 * across sibling subtrees (e.g., `Chat.vue` vs `StandaloneChat.vue`).
 * A module-level singleton works in both contexts without adding a
 * Pinia dependency.
 */
let _instance: ReturnType<typeof createFileComments> | null = null;

function createFileComments() {
  const comments = reactive<Record<string, FileComment[]>>({});
  const contentCache = reactive<Record<string, string>>({});

  /** Drop the current session's comments. Called by StandaloneChat
   *  when the user switches to a different session. Does NOT clear
   *  contentCache (see field doc above). */
  function resetForSession(): void {
    for (const k of Object.keys(comments)) delete comments[k];
  }

  /** Register a file's current full content. Idempotent. */
  function registerFileContent(filePath: string, content: string): void {
    contentCache[filePath] = content;
  }

  /** Add a comment, freezing lineContent / contextBefore / contextAfter
   *  from the cached content. Returns null if the cache has no entry
   *  for this file (caller shows a snackbar and keeps the editor open). */
  function addComment(input: {
    filePath: string;
    line: number;
    text: string;
  }): FileComment | null {
    const content = contentCache[input.filePath];
    if (content === undefined) return null;
    const ctx = extractLineContext(content, input.line);
    if (ctx === null) return null;
    const comment: FileComment = {
      id: newId(),
      filePath: input.filePath,
      line: input.line,
      lineContent: ctx.lineContent,
      contextBefore: ctx.contextBefore,
      contextAfter: ctx.contextAfter,
      text: input.text,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    (comments[input.filePath] ??= []).push(comment);
    return comment;
  }

  function updateComment(id: string, newText: string): void {
    for (const list of Object.values(comments)) {
      const c = list.find((c) => c.id === id);
      if (c) {
        c.text = newText;
        c.updatedAt = Date.now();
        return;
      }
    }
  }

  function deleteComment(id: string): void {
    for (const [path, list] of Object.entries(comments)) {
      const i = list.findIndex((c) => c.id === id);
      if (i >= 0) {
        list.splice(i, 1);
        if (list.length === 0) delete comments[path];
        return;
      }
    }
  }

  /** Find a comment by id in the current session. Returns null if not found. */
  function findCommentById(id: string): FileComment | null {
    for (const list of Object.values(comments)) {
      const c = list.find((c) => c.id === id);
      if (c) return c;
    }
    return null;
  }

  /** Total comment count for the current session (across all files). */
  const totalCount = computed<number>(() => {
    let n = 0;
    for (const list of Object.values(comments)) n += list.length;
    return n;
  });

  /** Comments for a specific file in the current session. */
  function commentsForFile(filePath: string): FileComment[] {
    return comments[filePath] ?? [];
  }

  /** All comments grouped by filePath, with each group sorted by line
   *  ASC. Groups themselves are sorted by filePath ASC for stable
   *  rendering. Returns a fresh array each call (safe to iterate /
   *  sort downstream). Used by CommentsPreviewDialog. */
  function commentsByFile(): Array<{ filePath: string; comments: FileComment[] }> {
    const entries = Object.entries(comments)
      .filter(([, list]) => list.length > 0)
      .map(([filePath, list]) => ({
        filePath,
        comments: [...list].sort((a, b) => a.line - b.line),
      }));
    entries.sort((a, b) => a.filePath.localeCompare(b.filePath));
    return entries;
  }

  /** Delete every comment across all files. Idempotent. Does not
   *  touch contentCache (content survives session switches). */
  function clearAll(): void {
    for (const k of Object.keys(comments)) delete comments[k];
  }

  /** Format all comments in the current session as a structured
   *  plain-text block ready to be appended to the user's outgoing
   *  message. Returns "" if no comments.
   *
   *  Output format: a leading prose section, then for each file a
   *  markdown header and a fenced code block (4-backtick outer fence
   *  so the user's comment text can contain 3-backtick fences
   *  without breaking the outer block — markdown supports this).
   *  The code block uses git-diff-style `>` marker for the commented
   *  line. See spec §5.1 for the full format spec. */
  function formatForLLM(): string {
    const allComments: FileComment[] = [];
    for (const list of Object.values(comments)) allComments.push(...list);
    if (allComments.length === 0) return "";

    const byFile = new Map<string, FileComment[]>();
    for (const c of allComments) {
      if (!byFile.has(c.filePath)) byFile.set(c.filePath, []);
      byFile.get(c.filePath)!.push(c);
    }

    const out: string[] = [
      "[File review comments]",
      "Each entry shows the line content (and 1 line of context above/below)",
      "that was current when the comment was written. Use the line content",
      "as a fingerprint to locate the line in the current file — line numbers",
      "may have drifted if the file was edited since the comment.",
    ];

    for (const [filePath, commentList] of byFile) {
      const sorted = [...commentList].sort((a, b) => a.line - b.line);

      // Group adjacent comments (line diff <= 3) into a shared window.
      type Window = { startLine: number; endLine: number; comments: FileComment[] };
      const windows: Window[] = [];
      for (const c of sorted) {
        const last = windows[windows.length - 1];
        if (last && c.line - last.endLine <= 3) {
          last.endLine = Math.max(last.endLine, c.line);
          last.comments.push(c);
        } else {
          windows.push({ startLine: c.line, endLine: c.line, comments: [c] });
        }
      }

      for (const win of windows) {
        const ctxStart = win.comments.some((c) => c.contextBefore !== null)
          ? Math.max(1, win.startLine - 1)
          : win.startLine;
        const ctxEnd = win.comments.some((c) => c.contextAfter !== null)
          ? win.endLine + 1
          : win.endLine;

        const header =
          win.startLine === win.endLine
            ? `\`${filePath}\` line ${win.startLine}:`
            : `\`${filePath}\` lines ${win.startLine}-${win.endLine}:`;
        out.push("");
        out.push(header);
        out.push("````");  // 4-backtick fence (see spec §5.1)
        const commentedSet = new Set(win.comments.map((c) => c.line));
        const commentByLine = new Map(win.comments.map((c) => [c.line, c]));

        for (let line = ctxStart; line <= ctxEnd; line++) {
          const c = commentByLine.get(line);
          let lineContent: string;
          if (c) {
            lineContent = c.lineContent;
          } else if (line === ctxStart && win.comments[0].contextBefore !== null) {
            lineContent = win.comments[0].contextBefore ?? "";
          } else if (
            line === ctxEnd &&
            win.comments[win.comments.length - 1].contextAfter !== null
          ) {
            lineContent = win.comments[win.comments.length - 1].contextAfter ?? "";
          } else {
            lineContent = "";
          }
          const marker = commentedSet.has(line) ? ">" : " ";
          const padded = String(line).padStart(4);
          out.push(`  ${marker} ${padded} │ ${lineContent}`);
          if (c) {
            const textLines = c.text.split("\n");
            out.push(`         │ Comment: ${textLines[0]}`);
            for (let i = 1; i < textLines.length; i++) {
              out.push(`         │ ${textLines[i]}`);
            }
          }
        }
        out.push("````");
      }
    }
  return out.join("\n");
  }

  return {
    totalCount,
    resetForSession,
    registerFileContent,
    addComment,
    updateComment,
    deleteComment,
    findCommentById,
    commentsForFile,
    commentsByFile,
    clearAll,
    formatForLLM,
  };
}

/**
 * Returns the singleton file-comments store. The first call creates
 * the store; subsequent calls return the same instance. See the file
 * header for the rationale (sibling component trees can't use
 * provide/inject).
 */
export function useFileComments() {
  if (!_instance) _instance = createFileComments();
  return _instance;
}

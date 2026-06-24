// Author: elecvoid243, 2026-06-24
// Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md
//      §4.2.3 (merged untracked) — extension to display actual line
//      counts AND expandable content for new-file rows in the diff
//      sidebar.
//
// Why this exists: /spcode/git-status returns the list of brand-new
// files (untracked / intent_to_add) but does NOT include patch data
// or line counts. Without a separate fetch, the diff sidebar would
// show "+0 −0" for new files and render an empty body when the user
// expands the row. This composable fills that gap by reading each
// new file via /spcode/file-browser ONCE and exposing both:
//
//   - `counts`   : Map<path, lineCount>    → for the "+N −0" badge
//   - `contents` : Map<path, rawText>      → for the expandable
//                                            preview, which the
//                                            sidebar synthesizes
//                                            into a unified-diff
//                                            slice for <DiffPreview>.
//
// Design notes:
//   - Counts and contents come from the same fetch, so they are
//     updated atomically: a single Map replacement per path makes
//     both reactive consumers re-evaluate in lock-step.
//   - Content is cached alongside the count so expanding a row is
//     instant (no extra round-trip). The trade-off is a longer
//     in-memory string per new file; for the typical "a few new
//     files per commit" workload this is negligible, and the file-
//     browser endpoint already enforces a max-bytes cap that we
//     honor by simply not writing the entry.
//   - `shallowRef<Map>` (not `ref<Map>`) is used because we always
//     replace the whole Map on update; this avoids the overhead of
//     deep Proxy tracking and matches the useSpcodeGitLog etc.
//     pattern.
//   - Binary / too-large / read-error files are silently skipped: the
//     row keeps "+0 −0" and `slice: null` (same UX as a regular diff
//     row with no slice). No error toast needed.
//   - Lifecycle: `dispose()` aborts in-flight requests on unmount.
import {
  onBeforeUnmount,
  shallowRef,
  toValue,
  watch,
  type MaybeRefOrGetter,
  type Ref,
} from "vue";
import { pluginExtensionApi } from "@/api/v1";

interface FileBrowserFilePayload {
  type: "file" | "directory" | "symlink" | null;
  is_binary?: boolean | null;
  content?: string | null;
  reason?: string | null;
}

export interface UseSpcodeNewFileLineCounts {
  /** Map<repoRelPath, lineCount>. Paths no longer present in the
   *  input `paths` set are removed automatically. */
  counts: Readonly<Ref<Map<string, number>>>;
  /** Map<repoRelPath, rawText>. Same lifecycle as `counts` — always
   *  populated for the same paths (a path is in `contents` iff it is
   *  in `counts`). Used by `newFileStub` to build a synthetic
   *  unified-diff slice for <DiffPreview>. */
  contents: Readonly<Ref<Map<string, string>>>;
  /** True while at least one fetch is in flight. */
  isLoading: Ref<boolean>;
  /** Re-fetch a single path (e.g. after the user edits the file). */
  refreshPath: (path: string) => Promise<void>;
  dispose: () => void;
}

/**
 * Count lines in a string the way `wc -l` (without -l trailing
 * newline adjustment) would for typical git diff stats: number of
 * logical lines including a trailing partial line, excluding a
 * trailing empty line introduced by a final newline character.
 *
 * Examples:
 *   ""            -> 0
 *   "hello"       -> 1
 *   "hello\n"     -> 1
 *   "a\nb"        -> 2
 *   "a\nb\n"      -> 2
 */
function countLines(text: string): number {
  if (!text) return 0;
  let n = 1;
  for (let i = 0; i < text.length; i++) {
    if (text.charCodeAt(i) === 10) n++;
  }
  if (text.endsWith("\n")) n--;
  return Math.max(n, 0);
}

/** Normalize a path to POSIX-style for join consistency. The
 *  file-browser endpoint accepts forward slashes on Windows. */
function joinPath(directory: string, relative: string): string {
  const trimmed = relative.replace(/\\/g, "/").replace(/^\/+/, "");
  const base = directory.replace(/\\/g, "/").replace(/\/+$/, "");
  return base ? `${base}/${trimmed}` : trimmed;
}

export function useSpcodeNewFileLineCounts(
  paths: MaybeRefOrGetter<ReadonlySet<string>>,
  directory: MaybeRefOrGetter<string>,
): UseSpcodeNewFileLineCounts {
  const counts = shallowRef<Map<string, number>>(new Map());
  const contents = shallowRef<Map<string, string>>(new Map());
  const isLoading = shallowRef(false);
  let isMounted = true;
  const inflight = new Map<string, AbortController>();

  async function fetchOne(relPath: string, dir: string): Promise<void> {
    if (!isMounted) return;
    inflight.get(relPath)?.abort();
    const ac = new AbortController();
    inflight.set(relPath, ac);
    isLoading.value = true;
    try {
      // pluginExtensionApi.get<T> wraps the response in ApiEnvelope<T>
      // (shape `{ status, data }`), so the generic must be the inner
      // payload type — NOT a `{ data: ... }` wrapper. Passing the wrapper
      // would make `resp.data?.data` resolve to the envelope again,
      // breaking property access on `type` / `is_binary` / `content`.
      const resp = await pluginExtensionApi.get<FileBrowserFilePayload>(
        "spcode/file-browser",
        {
          params: { path: joinPath(dir, relPath) },
          signal: ac.signal,
        },
      );
      if (!isMounted) return;
      const data = resp.data?.data;
      if (
        data?.type === "file" &&
        data.is_binary !== true &&
        typeof data.content === "string"
      ) {
        // Atomic dual-map update: replace both Maps together so
        // any consumer that reads `counts.get(p)` and
        // `contents.get(p)` in the same tick sees a consistent
        // view (a path is in `contents` iff it is in `counts`).
        const nextCounts = new Map(counts.value);
        const nextContents = new Map(contents.value);
        nextCounts.set(relPath, countLines(data.content));
        nextContents.set(relPath, data.content);
        counts.value = nextCounts;
        contents.value = nextContents;
      }
      // Binary / too-large / missing-content / error: do not write
      // to either map; the row continues to render "+0 −0" and the
      // expanded body shows the "noContent" placeholder (same as a
      // regular diff row with no slice).
    } catch (err) {
      if ((err as { name?: string })?.name === "CanceledError") return;
      // Network / permission error: silently keep the previous
      // values (or 0 / undefined if never fetched). No error UX.
    } finally {
      inflight.delete(relPath);
      if (inflight.size === 0) isLoading.value = false;
    }
  }

  watch(
    [() => toValue(paths), () => toValue(directory)],
    ([nextPaths, dir], [, prevDir]) => {
      if (!isMounted) return;
      const dirChanged = dir !== prevDir;
      if (dirChanged || !dir) {
        // Abort any in-flight requests against the previous worktree.
        for (const ac of inflight.values()) ac.abort();
        inflight.clear();
        isLoading.value = false;
        counts.value = new Map();
        contents.value = new Map();
        if (!dir) return;
      }
      // Prune both maps in lock-step (the watcher is the only
      // place we drop paths, and it MUST drop from both to keep
      // the "path in contents ⇔ path in counts" invariant).
      const currentCounts = counts.value;
      const currentContents = contents.value;
      const nextCounts = dirChanged
        ? new Map<string, number>()
        : new Map(currentCounts);
      const nextContents = dirChanged
        ? new Map<string, string>()
        : new Map(currentContents);
      let mutated = dirChanged;
      if (!dirChanged) {
        for (const k of currentCounts.keys()) {
          if (!nextPaths.has(k)) {
            nextCounts.delete(k);
            nextContents.delete(k);
            mutated = true;
          }
        }
      }
      if (mutated) {
        counts.value = nextCounts;
        contents.value = nextContents;
      }
      const tasks: Promise<void>[] = [];
      for (const p of nextPaths) {
        if (!nextCounts.has(p)) tasks.push(fetchOne(p, dir));
      }
      void Promise.allSettled(tasks);
    },
    { flush: "post" },
  );

  async function refreshPath(path: string): Promise<void> {
    const dir = toValue(directory);
    if (!dir) return;
    const nextCounts = new Map(counts.value);
    const nextContents = new Map(contents.value);
    nextCounts.delete(path);
    nextContents.delete(path);
    counts.value = nextCounts;
    contents.value = nextContents;
    await fetchOne(path, dir);
  }

  function dispose(): void {
    isMounted = false;
    for (const ac of inflight.values()) ac.abort();
    inflight.clear();
    isLoading.value = false;
  }

  onBeforeUnmount(dispose);

  return { counts, contents, isLoading, refreshPath, dispose };
}

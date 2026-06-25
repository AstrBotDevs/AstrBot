// Author: elecvoid243
// Date: 2026-06-25
// Spec: docs/superpowers/specs/2026-06-25-git-show-design.md
// API doc: docs/webapi-git-show-api.md
//
// Vue composable wrapping GET /spcode/git-show. One instance per
// sidebar (or any other view) supports an arbitrary number of distinct
// refs (typically commit SHAs from git-log); per-ref results are
// cached in a reactive Map. Mirrors the lifecycle of
// useSpcodeGitLog.ts (worktree-aware + ETag + dispose) but adapted to
// the per-ref (not per-list) access pattern.
//
// Design notes:
//   - `fetch(ref)` is idempotent: a second call for a cached ref is
//     a no-op; a second call for a ref already in flight is also a
//     no-op (we use the active AbortController).
//   - `state` and `data` are exposed via plain getter functions that
//     read the underlying reactive `ref<Map>`. Vue tracks the read,
//     so a v-for in the template that iterates expanded commits and
//     calls `state(sha)` re-renders on every transition.
//   - ETag is keyed by `umo + worktree + ref` so the same SHA across
//     different worktrees / projects has independent cache entries.

import {
  ref,
  toValue,
  watch,
  computed,
  type Ref,
  type MaybeRef,
} from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import {
  parseSpcodeGitShow,
  type GitShowData,
  type GitShowFileView,
  type ParseResult,
} from "./parseSpcodeGitShow";

/** Per-ref state. Component reads via the `state(sha)` getter below. */
export type GitShowFetchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: GitShowData; notModified?: boolean }
  | { kind: "error"; reason: string };

/** v3.9 (2026-06-25): per-(sha, path) state for the single-file
 *  patch view. Mirrors GitShowFetchState's shape; the snapshot is a
 *  GitShowFileView (or null when the backend signals an error). */
export type GitShowFileFetchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: GitShowFileView; notModified?: boolean }
  | { kind: "error"; reason: string };

export interface UseSpcodeGitShow {
  /** Reactive Set of refs that currently have data in the cache. */
  cached: Ref<ReadonlySet<string>>;
  /** Fetch (or no-op) for a single ref. Idempotent. */
  fetch: (refName: string) => Promise<void>;
  /** Read cached data for a ref. Returns null if not cached. */
  getData: (refName: string) => GitShowData | null;
  /** Read per-ref state. Returns { kind: "idle" } for unseen refs. */
  getState: (refName: string) => GitShowFetchState;
  /** True while a fetch for this ref is in flight. */
  isLoading: (refName: string) => boolean;
  /** v3.9: Fetch (or no-op) for a single file's patch within a
   *  commit. Idempotent; per-(sha, path) cached. */
  fetchFile: (refName: string, filePath: string) => Promise<void>;
  /** v3.9: Read cached single-file patch view. */
  getFileData: (refName: string, filePath: string) => GitShowFileView | null;
  /** v3.9: Read per-(sha, path) state. */
  getFileState: (refName: string, filePath: string) => GitShowFileFetchState;
  /** v3.9: True while a single-file fetch is in flight. */
  isFileLoading: (refName: string, filePath: string) => boolean;
  /** Clear every cached ref and ETag entry. Does NOT abort in-flight. */
  invalidateAll: () => void;
  /** Clear the ETag map only (e.g. on worktree / umo change). Keeps
   *  cached data so the user does not see a flash of "Loading…" after
   *  a worktree switch. The next fetch will get a fresh ETag. */
  invalidateEtag: () => void;
  /** Stop polling timers, abort in-flight, drop all caches. */
  dispose: () => void;
}

function etagKey(parts: {
  umo: string | null;
  worktree: string | null;
  ref: string;
}): string {
  return [parts.umo ?? "", parts.worktree ?? "", parts.ref].join("|");
}

export function useSpcodeGitShow(
  worktreeRef: MaybeRef<string | null> = null,
): UseSpcodeGitShow {
  // Reactive state. We mutate via .value.set(...) / .value.delete(...)
  // on the .value reference, then reassign the ref to force Vue's
  // reactivity to pick up the change in maps/sets (Vue 3 ref proxies
  // wrap only top-level mutations; nested writes do not trigger).
  const stateMap = ref<Map<string, GitShowFetchState>>(new Map());
  const dataMap = ref<Map<string, GitShowData>>(new Map());
  const etagMap = new Map<string, string>();
  const inflight = new Map<string, AbortController>();
  // v3.9: per-(sha, path) parallel state for the single-file patch
  // view. Kept in separate maps so the commit-level cache (dataMap)
  // remains untouched when a user expands / collapses file rows.
  const fileStateMap = ref<Map<string, GitShowFileFetchState>>(new Map());
  const fileDataMap = ref<Map<string, GitShowFileView>>(new Map());
  const fileEtagMap = new Map<string, string>();
  const fileInflight = new Map<string, AbortController>();
  let isMounted = true;
  const spcodeStatus = useSpcodeProjectStatus();

  function setState(refName: string, next: GitShowFetchState): void {
    const m = new Map(stateMap.value);
    m.set(refName, next);
    stateMap.value = m;
  }
  function setData(refName: string, next: GitShowData): void {
    const m = new Map(dataMap.value);
    m.set(refName, next);
    dataMap.value = m;
  }
  function deleteState(refName: string): void {
    const m = new Map(stateMap.value);
    m.delete(refName);
    stateMap.value = m;
  }
  function deleteData(refName: string): void {
    const m = new Map(dataMap.value);
    m.delete(refName);
    dataMap.value = m;
  }
  // v3.9: per-(sha, path) setters mirror the commit-level helpers
  // above; key format is `${sha}\u0001${path}` (NUL byte — illegal
  // in git paths — guarantees no collision with single-component keys).
  function setFileState(key: string, next: GitShowFileFetchState): void {
    const m = new Map(fileStateMap.value);
    m.set(key, next);
    fileStateMap.value = m;
  }
  function setFileData(key: string, next: GitShowFileView): void {
    const m = new Map(fileDataMap.value);
    m.set(key, next);
    fileDataMap.value = m;
  }
  function fileKey(sha: string, filePath: string): string {
    return `${sha}\u0001${filePath}`;
  }

  // Reactive Set of refs that have data. Kept in sync with dataMap.
  // Components can v-for over `cached` to know which refs to render
  // inline, but the most common access pattern is `getData(sha)` +
  // `getState(sha)` per-SHA from inside a per-commit v-for.
  const cached = computedReadonly(() => new Set(dataMap.value.keys()));

  async function fetch(refName: string): Promise<void> {
    if (!isMounted) return;
    if (!refName) return;
    // Idempotency: skip if we already have fresh data, or a request
    // is already in flight for this ref.
    if (inflight.has(refName)) return;
    const current = stateMap.value.get(refName);
    if (current?.kind === "ok") return;

    const umo = spcodeStatus.status.value.umo;
    if (!umo) {
      setState(refName, { kind: "error", reason: "no_project_loaded" });
      return;
    }

    const ctrl = new AbortController();
    inflight.set(refName, ctrl);
    setState(refName, { kind: "loading" });

    const worktree = toValue(worktreeRef);
    const key = etagKey({ umo, worktree, ref: refName });
    const etag = etagMap.get(key);

    try {
      const resp = await pluginExtensionApi.get<unknown>(
        "spcode/git-show",
        {
          params: {
            umo,
            ...(worktree ? { worktree } : {}),
            ref: refName,
            max_files: 500,
          },
          headers: etag ? { "If-None-Match": etag } : {},
          validateStatus: (s) => (s >= 200 && s < 300) || s === 304,
          signal: ctrl.signal,
        },
      );
      if (!isMounted) return;
      inflight.delete(refName);

      if (resp.status === 304) {
        // ETag hit → keep previous data, no state change.
        const prev = dataMap.value.get(refName);
        if (prev) {
          setState(refName, { kind: "ok", data: prev, notModified: true });
        }
        return;
      }

      const parsed: ParseResult<GitShowData> = parseSpcodeGitShow(resp.data);
      if (parsed.kind !== "ok") {
        setState(refName, { kind: "error", reason: "unknown" });
        return;
      }
      const snap = parsed.snapshot;
      if (!snap.success) {
        // The spec's reason codes (`ref_not_found`, `commit_too_large`,
        // `feature_disabled`, etc.) flow through `data.reason`. Pass
        // them as-is so the template can build an i18n key.
        setState(refName, {
          kind: "error",
          reason: snap.reason ?? "unknown",
        });
        return;
      }

      // Update ETag.
      const headers = resp.headers as
        | Record<string, string>
        | undefined;
      const newEtag = headers?.["etag"] ?? headers?.["ETag"];
      if (newEtag) etagMap.set(key, newEtag);

      setData(refName, snap);
      setState(refName, { kind: "ok", data: snap, notModified: false });
    } catch (err) {
      if (!isMounted) return;
      inflight.delete(refName);
      if ((err as { name?: string })?.name === "CanceledError") {
        // Aborted: do not touch state — another fetch in flight or
        // the component unmounted. The next non-aborted response
        // (or unmount cleanup) will overwrite the "loading" entry.
        return;
      }
      const anyErr = err as { code?: string; message?: string };
      const reason =
        anyErr.code === "ERR_NETWORK" ||
        /network/i.test(anyErr.message ?? "")
          ? "network"
          : "unknown";
      setState(refName, { kind: "error", reason });
    }
  }

  // ──────────────────────────────────────────────────────────
  // v3.9: per-(sha, path) single-file patch fetch
  // Mirrors `fetch()` but keyed on (ref + path) and hitting the same
  // /spcode/git-show endpoint with ?path=<file>. The response shape
  // is the standard envelope + data.file. Idempotency, abort handling
  // and ETag follow the same rules as the commit-level fetch above.
  // ──────────────────────────────────────────────────────────
  async function fetchFile(refName: string, filePath: string): Promise<void> {
    if (!isMounted) return;
    if (!refName || !filePath) return;
    const key = fileKey(refName, filePath);
    if (fileInflight.has(key)) return;
    const current = fileStateMap.value.get(key);
    if (current?.kind === "ok") return;

    const umo = spcodeStatus.status.value.umo;
    if (!umo) {
      setFileState(key, { kind: "error", reason: "no_project_loaded" });
      return;
    }

    const ctrl = new AbortController();
    fileInflight.set(key, ctrl);
    setFileState(key, { kind: "loading" });

    const worktree = toValue(worktreeRef);
    const etagKeyFull = `${etagKey({ umo, worktree, ref: refName })}|${filePath}`;
    const etag = fileEtagMap.get(etagKeyFull);

    try {
      const resp = await pluginExtensionApi.get<unknown>(
        "spcode/git-show",
        {
          params: {
            umo,
            ...(worktree ? { worktree } : {}),
            ref: refName,
            path: filePath,
            max_files: 1, // 单文件视图,后端不需要 N 个文件列表
          },
          headers: etag ? { "If-None-Match": etag } : {},
          validateStatus: (s) => (s >= 200 && s < 300) || s === 304,
          signal: ctrl.signal,
        },
      );
      if (!isMounted) return;
      fileInflight.delete(key);

      if (resp.status === 304) {
        const prev = fileDataMap.value.get(key);
        if (prev) {
          setFileState(key, { kind: "ok", data: prev, notModified: true });
        }
        return;
      }

      const parsed: ParseResult<GitShowData> = parseSpcodeGitShow(resp.data);
      if (parsed.kind !== "ok") {
        setFileState(key, { kind: "error", reason: "unknown" });
        return;
      }
      const snap = parsed.snapshot;
      if (!snap.success) {
        setFileState(key, { kind: "error", reason: snap.reason ?? "unknown" });
        return;
      }
      if (!snap.file) {
        // 后端成功但没有 file 字段(理论不应发生;保守兜底)
        setFileState(key, { kind: "error", reason: "unknown" });
        return;
      }

      const headers = resp.headers as
        | Record<string, string>
        | undefined;
      const newEtag = headers?.["etag"] ?? headers?.["ETag"];
      if (newEtag) fileEtagMap.set(etagKeyFull, newEtag);

      setFileData(key, snap.file);
      setFileState(key, { kind: "ok", data: snap.file, notModified: false });
    } catch (err) {
      if (!isMounted) return;
      fileInflight.delete(key);
      if ((err as { name?: string })?.name === "CanceledError") {
        return;
      }
      const anyErr = err as { code?: string; message?: string };
      const reason =
        anyErr.code === "ERR_NETWORK" ||
        /network/i.test(anyErr.message ?? "")
          ? "network"
          : "unknown";
      setFileState(key, { kind: "error", reason });
    }
  }

  function getData(refName: string): GitShowData | null {
    return dataMap.value.get(refName) ?? null;
  }
  function getState(refName: string): GitShowFetchState {
    return stateMap.value.get(refName) ?? { kind: "idle" };
  }
  function isLoading(refName: string): boolean {
    return getState(refName).kind === "loading";
  }

  // v3.9: per-(sha, path) read accessors. Same idempotency / shape
  // contract as their commit-level counterparts above.
  function getFileData(refName: string, filePath: string): GitShowFileView | null {
    return fileDataMap.value.get(fileKey(refName, filePath)) ?? null;
  }
  function getFileState(refName: string, filePath: string): GitShowFileFetchState {
    return fileStateMap.value.get(fileKey(refName, filePath)) ?? { kind: "idle" };
  }
  function isFileLoading(refName: string, filePath: string): boolean {
    return getFileState(refName, filePath).kind === "loading";
  }

  function invalidateAll(): void {
    stateMap.value = new Map();
    dataMap.value = new Map();
    etagMap.clear();
    // v3.9: also drop per-file cache; the next expand will re-fetch
    fileStateMap.value = new Map();
    fileDataMap.value = new Map();
    fileEtagMap.clear();
  }

  function invalidateEtag(): void {
    etagMap.clear();
    // v3.9: ETag-only drop for files; data is kept to avoid flash
    fileEtagMap.clear();
  }

  // Worktree / umo change: clear ETag only, keep cached data so the
  // user does not see a flash of "Loading…" after a worktree switch.
  // The cached `data` for a SHA from the previous worktree will still
  // satisfy `getData(sha)`, but the next `fetch(sha)` call will return
  // a fresh server response (and overwrite the cache). This is the
  // same trade-off useSpcodeGitLog makes: prevSnapshot is dropped
  // on invalidateEtag to avoid replaying 304 against a stale snapshot.
  watch(
    [() => toValue(worktreeRef), () => spcodeStatus.status.value.umo],
    () => {
      invalidateEtag();
    },
    { flush: "post" },
  );

  function dispose(): void {
    isMounted = false;
    for (const ctrl of inflight.values()) ctrl.abort();
    inflight.clear();
    etagMap.clear();
    stateMap.value = new Map();
    dataMap.value = new Map();
    // v3.9: also abort / drop the per-file fetches
    for (const ctrl of fileInflight.values()) ctrl.abort();
    fileInflight.clear();
    fileEtagMap.clear();
    fileStateMap.value = new Map();
    fileDataMap.value = new Map();
  }

  return {
    cached,
    fetch,
    getData,
    getState,
    isLoading,
    fetchFile,
    getFileData,
    getFileState,
    isFileLoading,
    invalidateAll,
    invalidateEtag,
    dispose,
  };
}

// Wrapper around Vue's `computed` so the public `cached` ref reads
// naturally as a `ReadonlySet<string>` to consumers. Vue's `computed`
// already returns a read-only ref, so this is a thin facade — but
// keeping the helper local means future tweaks (memoization, etc.)
// stay in one place.
function computedReadonly<T>(getter: () => T): Ref<T> {
  return computed(getter) as Ref<T>;
}

// Author: elecvoid243, 2026-07-12
// Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §3.5
//
// Vue composable wrapping GET /spcode/git-file. Mirrors the
// lifecycle of useSpcodeGitShow (per-(path, ref) cache, ETag
// with If-None-Match, dedup via AbortController, isMounted guard)
// but is keyed on (path, ref) instead of (ref, path).
//
// The endpoint returns:
//   { ref, resolved_sha, path, content, is_binary, size,
//     truncated, max_bytes, reason, ... }
// We surface `content` (string; "" for binary) and a derived
// `isBinary` for template-side switches. Cache key format is
// `<path>|<ref>` to match the spec §3.5 contract.

import {
  ref,
  watch,
  toValue,
  computed,
  type Ref,
  type MaybeRef,
} from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";

export interface GitFileData {
  sha: string;
  path: string;
  content: string;
  isBinary: boolean;
  ref: string;
  size: number;
  truncated: boolean;
  maxBytes: number;
  resolvedSha: string;
}

export type FileRevisionState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: GitFileData; notModified?: boolean }
  | { kind: "error"; reason: string };

export interface UseSpcodeGitFile {
  fetchRef(path: string, ref: string): Promise<void>;
  getData(path: string, ref: string): GitFileData | null;
  getState(path: string, ref: string): FileRevisionState;
  isLoading(path: string, ref: string): boolean;
  invalidateAll(): void;
  dispose(): void;
}

function cacheKey(path: string, ref: string): string {
  return `${path}|${ref}`;
}

function etagKey(parts: {
  umo: string | null;
  worktree: string | null;
  path: string;
  ref: string;
}): string {
  return [parts.umo ?? "", parts.worktree ?? "", parts.path, parts.ref].join("|");
}

export function useSpcodeGitFile(
  worktreeRef: MaybeRef<string | null> = null,
): UseSpcodeGitFile {
  const spcodeStatus = useSpcodeProjectStatus();
  const dataMap = ref<Map<string, GitFileData>>(new Map());
  const stateMap = ref<Map<string, FileRevisionState>>(new Map());
  const etagMap = new Map<string, string>();
  const inflight = new Map<string, AbortController>();
  let isMounted = true;

  function setState(key: string, next: FileRevisionState) {
    const m = new Map(stateMap.value);
    m.set(key, next);
    stateMap.value = m;
  }
  function setData(key: string, next: GitFileData) {
    const m = new Map(dataMap.value);
    m.set(key, next);
    dataMap.value = m;
  }

  async function fetchRef(path: string, ref: string): Promise<void> {
    if (!isMounted) return;
    if (!path || !ref) return;
    const key = cacheKey(path, ref);
    if (inflight.has(key)) return;
    const current = stateMap.value.get(key);
    if (current?.kind === "ok") return;

    const umo = spcodeStatus.status.value.umo;
    if (!umo) {
      setState(key, { kind: "error", reason: "no_project_loaded" });
      return;
    }

    const ctrl = new AbortController();
    inflight.set(key, ctrl);
    setState(key, { kind: "loading" });

    const worktree = toValue(worktreeRef);
    const ek = etagKey({ umo, worktree, path, ref });
    const etag = etagMap.get(ek);

    try {
      const resp = await pluginExtensionApi.get<unknown>("spcode/git-file", {
        params: {
          umo,
          ...(worktree ? { worktree } : {}),
          ref,
          path,
        },
        headers: etag ? { "If-None-Match": etag } : {},
        validateStatus: (s) => (s >= 200 && s < 300) || s === 304,
        signal: ctrl.signal,
      });
      if (!isMounted) return;
      inflight.delete(key);

      if (resp.status === 304) {
        const prev = dataMap.value.get(key);
        if (prev) {
          setState(key, { kind: "ok", data: prev, notModified: true });
        }
        return;
      }

      const envelope = resp.data as
        | { status: string; data?: Record<string, unknown> }
        | undefined;
      const data = envelope?.data;
      if (!data) {
        setState(key, { kind: "error", reason: "unknown" });
        return;
      }
      // Backend `_make_envelope` (webapi/_helpers.py:233) does NOT
      // echo the `success` kwarg into the response data. For the
      // historical-blob endpoint the equivalent signal is
      // `loaded: true`; the literal `success: true` legacy key is
      // still accepted if a future handler ever echoes it. Any
      // non-empty `reason` string is treated as a hard failure.
      if (typeof data.reason === "string" && data.reason) {
        setState(key, { kind: "error", reason: data.reason });
        return;
      }
      const acknowledged =
        data.success === true || data.loaded === true;
      if (!acknowledged) {
        setState(key, { kind: "error", reason: "unknown" });
        return;
      }
      const headers = (resp.headers ?? {}) as Record<string, string>;
      const newEtag = headers.etag ?? headers.ETag;
      if (newEtag) etagMap.set(ek, newEtag);

      const snap: GitFileData = {
        sha: typeof data.resolved_sha === "string" ? data.resolved_sha : "",
        path: typeof data.path === "string" ? data.path : path,
        content: typeof data.content === "string" ? data.content : "",
        isBinary: data.is_binary === true,
        ref: typeof data.ref === "string" ? data.ref : ref,
        size: typeof data.size === "number" ? data.size : 0,
        truncated: data.truncated === true,
        maxBytes: typeof data.max_bytes === "number" ? data.max_bytes : 1048576,
        resolvedSha:
          typeof data.resolved_sha === "string" ? data.resolved_sha : "",
      };
      setData(key, snap);
      setState(key, { kind: "ok", data: snap, notModified: false });
    } catch (err) {
      if (!isMounted) return;
      inflight.delete(key);
      if ((err as { name?: string })?.name === "CanceledError") return;
      const anyErr = err as { code?: string; message?: string };
      const reason =
        anyErr.code === "ERR_NETWORK" || /network/i.test(anyErr.message ?? "")
          ? "network"
          : "unknown";
      setState(key, { kind: "error", reason });
    }
  }

  function getData(path: string, ref: string): GitFileData | null {
    return dataMap.value.get(cacheKey(path, ref)) ?? null;
  }
  function getState(path: string, ref: string): FileRevisionState {
    return stateMap.value.get(cacheKey(path, ref)) ?? { kind: "idle" };
  }
  function isLoading(path: string, ref: string): boolean {
    return getState(path, ref).kind === "loading";
  }

  function invalidateAll(): void {
    stateMap.value = new Map();
    dataMap.value = new Map();
    etagMap.clear();
  }

  watch(
    [() => toValue(worktreeRef), () => spcodeStatus.status.value.umo],
    () => etagMap.clear(),
    { flush: "post" },
  );

  function dispose(): void {
    isMounted = false;
    for (const ctrl of inflight.values()) ctrl.abort();
    inflight.clear();
    etagMap.clear();
    stateMap.value = new Map();
    dataMap.value = new Map();
  }

  return {
    fetchRef,
    getData,
    getState,
    isLoading,
    invalidateAll,
    dispose,
  };
}

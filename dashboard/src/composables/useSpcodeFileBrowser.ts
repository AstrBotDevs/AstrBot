// Author: elecvoid243, 2026-06-20
// Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.2
// Mirrors the lifecycle pattern of useSpcodeGitDiff.ts but does NOT poll
// (file-browser is on-demand: user navigates to a directory or clicks a file).

import { ref, watch, toValue, type Ref, type MaybeRef } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import {
  parseSpcodeFileBrowser,
  FileBrowserParseError,
  type SpcodeFileBrowserRawResponse,
  type SpcodeFileBrowserDirectorySnapshot,
  type SpcodeFileBrowserFileSnapshot,
  type SpcodeFileBrowserSymlinkSnapshot,
} from "./parseSpcodeFileBrowser";

export type FileBrowserFetchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "directory"; snapshot: SpcodeFileBrowserDirectorySnapshot }
  | { kind: "file"; snapshot: SpcodeFileBrowserFileSnapshot }
  | { kind: "symlink"; snapshot: SpcodeFileBrowserSymlinkSnapshot }
  | {
      kind: "error";
      reason: string;
      previousSnapshot?:
        | SpcodeFileBrowserDirectorySnapshot
        | SpcodeFileBrowserFileSnapshot
        | SpcodeFileBrowserSymlinkSnapshot;
    };

export interface UseSpcodeFileBrowser {
  state: Ref<FileBrowserFetchState>;
  refresh: (path?: string) => Promise<void>;
  dispose: () => void;
}

/** Type guard for the three snapshot states (excludes idle/loading/error).
 *  Operates on the whole state object so `state.value.snapshot` is narrowed. */
function isSnapshotState(
  s: FileBrowserFetchState,
): s is { kind: "directory"; snapshot: SpcodeFileBrowserDirectorySnapshot }
  | { kind: "file"; snapshot: SpcodeFileBrowserFileSnapshot }
  | { kind: "symlink"; snapshot: SpcodeFileBrowserSymlinkSnapshot } {
  return s.kind === "directory" || s.kind === "file" || s.kind === "symlink";
}

/** Classify an axios/network error into a reason code for the UI. */
function classifyError(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const anyErr = err as { code?: string; message?: string };
    if (anyErr.code === "ERR_NETWORK" || /network/i.test(anyErr.message ?? "")) {
      return "network";
    }
  }
  return "unknown";
}

/**
 * Composable for /spcode/file-browser.
 *
 * Per file-browser spec §3.5.1: this endpoint is stateless (no umo).
 * Unlike useSpcodeGitDiff, this composable does NOT poll — file
 * content is loaded on demand. Callers can invoke refresh(path)
 * explicitly; the composable also auto-refreshes when pathRef changes.
 *
 * Lifecycle: per-instance. Caller must invoke dispose() in
 * onBeforeUnmount to prevent state writes after unmount.
 */
export function useSpcodeFileBrowser(pathRef: MaybeRef<string>): UseSpcodeFileBrowser {
  const state = ref<FileBrowserFetchState>({ kind: "idle" });
  let abortController: AbortController | null = null;
  let isMounted = true;

  async function refresh(targetPath?: string): Promise<void> {
    if (!isMounted) return;
    const path = targetPath ?? toValue(pathRef);
    if (!path) {
      // Empty path → backend returns path_not_found. Short-circuit.
      const prev = isSnapshotState(state.value) ? state.value.snapshot : undefined;
      state.value = { kind: "error", reason: "path_not_found", previousSnapshot: prev };
      return;
    }
    abortController?.abort();
    abortController = new AbortController();
    const isFirst = !isSnapshotState(state.value);
    if (isFirst) state.value = { kind: "loading" };
    try {
      const resp = await pluginExtensionApi.get<SpcodeFileBrowserRawResponse>(
        "spcode/file-browser",
        { params: { path }, signal: abortController.signal },
      );
      if (!isMounted) return;
      const data = resp.data?.data;
      if (!data) throw new Error("empty response data");
      const snapshot = parseSpcodeFileBrowser(data);
      state.value = snapshot;
    } catch (err) {
      if (!isMounted) return;
      if ((err as { name?: string })?.name === "CanceledError") return;
      const prev = isSnapshotState(state.value) ? state.value.snapshot : undefined;
      if (err instanceof FileBrowserParseError) {
        state.value = { kind: "error", reason: err.reason, previousSnapshot: prev };
        return;
      }
      state.value = { kind: "error", reason: classifyError(err), previousSnapshot: prev };
    }
  }

  // Auto-refresh when pathRef changes (post-flush so initial assignment
  // doesn't trigger an extra fetch for the first navigation).
  watch(
    () => toValue(pathRef),
    () => { if (isMounted) void refresh(); },
    { flush: "post" },
  );

  function dispose(): void {
    isMounted = false;
    abortController?.abort();
    abortController = null;
  }

  return { state, refresh, dispose };
}
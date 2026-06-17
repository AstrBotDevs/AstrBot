// Author: elecvoid243
// Date: 2026-06-17
// Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.1.2

import { ref, type Ref } from 'vue'
import { pluginExtensionApi } from '@/api/v1'
import { useSpcodeProjectStatus } from '@/composables/useSpcodeProjectStatus'
import {
  parseSpcodeGitDiff,
  type SpcodeGitDiffSnapshot,
  type SpcodeGitDiffRawResponse,
} from '@/composables/parseSpcodeGitDiff'

export type GitDiffFetchState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; snapshot: SpcodeGitDiffSnapshot }
  | { kind: 'error'; reason: string; previousSnapshot?: SpcodeGitDiffSnapshot }

export interface UseSpcodeGitDiff {
  state: Ref<GitDiffFetchState>
  refresh: () => Promise<void>
  startPolling: (intervalMs?: number) => void
  stopPolling: () => void
  dispose: () => void
}

const DEFAULT_POLL_MS = 10_000

export function useSpcodeGitDiff(): UseSpcodeGitDiff {
  const state = ref<GitDiffFetchState>({ kind: 'idle' })
  const spcodeStatus = useSpcodeProjectStatus()
  let abortController: AbortController | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let isMounted = true

  async function refresh(): Promise<void> {
    if (!isMounted) return
    // Per-instance contract: each useSpcodeGitDiff() call owns its own closure
    // (isMounted, abortController, pollTimer). The Chunk 2 GitDiffSidebar
    // instantiates this once per <mount> and calls dispose() in onBeforeUnmount.
    // Do NOT export a module-level singleton; the composable is per-component.
    const umo = spcodeStatus.status.value.umo
    if (!umo) {
      // Note: spec §4.1.2 originally listed 'not_loaded', but i18n key list
      // (spec §5.1.1) only has 'no_project_loaded'. Use the i18n-covered
      // value to keep the UI renderable.
      const prev = state.value.kind === 'ok' ? state.value.snapshot : undefined
      state.value = { kind: 'error', reason: 'no_project_loaded', previousSnapshot: prev }
      return
    }
    abortController?.abort()
    abortController = new AbortController()
    const isFirst = state.value.kind !== 'ok'
    if (isFirst) state.value = { kind: 'loading' }
    try {
      // pluginExtensionApi.get<T>() auto-wraps in ApiEnvelope<T>, so T is
      // the inner data shape (matches useSpcodeProjectStatus.ts:45 pattern).
      const resp = await pluginExtensionApi.get<SpcodeGitDiffRawResponse>(
        'spcode/git-diff',
        {
          params: { umo },
          signal: abortController.signal,
        },
      )
      if (!isMounted) return
      const data = resp.data?.data
      if (!data) throw new Error('empty response data')
      state.value = { kind: 'ok', snapshot: parseSpcodeGitDiff(data) }
    } catch (err) {
      if (!isMounted) return
      if ((err as { name?: string })?.name === 'CanceledError') return
      const prev = state.value.kind === 'ok' ? state.value.snapshot : undefined
      state.value = {
        kind: 'error',
        reason: classifyError(err),
        previousSnapshot: prev,
      }
    }
  }

  function startPolling(intervalMs: number = DEFAULT_POLL_MS): void {
    if (pollTimer) return
    pollTimer = setInterval(() => {
      void refresh()
    }, intervalMs)
  }

  function stopPolling(): void {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function dispose(): void {
    isMounted = false
    stopPolling()
    abortController?.abort()
    abortController = null
  }

  return { state, refresh, startPolling, stopPolling, dispose }
}

function classifyError(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const anyErr = err as { code?: string; message?: string }
    if (anyErr.code === 'ERR_NETWORK' || /network/i.test(anyErr.message ?? '')) {
      return 'network'
    }
  }
  return 'unknown'
}

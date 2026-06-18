
import { ref, toValue, watch, type Ref, type MaybeRef } from 'vue'
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

export function useSpcodeGitDiff(
  worktreeRef: MaybeRef<string | null> = null,
): UseSpcodeGitDiff {
  const state = ref<GitDiffFetchState>({ kind: 'idle' })
  const spcodeStatus = useSpcodeProjectStatus()
  let abortController: AbortController | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let isMounted = true

  async function refresh(): Promise<void> {
    if (!isMounted) return
    const umo = spcodeStatus.status.value.umo
    if (!umo) {
      const prev = state.value.kind === 'ok' ? state.value.snapshot : undefined
      state.value = { kind: 'error', reason: 'no_project_loaded', previousSnapshot: prev }
      return
    }
    abortController?.abort()
    abortController = new AbortController()
    const isFirst = state.value.kind !== 'ok'
    if (isFirst) state.value = { kind: 'loading' }
    try {
      const worktree = toValue(worktreeRef)
      const resp = await pluginExtensionApi.get<SpcodeGitDiffRawResponse>(
        'spcode/git-diff',
        {
          params: {
            umo,
            ...(worktree ? { worktree } : {}),
          },
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

  watch(
    () => toValue(worktreeRef),
    () => {
      if (isMounted) void refresh()
    },
    { flush: 'post' },
  )

  watch(
    () => spcodeStatus.status.value.umo,
    (newUmo, oldUmo) => {
      if (!isMounted) return
      if (newUmo && newUmo !== oldUmo) {
        void refresh()
      }
    },
  )
  watch(
    () => spcodeStatus.status.value.directory,
    (newDir, oldDir) => {
      if (!isMounted) return
      if (newDir && newDir !== oldDir && spcodeStatus.status.value.umo) {
        void refresh()
      }
    },
  )

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

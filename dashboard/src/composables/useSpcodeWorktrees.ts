// Author: elecvoid243
// Date: 2026-06-18
// Spec: docs/superpowers/specs/2026-06-18-git-worktree-switcher-design.md §3.3

import { ref, type Ref } from 'vue'
import { pluginExtensionApi } from '@/api/v1'
import { useSpcodeProjectStatus } from '@/composables/useSpcodeProjectStatus'
import {
  parseSpcodeGitWorktrees,
  type SpcodeGitWorktreesSnapshot,
  type SpcodeGitWorktreesRawResponse,
} from '@/composables/parseSpcodeWorktrees'

export type WorktreesFetchState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; snapshot: SpcodeGitWorktreesSnapshot }
  | {
      kind: 'error'
      reason: string
      previousSnapshot?: SpcodeGitWorktreesSnapshot
    }

export interface UseSpcodeWorktrees {
  state: Ref<WorktreesFetchState>
  refresh: () => Promise<void>
  dispose: () => void
}

/**
 * Composable for the worktree list.
 *
 * Per spec §3.3, this composable does NOT watch umo — it operates on the
 * loaded project's directory at refresh time. If no project is loaded,
 * it sets state to { kind: 'error', reason: 'no_project_loaded' }.
 *
 * The composable is per-instance (NOT a module-level singleton), matching
 * the useSpcodeGitDiff pattern. GitDiffSidebar instantiates one and
 * disposes it in onBeforeUnmount.
 */
export function useSpcodeWorktrees(): UseSpcodeWorktrees {
  const state = ref<WorktreesFetchState>({ kind: 'idle' })
  const spcodeStatus = useSpcodeProjectStatus()
  let abortController: AbortController | null = null
  let isMounted = true

  async function refresh(): Promise<void> {
    if (!isMounted) return

    const umo = spcodeStatus.status.value.umo
    if (!umo) {
      const prev = state.value.kind === 'ok' ? state.value.snapshot : undefined
      state.value = {
        kind: 'error',
        reason: 'no_project_loaded',
        previousSnapshot: prev,
      }
      return
    }

    abortController?.abort()
    abortController = new AbortController()
    const isFirst = state.value.kind !== 'ok'
    if (isFirst) state.value = { kind: 'loading' }
    try {
      const resp = await pluginExtensionApi.get<SpcodeGitWorktreesRawResponse>(
        'spcode/git-worktrees',
        {
          params: { umo },
          signal: abortController.signal,
        },
      )
      if (!isMounted) return
      const data = resp.data?.data
      if (!data) throw new Error('empty response data')
      state.value = { kind: 'ok', snapshot: parseSpcodeGitWorktrees(data) }
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

  function dispose(): void {
    isMounted = false
    abortController?.abort()
    abortController = null
  }

  return { state, refresh, dispose }
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

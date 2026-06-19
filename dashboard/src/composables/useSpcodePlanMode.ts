// src/composables/useSpcodePlanMode.ts
//
// Singleton state for the spcode plan/build mode chip. Mirrors the
// pattern of `useSpcodeProjectStatus.ts`:
//
//   - one module-level ref so every consumer (the chip, the
//     +menu entry, the chat-stream parser) reads the same value
//     without coordinating fetches;
//   - explicit mutation methods (`refresh` / `setActive` / `reset`)
//     so the only way to write the ref is through a documented API;
//   - a soft-fail `refresh` that never throws to callers.
//
// The chip itself is mounted in `ChatInput.vue` next to
// `SpcodeProjectIndicator` and `GitDiffChip`; this composable feeds
// it the current per-umo state.
//
// Author: elecvoid243
// Last-Modified: 2026-06-19

import { ref } from 'vue'
import { pluginExtensionApi } from '@/api/v1'
import {
  EMPTY_PLAN_MODE_STATUS,
  type SpcodePlanModeStatus,
} from './parseSpcodePlanMode'

// Re-export the type so existing consumers of this module keep
// importing it from a single place.
export type { SpcodePlanModeStatus } from './parseSpcodePlanMode'

const status = ref<SpcodePlanModeStatus>({ ...EMPTY_PLAN_MODE_STATUS })

/**
 * Composable returning the spcode plan/build mode singleton.
 *
 * The dashboard only ever writes to the ref through one of three
 * explicit methods:
 *
 *   - `refresh(umo?)` — pull the authoritative state from the
 *     plugin's HTTP endpoint. Pass `umo` to query a specific session;
 *     omit it to receive the default build state for the whole
 *     plugin (we intentionally do NOT fall back to "most recent
 *     plan-mode session" because plan/build is strictly per-session
 *     and silently inheriting another session's mode would be
 *     confusing).
 *   - `setActive(value)` — optimistic local flip, used right after
 *     a `/plan` or `/build` command is dispatched so the chip
 *     updates before the round-trip completes.
 *   - `reset()` — wipe the ref to the empty state (e.g. on logout
 *     or when the active session becomes null).
 */
export function useSpcodePlanMode() {
  /**
   * Query the spcode plugin via its registered web API and update
   * the shared status ref.
   *
   * The endpoint accepts an optional `umo` query param. When the
   * dashboard does not know its umo, it can omit it and receive
   * the default build state — the chip should treat that as
   * "unknown" rather than "build", which is what the
   * `SpcodePlanModeChip`'s v-if gate is for.
   */
  async function refresh(umo?: string | null): Promise<void> {
    try {
      const res = await pluginExtensionApi.get<{
        active: boolean
        umo: string | null
        all_active_count: number
      }>('spcode/plan-mode', {
        params: umo ? { umo } : {},
      })
      const data = res.data?.data
      if (!data) {
        // Soft-fail: keep the last known state.
        return
      }
      status.value = {
        active: Boolean(data.active),
        umo: data.umo ?? null,
        allActiveCount:
          typeof data.all_active_count === 'number'
            ? data.all_active_count
            : 0,
        fetchedAt: Date.now(),
      }
    } catch (err) {
      // Network or auth error: keep previous state, do not throw.
      console.warn('[useSpcodePlanMode] refresh failed:', err)
    }
  }

  /**
   * Optimistically set the current session's plan mode flag.
   *
   * Used right after the dashboard dispatches a `/plan` or `/build`
   * command so the chip flips immediately rather than waiting for
   * the bot to respond and the next refresh tick to fire.
   *
   * The all-active count is bumped/decremented in lockstep so the
   * tooltip ("N sessions in plan mode") stays consistent during the
   * optimistic window. The authoritative refresh fires from
   * `Chat.vue`'s `currSessionId` watcher once the response arrives,
   * which corrects any drift.
   */
  function setActive(active: boolean): void {
    const wasActive = status.value.active
    if (wasActive === active) {
      // No-op: avoid mutating allActiveCount on a redundant call.
      return
    }
    const delta = active ? 1 : -1
    status.value = {
      ...status.value,
      active,
      allActiveCount: Math.max(0, status.value.allActiveCount + delta),
      fetchedAt: Date.now(),
    }
  }

  /**
   * Reset the status to the empty state (e.g. on logout or session
   * switch to a session that has never been seen).
   */
  function reset(): void {
    status.value = { ...EMPTY_PLAN_MODE_STATUS }
  }

  return {
    status,
    refresh,
    setActive,
    reset,
  }
}

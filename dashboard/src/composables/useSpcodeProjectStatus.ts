import { ref } from 'vue'
import { pluginExtensionApi } from '@/api/v1'
import {
  EMPTY_STATUS,
  type SpcodeProjectStatus,
} from './parseSpcodeStatus'

// Re-export the type so existing consumers of this module keep working.
export type { SpcodeProjectStatus } from './parseSpcodeStatus'

const status = ref<SpcodeProjectStatus>({ ...EMPTY_STATUS })

/**
 * Shared state holder for the spcode "currently loaded project" chip.
 *
 * The composable wraps the plugin's HTTP API and exposes a single
 * module-level `status` ref so every consumer (indicator chip, dialog
 * refresh, chat-stream parser) sees the same value.
 *
 * The dashboard only ever writes to the ref through one of three
 * explicit methods:
 *   - `refresh(umo?)` — pull the authoritative state from the spcode
 *     plugin's HTTP endpoint.
 *   - `setLoaded` / `setUnloaded` — optimistic local flips, used right
 *     after a `/project load` or `/project unload` command is
 *     dispatched so the chip updates before the round-trip completes.
 *   - `reset()` — wipe the ref to the empty state (e.g. on logout or
 *     when the active session becomes null).
 *
 * There is intentionally no chat-stream parser here: the dashboard
 * never inspects bot message text for status signals. All chat-driven
 * updates arrive via the `refresh()` call in `Chat.vue`'s
 * `currSessionId` watcher (and the `showSpcodeIndicator` watcher in
 * `ChatInput.vue`), keeping a single source of truth on the backend.
 */
export function useSpcodeProjectStatus() {
  /**
   * Query the spcode plugin via its registered web API and update the
   * shared status ref. Pass `umo` to look up a specific session; omit it
   * to receive the most-recently-loaded project (suitable for the
   * dashboard's single-user assumption).
   */
  async function refresh(umo?: string | null): Promise<void> {
    try {
      const res = await pluginExtensionApi.get<{
        loaded: boolean
        directory: string | null
        loaded_at: number | null
        umo: string | null
        all_loaded_count: number
      }>('spcode/project-status', {
        params: umo ? { umo } : {},
      })
      const data = res.data?.data
      if (!data) {
        // Soft-fail: keep the last known state.
        return
      }
      status.value = {
        loaded: Boolean(data.loaded),
        directory: data.directory ?? null,
        loadedAt:
          typeof data.loaded_at === 'number' ? data.loaded_at : null,
        umo: data.umo ?? null,
        allLoadedCount:
          typeof data.all_loaded_count === 'number'
            ? data.all_loaded_count
            : 0,
        fetchedAt: Date.now(),
      }
    } catch (err) {
      // Network or auth error: keep previous state, do not throw to callers.
      console.warn('[useSpcodeProjectStatus] refresh failed:', err)
    }
  }

  /**
   * Optimistically mark the current session as having a project loaded.
   * Used right after the dashboard dispatches a `/project load` command
   * so the chip updates immediately rather than waiting for the bot to
   * respond and the next refresh tick to fire.
   */
  function setLoaded(directory: string, loadedAt: number = Date.now() / 1000) {
    status.value = {
      ...status.value,
      loaded: true,
      directory,
      loadedAt,
      fetchedAt: Date.now(),
    }
  }

  /** Optimistically mark the current session as having no project loaded. */
  function setUnloaded() {
    status.value = {
      ...EMPTY_STATUS,
      umo: status.value.umo,
      allLoadedCount: Math.max(0, status.value.allLoadedCount - 1),
      fetchedAt: Date.now(),
    }
  }

  /**
   * Reset the status to the empty state (e.g. on logout or session switch).
   */
  function reset() {
    status.value = { ...EMPTY_STATUS }
  }

  return {
    status,
    refresh,
    setLoaded,
    setUnloaded,
    reset,
  }
}

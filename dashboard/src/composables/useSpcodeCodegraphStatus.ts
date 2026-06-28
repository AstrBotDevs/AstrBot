/**
 * useSpcodeCodegraphStatus.ts
 *
 * Singleton state for the spcode codegraph MCP server status, fetched
 * from the backend's GET /spcode/codegraph-status endpoint.
 *
 * Mirrors the pattern used by useSpcodeProjectStatus.ts — a module-level
 * ref shared across consumers (the SpcodeCodegraphChip, refresh watcher,
 * etc.) so they all read the same value.
 *
 * Author: elecvoid243
 * Last-Modified: 2026-06-28
 */

import { ref } from 'vue'
import { pluginExtensionApi } from '@/api/v1'

/**
 * Shape of the codegraph MCP status returned by the backend.
 */
export interface CodegraphStatus {
  /** Whether codegraph is enabled in plugin config. */
  enabled: boolean
  /** Whether the codegraph MCP server is currently running. */
  mcpRunning: boolean
  /** Active project path (empty string = no project set). */
  activeProject: string
  /** Local timestamp in ms of the last successful refresh. */
  fetchedAt: number | null
}

export const EMPTY_CODEGRAPH_STATUS: CodegraphStatus = {
  enabled: false,
  mcpRunning: false,
  activeProject: '',
  fetchedAt: null,
}

// ── Module-level shared state ────────────────────────────────────────────
//
// Singleton ref so every consumer (chip, watcher, dialog) observes the
// same data without redundant fetches.

const status = ref<CodegraphStatus>({ ...EMPTY_CODEGRAPH_STATUS })

/**
 * Fetch the codegraph MCP status from the spcode plugin's HTTP endpoint
 * and update the shared singleton ref. On failure the previous state is
 * preserved (soft-fail).
 */
async function fetchCodegraphStatus(): Promise<void> {
  try {
    const res = await pluginExtensionApi.get<{
      enabled: boolean
      mcp_running: boolean
      active_project: string
    }>('spcode/codegraph-status')
    const data = res.data?.data
    if (!data) {
      return
    }
    status.value = {
      enabled: Boolean(data.enabled),
      mcpRunning: Boolean(data.mcp_running),
      activeProject: data.active_project ?? '',
      fetchedAt: Date.now(),
    }
  } catch (err) {
    // Soft-fail: keep the last known state. A transient network blip
    // should not clear the chip's current display.
    console.warn('[useSpcodeCodegraphStatus] refresh failed:', err)
  }
}

/**
 * Optimistically mark the codegraph MCP server as running (or stopped).
 * Used right after the dashboard dispatches a `/codegraph start` or
 * `/codegraph stop` command so the chip updates immediately rather
 * than waiting for the next poll tick.
 */
function setRunning(running: boolean): void {
  status.value = {
    ...status.value,
    mcpRunning: running,
    fetchedAt: Date.now(),
  }
}

/**
 * Optimistically update the active project path.
 * Used after the user dispatches `/codegraph set <path>`.
 */
function setProject(project: string): void {
  status.value = {
    ...status.value,
    activeProject: project,
    fetchedAt: Date.now(),
  }
}

/**
 * Reset the singleton status to the empty state.
 */
function resetCodegraphStatus(): void {
  status.value = { ...EMPTY_CODEGRAPH_STATUS }
}

/**
 * Singleton composable for the codegraph MCP server status.
 *
 * Returns:
 *   - status:  the shared ref (reactive CodegraphStatus)
 *   - refresh: trigger an explicit re-fetch from the backend
 *   - setRunning: optimistically set the MCP running state
 *   - setProject: optimistically set the active project path
 *   - reset:   wipe to the empty state (e.g. on logout)
 */
export function useSpcodeCodegraphStatus() {
  return {
    status,
    refresh: fetchCodegraphStatus,
    setRunning,
    setProject,
    reset: resetCodegraphStatus,
  }
}

/**
 * Shared types and constants for the spcode "currently loaded project"
 * chip state.
 *
 * Author: elecvoid243
 */

export interface SpcodeProjectStatus {
  loaded: boolean
  directory: string | null
  loadedAt: number | null
  /** The umo the status was reported for; may be null when nothing is loaded. */
  umo: string | null
  /** Total number of umos with a project loaded, across all sessions. */
  allLoadedCount: number
  /** Local timestamp of the last successful refresh (ms). */
  fetchedAt: number | null
}

export const EMPTY_STATUS: SpcodeProjectStatus = {
  loaded: false,
  directory: null,
  loadedAt: null,
  umo: null,
  allLoadedCount: 0,
  fetchedAt: null,
}

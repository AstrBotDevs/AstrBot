/**
 * Shared types and constants for the spcode "plan vs build mode" chip
 * state.
 *
 * The plan/build switch mirrors the design of `parseSpcodeStatus.ts`:
 * the backend exposes a single GET endpoint that returns the current
 * per-umo state and a process-wide counter, and the dashboard caches
 * it in a single module-level ref consumed by `SpcodePlanModeChip`.
 *
 * Author: elecvoid243
 * Last-Modified: 2026-06-19
 */

/**
 * Snapshot of the spcode plugin's per-umo plan/build mode state.
 *
 * The semantics of `active` are:
 *   - `true`  → plan mode is active for the queried umo; the plugin's
 *     `_plan_filter_tools` hook will filter `plan_mode_blocked_tools`
 *     out of the LLM tool list on the next request.
 *   - `false` → build mode (the default). All tools are available.
 *
 * Both unknown umos and umos whose entry is explicitly `false` report
 * `active = false`; the backend treats them identically.
 */
export interface SpcodePlanModeStatus {
  /** True when plan mode is active for the queried umo. */
  active: boolean
  /** The umo the status was reported for; null when the caller omitted it. */
  umo: string | null
  /**
   * Total number of umos with plan mode active across the whole
   * plugin instance. Useful for cross-session telemetry in the chip
   * tooltip ("3 sessions in plan mode").
   */
  allActiveCount: number
  /**
   * Local timestamp (ms) of the last successful refresh. Lets the
   * UI detect stale state without having to re-issue the request.
   */
  fetchedAt: number | null
}

/** The neutral initial state used before the first refresh resolves. */
export const EMPTY_PLAN_MODE_STATUS: SpcodePlanModeStatus = {
  active: false,
  umo: null,
  allActiveCount: 0,
  fetchedAt: null,
}

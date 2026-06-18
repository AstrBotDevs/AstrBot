// Author: elecvoid243
// Date: 2026-06-18
// Spec: docs/superpowers/specs/2026-06-18-git-worktree-switcher-design.md §3.5

/**
 * Parsed types for the GET /spcode/git-worktrees endpoint.
 *
 * Backend envelope (SpcodeGitWorktreesResponse):
 *   {
 *     "status": "ok",
 *     "data": {
 *       "loaded": bool,
 *       "directory": str | null,
 *       "umo": str | null,
 *       "worktrees": [ { path, head_sha, branch, is_main, prunable, locked }, ... ],
 *       "reason": str | null,
 *       "stderr": str,
 *       "elapsed_ms": int
 *     }
 *   }
 */

export interface SpcodeGitWorktreeRaw {
  path: string
  head_sha: string
  branch: string | null
  is_main: boolean
  prunable: boolean
  locked: string | null
}

export interface SpcodeGitWorktreesRawResponse {
  loaded: boolean
  directory: string | null
  umo: string | null
  worktrees: SpcodeGitWorktreeRaw[]
  reason: string | null
  stderr: string
  elapsed_ms: number
}

export interface SpcodeGitWorktree {
  /** Absolute filesystem path (forward slashes from git porcelain). */
  path: string
  /** Commit SHA at HEAD (short or full, as returned by git). */
  headSha: string
  /** Branch name; null for detached worktrees. */
  branch: string | null
  /** True for the primary worktree (the one containing the .git dir). */
  isMain: boolean
  /** True if `git worktree prune` would remove this entry. */
  prunable: boolean
  /** Lock reason; null if not locked. */
  locked: string | null
}

export interface SpcodeGitWorktreesSnapshot {
  meta: {
    directory: string | null
    umo: string | null
    loaded: boolean
    reason: string | null
    stderr: string
    elapsedMs: number
    fetchedAt: number
  }
  worktrees: SpcodeGitWorktree[]
}

/**
 * Convert the raw backend response into a frontend-friendly snapshot.
 * Performs strict normalization: status fields outside the known set
 * collapse to safe defaults rather than throwing.
 */
export function parseSpcodeGitWorktrees(
  data: SpcodeGitWorktreesRawResponse,
): SpcodeGitWorktreesSnapshot {
  return {
    meta: {
      directory: data.directory ?? null,
      umo: data.umo ?? null,
      loaded: Boolean(data.loaded),
      reason: data.reason ?? null,
      stderr: data.stderr ?? '',
      elapsedMs:
        typeof data.elapsed_ms === 'number' ? data.elapsed_ms : 0,
      fetchedAt: Date.now(),
    },
    worktrees: Array.isArray(data.worktrees)
      ? data.worktrees.map((w) => ({
          path: String(w.path ?? ''),
          headSha: String(w.head_sha ?? ''),
          branch: w.branch ?? null,
          isMain: Boolean(w.is_main),
          prunable: Boolean(w.prunable),
          locked: w.locked ?? null,
        }))
      : [],
  }
}

// Author: elecvoid243
// Date: 2026-06-24
// Spec: docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md §3-5
//
// Pure parser for the 4 git workflow endpoints (git-stage / git-unstage /
// git-commit / git-log). No Vue / no axios — importable by node --test
// (see tests/parseSpcodeGitWorkflow.test.mjs). Mirrors the existing
// parseSpcodeFileRestore.ts + parseSpcodeGitDiff.ts split.

// ─── Endpoint id union ────────────────────────────────────────────
export type GitWorkflowEndpoint = "stage" | "unstage" | "commit" | "log";

// ─── Stage / Unstage snapshot ─────────────────────────────────────
export interface SpcodeStageRawData {
  success: boolean;
  reason: string | null;
  stderr: string;
  elapsed_ms: number;
  umo: string;
  worktree: string;
  directory: string;
  staged?: boolean; // git-stage only
  unstaged?: boolean; // git-unstage only
  files: string[];
  staged_count: number;
}

export interface SpcodeStageSnapshot {
  success: boolean;
  reason: string | null;
  stderr: string;
  elapsedMs: number;
  umo: string;
  worktree: string;
  directory: string;
  /** True 表示本次调用执行了 stage;git-unstage 时为 false (后端字段是 `unstaged`) */
  staged: boolean;
  /** True 表示本次调用执行了 unstage;git-stage 时为 false */
  unstaged: boolean;
  files: string[];
  stagedCount: number;
}

// ─── Commit snapshot ──────────────────────────────────────────────
export interface SpcodeCommitRawData {
  success: boolean;
  reason: string | null;
  stderr: string;
  elapsed_ms: number;
  umo: string;
  worktree: string;
  directory: string;
  committed: boolean;
  sha: string;
  files: string[];
  committed_count: number;
  staged_count: number;
}

export interface SpcodeCommitSnapshot {
  success: boolean;
  reason: string | null;
  stderr: string;
  elapsedMs: number;
  umo: string;
  worktree: string;
  directory: string;
  committed: boolean;
  sha: string;
  files: string[];
  committedCount: number;
  stagedCount: number;
}

// ─── Log snapshot ─────────────────────────────────────────────────
export interface SpcodeLogRawCommit {
  sha: string;
  sha_short: string;
  author: { name: string; email: string };
  committer: { name: string; email: string };
  date: string;
  subject: string;
  body: string | null;
  parents: string[];
  shortstat: { files: number; additions: number; deletions: number };
}

export interface SpcodeLogRawData {
  success: boolean;
  reason: string | null;
  loaded: boolean;
  elapsed_ms: number;
  umo: string;
  worktree: string;
  directory: string;
  ref: string;
  count: number;
  has_more: boolean;
  truncated: boolean;
  max_bytes: number;
  commits: SpcodeLogRawCommit[];
}

export interface SpcodeLogCommit {
  sha: string;
  shaShort: string;
  author: { name: string; email: string };
  committer: { name: string; email: string };
  date: string;
  subject: string;
  body: string | null;
  parents: string[];
  shortstat: { files: number; additions: number; deletions: number };
}

export interface SpcodeLogSnapshot {
  success: boolean;
  reason: string | null;
  loaded: boolean;
  elapsedMs: number;
  umo: string;
  worktree: string;
  directory: string;
  ref: string;
  count: number;
  hasMore: boolean;
  truncated: boolean;
  maxBytes: number;
  commits: SpcodeLogCommit[];
}

export type ParseResult<T> =
  | { kind: "ok"; snapshot: T }
  | { kind: "error"; reason: string };

// ─── Envelope helpers ─────────────────────────────────────────────
function unwrapEnvelope(raw: unknown): unknown {
  if (typeof raw !== "object" || raw === null) {
    throw new Error("missing status envelope");
  }
  const env = raw as { status?: unknown; data?: unknown };
  if (env.status !== "ok") {
    throw new Error("unexpected status envelope");
  }
  if (typeof env.data !== "object" || env.data === null) {
    throw new Error("missing data in response");
  }
  return env.data;
}

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}
function asNumber(v: unknown, fallback = 0): number {
  return typeof v === "number" ? v : fallback;
}
function asBoolean(v: unknown, fallback = false): boolean {
  return typeof v === "boolean" ? v : fallback;
}
function asStringArray(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.filter((x): x is string => typeof x === "string");
}

/** Derive success/failure from the spcode git-workflow envelope.
 *
 * Spec §3 contract (tools/webapi/_helpers.py: `_make_envelope`):
 *   success=True  → data.reason === null
 *   success=False → data.reason === "<reason_code>"
 * The backend never writes `success` into `data`. Reading
 * `asBoolean(d.success)` returns `false` for every response,
 * silently turning every success into a "reason=unknown" snackbar.
 * Anchoring on `reason === null` matches the spec exactly and
 * fixes the regression reported 2026-06-24 (vue-side "unknown
 * error" toast on successful code-file staging). */
function deriveSuccess(d: { success?: unknown; reason?: unknown }): boolean {
  // Honor an explicit `success` field if a future backend adds it;
  // otherwise fall back to the canonical spec indicator.
  if (d.success !== undefined) return asBoolean(d.success);
  return d.reason === null;
}

// ─── Endpoint-specific parsers ────────────────────────────────────

/** Parse the envelope from POST /spcode/git-stage. */
export function parseSpcodeGitStage(raw: unknown): ParseResult<SpcodeStageSnapshot> {
  const d = unwrapEnvelope(raw) as Partial<SpcodeStageRawData>;
  return {
    kind: "ok",
    snapshot: {
      success: deriveSuccess(d),
      reason: d.reason ?? null,
      stderr: asString(d.stderr),
      elapsedMs: asNumber(d.elapsed_ms),
      umo: asString(d.umo),
      worktree: asString(d.worktree),
      directory: asString(d.directory),
      // 缺省 false — v3.7 之前 plugin 不返回 staged 字段
      staged: asBoolean(d.staged),
      unstaged: asBoolean(d.unstaged),
      files: asStringArray(d.files),
      stagedCount: asNumber(d.staged_count),
    },
  };
}

/** Parse the envelope from POST /spcode/git-unstage. */
export function parseSpcodeGitUnstage(raw: unknown): ParseResult<SpcodeStageSnapshot> {
  // Reuse stage parser — same shape, only the echoed flag name differs.
  return parseSpcodeGitStage(raw);
}

/** Parse the envelope from POST /spcode/git-commit. */
export function parseSpcodeGitCommit(raw: unknown): ParseResult<SpcodeCommitSnapshot> {
  const d = unwrapEnvelope(raw) as Partial<SpcodeCommitRawData>;
  return {
    kind: "ok",
    snapshot: {
      success: deriveSuccess(d),
      reason: d.reason ?? null,
      stderr: asString(d.stderr),
      elapsedMs: asNumber(d.elapsed_ms),
      umo: asString(d.umo),
      worktree: asString(d.worktree),
      directory: asString(d.directory),
      committed: asBoolean(d.committed),
      // 失败时 sha 必为空;允许任意字符串值透传
      sha: asString(d.sha),
      files: asStringArray(d.files),
      committedCount: asNumber(d.committed_count),
      stagedCount: asNumber(d.staged_count),
    },
  };
}

/** Parse the envelope from GET /spcode/git-log. */
export function parseSpcodeGitLog(raw: unknown): ParseResult<SpcodeLogSnapshot> {
  const d = unwrapEnvelope(raw) as Partial<SpcodeLogRawData>;
  const rawCommits = Array.isArray(d.commits) ? d.commits : [];
  const commits: SpcodeLogCommit[] = rawCommits.map((c) => {
    const c0 = c as Partial<SpcodeLogRawCommit>;
    return {
      sha: asString(c0.sha),
      shaShort: asString(c0.sha_short),
      author: {
        name: asString(c0.author?.name),
        email: asString(c0.author?.email),
      },
      committer: {
        name: asString(c0.committer?.name),
        email: asString(c0.committer?.email),
      },
      date: asString(c0.date),
      subject: asString(c0.subject),
      body: typeof c0.body === "string" ? c0.body : null,
      parents: asStringArray(c0.parents),
      shortstat: {
        files: asNumber(c0.shortstat?.files),
        additions: asNumber(c0.shortstat?.additions),
        deletions: asNumber(c0.shortstat?.deletions),
      },
    };
  });
  return {
    kind: "ok",
    snapshot: {
      success: deriveSuccess(d),
      reason: d.reason ?? null,
      loaded: asBoolean(d.loaded),
      elapsedMs: asNumber(d.elapsed_ms),
      umo: asString(d.umo),
      worktree: asString(d.worktree),
      directory: asString(d.directory),
      ref: asString(d.ref, "HEAD"),
      count: asNumber(d.count),
      hasMore: asBoolean(d.has_more),
      truncated: asBoolean(d.truncated),
      maxBytes: asNumber(d.max_bytes),
      commits,
    },
  };
}

// ─── Reason classification (spec §5.1) ────────────────────────────

/** Reason code meta for the 4 git-workflow endpoints.
 *  withStderr: 失败时 data.stderr 携带 git 原始输出,模板渲染 <pre> 块
 *  withReason: fallback reason 需要展示字面值(用于"未知 reason"兜底)
 */
export interface ReasonMeta {
  i18nKey: string;
  color: "error" | "warning";
  withStderr?: boolean;
  withReason?: boolean;
}

/** Shared dictionary used by all 4 endpoints.
 *  P0-3 修复:`empty_repository` 不进此字典 — 它是 git-log 的判别式
 *  "空状态" 而非错误。`useSpcodeGitLog` 在解析后直接将 `snap.reason ===
 *  "empty_repository"` 转写为 `{ kind: "error", reason: "empty_repository" }`,
 *  GitLogView 模板用 `isEmptyRepository` 计算属性(`kind === "error" &&
 *  reason === "empty_repository"`)分支渲染空仓库插画,且不触发
 *  snackbar / error banner(spec §5.1 P0-3)。 */
export const GIT_WORKFLOW_REASON_CODES: Record<string, ReasonMeta> = {
  // 前置类
  feature_disabled: { i18nKey: "error.reason.feature_disabled", color: "error" },
  no_project_loaded: { i18nKey: "error.reason.no_project_loaded", color: "error" },
  worktree_invalid: { i18nKey: "error.reason.worktree_invalid", color: "error" },
  directory_missing: { i18nKey: "error.reason.directory_missing", color: "error" },
  not_a_git_repo: { i18nKey: "error.reason.not_a_git_repo", color: "error" },
  git_unavailable: { i18nKey: "error.reason.git_unavailable", color: "error" },
  git_error: { i18nKey: "error.reason.git_error", color: "error", withStderr: true },
  // Body 类
  invalid_body: { i18nKey: "error.reason.invalid_body", color: "error" },
  invalid_files: { i18nKey: "error.reason.invalid_files", color: "error" },
  invalid_all: { i18nKey: "error.reason.invalid_all", color: "error" },
  invalid_message: { i18nKey: "error.reason.invalid_message", color: "error" },
  invalid_param: { i18nKey: "error.reason.invalid_param", color: "error" },
  // 路径类
  path_unsafe: { i18nKey: "error.reason.path_unsafe", color: "error" },
  // 业务类
  nothing_to_commit: { i18nKey: "error.reason.nothing_to_commit", color: "warning" },
  hook_rejected: { i18nKey: "error.reason.hook_rejected", color: "warning", withStderr: true },
  identity_not_set: { i18nKey: "error.reason.identity_not_set", color: "warning" },
  // 前端
  network: { i18nKey: "error.reason.network", color: "error" },
  unknown: { i18nKey: "error.reason.unknown", color: "error", withReason: true },
};

/** Allowed reason codes per endpoint (spec §5.2).
 *  git-log 故意不列 empty_repository — 它走空状态分支;
 *  详见上方 GIT_WORKFLOW_REASON_CODES 注释及 useSpcodeGitLog 的状态转换。 */
export const ALLOWED_REASONS: Record<GitWorkflowEndpoint, readonly string[]> = {
  stage: [
    "feature_disabled",
    "no_project_loaded",
    "worktree_invalid",
    "directory_missing",
    "not_a_git_repo",
    "git_unavailable",
    "invalid_body",
    "invalid_files",
    "invalid_all",
    "path_unsafe",
    "git_error",
  ],
  unstage: [
    "feature_disabled",
    "no_project_loaded",
    "worktree_invalid",
    "directory_missing",
    "not_a_git_repo",
    "git_unavailable",
    "invalid_body",
    "invalid_files",
    "invalid_all",
    "path_unsafe",
    "git_error",
  ],
  commit: [
    "feature_disabled",
    "no_project_loaded",
    "worktree_invalid",
    "directory_missing",
    "not_a_git_repo",
    "git_unavailable",
    "invalid_body",
    "invalid_message",
    "nothing_to_commit",
    "hook_rejected",
    "identity_not_set",
    "git_error",
  ],
  log: [
    "feature_disabled",
    "no_project_loaded",
    "worktree_invalid",
    "directory_missing",
    "not_a_git_repo",
    "git_unavailable",
    "invalid_param",
    "path_unsafe",
    "git_error",
  ],
};

/** Classify a reason string to a ReasonMeta.
 *  Returns `unknown` for null / undefined / unknown / endpoint-mismatched codes. */
export function classifyReason(
  reason: string | null | undefined,
  endpoint: GitWorkflowEndpoint,
): ReasonMeta {
  if (reason === null || reason === undefined) {
    return GIT_WORKFLOW_REASON_CODES.unknown;
  }
  if (reason === "network") {
    return GIT_WORKFLOW_REASON_CODES.network;
  }
  if (!(ALLOWED_REASONS[endpoint] as readonly string[]).includes(reason)) {
    return GIT_WORKFLOW_REASON_CODES.unknown;
  }
  return GIT_WORKFLOW_REASON_CODES[reason] ?? GIT_WORKFLOW_REASON_CODES.unknown;
}

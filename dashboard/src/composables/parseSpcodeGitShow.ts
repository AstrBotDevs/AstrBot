// Author: elecvoid243
// Date: 2026-06-25
// Spec: docs/superpowers/specs/2026-06-25-git-show-design.md
// API doc: docs/webapi-git-show-api.md
//
// Pure parser for GET /spcode/git-show. No Vue / no axios — importable
// by node --test (see tests/parseSpcodeGitShow.test.mjs). Mirrors the
// shape of parseSpcodeGitWorkflow.ts (commit-meta block + files array)
// so a single import path covers the entire git-history surface.

// ─── Raw API response shape ────────────────────────────────────────

export interface SpcodeGitShowRawFile {
  path: string;
  status: string;
  additions: number;
  deletions: number;
  // R / C only:
  old_path?: string;
  similarity?: number;
}

export interface SpcodeGitShowRawData {
  success: boolean;
  reason: string | null;
  loaded: boolean;
  stderr: string;
  elapsed_ms: number;
  umo: string | null;
  worktree: string | null;
  directory: string | null;

  // commit meta
  ref: string;
  resolved_sha: string;
  parents: string[];
  author: { name: string; email: string };
  date: string;
  subject: string;
  body: string | null;

  // file list
  files: SpcodeGitShowRawFile[];
  count: number;
  truncated: boolean;
  max_files: number;

  // v3.9 (2026-06-25): 单文件 patch 视图(可选;仅在 ?path= 给出时存在)
  // binary 文件 patch=null;path 不在该 ref 中时 status="unknown"
  file?: SpcodeGitShowRawFileView;
}

export interface GitShowFileView {
  path: string;
  status: GitShowFileStatus;
  additions: number;
  deletions: number;
  /** 仅 R / C 有值 */
  oldPath: string | null;
  /** binary 文件 patch 始终为 null,前端渲染 "binary file" 占位 */
  isBinary: boolean;
  /** unified diff 文本(含 diff --git / --- / +++ / hunk 头);
   *  null 时 (binary 或 unknown) 渲染 fallback 占位 */
  patch: string | null;
}

export interface SpcodeGitShowRawFileView {
  path: string;
  old_path?: string | null;
  status: string; // "M" | "A" | "D" | "R" | "C" | "unknown"
  additions: number;
  deletions: number;
  is_binary: boolean;
  patch: string | null; // unified diff 文本;binary 或 unknown 时为 null
}

// ─── Public types ──────────────────────────────────────────────────

/**
 * File status code. Matches `git diff --name-status` and the spcode
 * git-diff parser. Type changes (`T`) are folded into `M` per spec.
 */
export type GitShowFileStatus = "M" | "A" | "D" | "R" | "C" | "unknown";

export interface GitShowFile {
  path: string;
  status: GitShowFileStatus;
  additions: number;
  deletions: number;
  /** Original path; only set for status R / C. */
  oldPath: string | null;
  /** Rename / copy similarity (0-100); only set for status R / C. */
  similarity: number | null;
}

export interface GitShowCommit {
  ref: string;
  resolvedSha: string;
  parents: string[];
  author: { name: string; email: string };
  date: string;
  subject: string;
  body: string | null;
}

export interface GitShowData {
  // Envelope fields
  success: boolean;
  reason: string | null;
  loaded: boolean;
  stderr: string;
  elapsedMs: number;
  umo: string | null;
  worktree: string | null;
  directory: string | null;

  // Commit meta + files
  commit: GitShowCommit;
  files: GitShowFile[];
  count: number;
  truncated: boolean;
  maxFiles: number;

  // v3.9 (2026-06-25): 单文件 patch 视图(可选,仅在 ?path= 给出时存在)
  file: GitShowFileView | null;
}

export type ParseResult<T> =
  | { kind: "ok"; snapshot: T }
  | { kind: "error"; reason: string };

// ─── Helpers ───────────────────────────────────────────────────────

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}
function asNumber(v: unknown, fallback = 0): number {
  return typeof v === "number" ? v : fallback;
}
function asBoolean(v: unknown, fallback = false): boolean {
  return typeof v === "boolean" ? v : fallback;
}
function asStringOrNull(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}
function asNumberOrNull(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}
function asStringArray(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.filter((x): x is string => typeof x === "string");
}

const VALID_STATUSES: ReadonlySet<GitShowFileStatus> = new Set([
  "M",
  "A",
  "D",
  "R",
  "C",
]);

/** Normalize a raw status code. Anything outside M/A/D/R/C → "unknown". */
function normalizeStatus(raw: unknown): GitShowFileStatus {
  const s = typeof raw === "string" ? (raw[0] as GitShowFileStatus) : "unknown";
  return VALID_STATUSES.has(s) ? s : "unknown";
}

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

/** Mirror parseSpcodeGitWorkflow.deriveSuccess: backend never writes
 *  `success`; the canonical indicator is `reason === null`. */
function deriveSuccess(d: { success?: unknown; reason?: unknown }): boolean {
  if (d.success !== undefined) return asBoolean(d.success);
  return d.reason === null;
}

// ─── Public parser ─────────────────────────────────────────────────

/** Parse the envelope from GET /spcode/git-show. */
export function parseSpcodeGitShow(raw: unknown): ParseResult<GitShowData> {
  const d = unwrapEnvelope(raw) as Partial<SpcodeGitShowRawData>;
  const rawFiles = Array.isArray(d.files) ? d.files : [];
  const files: GitShowFile[] = rawFiles.map((f) => {
    const f0 = f as Partial<SpcodeGitShowRawFile>;
    const status = normalizeStatus(f0.status);
    return {
      path: asString(f0.path),
      status,
      additions: asNumber(f0.additions),
      deletions: asNumber(f0.deletions),
      oldPath: status === "R" || status === "C" ? asStringOrNull(f0.old_path) : null,
      similarity:
        status === "R" || status === "C" ? asNumberOrNull(f0.similarity) : null,
    };
  });

  // v3.9: 解析可选的单文件 patch 视图(?path= 时存在)
  // 后端在 data.file 字段;不存在 → null。前端把它跟 file list 解耦
  // (file list 总是返回,file 视图是 lazy fetch 单独的 per-file state)。
  let fileView: GitShowFileView | null = null;
  if (d.file && typeof d.file === "object") {
    const f0 = d.file as Partial<SpcodeGitShowRawFileView>;
    const fileStatus = normalizeStatus(f0.status);
    fileView = {
      path: asString(f0.path),
      status: fileStatus,
      additions: asNumber(f0.additions),
      deletions: asNumber(f0.deletions),
      oldPath:
        fileStatus === "R" || fileStatus === "C"
          ? asStringOrNull(f0.old_path)
          : null,
      isBinary: asBoolean(f0.is_binary),
      // binary 或 path 不匹配时后端给 null;空字符串也归一为 null
      patch: asStringOrNull(f0.patch),
    };
  }

  return {
    kind: "ok",
    snapshot: {
      success: deriveSuccess(d),
      reason: d.reason ?? null,
      loaded: asBoolean(d.loaded),
      stderr: asString(d.stderr),
      elapsedMs: asNumber(d.elapsed_ms),
      umo: asStringOrNull(d.umo),
      worktree: asStringOrNull(d.worktree),
      directory: asStringOrNull(d.directory),
      commit: {
        ref: asString(d.ref, "HEAD"),
        resolvedSha: asString(d.resolved_sha),
        parents: asStringArray(d.parents),
        author: {
          name: asString(d.author?.name),
          email: asString(d.author?.email),
        },
        date: asString(d.date),
        subject: asString(d.subject),
        body: asStringOrNull(d.body),
      },
      files,
      count: asNumber(d.count),
      truncated: asBoolean(d.truncated),
      maxFiles: asNumber(d.max_files, 500),
      file: fileView,
    },
  };
}

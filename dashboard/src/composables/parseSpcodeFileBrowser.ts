// Author: elecvoid243, 2026-06-20
// Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.1
// Mirrors the file-browser endpoint contract:
// astrbot_plugin_spcode_toolkit/docs/superpowers/specs/2026-06-20-file-browser-endpoint-design.md §3.5

/**
 * Single directory entry: directory / file / symlink, three-state.
 * For symlink targets, the backend does NOT follow them — type stays
 * "symlink" regardless of what the target resolves to.
 */
export interface SpcodeFileBrowserEntry {
  /** Absolute path of this entry (round-trip from backend) */
  path: string;
  /** Basename (unencoded) */
  name: string;
  /** "directory" / "file" / "symlink" — backend explicitly does not follow symlinks */
  type: "directory" | "file" | "symlink";
  /** Bytes (null for directories; for symlinks, lstat size of the link itself) */
  size: number | null;
  /** mtime in unix seconds; null if lstat failed */
  mtime: number | null;
  /** True when type === "symlink" */
  is_symlink: boolean;
  /** symlink only: raw target string */
  target?: string;
  /** symlink only: whether the target exists (for "dangling" UI) */
  target_exists?: boolean;
}

export interface SpcodeFileBrowserDirectorySnapshot {
  meta: {
    path: string;
    entryCount: number;
    truncated: boolean;
    maxEntries: number;
    reason: string | null;
    elapsedMs: number;
    fetchedAt: number;
  };
  /** Sorted: directories → files → symlinks */
  entries: SpcodeFileBrowserEntry[];
}

export interface SpcodeFileBrowserFileSnapshot {
  meta: {
    path: string;
    name: string;
    size: number;
    mtime: number | null;
    maxBytes: number;
    encoding: "utf-8" | null;
    isBinary: boolean | null;
    reason: string | null;
    elapsedMs: number;
    fetchedAt: number;
  };
  /** null when too large, binary, or read error */
  content: string | null;
}

export interface SpcodeFileBrowserSymlinkSnapshot {
  meta: {
    path: string;
    name: string;
    size: number;
    mtime: number | null;
    isSymlink: true;
    target: string;
    targetExists: boolean;
    elapsedMs: number;
    fetchedAt: number;
  };
}

/** Raw backend response (1:1 with the JSON schema). All fields optional except path/name/type. */
export interface SpcodeFileBrowserRawResponse {
  type: "file" | "directory" | "symlink" | null;
  path: string;
  name: string;
  size: number;
  mtime: number | null;
  is_symlink: boolean;
  // file
  encoding?: "utf-8" | null;
  is_binary?: boolean | null;
  content?: string | null;
  max_bytes?: number;
  // directory
  entry_count?: number;
  truncated?: boolean;
  max_entries?: number;
  entries?: Array<{
    path: string;
    name: string;
    type: "directory" | "file" | "symlink";
    size: number | null;
    mtime: number | null;
    is_symlink: boolean;
    target?: string;
    target_exists?: boolean;
  }>;
  // symlink (top-level, i.e. when the requested path itself is a symlink)
  target?: string;
  target_exists?: boolean;
  // error
  reason: string | null;
  elapsed_ms: number;
}

export type SpcodeFileBrowserSnapshot =
  | { kind: "directory"; snapshot: SpcodeFileBrowserDirectorySnapshot }
  | { kind: "file"; snapshot: SpcodeFileBrowserFileSnapshot }
  | { kind: "symlink"; snapshot: SpcodeFileBrowserSymlinkSnapshot };

/** Thrown when data.type === null (true backend error). */
export class FileBrowserParseError extends Error {
  public readonly reason: string;
  constructor(reason: string) {
    super(`file-browser parse error: ${reason}`);
    this.name = "FileBrowserParseError";
    this.reason = reason;
  }
}

function normalizeEntry(raw: NonNullable<SpcodeFileBrowserRawResponse["entries"]>[number]): SpcodeFileBrowserEntry {
  return {
    path: raw.path,
    name: raw.name,
    type: raw.type,
    size: raw.size,
    mtime: raw.mtime,
    is_symlink: raw.is_symlink,
    target: raw.target,
    target_exists: raw.target_exists,
  };
}

/**
 * Parse raw response into a typed snapshot.
 * @throws {FileBrowserParseError} when data.type is null (backend error).
 */
export function parseSpcodeFileBrowser(data: SpcodeFileBrowserRawResponse): SpcodeFileBrowserSnapshot {
  const fetchedAt = Date.now();
  if (data.type === null) {
    throw new FileBrowserParseError(data.reason ?? "unknown");
  }
  if (data.type === "directory") {
    return {
      kind: "directory",
      snapshot: {
        meta: {
          path: data.path,
          entryCount: data.entry_count ?? 0,
          truncated: data.truncated ?? false,
          maxEntries: data.max_entries ?? 1000,
          reason: data.reason ?? null,
          elapsedMs: data.elapsed_ms ?? 0,
          fetchedAt,
        },
        entries: Array.isArray(data.entries) ? data.entries.map(normalizeEntry) : [],
      },
    };
  }
  if (data.type === "file") {
    return {
      kind: "file",
      snapshot: {
        meta: {
          path: data.path,
          name: data.name,
          size: data.size ?? 0,
          mtime: data.mtime ?? null,
          maxBytes: data.max_bytes ?? 5 * 1024 * 1024,
          encoding: data.encoding ?? null,
          isBinary: data.is_binary ?? null,
          reason: data.reason ?? null,
          elapsedMs: data.elapsed_ms ?? 0,
          fetchedAt,
        },
        content: data.content ?? null,
      },
    };
  }
  // data.type === "symlink"
  return {
    kind: "symlink",
    snapshot: {
      meta: {
        path: data.path,
        name: data.name,
        size: data.size ?? 0,
        mtime: data.mtime ?? null,
        isSymlink: true,
        target: data.target ?? "",
        targetExists: data.target_exists ?? false,
        elapsedMs: data.elapsed_ms ?? 0,
        fetchedAt,
      },
    },
  };
}
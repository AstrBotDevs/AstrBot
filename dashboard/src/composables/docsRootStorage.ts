// Author: elecvoid243, 2026-07-12
// Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §3.4
//
// Pure-TS helpers for persisting the per-UMO docs root path in
// localStorage. No Vue imports — testable with node:test.
//
// The backend (POST/PATCH/DELETE /spcode/docs) does not persist
// docsRoot; this file is the only source of truth for the path the
// user sees in DocumentPathBar. localStorage is the storage layer;
// failures are swallowed (private mode / quota) and the caller
// falls back to the default.

export const DOCS_ROOT_STORAGE_KEY =
  "astrbot.spcode.documentManager.docsPathByUmo";
export const DEFAULT_DOCS_ROOT = "docs";

/** Minimal subset of the Storage interface so tests can inject
 *  a fake without touching the real `localStorage` global. */
export interface StorageBackend {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

let storageBackend: StorageBackend | null = null;

/** Test-only seam: replace the localStorage shim. Pass `null` to
 *  restore the default (which uses `globalThis.localStorage` when
 *  available and a no-op stub otherwise). Production code MUST NOT
 *  call this — it's exported only so `tests/*.test.mjs` can plug
 *  in an in-memory map. */
export function __setStorageBackend(backend: StorageBackend | null): void {
  storageBackend = backend;
}

function defaultBackend(): StorageBackend {
  if (storageBackend) return storageBackend;
  // Defensive: in node:test without happy-dom, globalThis.localStorage
  // is undefined. Wrap in try/catch because real localStorage can
  // also throw (private browsing, disabled storage).
  return {
    getItem(key) {
      try {
        return globalThis.localStorage?.getItem(key) ?? null;
      } catch {
        return null;
      }
    },
    setItem(key, value) {
      try {
        globalThis.localStorage?.setItem(key, value);
      } catch {
        /* swallow */
      }
    },
    removeItem(key) {
      try {
        globalThis.localStorage?.removeItem(key);
      } catch {
        /* swallow */
      }
    },
  };
}

/** Path validator. Mirrors spec §3.4 + §3.6 invariants; the
 *  backend re-validates with the same rules server-side, so this
 *  is defense-in-depth only.
 *
 *  Accepts: the literal "." (means "the project root itself"),
 *  forward-slash subpaths ("docs", "docs/sub", "./docs" — the
 *  leading "./" is harmless and will be normalized away by
 *  callers), and ordinary hidden-directory names (".github",
 *  ".vscode") used as docs roots.
 *
 *  Rejects: empty, absolute (POSIX or Windows), drive-letter,
 *  UNC (\\server\share), parent traversal ("..", "a/..", "../foo"),
 *  leading slash or backslash, leading "~" (POSIX home expansion,
 *  which would escape the project entirely). */
export function isValidDocsRoot(p: string): boolean {
  if (!p) return false;
  if (p.length > 512) return false; // sanity bound, not a spec rule
  // Reject any `..` segment. Cheap: just look for the substring;
  // covers literal "..", "a/..", "../foo", and "a/../b". Fine
  // because we forbid backslashes and absolute paths upstream.
  if (p.includes("..")) return false;
  if (/^[a-zA-Z]:/.test(p)) return false; // Windows drive letter
  if (/^\\\\/.test(p)) return false; // UNC
  if (p.startsWith("/") || p.startsWith("\\")) return false;
  if (p.startsWith("~")) return false; // POSIX home expansion escapes the project
  return true;
}

/** True when the (already-coerced) docsRoot represents the
 *  project root itself, i.e. the user typed "." (or "./" before
 *  the trailing-slash strip). Callers use this to decide whether
 *  to resolve a docs-rooted path as `${root}/<docsRoot>` (normal
 *  case) or as just `${root}` (project root case). The empty
 *  case is NOT considered project root — `loadDocsRoot` already
 *  falls back to DEFAULT_DOCS_ROOT for empty stored values, and
 *  we don't want a typo'd empty input to silently widen scope
 *  to the entire project. */
export function isProjectRootDocs(p: string): boolean {
  return p === "." || p === "./";
}

/** Coerce user-typed input: trim, backslash → forward slash,
 *  strip trailing slash. Returns the cleaned string; returns ""
 *  if the result is empty. */
export function coerceDocsRoot(p: string): string {
  return p.trim().replace(/\\/g, "/").replace(/\/+$/, "");
}

/** Load the docs root for `umo`. Returns `DEFAULT_DOCS_ROOT` if
 *  the key is missing, the umo is not in the map, the stored
 *  value is empty, or the stored value is invalid (defensive). */
export function loadDocsRoot(umo: string): string {
  const backend = defaultBackend();
  let raw: string | null = null;
  try {
    raw = backend.getItem(DOCS_ROOT_STORAGE_KEY);
  } catch {
    return DEFAULT_DOCS_ROOT;
  }
  if (!raw) return DEFAULT_DOCS_ROOT;
  let map: Record<string, string> | null = null;
  try {
    map = JSON.parse(raw);
  } catch {
    return DEFAULT_DOCS_ROOT;
  }
  if (!map || typeof map !== "object") return DEFAULT_DOCS_ROOT;
  const v = map[umo];
  if (typeof v !== "string" || !v || !isValidDocsRoot(v)) {
    return DEFAULT_DOCS_ROOT;
  }
  return v;
}

export type SaveDocsRootResult =
  | { ok: true }
  | { ok: false; reason: "invalid_path" | "storage_unavailable" };

/** Persist `path` for `umo`. Coerces first; rejects if the
 *  coerced value is invalid. Returns `{ ok: false, reason }`
 *  on either validation or storage failure so the caller can
 *  surface an error to the user. */
export function saveDocsRoot(
  umo: string,
  path: string,
): SaveDocsRootResult {
  const cleaned = coerceDocsRoot(path);
  if (!isValidDocsRoot(cleaned)) {
    return { ok: false, reason: "invalid_path" };
  }
  const backend = defaultBackend();
  let existing: Record<string, string> = {};
  try {
    const raw = backend.getItem(DOCS_ROOT_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        existing = parsed as Record<string, string>;
      }
    }
  } catch {
    // Treat parse failure as an empty map; we'll overwrite below.
    existing = {};
  }
  existing[umo] = cleaned;
  try {
    backend.setItem(DOCS_ROOT_STORAGE_KEY, JSON.stringify(existing));
    return { ok: true };
  } catch {
    return { ok: false, reason: "storage_unavailable" };
  }
}

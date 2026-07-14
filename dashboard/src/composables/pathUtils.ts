// Author: elecvoid243, 2026-07-13
//
// Pure-TS path-string helpers used by the document manager's
// breadcrumb / tree panel to translate between absolute paths
// (what the file-browser endpoint returns on every entry and on
// every breadcrumb segment) and project-relative paths (what
// DocumentManager stores in docsRoot / selectedDoc).
//
// No Vue imports — testable with node:test.
//
// The file-browser endpoint always returns absolute paths (see
// SpcodeFileBrowserEntry.path — "Absolute path of this entry
// (round-trip from backend)"). DocumentManager keeps docsRoot
// as a project-relative string and assembles the absolute path
// via `projectRoot + docsRoot + selectedDoc`. If we forward the
// absolute path straight through, DocumentManager would glue it
// back onto the prefix and produce "F:\repo\docs\F:\repo\docs\..."
// which the backend resolves as path_not_found. These helpers
// are the single source of truth for that translation.

/**
 * Strip the projectRoot prefix from an absolute path and return
 * the project-relative path.
 *
 * - Returns "" for the project root itself (so callers can use
 *   it as a docsRoot value without special-casing).
 * - Falls back to the basename when the prefix doesn't match
 *   (defensive — should not happen for paths the backend just
 *   returned for the same listing).
 * - Case-insensitive on the leading segment so Windows path
 *   casings (C:\foo vs c:\foo) both strip the same way.
 */
export function projectRelativePath(
  absPath: string,
  projectRoot: string | null | undefined,
): string {
  if (!projectRoot) return absPath;
  const normRoot = projectRoot.replace(/\\/g, "/").replace(/\/+$/, "");
  const normPath = absPath.replace(/\\/g, "/");
  if (normPath.toLowerCase() === normRoot.toLowerCase()) {
    return "";
  }
  if (normPath.toLowerCase().startsWith(normRoot.toLowerCase() + "/")) {
    return normPath.slice(normRoot.length + 1);
  }
  const m = normPath.match(/[^/]+$/);
  return m ? m[0] : absPath;
}

/**
 * Strip the (projectRoot + docsRoot) prefix from an absolute
 * path and return the docsRoot-relative path. The docsRoot
 * itself is itself a project-relative string (e.g. "docs" or
 * "docs/superpowers"), so we first join it onto projectRoot
 * and then strip the resulting absolute prefix.
 *
 * Returns the docsRoot itself (== "") for the docsRoot directory
 * itself, and the basename as a defensive fallback.
 */
export function docsRootRelativePath(
  absPath: string,
  projectRoot: string | null | undefined,
  docsRoot: string,
): string {
  if (!projectRoot) return absPath;
  const cleanDocsRoot = docsRoot.trim().replace(/\/+$/, "");
  const normRoot = projectRoot.replace(/\\/g, "/").replace(/\/+$/, "");
  const prefix = cleanDocsRoot
    ? `${normRoot}/${cleanDocsRoot.replace(/^[\\/]+/, "")}`
    : normRoot;
  const normPrefix = prefix.replace(/\/+$/, "").toLowerCase();
  const normPath = absPath.replace(/\\/g, "/");
  if (normPath.toLowerCase() === normPrefix) {
    return "";
  }
  if (normPath.toLowerCase().startsWith(normPrefix + "/")) {
    return normPath.slice(normPrefix.length + 1);
  }
  const m = normPath.match(/[^/]+$/);
  return m ? m[0] : absPath;
}

/**
 * Glue a docsRoot + selectedDoc pair (both already known to be
 * project-relative) into a single project-relative path string.
 *
 * This is the inverse of `docsRootRelativePath` and exists
 * because the spcode docs CRUD endpoints (`POST/PATCH/DELETE
 * /spcode/docs`) take a project-relative `path` — they resolve
 * it against the project root on the server side via
 * `_validate_repo_relative_file`. DocumentManager keeps
 * `selectedDoc` as docsRoot-relative internally (so the user-
 * visible path in `DocumentPathBar` and the breadcrumb stays
 * short), but every backend write needs the full project-
 * relative form.
 *
 * Edge cases:
 * - docsRoot "." → no prefix; the file lives directly under
 *   the project root.
 * - docsRoot "" → caller shouldn't be calling us (the path bar
 *   never stores ""; loadDocsRoot falls back to DEFAULT_DOCS_ROOT
 *   for empty stored values). We defensively return `doc` as-is
 *   so a malformed config still degrades to "file at project
 *   root" instead of throwing.
 * - doc that already starts with "/", "\\", or contains ".."
 *   is returned unchanged. Such paths would have failed
 *   `_validate_repo_relative_file` server-side anyway; we
 *   don't add new validation here — the existing isValidDocsRoot
 *   check on `docsRoot` plus the input validator in
 *   DocumentEditor (filename regex) is the trust boundary.
 */
export function projectRelativeFromDoc(docsRoot: string, doc: string): string {
  const cleanRoot = docsRoot.trim().replace(/\/+$/, "");
  const cleanDoc = doc.replace(/^[\\/]+/, "");
  if (!cleanRoot || cleanRoot === ".") return cleanDoc;
  return `${cleanRoot}/${cleanDoc}`;
}

/**
 * Glue projectRoot + docsRoot + selectedDoc into the absolute
 * path that `SpcodeFileBrowserEntry.path` returns (the file-
 * browser endpoint round-trips absolute paths on every entry
 * and breadcrumb segment). Inverse of `docsRootRelativePath`
 * for the same three inputs.
 *
 * Used by DocumentTreePanel to convert its docsRoot-relative
 * `selectedFile` back into the absolute form so it can be
 * compared against `entry.path` for the `is-selected` highlight
 * in `FileBrowserEntryList`. Without this, the highlight can
 * never match (entry.path is absolute, selectedFile is relative)
 * and the user's "currently-open file" cue is silently lost in
 * the document manager view.
 *
 * Edge cases mirror `projectRelativeFromDoc`:
 * - docsRoot "." → drop the prefix, just glue root + doc.
 * - empty projectRoot → return the doc unchanged (the parent
 *   will skip the highlight via its null check).
 * - leading "/" or "\" on the doc is stripped, but we do not
 *   re-validate `..` — the trust boundary is the editor's
 *   filename regex and isValidDocsRoot, same as the other
 *   helpers.
 */
export function absoluteFromSelectedDoc(
  projectRoot: string | null | undefined,
  docsRoot: string,
  selectedDoc: string,
): string {
  if (!projectRoot) return selectedDoc;
  // 2026-07-14: projectRoot comes from the backend (via
  // spcodeProjectStatus / spcodeWorktrees) which on Windows
  // uses backslashes and on POSIX uses forward slashes.
  // `SpcodeFileBrowserEntry.path` echoes the same format
  // because the backend round-trips the OS-native path. We
  // therefore join subsequent segments with whichever
  // separator the root uses — using a hard-coded "/" here
  // produced mixed-separator strings like
  // "F:\repo\docs/README.md" that never matched the
  // backslash-only `entry.path`, silently killing the
  // `is-selected` highlight in FileBrowserEntryList.
  // We also normalize any internal "/" inside docsRoot /
  // selectedDoc to the same separator so a user who types
  // "subdir/notes.md" in the new-file input still produces
  // a string that matches what the backend will return
  // (e.g. "F:\repo\docs\subdir\notes.md" on Windows).
  const sep = projectRoot.includes("\\") ? "\\" : "/";
  const cleanRoot = projectRoot.replace(/[\\/]+$/, "");
  const cleanDocsRoot = docsRoot
    .trim()
    .replace(/^[\\/]+/, "")
    .replace(/\//g, sep)
    .replace(/[\\/]+$/, "");
  const cleanDoc = selectedDoc
    .replace(/^[\\/]+/, "")
    .replace(/\//g, sep);
  const base =
    !cleanDocsRoot || cleanDocsRoot === "."
      ? cleanRoot
      : `${cleanRoot}${sep}${cleanDocsRoot}`;
  return cleanDoc ? `${base}${sep}${cleanDoc}` : base;
}

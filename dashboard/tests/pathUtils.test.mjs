// Author: elecvoid243, 2026-07-13
//
// Unit tests for the path-glue helpers added/changed alongside
// the document-manager edit/save/rename/delete fix. Run with:
//   node --test tests/pathUtils.test.mjs
//
// The spcode docs CRUD endpoints (POST/PATCH/DELETE /spcode/docs)
// take a project-relative `path` — the server resolves it against
// projectRoot via `_validate_repo_relative_file`. DocumentManager
// stores `selectedDoc` as docsRoot-relative internally (so the
// user-visible DocumentPathBar / breadcrumb stays short), so every
// write has to glue docsRoot onto the front. `projectRelativeFromDoc`
// is the inverse of `docsRootRelativePath` and owns that gluing.

import test from "node:test";
import assert from "node:assert/strict";

test("projectRelativeFromDoc: happy path glues docsRoot + filename", async () => {
  const { projectRelativeFromDoc } = await import(
    "../src/composables/pathUtils.ts"
  );
  assert.equal(projectRelativeFromDoc("docs", "README.md"), "docs/README.md");
  assert.equal(
    projectRelativeFromDoc("docs/superpowers", "specs/foo.md"),
    "docs/superpowers/specs/foo.md",
  );
});

test("projectRelativeFromDoc: docsRoot='.' (project root) drops the prefix", async () => {
  const { projectRelativeFromDoc } = await import(
    "../src/composables/pathUtils.ts"
  );
  // When the docs subtree IS the project root, the file is just
  // at the top level — no docsRoot prefix in the project-relative
  // path the backend wants.
  assert.equal(projectRelativeFromDoc(".", "README.md"), "README.md");
  assert.equal(projectRelativeFromDoc(".", "specs/foo.md"), "specs/foo.md");
});

test("projectRelativeFromDoc: trims trailing slash on docsRoot", async () => {
  const { projectRelativeFromDoc } = await import(
    "../src/composables/pathUtils.ts"
  );
  // User-typed values may carry a trailing slash from copy/paste;
  // the helper normalises it so we don't end up with a double slash.
  assert.equal(projectRelativeFromDoc("docs/", "README.md"), "docs/README.md");
  assert.equal(
    projectRelativeFromDoc("docs/superpowers///", "specs/foo.md"),
    "docs/superpowers/specs/foo.md",
  );
});

test("projectRelativeFromDoc: strips leading slash on doc", async () => {
  const { projectRelativeFromDoc } = await import(
    "../src/composables/pathUtils.ts"
  );
  // Defensive: if some upstream layer leaks an absolute-style
  // leading slash, we still produce a clean project-relative path.
  assert.equal(projectRelativeFromDoc("docs", "/README.md"), "docs/README.md");
});

test("projectRelativeFromDoc: empty docsRoot falls back to bare doc", async () => {
  const { projectRelativeFromDoc } = await import(
    "../src/composables/pathUtils.ts"
  );
  // This shouldn't normally happen — loadDocsRoot falls back to
  // DEFAULT_DOCS_ROOT for empty stored values — but the helper
  // degrades to "file at project root" rather than throwing.
  assert.equal(projectRelativeFromDoc("", "README.md"), "README.md");
});

test("projectRelativeFromDoc: is the inverse of docsRootRelativePath", async () => {
  const { projectRelativeFromDoc, docsRootRelativePath } = await import(
    "../src/composables/pathUtils.ts"
  );
  // Glue projectRoot + docsRoot + doc into an absolute-looking
  // path, then ask docsRootRelativePath to strip the prefix —
  // must round-trip back to the original docsRoot-relative doc.
  const projectRoot = "F:/repo";
  const docsRoot = "docs/superpowers";
  const doc = "specs/2026-07-11-document-manager-design.md";
  const abs = `${projectRoot}/${projectRelativeFromDoc(docsRoot, doc)}`;
  assert.equal(docsRootRelativePath(abs, projectRoot, docsRoot), doc);
});

test("absoluteFromSelectedDoc: glues projectRoot + docsRoot + selectedDoc", async () => {
  const { absoluteFromSelectedDoc } = await import(
    "../src/composables/pathUtils.ts"
  );
  assert.equal(
    absoluteFromSelectedDoc("F:/repo", "docs", "README.md"),
    "F:/repo/docs/README.md",
  );
  assert.equal(
    absoluteFromSelectedDoc("F:/repo", "docs/superpowers", "specs/foo.md"),
    "F:/repo/docs/superpowers/specs/foo.md",
  );
});

test("absoluteFromSelectedDoc: docsRoot='.' drops the docs prefix", async () => {
  const { absoluteFromSelectedDoc } = await import(
    "../src/composables/pathUtils.ts"
  );
  // docsRoot="." means the docs subtree IS the project root;
  // the absolute path is just projectRoot + selectedDoc.
  assert.equal(
    absoluteFromSelectedDoc("F:/repo", ".", "README.md"),
    "F:/repo/README.md",
  );
  assert.equal(
    absoluteFromSelectedDoc("F:/repo", ".", "specs/foo.md"),
    "F:/repo/specs/foo.md",
  );
});

test("absoluteFromSelectedDoc: normalises trailing slashes on projectRoot/docsRoot", async () => {
  const { absoluteFromSelectedDoc } = await import(
    "../src/composables/pathUtils.ts"
  );
  // projectRoot may carry a trailing separator (different callers
  // strip at different points); docsRoot may carry one from the
  // DocumentPathBar text input. We collapse them so we never emit
  // a double slash.
  assert.equal(
    absoluteFromSelectedDoc("F:/repo/", "docs/", "README.md"),
    "F:/repo/docs/README.md",
  );
  assert.equal(
    absoluteFromSelectedDoc("F:/repo///", "docs///", "README.md"),
    "F:/repo/docs/README.md",
  );
});

test("absoluteFromSelectedDoc: strips leading slash on selectedDoc", async () => {
  const { absoluteFromSelectedDoc } = await import(
    "../src/composables/pathUtils.ts"
  );
  // Defensive: if some upstream layer leaks an absolute-style
  // leading slash on selectedDoc, we still produce a clean
  // absolute path.
  assert.equal(
    absoluteFromSelectedDoc("F:/repo", "docs", "/README.md"),
    "F:/repo/docs/README.md",
  );
});

test("absoluteFromSelectedDoc: empty projectRoot returns the doc unchanged", async () => {
  const { absoluteFromSelectedDoc } = await import(
    "../src/composables/pathUtils.ts"
  );
  // projectRoot=null is the "no project loaded" signal; the
  // caller gates the highlight on a truthy projectRoot, so the
  // helper just returns the doc as-is. Same defensive shape as
  // the other helpers in this file.
  assert.equal(absoluteFromSelectedDoc(null, "docs", "README.md"), "README.md");
  assert.equal(absoluteFromSelectedDoc(undefined, "docs", "README.md"), "README.md");
});

test("absoluteFromSelectedDoc: is the inverse of docsRootRelativePath", async () => {
  const { absoluteFromSelectedDoc, docsRootRelativePath } = await import(
    "../src/composables/pathUtils.ts"
  );
  // Glue the three pieces into an absolute path, then ask
  // docsRootRelativePath to strip the prefix — must round-trip
  // back to the original selectedDoc. This is the property
  // DocumentTreePanel relies on to drive the `is-selected`
  // highlight in FileBrowserEntryList (entry.path === selectedPath).
  const projectRoot = "F:/repo";
  const docsRoot = "docs/superpowers";
  const selectedDoc = "specs/2026-07-11-document-manager-design.md";
  const abs = absoluteFromSelectedDoc(projectRoot, docsRoot, selectedDoc);
  assert.equal(docsRootRelativePath(abs, projectRoot, docsRoot), selectedDoc);
});

test("absoluteFromSelectedDoc: Windows backslash root uses \\ as the join separator", async () => {
  const { absoluteFromSelectedDoc } = await import(
    "../src/composables/pathUtils.ts"
  );
  // 2026-07-14 regression guard: the backend returns absolute
  // paths with the platform's native separator. On Windows
  // spcodeStatus.status.directory is e.g.
  // "F:\github\Astrbot\.worktrees\feature-x" (backslashes),
  // and the file-browser endpoint echoes the same format in
  // SpcodeFileBrowserEntry.path. The previous implementation
  // hard-coded "/" as the join separator, producing a
  // mixed-separator string ("F:\repo\docs/README.md") that
  // never matched the backslash-only entry.path — so the
  // `is-selected` highlight in FileBrowserEntryList silently
  // failed to fire. This test pins the all-backslash shape.
  assert.equal(
    absoluteFromSelectedDoc(
      "F:\\github\\Astrbot\\.worktrees\\document-manager-frontend",
      "docs",
      "README.md",
    ),
    "F:\\github\\Astrbot\\.worktrees\\document-manager-frontend\\docs\\README.md",
  );
  assert.equal(
    absoluteFromSelectedDoc("F:\\repo", "docs\\superpowers", "specs\\foo.md"),
    "F:\\repo\\docs\\superpowers\\specs\\foo.md",
  );
});

test("absoluteFromSelectedDoc: POSIX forward-slash root uses / as the join separator", async () => {
  const { absoluteFromSelectedDoc } = await import(
    "../src/composables/pathUtils.ts"
  );
  // Mirror of the Windows test: on POSIX, the backend returns
  // forward-slash paths, so the join must also use "/".
  assert.equal(
    absoluteFromSelectedDoc("/home/user/repo", "docs", "README.md"),
    "/home/user/repo/docs/README.md",
  );
  assert.equal(
    absoluteFromSelectedDoc("/home/user/repo", "docs/superpowers", "specs/foo.md"),
    "/home/user/repo/docs/superpowers/specs/foo.md",
  );
});

test("absoluteFromSelectedDoc: Windows root normalises user-typed / in selectedDoc to \\", async () => {
  const { absoluteFromSelectedDoc } = await import(
    "../src/composables/pathUtils.ts"
  );
  // The "new file" input in DocumentTreePanel allows "/" in the
  // filename (so users can pre-fill paths like "subdir/note.md").
  // After joining, that "/" must become the platform separator
  // so the constructed absolute path matches what the backend
  // will return once it creates the file. Otherwise the highlight
  // is missing for the new file until the user navigates away
  // and back.
  assert.equal(
    absoluteFromSelectedDoc(
      "F:\\repo",
      "docs",
      "subdir/notes.md",
    ),
    "F:\\repo\\docs\\subdir\\notes.md",
  );
  assert.equal(
    absoluteFromSelectedDoc(
      "F:\\repo",
      "docs/superpowers",
      "specs/foo.md",
    ),
    "F:\\repo\\docs\\superpowers\\specs\\foo.md",
  );
});

test("absoluteFromSelectedDoc: POSIX root normalises user-typed / in selectedDoc stays /", async () => {
  const { absoluteFromSelectedDoc } = await import(
    "../src/composables/pathUtils.ts"
  );
  // Symmetric guard for POSIX: the joiner is "/", so a user-typed
  // "/" in selectedDoc is already in the right shape — the
  // function should leave it alone.
  assert.equal(
    absoluteFromSelectedDoc("/home/user/repo", "docs", "subdir/notes.md"),
    "/home/user/repo/docs/subdir/notes.md",
  );
});

test("absoluteFromSelectedDoc: Windows root + docsRoot='.' uses \\ and drops the docs prefix", async () => {
  const { absoluteFromSelectedDoc } = await import(
    "../src/composables/pathUtils.ts"
  );
  // 2026-07-15 regression guard: DocumentManager's fileBrowser
  // pathRef delegates to this helper. With docsRoot="." the docs
  // subtree IS the project root, so the constructed absolute
  // path is `projectRoot + selectedDoc` (no docs segment) and
  // uses the platform separator. The previous hand-rolled glue
  // in DocumentManager had an early-return `if (!base ||
  // isProjectRootDocs(base)) return root` that ignored
  // selectedDoc — leaving pathRef stuck at projectRoot when the
  // user clicked a file, so the file-browser request was never
  // sent and the right-side preview stayed empty.
  assert.equal(
    absoluteFromSelectedDoc("F:\\github\\Astrbot", ".", "README.md"),
    "F:\\github\\Astrbot\\README.md",
  );
  assert.equal(
    absoluteFromSelectedDoc("F:\\repo", ".", "specs\\foo.md"),
    "F:\\repo\\specs\\foo.md",
  );
  // No file selected — pathRef must still be just the projectRoot
  // (so the listing shows the project root's children).
  assert.equal(
    absoluteFromSelectedDoc("F:\\github\\Astrbot", ".", ""),
    "F:\\github\\Astrbot",
  );
});

test("absoluteFromSelectedDoc: Windows round-trip matches backend entry.path shape", async () => {
  const { absoluteFromSelectedDoc, docsRootRelativePath } = await import(
    "../src/composables/pathUtils.ts"
  );
  // End-to-end property the highlight relies on: the string we
  // hand to FileBrowserEntryList (selectedAbsolutePath) is
  // byte-equal to what the backend returns as entry.path. On
  // Windows that means the absolute path must use "\" all the
  // way through, no mixed separators. We verify by constructing
  // the absolute path the way the backend would, then asserting
  // that our helper produces the same string for the same inputs.
  const projectRoot = "F:\\github\\Astrbot\\.worktrees\\document-manager-frontend";
  const docsRoot = "docs";
  const selectedDoc = "README.md";
  const ourAbsolute = absoluteFromSelectedDoc(projectRoot, docsRoot, selectedDoc);
  // Mimic what `SpcodeFileBrowserEntry.path` would look like
  // for the same file: os.path.join-equivalent on Windows uses "\\".
  const backendAbsolute = `${projectRoot}\\docs\\README.md`;
  assert.equal(ourAbsolute, backendAbsolute);
  // And the inverse direction still strips cleanly.
  assert.equal(docsRootRelativePath(ourAbsolute, projectRoot, docsRoot), selectedDoc);
});

// Author: elecvoid243, 2026-07-12
// Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §3.4

import assert from "node:assert/strict";
import test from "node:test";
import {
  isValidDocsRoot,
  loadDocsRoot,
  saveDocsRoot,
  DEFAULT_DOCS_ROOT,
  DOCS_ROOT_STORAGE_KEY,
} from "../src/composables/docsRootStorage.ts";

test("isValidDocsRoot: happy path", () => {
  assert.equal(isValidDocsRoot("docs"), true);
  assert.equal(isValidDocsRoot("specs/plans"), true);
  assert.equal(isValidDocsRoot("docs/2026"), true);
  assert.equal(isValidDocsRoot("a-b_c.d"), true);
});

test("isValidDocsRoot: rejects empty", () => {
  assert.equal(isValidDocsRoot(""), false);
});

test("isValidDocsRoot: rejects absolute + drive + UNC", () => {
  assert.equal(isValidDocsRoot("/etc/passwd"), false);
  assert.equal(isValidDocsRoot("\\foo"), false);
  assert.equal(isValidDocsRoot("C:/foo"), false);
  assert.equal(isValidDocsRoot("c:\\foo"), false);
  assert.equal(isValidDocsRoot("\\\\server\\share"), false);
});

test("isValidDocsRoot: rejects parent traversal", () => {
  assert.equal(isValidDocsRoot(".."), false);
  assert.equal(isValidDocsRoot("../foo"), false);
  assert.equal(isValidDocsRoot("a/../b"), false);
  assert.equal(isValidDocsRoot("a/.."), false);
});

test("isValidDocsRoot: rejects leading slash or backslash", () => {
  assert.equal(isValidDocsRoot("/docs"), false);
  assert.equal(isValidDocsRoot("\\docs"), false);
});

test("loadDocsRoot: returns default when key missing", async () => {
  globalThis.localStorage?.clear?.();
  // Use a private storage backend so we don't pollute the real one
  const { __setStorageBackend } = await import("../src/composables/docsRootStorage.ts");
  let store = {};
  __setStorageBackend({
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  });
  assert.equal(loadDocsRoot("umo-1"), "docs");
});

test("loadDocsRoot: returns default when umo not in map", async () => {
  const { __setStorageBackend } = await import("../src/composables/docsRootStorage.ts");
  let store = { [DOCS_ROOT_STORAGE_KEY]: JSON.stringify({ "other-umo": "specs" }) };
  __setStorageBackend({
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  });
  assert.equal(loadDocsRoot("umo-1"), "docs");
});

test("loadDocsRoot: returns persisted path for umo", async () => {
  const { __setStorageBackend } = await import("../src/composables/docsRootStorage.ts");
  let store = { [DOCS_ROOT_STORAGE_KEY]: JSON.stringify({ "umo-1": "specs/plans" }) };
  __setStorageBackend({
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  });
  assert.equal(loadDocsRoot("umo-1"), "specs/plans");
});

test("loadDocsRoot: handles localStorage exception", async () => {
  const { __setStorageBackend } = await import("../src/composables/docsRootStorage.ts");
  __setStorageBackend({ getItem: () => { throw new Error("quota"); }, setItem: () => {}, removeItem: () => {} });
  assert.equal(loadDocsRoot("umo-1"), "docs");
});

test("saveDocsRoot: writes to storage keyed by umo", async () => {
  const { __setStorageBackend } = await import("../src/composables/docsRootStorage.ts");
  let store = {};
  __setStorageBackend({
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  });
  const r = saveDocsRoot("umo-1", "specs");
  assert.equal(r.ok, true);
  assert.equal(JSON.parse(store[DOCS_ROOT_STORAGE_KEY])["umo-1"], "specs");
});

test("saveDocsRoot: rejects invalid path", async () => {
  const { __setStorageBackend } = await import("../src/composables/docsRootStorage.ts");
  let store = {};
  __setStorageBackend({
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  });
  const r = saveDocsRoot("umo-1", "../foo");
  assert.equal(r.ok, false);
  assert.equal(r.reason, "invalid_path");
  assert.equal(Object.keys(store).length, 0);
});

test("saveDocsRoot: returns ok=false on storage exception", async () => {
  const { __setStorageBackend } = await import("../src/composables/docsRootStorage.ts");
  __setStorageBackend({ getItem: () => null, setItem: () => { throw new Error("quota"); }, removeItem: () => {} });
  const r = saveDocsRoot("umo-1", "docs");
  assert.equal(r.ok, false);
  assert.equal(r.reason, "storage_unavailable");
});

test("DEFAULT_DOCS_ROOT is 'docs'", () => {
  assert.equal(DEFAULT_DOCS_ROOT, "docs");
});

test("isValidDocsRoot: accepts project-root sentinel and hidden subdirs", () => {
  // "." is a special sentinel meaning "the project root itself",
  // so listing the docs subtree becomes listing the project root.
  assert.equal(isValidDocsRoot("."), true);
  // "./docs" and a bare hidden-directory name are ordinary paths
  // that the user may legitimately choose (e.g. ".github").
  assert.equal(isValidDocsRoot("./docs"), true);
  assert.equal(isValidDocsRoot(".github"), true);
  assert.equal(isValidDocsRoot("docs/.github/ISSUE_TEMPLATE"), true);
});

test("isValidDocsRoot: still rejects POSIX home expansion", () => {
  // "~" would expand to the OS user's home directory, escaping
  // the project entirely. The leading-tilde rule stays.
  assert.equal(isValidDocsRoot("~"), false);
  assert.equal(isValidDocsRoot("~/projects"), false);
});

test("isProjectRootDocs: recognises '.' and './' (post-coerce)", async () => {
  const { isProjectRootDocs } = await import(
    "../src/composables/docsRootStorage.ts"
  );
  assert.equal(isProjectRootDocs("."), true);
  // coerceDocsRoot strips the trailing slash, so "./" is what
  // a freshly-typed "./" turns into before the caller can check.
  assert.equal(isProjectRootDocs("./"), true);
  // Anything else — including an empty string, plain "docs", or
  // a hidden-directory path — is NOT the project root.
  assert.equal(isProjectRootDocs(""), false);
  assert.equal(isProjectRootDocs("docs"), false);
  assert.equal(isProjectRootDocs(".github"), false);
});

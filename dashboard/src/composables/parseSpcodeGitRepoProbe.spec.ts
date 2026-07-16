// Author: elecvoid243, 2026-07-16
// Spec: docs/superpowers/specs/2026-07-16-git-repo-init-prompt-design.md §Architecture
//
// These tests exercise the parser with the **actual** wire shape
// produced by the spcode plugin's `GET /spcode/git-branches` endpoint
// after axios auto-unwraps the outer `data` key. See
// `tools/webapi/_helpers.py::_make_envelope` for the backend contract:
// the envelope never emits a `success` field; success is conveyed by
// `reason: null`. Endpoint-specific fields (`current`, `directory`)
// live at the top level of the response.

import { describe, expect, it } from "vitest";
import { parseSpcodeGitRepoProbe } from "./parseSpcodeGitRepoProbe";

describe("parseSpcodeGitRepoProbe", () => {
  it("returns 'ok' with the active branch when the probe succeeds", () => {
    const r = parseSpcodeGitRepoProbe({
      reason: null,
      stderr: "",
      elapsed_ms: 12,
      branches: [],
      current: "main",
      detached: false,
      total: 0,
    });
    expect(r).toEqual({ kind: "ok", defaultBranch: "main" });
  });

  it("falls back to 'default' if 'current' is missing (spec-original field name)", () => {
    const r = parseSpcodeGitRepoProbe({
      reason: null,
      stderr: "",
      elapsed_ms: 12,
      default: "main",
    });
    expect(r).toEqual({ kind: "ok", defaultBranch: "main" });
  });

  it("returns 'ok' with null defaultBranch when neither 'current' nor 'default' is present", () => {
    const r = parseSpcodeGitRepoProbe({
      reason: null,
      stderr: "",
      elapsed_ms: 12,
    });
    expect(r).toEqual({ kind: "ok", defaultBranch: null });
  });

  it("returns 'not_a_git_repo' with the directory on the dedicated reason", () => {
    const r = parseSpcodeGitRepoProbe({
      reason: "not_a_git_repo",
      stderr: "fatal: not a git repository",
      elapsed_ms: 5,
      directory: "D:/tmp/foo",
      umo: "session:test",
      worktree: "D:/tmp/foo",
    });
    expect(r).toEqual({ kind: "not_a_git_repo", directory: "D:/tmp/foo" });
  });

  it("returns 'not_a_git_repo' with empty directory if the field is missing", () => {
    const r = parseSpcodeGitRepoProbe({
      reason: "not_a_git_repo",
      stderr: "",
      elapsed_ms: 5,
    });
    expect(r).toEqual({ kind: "not_a_git_repo", directory: "" });
  });

  it("returns 'error' with the reason for any other failure reason", () => {
    const r = parseSpcodeGitRepoProbe({
      reason: "git_unavailable",
      stderr: "",
      elapsed_ms: 3,
    });
    expect(r).toEqual({ kind: "error", reason: "git_unavailable" });
  });

  it("returns 'error' with 'unknown' when the envelope is unparseable", () => {
    expect(parseSpcodeGitRepoProbe(null)).toEqual({
      kind: "error",
      reason: "unknown",
    });
    expect(parseSpcodeGitRepoProbe({})).toEqual({
      kind: "error",
      reason: "unknown",
    });
  });

  it("propagates stderr when present on an error reason", () => {
    const r = parseSpcodeGitRepoProbe({
      reason: "git_error",
      stderr: "fatal: bad config",
      elapsed_ms: 4,
    });
    expect(r).toEqual({
      kind: "error",
      reason: "git_error",
      stderr: "fatal: bad config",
    });
  });

  // Regression guard: a previous version of this parser required
  // `raw.success === true`, which the backend never emits. The full
  // `git-branches` success response (no `success` field, top-level
  // `current`/`branches`/etc.) must still resolve to `kind: "ok"`.
  it("parses a real git-branches success response (regression: no 'success' field)", () => {
    const realShape = {
      reason: null,
      stderr: "",
      elapsed_ms: 7,
      branches: [
        {
          name: "main",
          sha: "35b653b",
          upstream: "origin/main",
          upstream_track: "",
          current: true,
          remote: false,
        },
      ],
      total: 1,
      current: "main",
      detached: false,
    };
    expect(parseSpcodeGitRepoProbe(realShape)).toEqual({
      kind: "ok",
      defaultBranch: "main",
    });
  });
});

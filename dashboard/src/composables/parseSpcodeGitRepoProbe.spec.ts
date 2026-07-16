// Author: elecvoid243, 2026-07-16 (updated 2026-07-16 for git-repo-check)
//
// These tests exercise the parser with the **actual** wire shape
// produced by the spcode plugin's `GET /spcode/git-repo-check` endpoint
// after axios auto-unwraps the outer `data` key. See
// `tools/webapi/_helpers.py::_make_envelope` for the backend contract:
// the envelope never emits a `success` field; success is conveyed by
// `reason: null`. Endpoint-specific fields (`is_git_repo`,
// `git_available`, `directory`) live at the top level of the response.

import { describe, expect, it } from "vitest";
import { parseSpcodeGitRepoProbe } from "./parseSpcodeGitRepoProbe";

describe("parseSpcodeGitRepoProbe", () => {
  it("returns 'ok' with the directory when is_git_repo is true", () => {
    const r = parseSpcodeGitRepoProbe({
      is_git_repo: true,
      git_available: true,
      directory: "D:/tmp",
      reason: null,
      stderr: "",
      elapsed_ms: 12,
    });
    expect(r).toEqual({ kind: "ok", directory: "D:/tmp" });
  });

  it("returns 'not_a_git_repo' with the directory on the dedicated reason", () => {
    const r = parseSpcodeGitRepoProbe({
      is_git_repo: false,
      git_available: true,
      directory: "D:/tmp/foo",
      reason: "not_a_git_repo",
      stderr: "fatal: not a git repository",
      elapsed_ms: 5,
    });
    expect(r).toEqual({ kind: "not_a_git_repo", directory: "D:/tmp/foo" });
  });

  it("returns 'not_a_git_repo' with empty directory if the field is missing", () => {
    const r = parseSpcodeGitRepoProbe({
      is_git_repo: false,
      git_available: true,
      reason: "not_a_git_repo",
      stderr: "",
      elapsed_ms: 5,
    });
    expect(r).toEqual({ kind: "not_a_git_repo", directory: "" });
  });

  it("returns 'error' with the reason for git_unavailable", () => {
    const r = parseSpcodeGitRepoProbe({
      is_git_repo: null,
      git_available: false,
      directory: "D:/tmp",
      reason: "git_unavailable",
      stderr: "git not found",
      elapsed_ms: 3,
    });
    expect(r).toEqual({ kind: "error", reason: "git_unavailable", stderr: "git not found" });
  });

  it("returns 'error' with the reason for any other failure reason", () => {
    const r = parseSpcodeGitRepoProbe({
      is_git_repo: null,
      git_available: null,
      directory: "D:/tmp",
      reason: "git_error",
      stderr: "",
      elapsed_ms: 3,
    });
    expect(r).toEqual({ kind: "error", reason: "git_error" });
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
      is_git_repo: null,
      git_available: null,
      directory: "D:/tmp",
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
});

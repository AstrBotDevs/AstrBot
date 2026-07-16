// Author: elecvoid243, 2026-07-16
// Spec: docs/superpowers/specs/2026-07-16-git-repo-init-prompt-design.md §Architecture
import { describe, expect, it } from "vitest";
import { parseSpcodeGitRepoProbe } from "./parseSpcodeGitRepoProbe";

describe("parseSpcodeGitRepoProbe", () => {
  it("returns 'ok' with defaultBranch when the probe succeeds", () => {
    const r = parseSpcodeGitRepoProbe({
      success: true,
      reason: null,
      elapsed_ms: 12,
      data: { branches: [], default: "main", detached: false, total: 0 },
    });
    expect(r).toEqual({ kind: "ok", defaultBranch: "main" });
  });

  it("returns 'not_a_git_repo' with the directory on the dedicated reason", () => {
    const r = parseSpcodeGitRepoProbe({
      success: false,
      reason: "not_a_git_repo",
      elapsed_ms: 5,
      data: { directory: "D:/tmp/foo" },
    });
    expect(r).toEqual({ kind: "not_a_git_repo", directory: "D:/tmp/foo" });
  });

  it("returns 'error' with the reason for any other failure reason", () => {
    const r = parseSpcodeGitRepoProbe({
      success: false,
      reason: "git_unavailable",
      elapsed_ms: 3,
      data: {},
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
      success: false,
      reason: "git_error",
      elapsed_ms: 4,
      data: {},
      stderr: "fatal: bad config",
    });
    expect(r).toEqual({
      kind: "error",
      reason: "git_error",
      stderr: "fatal: bad config",
    });
  });
});

// Author: elecvoid243, 2026-07-16 (updated 2026-07-16 for git-repo-check)
//
// Tests exercise the composable against the **actual** wire shape
// produced by the spcode plugin:
//
//   HTTP body       = { status: "ok", data: <inner> }
//   `resp.data`     = { status: "ok", data: <inner> }     ← OpenAPI envelope
//   `resp.data.data` = <inner>                            ← parsed by parser
//
// <inner> is what `_make_envelope` produces: it never emits a `success`
// field; success is conveyed by `reason: null`, and endpoint-specific
// fields (`is_git_repo`, `git_available`, `directory`, etc.) live at the
// top level of the INNER payload. Mocks below wrap their fixtures in
// the outer envelope so the composable's `resp.data?.data` unwrap is
// exercised rather than bypassed.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { mount } from "@vue/test-utils";

// vi.mock factories are hoisted to the top of the file by Vitest, so any
// references to top-level `const`s in those factories would be TDZ errors.
// `vi.hoisted` runs the callback first and exposes the result synchronously
// to both the mock factories and the rest of the test file.
const { getMock, postMock, statusRef } = vi.hoisted(() => {
  const getMock = vi.fn();
  const postMock = vi.fn();
  const statusRef = {
    value: { umo: "session:test" as string | null, directory: "D:/tmp" as string | null },
  };
  return { getMock, postMock, statusRef };
});

vi.mock("@/api/v1", () => ({
  pluginExtensionApi: { get: getMock, post: postMock },
}));

vi.mock("./useSpcodeProjectStatus", () => ({
  useSpcodeProjectStatus: () => ({ status: statusRef }),
}));

import { useSpcodeGitRepoProbe } from "./useSpcodeGitRepoProbe";

function withSetup<T>(fn: () => T): { result: T; unmount: () => void } {
  let captured!: T;
  const Comp = defineComponent({
    setup() {
      captured = fn();
      return () => h("div");
    },
  });
  const wrapper = mount(Comp);
  return { result: captured, unmount: () => wrapper.unmount() };
}

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  localStorage.clear();
  statusRef.value = { umo: "session:test", directory: "D:/tmp" };
});

afterEach(() => {
  vi.useRealTimers();
});

// Real backend wire shape for `GET /spcode/git-repo-check` success
// (is a Git repo).
const GIT_REPO_CHECK_OK = {
  is_git_repo: true,
  git_available: true,
  directory: "D:/tmp",
  reason: null,
  stderr: "",
  elapsed_ms: 12.34,
};

// Real backend wire shape for `GET /spcode/git-repo-check` non-git.
const GIT_REPO_CHECK_NOT_A_REPO = {
  is_git_repo: false,
  git_available: true,
  directory: "D:/tmp/foo",
  reason: "not_a_git_repo",
  stderr: "fatal: not a git repository",
  elapsed_ms: 15.67,
};

// Real backend wire shape for `POST /spcode/git-init` success.
const GIT_INIT_OK = {
  reason: null,
  stderr: "",
  elapsed_ms: 10,
  initialized: true,
  path: "D:/tmp",
  initial_branch: "main",
  bare: false,
  force: false,
  git_dir: "D:/tmp/.git",
  umo: "session:test",
  worktree: "",
};

// Wrap a fixture in the OpenAPI envelope `{ status: "ok", data: <inner> }`
// exactly as the spcode plugin emits it on the wire.
function okEnvelope<T>(inner: T): { data: { status: "ok"; data: T } } {
  return { data: { status: "ok" as const, data: inner } };
}

describe("useSpcodeGitRepoProbe", () => {
  it("refresh() against a Git repo transitions state to 'ok'", async () => {
    getMock.mockResolvedValueOnce(okEnvelope(GIT_REPO_CHECK_OK));
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    await result.refresh();
    expect(result.state.value).toEqual({ kind: "ok", directory: "D:/tmp" });
    unmount();
  });

  it("refresh() sends path param (not umo) to git-repo-check", async () => {
    getMock.mockResolvedValueOnce(okEnvelope(GIT_REPO_CHECK_OK));
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    await result.refresh();
    expect(getMock).toHaveBeenCalledWith(
      "spcode/git-repo-check",
      expect.objectContaining({
        params: { path: "D:/tmp" },
      }),
    );
    unmount();
  });

  it("refresh() against a non-Git directory transitions state to 'not_a_git_repo'", async () => {
    getMock.mockResolvedValueOnce(okEnvelope(GIT_REPO_CHECK_NOT_A_REPO));
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    await result.refresh();
    expect(result.state.value).toEqual({
      kind: "not_a_git_repo",
      directory: "D:/tmp/foo",
    });
    unmount();
  });

  it("refresh() with no directory transitions state to 'idle'", async () => {
    statusRef.value = { umo: "session:test", directory: null };
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    await result.refresh();
    expect(result.state.value).toEqual({ kind: "idle" });
    expect(getMock).not.toHaveBeenCalled();
    unmount();
  });

  it("gitInit() success re-probes to 'ok'", async () => {
    postMock.mockResolvedValueOnce(okEnvelope(GIT_INIT_OK));
    getMock.mockResolvedValueOnce(okEnvelope(GIT_REPO_CHECK_OK));
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    const r = await result.gitInit({ path: "D:/tmp" });
    expect(r).toEqual({ ok: true, defaultBranch: "main" });
    expect(result.state.value).toEqual({ kind: "ok", directory: "D:/tmp" });
    unmount();
  });

  it("gitInit({ force: true }) forwards force in the request body (v2.17.1)", async () => {
    postMock.mockResolvedValueOnce(okEnvelope(GIT_INIT_OK));
    getMock.mockResolvedValueOnce(okEnvelope(GIT_REPO_CHECK_OK));
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    await result.gitInit({ path: "D:/tmp", force: true });
    expect(postMock).toHaveBeenCalledWith(
      "spcode/git-init",
      expect.objectContaining({ force: true }),
      expect.any(Object),
    );
    unmount();
  });

  it("gitInit() defaults force to false in the request body when omitted", async () => {
    postMock.mockResolvedValueOnce(okEnvelope(GIT_INIT_OK));
    getMock.mockResolvedValueOnce(okEnvelope(GIT_REPO_CHECK_OK));
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    await result.gitInit({ path: "D:/tmp" });
    expect(postMock).toHaveBeenCalledWith(
      "spcode/git-init",
      expect.objectContaining({ force: false }),
      expect.any(Object),
    );
    unmount();
  });

  it("gitInit() failure returns { ok: false, reason, stderr } and state stays 'not_a_git_repo'", async () => {
    postMock.mockResolvedValueOnce(
      okEnvelope({
        reason: "directory_not_empty",
        stderr: "fatal: directory not empty",
        elapsed_ms: 5,
        initialized: false,
        path: "D:/tmp",
      }),
    );
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    const r = await result.gitInit({ path: "D:/tmp" });
    expect(r).toEqual({
      ok: false,
      reason: "directory_not_empty",
      stderr: "fatal: directory not empty",
    });
    expect(result.state.value).toEqual({
      kind: "not_a_git_repo",
      directory: "D:/tmp",
    });
    unmount();
  });

  it("gitInit() is single-flight: a second call aborts the first", async () => {
    let resolveFirst!: (v: unknown) => void;
    postMock.mockImplementationOnce(
      () => new Promise((res) => { resolveFirst = res; }),
    );
    postMock.mockResolvedValueOnce(okEnvelope(GIT_INIT_OK));
    getMock.mockResolvedValueOnce(okEnvelope(GIT_REPO_CHECK_OK));
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    const first = result.gitInit({ path: "D:/tmp" });
    // Let the first call settle into the awaited postMock.
    await nextTick();
    const second = result.gitInit({ path: "D:/tmp" });
    resolveFirst({
      data: { reason: "aborted", stderr: "", elapsed_ms: 0, initialized: false, path: "D:/tmp" },
    });
    const firstR = await first;
    const secondR = await second;
    expect(firstR.ok).toBe(false);
    expect(secondR.ok).toBe(true);
    unmount();
  });
});

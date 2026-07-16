// Author: elecvoid243, 2026-07-16
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
// fields (`current`, `initial_branch`, etc.) live at the top level of
// the INNER payload. Mocks below wrap their fixtures in the outer
// envelope so the composable's `resp.data?.data` unwrap is exercised
// rather than bypassed.

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

// Real backend wire shape for `GET /spcode/git-branches` success:
// no `success` field, `current` (not `default`) at the top level.
const GIT_BRANCHES_OK = {
  reason: null,
  stderr: "",
  elapsed_ms: 1,
  branches: [],
  current: "main",
  detached: false,
  total: 0,
};

// Real backend wire shape for `GET /spcode/git-branches` not_a_git_repo.
const GIT_BRANCHES_NOT_A_REPO = {
  reason: "not_a_git_repo",
  stderr: "fatal: not a git repository",
  elapsed_ms: 5,
  directory: "D:/tmp/foo",
  umo: "session:test",
  worktree: "D:/tmp/foo",
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
  git_dir: "D:/tmp/.git",
  umo: "session:test",
  worktree: "",
};

// Wrap a fixture in the OpenAPI envelope `{ status: "ok", data: <inner> }`
// exactly as the spcode plugin emits it on the wire. Every 200-OK mock
// below must use this; the composable unwraps via `resp.data?.data` and
// would otherwise see the outer envelope and fail every parse.
function okEnvelope<T>(inner: T): { data: { status: "ok"; data: T } } {
  return { data: { status: "ok" as const, data: inner } };
}

describe("useSpcodeGitRepoProbe", () => {
  it("refresh() against a Git repo transitions state to 'ok'", async () => {
    getMock.mockResolvedValueOnce(okEnvelope(GIT_BRANCHES_OK));
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    await result.refresh();
    expect(result.state.value).toEqual({ kind: "ok", defaultBranch: "main" });
    unmount();
  });

  it("refresh() against a non-Git directory transitions state to 'not_a_git_repo'", async () => {
    getMock.mockResolvedValueOnce(okEnvelope(GIT_BRANCHES_NOT_A_REPO));
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    await result.refresh();
    expect(result.state.value).toEqual({
      kind: "not_a_git_repo",
      directory: "D:/tmp/foo",
    });
    unmount();
  });

  it("refresh() with cached ETag sends If-None-Match and restores cached state on 304", async () => {
    localStorage.setItem(
      "astrbot.spcode.gitRepoProbe.etag.session:test.",
      '"abc123"',
    );
    localStorage.setItem(
      "astrbot.spcode.gitRepoProbe.snapshot.session:test.",
      JSON.stringify({ defaultBranch: "main" }),
    );
    getMock.mockResolvedValueOnce({ status: 304, data: null });
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    await result.refresh();
    expect(getMock).toHaveBeenCalledWith(
      "spcode/git-branches",
      expect.objectContaining({
        params: { umo: "session:test" },
        // `validateStatus` must allow 304 so axios doesn't throw.
        validateStatus: expect.any(Function),
        headers: expect.objectContaining({ "If-None-Match": '"abc123"' }),
      }),
    );
    // 304 must be accepted by validateStatus, not surfaced as an error.
    expect(result.state.value).toEqual({ kind: "ok", defaultBranch: "main" });
    unmount();
  });

  it("gitInit() success invalidates the ETag and re-probes to 'ok'", async () => {
    localStorage.setItem(
      "astrbot.spcode.gitRepoProbe.etag.session:test.",
      '"stale"',
    );
    postMock.mockResolvedValueOnce(okEnvelope(GIT_INIT_OK));
    getMock.mockResolvedValueOnce(okEnvelope(GIT_BRANCHES_OK));
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    const r = await result.gitInit({ path: "D:/tmp" });
    expect(r).toEqual({ ok: true, defaultBranch: "main" });
    expect(localStorage.getItem("astrbot.spcode.gitRepoProbe.etag.session:test.")).toBeNull();
    expect(result.state.value).toEqual({ kind: "ok", defaultBranch: "main" });
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

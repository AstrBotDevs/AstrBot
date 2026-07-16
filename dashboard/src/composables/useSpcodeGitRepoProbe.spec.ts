// Author: elecvoid243, 2026-07-16
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

describe("useSpcodeGitRepoProbe", () => {
  it("refresh() against a Git repo transitions state to 'ok'", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        success: true,
        reason: null,
        elapsed_ms: 1,
        data: { branches: [], default: "main", detached: false, total: 0 },
      },
    });
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    await result.refresh();
    expect(result.state.value).toEqual({ kind: "ok", defaultBranch: "main" });
    unmount();
  });

  it("refresh() against a non-Git directory transitions state to 'not_a_git_repo'", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        success: false,
        reason: "not_a_git_repo",
        elapsed_ms: 1,
        data: { directory: "D:/tmp/foo" },
      },
    });
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
        headers: expect.objectContaining({ "If-None-Match": '"abc123"' }),
      }),
    );
    expect(result.state.value).toEqual({ kind: "ok", defaultBranch: "main" });
    unmount();
  });

  it("gitInit() success invalidates the ETag and re-probes to 'ok'", async () => {
    localStorage.setItem(
      "astrbot.spcode.gitRepoProbe.etag.session:test.",
      '"stale"',
    );
    postMock.mockResolvedValueOnce({
      data: {
        success: true,
        reason: null,
        elapsed_ms: 10,
        data: { initialized: true, directory: "D:/tmp", initial_branch: "main", bare: false, hint: "ok" },
      },
    });
    getMock.mockResolvedValueOnce({
      data: {
        success: true,
        reason: null,
        elapsed_ms: 1,
        data: { branches: [], default: "main", detached: false, total: 0 },
      },
    });
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    const r = await result.gitInit({ path: "D:/tmp" });
    expect(r).toEqual({ ok: true, defaultBranch: "main" });
    expect(localStorage.getItem("astrbot.spcode.gitRepoProbe.etag.session:test.")).toBeNull();
    expect(result.state.value).toEqual({ kind: "ok", defaultBranch: "main" });
    unmount();
  });

  it("gitInit() failure returns { ok: false, reason, stderr } and state stays 'not_a_git_repo'", async () => {
    postMock.mockResolvedValueOnce({
      data: {
        success: false,
        reason: "directory_not_empty",
        elapsed_ms: 5,
        data: {},
        stderr: "fatal: directory not empty",
      },
    });
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
    postMock.mockResolvedValueOnce({
      data: { success: true, reason: null, elapsed_ms: 1, data: { initialized: true, directory: "D:/tmp", initial_branch: "main", bare: false, hint: "" } },
    });
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    const first = result.gitInit({ path: "D:/tmp" });
    // Let the first call settle into the awaited postMock.
    await nextTick();
    const second = result.gitInit({ path: "D:/tmp" });
    resolveFirst({ data: { success: false, reason: "aborted", elapsed_ms: 0, data: {} } });
    const firstR = await first;
    const secondR = await second;
    expect(firstR.ok).toBe(false);
    expect(secondR.ok).toBe(true);
    unmount();
  });
});

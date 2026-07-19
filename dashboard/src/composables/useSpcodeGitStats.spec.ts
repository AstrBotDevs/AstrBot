// Author: elecvoid243
// Date: 2026-07-18
// Spec: docs/superpowers/specs/2026-07-18-git-stats-heatmap-range-design.md
//
// Tests the composable's `refresh({ since?, until? })` plumbing:
// since/until are forwarded to axios params, the ETag bucket is
// partitioned by (umo|worktree|since|until), and an in-flight refresh
// is aborted when a second one is issued before the first settles.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";

const { getMock, statusRef } = vi.hoisted(() => {
  const getMock = vi.fn();
  const statusRef = {
    value: { umo: "umo-1" as string | null, directory: "D:/repo" as string | null },
  };
  return { getMock, statusRef };
});

vi.mock("@/api/v1", () => ({
  pluginExtensionApi: { get: getMock, post: vi.fn() },
}));

vi.mock("./useSpcodeProjectStatus", () => ({
  useSpcodeProjectStatus: () => ({ status: statusRef }),
}));

import { useSpcodeGitStats } from "./useSpcodeGitStats";

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

function makeAxiosResponse(status: number, data: unknown, etag?: string) {
  return {
    status,
    data,
    headers: etag ? { etag } : {},
  };
}

function okEnvelope(days: unknown[] = []) {
  return {
    status: "ok",
    data: {
      success: true,
      reason: null,
      loaded: true,
      stderr: "",
      elapsed_ms: 10,
      umo: "umo-1",
      worktree: null,
      directory: "D:/repo",
      ref: "HEAD",
      resolved_sha: "deadbeef",
      days,
      hot_files: [],
      totals: { commits: 0, additions: 0, deletions: 0, files_changed: 0 },
      range: { first: null, last: null },
      truncated: false,
      max_commits: 5000,
    },
  };
}

beforeEach(() => {
  getMock.mockReset();
  statusRef.value = { umo: "umo-1", directory: "D:/repo" };
});

describe("useSpcodeGitStats refresh params and ETag", () => {
  it("refresh() without since/until defaults top_files to 10", async () => {
    getMock.mockResolvedValueOnce(makeAxiosResponse(200, okEnvelope()));
    const { result, unmount } = withSetup(() => useSpcodeGitStats());
    await result.refresh();
    const call = getMock.mock.calls[0];
    expect(call[1]?.params).toEqual({ umo: "umo-1", top_files: 10 });
    unmount();
  });

  it("refresh({since,until}) forwards them in params", async () => {
    getMock.mockResolvedValueOnce(makeAxiosResponse(200, okEnvelope()));
    const { result, unmount } = withSetup(() => useSpcodeGitStats());
    await result.refresh({ since: "2025-01-01", until: "2025-12-31" });
    const call = getMock.mock.calls[0];
    expect(call[1]?.params).toEqual({
      umo: "umo-1",
      since: "2025-01-01",
      until: "2025-12-31",
      top_files: 10,
    });
    unmount();
  });

  it("refresh({topFiles}) forwards top_files in params with the supplied value", async () => {
    getMock.mockResolvedValueOnce(makeAxiosResponse(200, okEnvelope()));
    const { result, unmount } = withSetup(() => useSpcodeGitStats());
    await result.refresh({ topFiles: 20 });
    const call = getMock.mock.calls[0];
    expect(call[1]?.params).toEqual({ umo: "umo-1", top_files: 20 });
    unmount();
  });

  it("refresh({topFiles}) clamps out-of-range values to backend limits (1..50)", async () => {
    getMock.mockResolvedValue(makeAxiosResponse(200, okEnvelope()));
    const { result, unmount } = withSetup(() => useSpcodeGitStats());
    await result.refresh({ topFiles: 0 });
    await result.refresh({ topFiles: 9999 });
    expect(getMock.mock.calls[0][1]?.params.top_files).toBe(1);
    expect(getMock.mock.calls[1][1]?.params.top_files).toBe(50);
    unmount();
  });

  it("different topFiles values produce a new ETag bucket", async () => {
    getMock
      .mockResolvedValueOnce(makeAxiosResponse(200, okEnvelope(), "etag-A"))
      .mockResolvedValueOnce(makeAxiosResponse(200, okEnvelope(), "etag-B"));
    const { result, unmount } = withSetup(() => useSpcodeGitStats());
    await result.refresh({ topFiles: 10 });
    await result.refresh({ topFiles: 20 });
    const secondCall = getMock.mock.calls[1];
    expect(secondCall[1]?.headers).toEqual({});
    unmount();
  });

  it("different since/until produces a new ETag bucket (no If-None-Match on second range)", async () => {
    getMock
      .mockResolvedValueOnce(makeAxiosResponse(200, okEnvelope(), "etag-A"))
      .mockResolvedValueOnce(makeAxiosResponse(200, okEnvelope(), "etag-B"));
    const { result, unmount } = withSetup(() => useSpcodeGitStats());
    await result.refresh({ since: "2025-01-01", until: "2025-06-30" });
    await result.refresh({ since: "2025-07-01", until: "2025-12-31" });
    const secondCall = getMock.mock.calls[1];
    expect(secondCall[1]?.headers).toEqual({});
    unmount();
  });

  it("same since/until on second call sends If-None-Match and replays cache on 304", async () => {
    getMock
      .mockResolvedValueOnce(makeAxiosResponse(200, okEnvelope(), "etag-X"))
      .mockResolvedValueOnce(makeAxiosResponse(304, null));
    const { result, unmount } = withSetup(() => useSpcodeGitStats());
    await result.refresh({ since: "2025-01-01", until: "2025-12-31" });
    const firstSnapshot = (result.state.value as { kind: "ok"; snapshot: unknown })
      .snapshot;

    await result.refresh({ since: "2025-01-01", until: "2025-12-31" });
    expect(result.state.value.kind).toBe("ok");
    if (result.state.value.kind === "ok") {
      expect(result.state.value.snapshot).toBe(firstSnapshot);
      expect(result.state.value.notModified).toBe(true);
    }
    const secondCall = getMock.mock.calls[1];
    expect(secondCall[1]?.headers).toEqual({ "If-None-Match": "etag-X" });
    unmount();
  });

  it("second refresh aborts the first when called while first is pending", async () => {
    let resolveFirst!: (v: unknown) => void;
    const first = new Promise((r) => {
      resolveFirst = r;
    });
    getMock
      .mockReturnValueOnce(first as never)
      .mockResolvedValueOnce(makeAxiosResponse(200, okEnvelope(), "etag-Z"));

    const { result, unmount } = withSetup(() => useSpcodeGitStats());
    const p1 = result.refresh({ since: "2025-01-01", until: "2025-06-30" });
    const p2 = result.refresh({ since: "2025-07-01", until: "2025-12-31" });

    const firstCallSig = getMock.mock.calls[0][1]?.signal;
    resolveFirst(makeAxiosResponse(200, okEnvelope()));
    await p1;
    await p2;

    expect(firstCallSig?.aborted).toBe(true);
    unmount();
  });
});

# GitDiffSidebar Git Repo Init Prompt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface a "this is not a Git project" prompt inside `GitDiffSidebar` whenever the loaded directory has no `.git/`, and let the user initialize one with a single click via `POST /spcode/git-init`. No branch-management UI.

**Architecture:** One new parser + one new composable (with ETag-cached probe via `GET /spcode/git-branches`) + one new component + minimal edits to `GitDiffSidebar.vue` (5 template changes, 2 handlers, 1 composable wiring block) + 15 i18n keys × 3 locales. Probe endpoint reused from the v2.17.0 spec; no backend changes.

**Tech Stack:** Vue 3 (`<script setup>`) + TypeScript + Vitest + `@vue/test-utils` + `pluginExtensionApi` (`@/api/v1`) + localStorage-backed ETag cache. Existing pattern is cloned from `useSpcodeWorktrees.ts` / `useSpcodeGitStatus.ts`.

**Related spec:** `docs/superpowers/specs/2026-07-16-git-repo-init-prompt-design.md`

## Global Constraints

- Cross-platform: must work on Windows / macOS / Linux; paths may use either `\` or `/` — never assume.
- Python 3.10+ compatibility; Node 18+ for the dashboard.
- Use English for all comments and logs. Use Chinese only in user-facing i18n strings.
- All new Vue components must follow the existing `GitDiffSidebar.vue` style: `<script setup lang="ts">`, scoped CSS, `useModuleI18n("features/chat")` for translations.
- All new composables must follow the single-instance-per-component lifecycle (own `AbortController` + `isMounted` guard + `dispose()`).
- Run `pnpm lint` (or `pnpm exec eslint .`) and `pnpm exec vitest run` after the final task; both must pass.
- All commits use conventional commit messages (`docs:`, `feat:`, `test:`, `chore:`).
- No new npm dependencies.
- All new TypeScript files use Google-style JSDoc on exported functions.

## File Layout (final state)

```
dashboard/src/composables/
  parseSpcodeGitRepoProbe.ts                 [NEW, ~50 lines]
  parseSpcodeGitRepoProbe.spec.ts            [NEW, ~60 lines]
  useSpcodeGitRepoProbe.ts                   [NEW, ~180 lines]
  useSpcodeGitRepoProbe.spec.ts              [NEW, ~140 lines]

dashboard/src/components/chat/
  GitDiffSidebar.vue                         [MODIFY, + ~60 lines, -0]
  message_list_comps/
    GitRepoInitPrompt.vue                    [NEW, ~100 lines]
    GitRepoInitPrompt.spec.ts                [NEW, ~80 lines]

dashboard/src/i18n/locales/
  en-US/features/chat.json                   [MODIFY, +15 keys]
  zh-CN/features/chat.json                   [MODIFY, +15 keys]
  ru-RU/features/chat.json                   [MODIFY, +15 keys]
```

Total: 4 new files, 1 new spec, 2 modified source files, 3 modified i18n files.

---

### Task 1: Parse probe response (`parseSpcodeGitRepoProbe.ts` + spec)

**Files:**
- Create: `dashboard/src/composables/parseSpcodeGitRepoProbe.ts`
- Create: `dashboard/src/composables/parseSpcodeGitRepoProbe.spec.ts`

**Interfaces:**
- Consumes: `unknown` (raw HTTP response data)
- Produces: `GitRepoProbeParseResult` discriminated union: `{ kind: 'ok'; defaultBranch: string | null }` | `{ kind: 'not_a_git_repo'; directory: string }` | `{ kind: 'error'; reason: string; stderr?: string }`

- [ ] **Step 1: Write the failing spec**

Create `dashboard/src/composables/parseSpcodeGitRepoProbe.spec.ts`:

```ts
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
```

- [ ] **Step 2: Run the spec to verify it fails**

Run from `dashboard/`:

```bash
pnpm exec vitest run src/composables/parseSpcodeGitRepoProbe.spec.ts
```

Expected: FAIL with `Failed to resolve import "./parseSpcodeGitRepoProbe" from ... Does the file exist?`

- [ ] **Step 3: Implement the parser**

Create `dashboard/src/composables/parseSpcodeGitRepoProbe.ts`:

```ts
// Author: elecvoid243, 2026-07-16
// Spec: docs/superpowers/specs/2026-07-16-git-repo-init-prompt-design.md §Architecture
//
// Parses the `GET /spcode/git-branches` response into a 3-state result
// relevant to the init-prompt feature. Only three things matter:
//   1. success + reason null → "is a Git repo" + the default branch name
//   2. reason === "not_a_git_repo" → show the init prompt
//   3. anything else → an error chip
// The full branch list is intentionally NOT extracted here; that will
// be owned by a future branch-management composable.

export type GitRepoProbeParseResult =
  | { kind: "ok"; defaultBranch: string | null }
  | { kind: "not_a_git_repo"; directory: string }
  | { kind: "error"; reason: string; stderr?: string };

/** Parse the `git-branches` envelope into the 3-state init-prompt result. */
export function parseSpcodeGitRepoProbe(raw: unknown): GitRepoProbeParseResult {
  if (!isObject(raw)) return { kind: "error", reason: "unknown" };
  const reason = typeof raw.reason === "string" ? raw.reason : null;
  const success = raw.success === true;
  const data = isObject(raw.data) ? raw.data : null;
  const stderr = typeof raw.stderr === "string" ? raw.stderr : undefined;

  if (success && reason === null) {
    const defaultBranch =
      data && typeof data.default === "string" ? data.default : null;
    return { kind: "ok", defaultBranch };
  }
  if (reason === "not_a_git_repo") {
    const directory =
      data && typeof data.directory === "string" ? data.directory : "";
    return { kind: "not_a_git_repo", directory };
  }
  return {
    kind: "error",
    reason: reason ?? "unknown",
    ...(stderr !== undefined ? { stderr } : {}),
  };
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}
```

- [ ] **Step 4: Run the spec to verify it passes**

```bash
pnpm exec vitest run src/composables/parseSpcodeGitRepoProbe.spec.ts
```

Expected: 5 passed, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/composables/parseSpcodeGitRepoProbe.ts dashboard/src/composables/parseSpcodeGitRepoProbe.spec.ts
git commit -m "feat(dashboard): parse git-repo-probe response"
```

---

### Task 2: Probe composable (`useSpcodeGitRepoProbe.ts` + spec)

**Files:**
- Create: `dashboard/src/composables/useSpcodeGitRepoProbe.ts`
- Create: `dashboard/src/composables/useSpcodeGitRepoProbe.spec.ts`

**Interfaces:**
- Consumes: `useSpcodeProjectStatus()` (read `umo`), `pluginExtensionApi` for `GET spcode/git-branches` and `POST spcode/git-init`
- Produces: `UseSpcodeGitRepoProbe` with `state: Ref<GitRepoProbeState>`, `refresh()`, `startPolling(intervalMs?)`, `stopPolling()`, `gitInit(params)`, `dispose()`. `state` discriminated union: `{ kind: 'idle' } | { kind: 'loading' } | { kind: 'ok'; defaultBranch: string | null } | { kind: 'not_a_git_repo'; directory: string } | { kind: 'error'; reason: string; stderr?: string }`.

- [ ] **Step 1: Write the failing spec**

Create `dashboard/src/composables/useSpcodeGitRepoProbe.spec.ts`:

```ts
// Author: elecvoid243, 2026-07-16
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { mount } from "@vue/test-utils";

// Mocks must be declared before the import of the SUT.
const getMock = vi.fn();
const postMock = vi.fn();
vi.mock("@/api/v1", () => ({
  pluginExtensionApi: { get: getMock, post: postMock },
}));

const statusRef = { value: { umo: "session:test" as string | null, directory: "D:/tmp" as string | null } };
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

  it("gitInit() failure returns { ok: false, reason, stderr } and state returns to 'not_a_git_repo'", async () => {
    postMock.mockResolvedValueOnce({
      data: {
        success: false,
        reason: "directory_not_empty",
        elapsed_ms: 5,
        data: {},
        stderr: "fatal: directory not empty",
      },
    });
    getMock.mockResolvedValueOnce({
      data: {
        success: false,
        reason: "not_a_git_repo",
        elapsed_ms: 1,
        data: { directory: "D:/tmp" },
      },
    });
    const { result, unmount } = withSetup(() => useSpcodeGitRepoProbe());
    const r = await result.gitInit({ path: "D:/tmp" });
    expect(r).toEqual({
      ok: false,
      reason: "directory_not_empty",
      stderr: "fatal: directory not empty",
    });
    expect(result.state.value).toMatchObject({ kind: "not_a_git_repo" });
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
```

- [ ] **Step 2: Run the spec to verify it fails**

```bash
pnpm exec vitest run src/composables/useSpcodeGitRepoProbe.spec.ts
```

Expected: FAIL with `Failed to resolve import "./useSpcodeGitRepoProbe"`.

- [ ] **Step 3: Implement the composable**

Create `dashboard/src/composables/useSpcodeGitRepoProbe.ts`:

```ts
// Author: elecvoid243, 2026-07-16
// Spec: docs/superpowers/specs/2026-07-16-git-repo-init-prompt-design.md §State Machine
//
// Single-purpose composable that owns the "is the loaded directory a Git
// repo?" question. State is intentionally minimal — branch lists, files,
// and the rest are owned by other composables. This one only knows about
// `ok` / `not_a_git_repo` / `error` and the `defaultBranch` name.

import { ref, watch, type Ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { parseSpcodeGitRepoProbe, type GitRepoProbeParseResult } from "./parseSpcodeGitRepoProbe";

export type GitRepoProbeState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; defaultBranch: string | null }
  | { kind: "not_a_git_repo"; directory: string }
  | { kind: "error"; reason: string; stderr?: string };

export interface GitInitParams {
  path: string;
}

export type GitInitResult =
  | { ok: true; defaultBranch: string }
  | { ok: false; reason: string; stderr?: string };

export interface UseSpcodeGitRepoProbe {
  state: Ref<GitRepoProbeState>;
  refresh: () => Promise<void>;
  startPolling: (intervalMs?: number) => void;
  stopPolling: () => void;
  gitInit: (params: GitInitParams) => Promise<GitInitResult>;
  dispose: () => void;
}

const DEFAULT_POLL_MS = 30_000;
const ETAG_KEY_PREFIX = "astrbot.spcode.gitRepoProbe.etag";
const SNAPSHOT_KEY_PREFIX = "astrbot.spcode.gitRepoProbe.snapshot";

/** Composable for the "is this a Git repo?" probe + init mutation. */
export function useSpcodeGitRepoProbe(): UseSpcodeGitRepoProbe {
  const state = ref<GitRepoProbeState>({ kind: "idle" });
  const spcodeStatus = useSpcodeProjectStatus();
  let abortController: AbortController | null = null;
  let initAbort: AbortController | null = null;
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let lastEtag: string | null = null;
  let isMounted = true;

  function cacheKey(umo: string, worktree: string | null | undefined): string {
    return `${umo}.${worktree ?? ""}`;
  }

  function readCachedEtag(key: string): string | null {
    try {
      return localStorage.getItem(`${ETAG_KEY_PREFIX}.${key}`);
    } catch {
      return null;
    }
  }
  function writeCachedEtag(key: string, etag: string): void {
    try {
      localStorage.setItem(`${ETAG_KEY_PREFIX}.${key}`, etag);
    } catch {
      /* no-op */
    }
  }
  function clearCachedEtag(key: string): void {
    try {
      localStorage.removeItem(`${ETAG_KEY_PREFIX}.${key}`);
      localStorage.removeItem(`${SNAPSHOT_KEY_PREFIX}.${key}`);
    } catch {
      /* no-op */
    }
  }
  function readCachedSnapshot<T>(key: string): T | null {
    try {
      const raw = localStorage.getItem(`${SNAPSHOT_KEY_PREFIX}.${key}`);
      return raw ? (JSON.parse(raw) as T) : null;
    } catch {
      return null;
    }
  }
  function writeCachedSnapshot(key: string, value: unknown): void {
    try {
      localStorage.setItem(`${SNAPSHOT_KEY_PREFIX}.${key}`, JSON.stringify(value));
    } catch {
      /* no-op */
    }
  }

  async function refresh(): Promise<void> {
    if (!isMounted) return;
    const umo = spcodeStatus.status.value.umo;
    if (!umo) {
      state.value = { kind: "error", reason: "no_project_loaded" };
      return;
    }
    const key = cacheKey(umo, null);
    const cachedEtag = readCachedEtag(key);
    lastEtag = cachedEtag;

    abortController?.abort();
    abortController = new AbortController();
    state.value = { kind: "loading" };
    try {
      const resp = await pluginExtensionApi.get<unknown>("spcode/git-branches", {
        params: { umo },
        signal: abortController.signal,
        ...(cachedEtag ? { headers: { "If-None-Match": cachedEtag } } : {}),
      });
      if (!isMounted) return;

      // 304 path: server confirmed the cached ETag is still valid.
      const httpStatus = (resp as { status?: number }).status;
      if (httpStatus === 304) {
        const cached = readCachedSnapshot<{ defaultBranch: string | null }>(key);
        state.value = {
          kind: "ok",
          defaultBranch: cached?.defaultBranch ?? null,
        };
        return;
      }

      const newEtag = (resp.headers?.get?.("etag") ?? null) as string | null;
      if (newEtag) {
        lastEtag = newEtag;
        writeCachedEtag(key, newEtag);
      }
      const parsed: GitRepoProbeParseResult = parseSpcodeGitRepoProbe(
        (resp as { data?: unknown }).data,
      );
      applyParsed(parsed, key);
    } catch (err) {
      if (!isMounted) return;
      if ((err as { name?: string })?.name === "CanceledError") return;
      state.value = {
        kind: "error",
        reason: classifyNetworkError(err),
      };
    }
  }

  function applyParsed(parsed: GitRepoProbeParseResult, cacheKey_: string): void {
    if (parsed.kind === "ok") {
      writeCachedSnapshot(cacheKey_, { defaultBranch: parsed.defaultBranch });
      state.value = { kind: "ok", defaultBranch: parsed.defaultBranch };
    } else if (parsed.kind === "not_a_git_repo") {
      clearCachedEtag(cacheKey_);
      state.value = { kind: "not_a_git_repo", directory: parsed.directory };
    } else {
      state.value = {
        kind: "error",
        reason: parsed.reason,
        ...(parsed.stderr !== undefined ? { stderr: parsed.stderr } : {}),
      };
    }
  }

  function startPolling(intervalMs: number = DEFAULT_POLL_MS): void {
    if (pollTimer) return;
    pollTimer = setInterval(() => {
      void refresh();
    }, intervalMs);
  }
  function stopPolling(): void {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function gitInit(params: GitInitParams): Promise<GitInitResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    const umo = spcodeStatus.status.value.umo;
    if (!umo) return { ok: false, reason: "no_project_loaded" };

    initAbort?.abort();
    initAbort = new AbortController();
    state.value = { kind: "loading" };
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/git-init",
        { path: params.path, initial_branch: "main", bare: false },
        { signal: initAbort.signal, params: { umo } },
      );
      if (!isMounted || initAbort.signal.aborted) {
        return { ok: false, reason: "aborted" };
      }
      const envelope = (resp as { data?: unknown }).data;
      const result = parseGitInitResponse(envelope);
      if (!result.ok) return result;
      // Success: invalidate cache and re-probe.
      clearCachedEtag(cacheKey(umo, null));
      await refresh();
      return result;
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      return { ok: false, reason: classifyNetworkError(err) };
    }
  }

  function dispose(): void {
    isMounted = false;
    stopPolling();
    abortController?.abort();
    abortController = null;
    initAbort?.abort();
    initAbort = null;
  }

  // Re-probe when umo or directory changes.
  watch(
    () => [spcodeStatus.status.value.umo, spcodeStatus.status.value.directory] as const,
    ([newUmo, newDir], [oldUmo, oldDir]) => {
      if (!isMounted) return;
      if (newUmo && (newUmo !== oldUmo || newDir !== oldDir)) {
        void refresh();
      }
    },
  );

  return { state, refresh, startPolling, stopPolling, gitInit, dispose };
}

function parseGitInitResponse(raw: unknown): GitInitResult {
  if (typeof raw !== "object" || raw === null) {
    return { ok: false, reason: "unknown" };
  }
  const env = raw as Record<string, unknown>;
  if (env.success === true) {
    const data = env.data as Record<string, unknown> | undefined;
    const initialBranch =
      data && typeof data.initial_branch === "string" ? data.initial_branch : "main";
    return { ok: true, defaultBranch: initialBranch };
  }
  const reason = typeof env.reason === "string" ? env.reason : "unknown";
  const stderr = typeof env.stderr === "string" ? env.stderr : undefined;
  return {
    ok: false,
    reason,
    ...(stderr !== undefined ? { stderr } : {}),
  };
}

function classifyNetworkError(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const anyErr = err as { code?: string; message?: string };
    if (anyErr.code === "ERR_NETWORK" || /network/i.test(anyErr.message ?? "")) {
      return "network";
    }
  }
  return "unknown";
}
```

- [ ] **Step 4: Run the spec to verify it passes**

```bash
pnpm exec vitest run src/composables/useSpcodeGitRepoProbe.spec.ts
```

Expected: 6 passed, 0 failed. If the 6th test (single-flight) is flaky because of microtask timing, add `await new Promise((r) => setTimeout(r, 0))` between the two `gitInit` calls and re-run.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/composables/useSpcodeGitRepoProbe.ts dashboard/src/composables/useSpcodeGitRepoProbe.spec.ts
git commit -m "feat(dashboard): add git-repo-probe composable with ETag cache"
```

---

### Task 3: Prompt component (`GitRepoInitPrompt.vue` + spec)

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/GitRepoInitPrompt.vue`
- Create: `dashboard/src/components/chat/message_list_comps/GitRepoInitPrompt.spec.ts`

**Interfaces:**
- Consumes: `directory: string`, `isSubmitting: boolean`, `lastError: { reason: string; stderr?: string } | null`
- Emits: `confirm()`, `cancel()`

- [ ] **Step 1: Write the failing spec**

Create `dashboard/src/components/chat/message_list_comps/GitRepoInitPrompt.spec.ts`:

```ts
// Author: elecvoid243, 2026-07-16
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import GitRepoInitPrompt from "./GitRepoInitPrompt.vue";

const i18nMock = {
  spcodeProjectLoad: {
    diffSidebar: {
      repoInit: {
        title: "Not a Git project",
        body: "Folder {directory} has no .git/",
        hint: "Will create default branch {defaultBranch}.",
        confirm: "Initialize",
        cancel: "Cancel",
        submitting: "Initializing…",
        errors: {
          directory_not_empty: "Directory not empty",
          path_not_directory: "Not a directory",
          already_a_git_repo: "Already a Git repo",
          worktree_blacklisted: "Path protected",
          path_unsafe: "Path not allowed",
          init_failed: "Init failed: {stderr}",
          unknown: "Unknown error",
        },
      },
    },
  },
};

function mountPrompt(props: Record<string, unknown> = {}) {
  return mount(GitRepoInitPrompt, {
    props: { directory: "D:/tmp", isSubmitting: false, lastError: null, ...props },
    global: { mocks: { $t: (k: string) => k, tm: () => i18nMock } },
  });
}

describe("GitRepoInitPrompt", () => {
  it("renders the directory path in the body", () => {
    const w = mountPrompt({ directory: "D:/tmp/foo" });
    expect(w.text()).toContain("D:/tmp/foo");
  });

  it("emits 'confirm' when the primary button is clicked", async () => {
    const w = mountPrompt();
    await w.find('[data-testid="repo-init-confirm"]').trigger("click");
    expect(w.emitted("confirm")).toBeTruthy();
  });

  it("emits 'cancel' when the secondary button is clicked", async () => {
    const w = mountPrompt();
    await w.find('[data-testid="repo-init-cancel"]').trigger("click");
    expect(w.emitted("cancel")).toBeTruthy();
  });

  it("disables both buttons while isSubmitting is true", () => {
    const w = mountPrompt({ isSubmitting: true });
    const btns = w.findAll("button");
    expect(btns.every((b) => b.attributes("disabled") !== undefined)).toBe(true);
  });

  it("renders lastError.stderr when provided", () => {
    const w = mountPrompt({
      lastError: { reason: "directory_not_empty", stderr: "fatal: not empty" },
    });
    expect(w.text()).toContain("fatal: not empty");
  });

  it("does not render the lastError block when lastError is null", () => {
    const w = mountPrompt({ lastError: null });
    expect(w.find('[data-testid="repo-init-error"]').exists()).toBe(false);
  });
});
```

- [ ] **Step 2: Run the spec to verify it fails**

```bash
pnpm exec vitest run src/components/chat/message_list_comps/GitRepoInitPrompt.spec.ts
```

Expected: FAIL with `Failed to resolve import "./GitRepoInitPrompt.vue"`.

- [ ] **Step 3: Implement the component**

Create `dashboard/src/components/chat/message_list_comps/GitRepoInitPrompt.vue`:

```vue
<!-- Author: elecvoid243, 2026-07-16
     Spec: docs/superpowers/specs/2026-07-16-git-repo-init-prompt-design.md §Component -->
<script setup lang="ts">
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  directory: string;
  isSubmitting: boolean;
  lastError: { reason: string; stderr?: string } | null;
}>();
const emit = defineEmits<{
  (e: "confirm"): void;
  (e: "cancel"): void;
}>();
const { tm } = useModuleI18n("features/chat");

const errorKey = (reason: string): string =>
  `spcodeProjectLoad.diffSidebar.repoInit.errors.${reason}`;

function onKeyDown(e: KeyboardEvent): void {
  if (e.key === "Escape" && !props.isSubmitting) emit("cancel");
}
</script>

<template>
  <div
    class="git-repo-init-prompt"
    role="dialog"
    aria-modal="false"
    :aria-label="tm('spcodeProjectLoad.diffSidebar.repoInit.title')"
    tabindex="-1"
    @keydown="onKeyDown"
  >
    <v-icon size="32" class="git-repo-init-prompt-icon"
      >mdi-information-outline</v-icon
    >
    <h2 class="git-repo-init-prompt-title">
      {{ tm("spcodeProjectLoad.diffSidebar.repoInit.title") }}
    </h2>
    <p class="git-repo-init-prompt-body">
      {{
        tm("spcodeProjectLoad.diffSidebar.repoInit.body", {
          directory: props.directory,
        })
      }}
    </p>
    <p class="git-repo-init-prompt-hint">
      {{
        tm("spcodeProjectLoad.diffSidebar.repoInit.hint", {
          defaultBranch: "main",
        })
      }}
    </p>

    <div
      v-if="props.lastError"
      data-testid="repo-init-error"
      class="git-repo-init-prompt-error"
    >
      <v-icon size="16" color="error">mdi-alert-circle-outline</v-icon>
      <span>
        {{
          props.lastError.stderr
            ? tm(errorKey("init_failed"), { stderr: props.lastError.stderr })
            : tm(errorKey(props.lastError.reason))
        }}
      </span>
    </div>

    <div class="git-repo-init-prompt-actions">
      <button
        type="button"
        data-testid="repo-init-cancel"
        class="git-repo-init-prompt-btn git-repo-init-prompt-btn--secondary"
        :disabled="props.isSubmitting"
        @click="emit('cancel')"
      >
        {{ tm("spcodeProjectLoad.diffSidebar.repoInit.cancel") }}
      </button>
      <button
        type="button"
        data-testid="repo-init-confirm"
        class="git-repo-init-prompt-btn git-repo-init-prompt-btn--primary"
        :disabled="props.isSubmitting"
        @click="emit('confirm')"
      >
        <v-progress-circular
          v-if="props.isSubmitting"
          indeterminate
          :size="14"
          :width="2"
          class="git-repo-init-prompt-spinner"
        />
        {{
          props.isSubmitting
            ? tm("spcodeProjectLoad.diffSidebar.repoInit.submitting")
            : tm("spcodeProjectLoad.diffSidebar.repoInit.confirm")
        }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.git-repo-init-prompt {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 32px 24px;
  text-align: center;
}
.git-repo-init-prompt-icon {
  color: rgb(var(--v-theme-primary));
}
.git-repo-init-prompt-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}
.git-repo-init-prompt-body,
.git-repo-init-prompt-hint {
  font-size: 13px;
  line-height: 1.5;
  margin: 0;
  color: rgba(var(--v-theme-on-surface), 0.8);
  max-width: 480px;
}
.git-repo-init-prompt-error {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px 12px;
  background: rgba(var(--v-theme-error), 0.08);
  border-radius: 4px;
  font-size: 12px;
  text-align: left;
  max-width: 480px;
  width: 100%;
  box-sizing: border-box;
}
.git-repo-init-prompt-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.git-repo-init-prompt-btn {
  padding: 6px 16px;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid transparent;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.git-repo-init-prompt-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.git-repo-init-prompt-btn--secondary {
  background: transparent;
  border-color: rgba(var(--v-theme-on-surface), 0.24);
  color: rgba(var(--v-theme-on-surface), 0.8);
}
.git-repo-init-prompt-btn--primary {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}
</style>
```

- [ ] **Step 4: Run the spec to verify it passes**

```bash
pnpm exec vitest run src/components/chat/message_list_comps/GitRepoInitPrompt.spec.ts
```

Expected: 6 passed, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/chat/message_list_comps/GitRepoInitPrompt.vue dashboard/src/components/chat/message_list_comps/GitRepoInitPrompt.spec.ts
git commit -m "feat(dashboard): add GitRepoInitPrompt component"
```

---

### Task 4: Wire the composable into `GitDiffSidebar.vue` (script section)

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue`
  - Add import for `GitRepoInitPrompt` and `useSpcodeGitRepoProbe` (find the existing import block near the top of `<script setup>`).
  - Add the composable instance + 6 derived refs (`isGitRepo`, `isRepoInitSubmitting`, `repoInitLastError`, `repoPromptDismissed`, `showRepoInitPrompt`, `showNotGitRepoChip`) immediately after `useSpcodeWorktrees()` (line ~296).
  - Add `void gitRepoProbe.refresh()` + `gitRepoProbe.startPolling(30_000)` in `onMounted` (after the existing `worktreesComposable.refresh()` call, ~line 991).
  - Add `gitRepoProbe.stopPolling()` + `gitRepoProbe.dispose()` in `onBeforeUnmount` (after the existing `worktreesComposable.stopPolling()` call, ~line 1041).
  - Add `repoPromptDismissed.value = false;` to the existing `onWorktreeChange()` handler (so the prompt re-presents when the user switches to a different non-Git worktree).
  - Add 2 new handlers (`onRepoInitConfirm`, `onRepoInitCancel`) near `onInitSubmit` (~line 1480).

**Interfaces:**
- Consumes: `useSpcodeProjectStatus().status.umo` and `projectRoot` (already defined as `computed` ~line 315).
- Produces: `gitRepoProbe.state`, `isGitRepo`, `showRepoInitPrompt`, `showNotGitRepoChip`, `isRepoInitSubmitting`, `repoInitLastError`, `repoPromptDismissed`, `onRepoInitConfirm`, `onRepoInitCancel`. The composable instance is referenced later by Task 5 (template) and is **not** used by any other task in this plan.

- [ ] **Step 1: Add the new imports**

In `<script setup>`, after the existing `import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";` line, add:

```ts
import GitRepoInitPrompt from "@/components/chat/message_list_comps/GitRepoInitPrompt.vue";
import { useSpcodeGitRepoProbe } from "@/composables/useSpcodeGitRepoProbe";
```

- [ ] **Step 2: Add the composable instance + derived refs**

Immediately after the existing `const worktreesComposable = useSpcodeWorktrees();` line, add:

```ts
const gitRepoProbe = useSpcodeGitRepoProbe();
const isGitRepo = computed(
  () => gitRepoProbe.state.value.kind === "ok",
);
const isRepoInitSubmitting = ref(false);
const repoInitLastError = ref<{ reason: string; stderr?: string } | null>(null);
const repoPromptDismissed = ref(false);
const showRepoInitPrompt = computed(
  () =>
    isProjectLoaded.value
    && gitRepoProbe.state.value.kind === "not_a_git_repo"
    && !repoPromptDismissed.value,
);
const showNotGitRepoChip = computed(
  () =>
    isProjectLoaded.value
    && gitRepoProbe.state.value.kind === "not_a_git_repo"
    && repoPromptDismissed.value,
);
```

Note: `isProjectLoaded` is already defined later in the file (around line 928) as `computed(() => spcodeStatus.status.value.umo !== null)`. Because `<script setup>` is executed top-to-bottom, the read of `isProjectLoaded.value` inside a `computed` is lazy — it does **not** throw even if the source is declared further down. If the project's eslint complains (it shouldn't — existing code already relies on this for `worktreesComposable.refresh()` at line 988), add a `void isProjectLoaded;` placeholder above the new block.

- [ ] **Step 3: Add polling lifecycle calls**

In `onMounted` (find the existing `void worktreesComposable.refresh();` line ~line 991), add immediately after it:

```ts
void gitRepoProbe.refresh();
gitRepoProbe.startPolling(30_000);
```

In `onBeforeUnmount` (find the existing `worktreesComposable.stopPolling();` line ~line 1041), add immediately after it:

```ts
gitRepoProbe.stopPolling();
gitRepoProbe.dispose();
```

- [ ] **Step 4: Reset the dismissed flag on worktree switches**

Find the existing `onWorktreeChange` function. It contains a body that ends with `selectedWorktree.value = path;`. Add the line `repoPromptDismissed.value = false;` as the first line of the function body (so it runs before the rest of the switch logic).

If the exact existing signature is:

```ts
function onWorktreeChange(path: string | null): void {
  selectedWorktree.value = path;
  // ... other existing logic ...
}
```

then add `repoPromptDismissed.value = false;` immediately after the opening `{`, before the existing assignment.

- [ ] **Step 5: Add the 2 handlers**

Find the existing `async function onConfirmCommit(...)` (around line 2228) — this is a stable anchor because the function is unique. Add the following block immediately before it:

```ts
async function onRepoInitConfirm(): Promise<void> {
  if (!projectRoot.value) return;
  repoInitLastError.value = null;
  isRepoInitSubmitting.value = true;
  const result = await gitRepoProbe.gitInit({ path: projectRoot.value });
  isRepoInitSubmitting.value = false;
  if (result.ok) {
    repoPromptDismissed.value = false;
    return;
  }
  repoInitLastError.value = {
    reason: result.reason,
    ...(result.stderr !== undefined ? { stderr: result.stderr } : {}),
  };
}

function onRepoInitCancel(): void {
  repoPromptDismissed.value = true;
  repoInitLastError.value = null;
}
```

- [ ] **Step 6: Verify the file still type-checks**

```bash
cd dashboard && pnpm exec vue-tsc --noEmit
```

Expected: exit code 0. (If `vue-tsc` is not available in this project, fall back to `pnpm exec tsc --noEmit -p .`. The dashboard ships its own `tsconfig.json`.)

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/components/chat/GitDiffSidebar.vue
git commit -m "feat(dashboard): wire git-repo-probe composable into GitDiffSidebar"
```

---

### Task 5: Add the template slots (`GitDiffSidebar.vue` template section)

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue` (template only, ~30 lines added, ~0 removed)

- [ ] **Step 1: Gate the view-mode tab strip**

Find the existing `<div class="git-diff-sidebar-view-tabs" ...>` block in the template (around line 2624). Add `v-if` as the first attribute:

Before:

```vue
<div
  class="git-diff-sidebar-view-tabs"
  role="tablist"
  aria-label="Switch view"
>
```

After:

```vue
<div
  v-if="isGitRepo || showNotGitRepoChip"
  class="git-diff-sidebar-view-tabs"
  role="tablist"
  aria-label="Switch view"
>
```

- [ ] **Step 2: Gate the worktree tab strip**

Find the existing `<div v-if="hasMultipleWorktrees" class="git-diff-sidebar-tabs" ...>` block (around line 2688). Replace the `v-if` value with the conjunctive form:

Before:

```vue
<div
  v-if="hasMultipleWorktrees"
  class="git-diff-sidebar-tabs"
```

After:

```vue
<div
  v-if="hasMultipleWorktrees && (isGitRepo || showNotGitRepoChip)"
  class="git-diff-sidebar-tabs"
```

- [ ] **Step 3: Insert the prompt + chip slot above the body**

Find the existing `<div class="git-diff-sidebar-body">` (around line 2825). Insert the following block **immediately above** it:

```vue
<GitRepoInitPrompt
  v-if="showRepoInitPrompt"
  :directory="
    gitRepoProbe.state.value.kind === 'not_a_git_repo'
      ? gitRepoProbe.state.value.directory
      : ''
  "
  :is-submitting="isRepoInitSubmitting"
  :last-error="repoInitLastError"
  @confirm="onRepoInitConfirm"
  @cancel="onRepoInitCancel"
/>
<div
  v-else-if="showNotGitRepoChip"
  class="git-diff-sidebar-repo-chip"
  role="status"
>
  <v-icon size="14">mdi-information-outline</v-icon>
  <span>{{ tm("spcodeProjectLoad.diffSidebar.repoInit.dismissedChip") }}</span>
  <button
    type="button"
    class="git-diff-sidebar-repo-chip-action"
    @click="repoPromptDismissed = false"
  >
    {{ tm("spcodeProjectLoad.diffSidebar.repoInit.reopenPrompt") }}
  </button>
</div>
```

- [ ] **Step 4: Add the chip's scoped CSS**

Find the closing `</style>` of the existing `<style scoped>` block (near the end of the file, just before `</script>` closes — actually the `<style>` is at the end of the file). Insert the following CSS immediately before the closing `</style>` tag:

```css
.git-diff-sidebar-repo-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  font-size: 12px;
}
.git-diff-sidebar-repo-chip-action {
  margin-left: auto;
  background: none;
  border: none;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
  font: inherit;
  padding: 0;
}
```

- [ ] **Step 5: Verify the file type-checks and renders**

```bash
cd dashboard && pnpm exec vue-tsc --noEmit
```

Expected: exit code 0.

Then start the dashboard dev server (separate terminal) and open the GitDiffSidebar against a known non-Git directory (e.g. a freshly created empty folder). Expected: the prompt is visible, centered, with two buttons. Clicking the cancel button hides the prompt and shows the chip.

```bash
cd dashboard && pnpm dev
```

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/components/chat/GitDiffSidebar.vue
git commit -m "feat(dashboard): add repo-init prompt slot in GitDiffSidebar"
```

---

### Task 6: Add i18n keys (3 locales)

**Files:**
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json`
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json`

- [ ] **Step 1: Add keys to en-US**

Open `dashboard/src/i18n/locales/en-US/features/chat.json`. Find the closing `}` of the `"spcodeProjectLoad"` object (search for the top-level key). Add the following object as a sibling of any existing `spcodeProjectLoad.diffSidebar` keys, **inside** `spcodeProjectLoad.diffSidebar`:

```jsonc
"repoInit": {
  "title": "This is not a Git project",
  "body": "The current folder {directory} does not contain a .git/ directory.",
  "hint": "Initializing a new Git repository here will create the default branch ({defaultBranch}).",
  "confirm": "Initialize Git repository",
  "cancel": "Cancel",
  "dismissedChip": "This is not a Git project. Some features are unavailable.",
  "reopenPrompt": "Initialize now",
  "submitting": "Initializing…",
  "errors": {
    "directory_not_empty": "The directory is not empty. Please clean it up first, or use a bare repository.",
    "path_not_directory": "The path does not exist or is not a directory.",
    "already_a_git_repo": "This directory is already a Git repository.",
    "worktree_blacklisted": "The path is protected by configuration.",
    "path_unsafe": "The path is not allowed.",
    "init_failed": "Git initialization failed: {stderr}",
    "unknown": "An unexpected error occurred."
  }
}
```

(Use the file's existing indentation style — typically 2 spaces. The above is shown at 2-space depth for clarity.)

- [ ] **Step 2: Add keys to zh-CN**

Same path, `dashboard/src/i18n/locales/zh-CN/features/chat.json`, same location. Use these values:

```jsonc
"repoInit": {
  "title": "这不是一个 Git 项目",
  "body": "当前文件夹 {directory} 下未检测到 .git/ 目录。",
  "hint": "在此初始化新的 Git 仓库后将自动创建默认分支({defaultBranch})。",
  "confirm": "初始化 Git 仓库",
  "cancel": "取消",
  "dismissedChip": "当前目录不是 Git 项目,部分功能受限。",
  "reopenPrompt": "立即初始化",
  "submitting": "正在初始化…",
  "errors": {
    "directory_not_empty": "目录非空,请先清理或使用 bare 仓库。",
    "path_not_directory": "路径不存在或不是目录。",
    "already_a_git_repo": "该目录已是 Git 仓库,无需初始化。",
    "worktree_blacklisted": "该路径受配置保护。",
    "path_unsafe": "路径不合法。",
    "init_failed": "初始化失败:{stderr}",
    "unknown": "发生意外错误。"
  }
}
```

- [ ] **Step 3: Add keys to ru-RU**

Same path, `dashboard/src/i18n/locales/ru-RU/features/chat.json`, same location. Use these values:

```jsonc
"repoInit": {
  "title": "Это не Git-проект",
  "body": "В текущей папке {directory} не найден каталог .git/.",
  "hint": "Инициализация нового Git-репозитория создаст ветку по умолчанию ({defaultBranch}).",
  "confirm": "Инициализировать Git-репозиторий",
  "cancel": "Отмена",
  "dismissedChip": "Это не Git-проект, часть функций недоступна.",
  "reopenPrompt": "Инициализировать сейчас",
  "submitting": "Инициализация…",
  "errors": {
    "directory_not_empty": "Каталог не пуст. Сначала очистите его или используйте bare-репозиторий.",
    "path_not_directory": "Путь не существует или не является каталогом.",
    "already_a_git_repo": "Этот каталог уже является Git-репозиторием.",
    "worktree_blacklisted": "Путь защищён конфигурацией.",
    "path_unsafe": "Путь недопустим.",
    "init_failed": "Ошибка инициализации: {stderr}",
    "unknown": "Произошла непредвиденная ошибка."
  }
}
```

- [ ] **Step 4: Validate the i18n files**

```bash
cd dashboard && pnpm exec node -e "const v=require('./src/i18n/validator.ts'); console.log(v.default ? 'validator loaded' : 'no default export')" 2>/dev/null || cd dashboard && pnpm exec vitest run src/i18n 2>&1 | tail -20
```

If the project ships a dedicated script (check `package.json` for `i18n:validate` or similar), use it instead:

```bash
cd dashboard && pnpm run i18n:validate
```

Expected: all three locales pass with the same key count and no missing translations.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/i18n/locales/en-US/features/chat.json dashboard/src/i18n/locales/zh-CN/features/chat.json dashboard/src/i18n/locales/ru-RU/features/chat.json
git commit -m "feat(dashboard): add i18n keys for git repo init prompt"
```

---

### Task 7: End-to-end verification and cleanup

**Files:**
- Possibly modify: any file that lint flags.

- [ ] **Step 1: Run the linter and formatter**

```bash
cd dashboard && pnpm exec eslint . --ext .ts,.vue
cd dashboard && pnpm exec prettier --check .
```

Expected: zero errors. If `prettier` is not configured, skip it; the project uses `prettier` only if `prettier` is in `package.json`. If `prettier --check` reports files that would be reformatted, run `pnpm exec prettier --write .` on those files and amend the previous commit (`git add -u && git commit --amend --no-edit`).

- [ ] **Step 2: Run the full test suite**

```bash
cd dashboard && pnpm exec vitest run
```

Expected: all tests pass, including the 3 new spec files (parser, composable, prompt component).

- [ ] **Step 3: Manual smoke test — happy path**

1. Start the dashboard: `cd dashboard && pnpm dev` (in a separate terminal).
2. Create a fresh empty directory on disk: `mkdir -p /tmp/spcode-smoke-non-git` (or `C:\Users\<you>\AppData\Local\Temp\spcode-smoke-non-git` on Windows).
3. In the chat, load that directory via `/project load`.
4. Open `GitDiffSidebar`. Expected: the prompt is shown, centered, with the directory path. The view-mode tab strip and the worktree tab strip are hidden.
5. Click **Initialize Git repository**. Expected: the prompt disappears within ~500 ms, the view-mode tabs reappear, and `⎇ main ✔` is shown in the path strip.
6. Verify on disk: `/tmp/spcode-smoke-non-git/.git/` exists.

- [ ] **Step 4: Manual smoke test — cancel path**

1. Re-load the same directory and open `GitDiffSidebar` (or load a different non-Git directory).
2. Click **Cancel**. Expected: the prompt disappears, the dismissed chip is shown at the top, the view-mode tabs reappear, but the **Diff / History** tabs are visibly disabled (clicking them surfaces the standard `not_a_git_repo` error toast).
3. Click the **Initialize now** action on the chip. Expected: the prompt reappears.

- [ ] **Step 5: Manual smoke test — git project regression**

1. Load a known Git repository (e.g. the AstrBot repo itself).
2. Open `GitDiffSidebar`. Expected: the prompt is **not** shown, the path strip shows the branch name, and all four views (Files / Diff / History / Docs) work as before. No behavioral change for Git repositories.

- [ ] **Step 6: Final commit (only if cleanup was needed)**

If Steps 1–2 produced no changes, skip this step. Otherwise:

```bash
git add -u
git commit -m "chore(dashboard): address lint and format findings from git-repo-init-prompt"
```

---

## Self-Review Checklist (run after writing the plan, before execution)

- [x] **Spec coverage:** Every section of the spec is implemented by at least one task. The spec's 5 sections (Architecture / State Machine / Probe Endpoint / gitInit Mutation / GitDiffSidebar Integration / Component / i18n / Error Handling / Testing / Non-Goals) map to Tasks 1–6. Non-Goals are excluded by design.
- [x] **Placeholder scan:** No "TBD", "TODO", "implement later", "appropriate", "similar to", or unfilled code blocks. Every code block is complete and runnable.
- [x] **Type consistency:** `GitRepoProbeState` is defined in Task 2 and consumed verbatim by Tasks 4 and 5. `GitRepoProbeParseResult` is defined in Task 1 and consumed in Task 2. `useSpcodeGitRepoProbe()` is the single source of the composable contract; Tasks 4 and 5 use only its public interface (`state`, `refresh`, `startPolling`, `stopPolling`, `gitInit`, `dispose`).
- [x] **i18n key count:** 15 keys × 3 locales = 45 insertions across 3 files. Matches the spec.
- [x] **File paths:** All paths use the existing project layout (`dashboard/src/composables/...`, `dashboard/src/components/chat/...`, `dashboard/src/i18n/locales/...`).
- [x] **No backend changes:** Confirmed — every task operates on frontend files only.

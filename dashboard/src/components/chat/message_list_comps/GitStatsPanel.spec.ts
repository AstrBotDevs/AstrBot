// Author: elecvoid243, 2026-07-19
// 2026-07-19: regression tests for the hot-files exclude-pattern
// filter. The original impl anchored every pattern with `^...$`,
// which made a user typing `*.json` only match files in the repo
// root AND a bare filename like `tool_loop_agent_runner.py` only
// match the literal root entry. The fix uses .gitignore-style
// semantics: a pattern without `/` matches the basename at any
// depth, a pattern with `/` matches the full path.
import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";

// Self-contained i18n mock (returns the key + k=v params).
const tmMock = vi.fn(
  (key: string, params?: Record<string, string | number>) => {
    if (!params) return key;
    return Object.entries(params).reduce(
      (acc, [k, v]) => `${acc} ${k}=${String(v)}`,
      key,
    );
  },
);
vi.mock("@/i18n/composables", () => ({
  useModuleI18n: () => ({ tm: tmMock, getRaw: vi.fn() }),
}));

import GitStatsPanel from "./GitStatsPanel.vue";
import type { GitStatsFetchState } from "@/composables/useSpcodeGitStats";
import type { GitStatsData } from "@/composables/parseSpcodeGitStats";

// Vuetify stubs: the panel uses v-menu, v-btn, v-icon directly in the
// template. We render them as cheap <button>/<i> elements so the DOM
// stays inspectable via vue-test-utils without pulling in the Vuetify
// runtime. v-menu's default slot is rendered so the exclude input
// and the hot-files rows end up in the tree (v-menu normally
// portals).
const vuetifyStubs = {
  "v-icon": { template: "<i />" },
  "v-btn": {
    props: ["disabled", "loading"],
    emits: ["click"],
    template:
      '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
  },
  "v-card": { template: "<div><slot /></div>" },
  "v-menu": {
    props: ["modelValue"],
    emits: ["update:modelValue"],
    template: '<div class="v-menu-stub"><slot /></div>',
  },
};

const EXCLUDE_STORAGE_KEY =
  "astrbot.spcode.gitDiffSidebar.hotFilesExclude";

function buildSnapshot(): GitStatsData {
  return {
    success: true,
    reason: null,
    loaded: true,
    stderr: "",
    elapsedMs: 1,
    umo: "test",
    worktree: null,
    directory: null,
    ref: "HEAD",
    resolvedSha: "deadbeef",
    days: [],
    hotFiles: [
      // .json at various depths — the 2026-07-19 #1 regression case.
      { path: "chat.json", commits: 99, additions: 0, deletions: 0 },
      {
        path: "dashboard/src/i18n/locales/zh-CN/features/chat.json",
        commits: 80,
        additions: 0,
        deletions: 0,
      },
      { path: "pyproject.toml", commits: 50, additions: 0, deletions: 0 },
      // Decoy: name contains "json" but isn't a .json file. The
      // trailing `$` anchor must keep `*.json` from matching this.
      { path: "jsonish.txt", commits: 40, additions: 0, deletions: 0 },
      // Plain file that should never be excluded by `*.json`.
      {
        path: "astrbot/core/pipeline/foo.py",
        commits: 30,
        additions: 0,
        deletions: 0,
      },
      // Deep file with a name a user might reasonably want to filter
      // by typing the bare filename. Reproduces the 2026-07-19
      // screenshot: typing `tool_loop_agent_runner.py` must hide
      // this entry, and only this entry.
      {
        path: "astrbot/core/agent/runners/tool_loop_agent_runner.py",
        commits: 60,
        additions: 0,
        deletions: 0,
      },
    ],
    totals: {
      commits: 339,
      additions: 0,
      deletions: 0,
      filesChanged: 6,
    },
    range: { first: "2026-01-01", last: "2026-07-19" },
    truncated: false,
    maxCommits: 5000,
  };
}

function buildState(snapshot: GitStatsData): GitStatsFetchState {
  return { kind: "ok", snapshot };
}

function mountPanel(state: GitStatsFetchState) {
  return mount(GitStatsPanel, {
    props: {
      state,
      open: true,
      isDark: false,
      range: { kind: "preset", preset: "1y" },
      topFilesLimit: 20,
    },
    global: { stubs: vuetifyStubs },
  });
}

/** Read the visible hot-files paths from the rendered DOM. The panel
 *  renders each row as `<button class="git-stats-hot-row" :title="f.path">`
 *  so the title attribute is the cheapest unambiguous handle. */
function visiblePaths(wrapper: ReturnType<typeof mountPanel>): string[] {
  return wrapper
    .findAll(".git-stats-hot-row")
    .map((b) => b.attributes("title") ?? "");
}

function mountWithExclude(patterns: string) {
  localStorage.setItem(EXCLUDE_STORAGE_KEY, patterns);
  return mountPanel(buildState(buildSnapshot()));
}

describe("GitStatsPanel hot-files exclude patterns", () => {
  it("shows every file when no patterns are configured", () => {
    const wrapper = mountWithExclude("");
    expect(visiblePaths(wrapper)).toEqual([
      "chat.json",
      "dashboard/src/i18n/locales/zh-CN/features/chat.json",
      "pyproject.toml",
      "jsonish.txt",
      "astrbot/core/pipeline/foo.py",
      "astrbot/core/agent/runners/tool_loop_agent_runner.py",
    ]);
  });

  // 2026-07-19 #1 regression: `*.json` previously compiled to
  // `^[^/]*\.json$` and only matched files in the repo root, so a
  // nested json file still showed up.
  it("`*.json` hides .json files at any depth", () => {
    const wrapper = mountWithExclude("*.json");
    expect(visiblePaths(wrapper)).toEqual([
      "pyproject.toml",
      "jsonish.txt",
      "astrbot/core/pipeline/foo.py",
      "astrbot/core/agent/runners/tool_loop_agent_runner.py",
    ]);
  });

  it("multiple comma-separated patterns all apply (AND-of-OR)", () => {
    const wrapper = mountWithExclude("*.json, pyproject.toml");
    expect(visiblePaths(wrapper)).toEqual([
      "jsonish.txt",
      "astrbot/core/pipeline/foo.py",
      "astrbot/core/agent/runners/tool_loop_agent_runner.py",
    ]);
  });

  it("a literal filename pattern matches at any depth", () => {
    const wrapper = mountWithExclude("pyproject.toml");
    expect(visiblePaths(wrapper)).toEqual([
      "chat.json",
      "dashboard/src/i18n/locales/zh-CN/features/chat.json",
      "jsonish.txt",
      "astrbot/core/pipeline/foo.py",
      "astrbot/core/agent/runners/tool_loop_agent_runner.py",
    ]);
  });

  // 2026-07-19 #2 regression: a plain filename (no wildcards) must
  // still match at any depth. The earlier `^...$`-only
  // implementation required the whole path to equal the pattern,
  // so typing `tool_loop_agent_runner.py` did not hide
  // `astrbot/core/agent/runners/tool_loop_agent_runner.py`.
  it("a plain filename pattern (no wildcards) matches at any depth", () => {
    const wrapper = mountWithExclude("tool_loop_agent_runner.py");
    expect(visiblePaths(wrapper)).not.toContain(
      "astrbot/core/agent/runners/tool_loop_agent_runner.py",
    );
    // Every other file (and unrelated `.py` files at other depths)
    // is still visible.
    expect(visiblePaths(wrapper)).toEqual([
      "chat.json",
      "dashboard/src/i18n/locales/zh-CN/features/chat.json",
      "pyproject.toml",
      "jsonish.txt",
      "astrbot/core/pipeline/foo.py",
    ]);
  });

  it("`*.json` does not match a file that merely contains 'json' in its name", () => {
    // Defends the trailing `$` anchor: `jsonish.txt` ends in .txt,
    // not .json, so `*.json` must not exclude it.
    const wrapper = mountWithExclude("*.json");
    expect(visiblePaths(wrapper)).toContain("jsonish.txt");
  });

  it("a path-shaped pattern with `/` only matches that exact path", () => {
    // `dashboard/*.json` is intentionally narrower than `*.json`:
    // the literal `/` in the pattern pins the location. `*`
    // matches a single segment (`[^/]*`) so this must not bleed
    // into nested subdirectories.
    const wrapper = mountWithExclude("dashboard/*.json");
    expect(visiblePaths(wrapper)).toContain("chat.json"); // root .json still visible
    expect(visiblePaths(wrapper)).toContain("jsonish.txt");
  });

  it("editing the input updates the rendered list live", async () => {
    const wrapper = mountWithExclude("");
    const input = wrapper.find("#git-stats-hot-exclude");
    await input.setValue("*.json");
    await nextTick();
    expect(visiblePaths(wrapper)).toEqual([
      "pyproject.toml",
      "jsonish.txt",
      "astrbot/core/pipeline/foo.py",
      "astrbot/core/agent/runners/tool_loop_agent_runner.py",
    ]);
  });

  it("surfaces the excluded-count pill when at least one row is hidden", () => {
    const wrapper = mountWithExclude("*.json");
    const pill = wrapper.find(".git-stats-hot-excluded-pill");
    expect(pill.exists()).toBe(true);
    expect(pill.text()).toContain("\u22122"); // unicode minus + "2"
  });

  it("does not render the excluded-count pill when nothing is hidden", () => {
    const wrapper = mountWithExclude("");
    expect(wrapper.find(".git-stats-hot-excluded-pill").exists()).toBe(false);
  });
});
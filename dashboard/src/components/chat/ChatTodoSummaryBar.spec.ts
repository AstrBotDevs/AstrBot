// Author: elecvoid243, 2026-07-19
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function readSiblingSource(filename: string): string {
  return readFileSync(fileURLToPath(new URL(filename, import.meta.url)), "utf8");
}

describe("TodoSummaryBar and GitDiffSidebar layering contract", () => {
  it("lowers the TodoSummaryBar below the Git Diff fullscreen layer", () => {
    const chatSource = readSiblingSource("./Chat.vue");
    const gitDiffSource = readSiblingSource("./GitDiffSidebar.vue");

    expect(gitDiffSource).toContain(
      '(e: "fullscreen-change", v: boolean): void',
    );
    expect(gitDiffSource).toContain('emit("fullscreen-change", v);');
    expect(chatSource).toContain("const gitDiffFullscreen = ref(false);");
    expect(chatSource).toMatch(
      /@fullscreen-change="gitDiffFullscreen = \$event"/,
    );
    expect(chatSource).toMatch(
      /'todo-summary-bar--gitdiff-fullscreen':\s*\n?\s*gitDiffSidebarOpen\s*&&\s*gitDiffFullscreen/,
    );
    expect(chatSource).toMatch(
      /\.todo-summary-bar\s*\{[\s\S]*?z-index:\s*9999;/,
    );
    expect(chatSource).toMatch(
      /\.todo-summary-bar--gitdiff-fullscreen\s*\{[\s\S]*?z-index:\s*1200;/,
    );
    expect(gitDiffSource).toMatch(
      /\.git-diff-sidebar\.is-fullscreen\s*\{[\s\S]*?z-index:\s*1300;/,
    );
  });
});

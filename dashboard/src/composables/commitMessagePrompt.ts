// Author: elecvoid243
// Date: 2026-07-17
// Spec: docs/superpowers/specs/2026-07-17-commit-message-ai-generate-design.md §4.2
//
// Pure builder for the commit-message-generation prompt sent to
// POST /spcode/btw. No Vue / no axios — importable by node --test
// (see tests/commitMessagePrompt.test.mjs). The btw endpoint mounts
// no LLM tools, so everything the model knows about the change must
// be embedded in this prompt text.

export type CommitMessageLanguage = "zh" | "en";

export interface CommitMessagePromptFile {
  path: string;
  status: string;
  additions: number;
  deletions: number;
}

export interface CommitMessagePromptInput {
  language: CommitMessageLanguage;
  files: CommitMessagePromptFile[];
  rawDiff: string | null;
}

/**
 * Character budget for the embedded diff section. The backend git-diff
 * endpoint already truncates at its own byte cap; this second cap keeps
 * the btw prompt within a size the LLM can digest cheaply.
 */
export const DIFF_CHAR_BUDGET = 6000;

/**
 * Build the single-turn user prompt for commit message generation.
 *
 * Args:
 *   input: target language, staged file stats, and the raw unified
 *     diff text (null/empty when the backend shipped no patch, e.g.
 *     binary-only changes).
 *
 * Returns:
 *   The complete prompt string: instruction + full file-stat list +
 *   (optionally truncated) diff section.
 */
export function buildCommitMessagePrompt(
  input: CommitMessagePromptInput,
): string {
  const stats = input.files
    .map((f) => `${f.path} (${f.status}, +${f.additions}/-${f.deletions})`)
    .join("\n");

  const rawDiff = input.rawDiff?.trim() ?? "";
  const hasDiff = rawDiff.length > 0;
  const truncated = rawDiff.length > DIFF_CHAR_BUDGET;
  const diffText = truncated ? rawDiff.slice(0, DIFF_CHAR_BUDGET) : rawDiff;

  if (input.language === "zh") {
    const parts = [
      "根据以下 git 暂存区(staged)改动,生成一条 Conventional Commits 风格的 commit message。",
      "要求:",
      "1. 格式为 <type>(<可选 scope>): <subject>,type 从 feat/fix/docs/style/refactor/perf/test/build/ci/chore/revert 中选择;",
      "2. 首行(subject)不超过 72 个字符;",
      "3. message 用中文书写;",
      "4. 如改动较复杂,可在首行后空一行,用简短的要点列表补充说明;",
      "5. 只返回 commit message 文本本身,不要输出任何解释、前后缀或 Markdown 代码块。",
      "",
      "变更文件统计:",
      stats,
    ];
    if (hasDiff) {
      parts.push(
        "",
        "diff 内容:",
        diffText + (truncated ? "\n……(diff 已截断)" : ""),
      );
    } else {
      parts.push("", "(无可用 diff 文本,请仅根据文件统计推断改动意图。)");
    }
    return parts.join("\n");
  }

  const parts = [
    "Based on the following git staged changes, generate a Conventional Commits style commit message.",
    "Requirements:",
    "1. Format: <type>(<optional scope>): <subject>, where type is one of feat/fix/docs/style/refactor/perf/test/build/ci/chore/revert;",
    "2. The subject line must be at most 72 characters;",
    "3. Write the message in English;",
    "4. For complex changes, you may add a blank line after the subject followed by a short bullet list;",
    "5. Return only the commit message text itself — no explanations, no prefixes, no Markdown code fences.",
    "",
    "Changed files:",
    stats,
  ];
  if (hasDiff) {
    parts.push(
      "",
      "Diff:",
      diffText + (truncated ? "\n...(diff truncated)" : ""),
    );
  } else {
    parts.push(
      "",
      "(No diff text available; infer the intent from the file stats only.)",
    );
  }
  return parts.join("\n");
}

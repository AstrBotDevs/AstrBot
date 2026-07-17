// Author: elecvoid243
// Date: 2026-07-17
// Spec: docs/superpowers/specs/2026-07-17-commit-message-ai-generate-design.md §4.2
// + Revision 2026-07-17 (structured JSON reply with few-shot examples)
//
// Pure builder for the commit-message-generation prompt sent to
// POST /spcode/btw, plus the parser for the model's structured reply.
// No Vue / no axios — importable by node --test (see
// tests/commitMessagePrompt.test.mjs). The btw endpoint mounts no LLM
// tools, so everything the model knows about the change must be
// embedded in this prompt text.
//
// Reply contract (revision 2026-07-17): the model is instructed to
// answer with exactly one JSON object {"subject": string, "body":
// string} — free-form replies tend to carry prose, code fences or
// commentary that cannot be committed as-is. parseCommitMessageReply
// extracts that object tolerantly; the dialog falls back to the
// cleaned raw reply when parsing fails.
//
// Robustness (revision 2026-07-17 (3)): reasoning/chatty models may
// leak <think> blocks, wrap the answer in a ```json fence, or discuss
// the contract with brace fragments like {"subject","body"} in prose.
// Extraction therefore (a) strips <think> blocks, (b) tries json-
// labeled fenced blocks first, then other fences, then the bare text,
// and (c) within each haystack scans for balanced {...} spans — every
// candidate must survive JSON.parse + subject validation, so invalid
// prose fragments are skipped naturally.

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
 *   The complete prompt string: instruction (JSON reply contract +
 *   few-shot output examples) + full file-stat list + (optionally
 *   truncated) diff section.
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
      "4. 如改动较复杂,可在 body 中用简短的要点列表补充说明;",
      "5. 严格只输出一个 JSON 对象,不要输出任何解释、前后缀或 Markdown 代码块。JSON 格式:",
      '   {"subject": "<首行>", "body": "<正文,无则空字符串>"}',
      "输出示例(仅演示格式):",
      '{"subject": "feat(auth): 新增登录失败重试限制", "body": "- 连续失败 5 次后锁定 10 分钟\\n- 新增 RetryLimiter 类"}',
      '{"subject": "fix: 修复空配置导致的启动崩溃", "body": ""}',
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
    "4. For complex changes, use the body for a short bullet list;",
    "5. Output exactly one JSON object and nothing else — no explanations, no prefixes, no Markdown code fences. JSON shape:",
    '   {"subject": "<subject line>", "body": "<body text, or empty string>"}',
    "Output examples (format only):",
    '{"subject": "feat(auth): add login retry limit", "body": "- lock account for 10 minutes after 5 consecutive failures\\n- add RetryLimiter class"}',
    '{"subject": "fix: prevent startup crash on null config", "body": ""}',
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

/**
 * Extract every balanced `{...}` span from text, in order of
 * appearance. Braces inside JSON string literals are ignored via a
 * small state machine. Unterminated spans (depth never returns to 0)
 * are dropped.
 */
function extractBalancedObjects(text: string): string[] {
  const objects: string[] = [];
  let depth = 0;
  let start = -1;
  let inString = false;
  let escaped = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === "\\") escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') {
      if (depth > 0) inString = true;
    } else if (ch === "{") {
      if (depth === 0) start = i;
      depth++;
    } else if (ch === "}" && depth > 0) {
      depth--;
      if (depth === 0 && start !== -1) {
        objects.push(text.slice(start, i + 1));
        start = -1;
      }
    }
  }
  return objects;
}

/**
 * Parse the model's structured reply into a plain commit message.
 *
 * Tolerates chatty / reasoning-model output: <think> blocks are
 * stripped, ```json fenced blocks are preferred over other fenced
 * blocks and bare text, and within each haystack every balanced {...}
 * span is tried until one parses to an object with a non-empty string
 * `subject`.
 *
 * Args:
 *   text: raw `reply` string returned by POST /spcode/btw.
 *
 * Returns:
 *   `subject` alone when body is empty, otherwise
 *   `subject + "\n\n" + body`; null when no valid candidate exists
 *   (caller falls back to the cleaned raw reply).
 */
export function parseCommitMessageReply(text: string): string | null {
  // Drop reasoning-model thinking blocks if the provider leaks them.
  const withoutThink = text.replace(/<think>[\s\S]*?<\/think>/gi, "");
  // Candidate haystacks, highest confidence first: json-labeled fenced
  // blocks, other fenced blocks, then the whole bare text.
  const fenced = [
    ...withoutThink.matchAll(/```(\w*)[^\S\r\n]*\r?\n([\s\S]*?)```/g),
  ];
  const haystacks = [
    ...fenced.filter((m) => m[1].toLowerCase() === "json"),
    ...fenced.filter((m) => m[1].toLowerCase() !== "json"),
  ].map((m) => m[2]);
  haystacks.push(withoutThink);

  for (const haystack of haystacks) {
    for (const candidate of extractBalancedObjects(haystack)) {
      let parsed: unknown;
      try {
        parsed = JSON.parse(candidate);
      } catch {
        continue; // prose brace fragment — try the next span
      }
      if (
        typeof parsed !== "object" ||
        parsed === null ||
        Array.isArray(parsed)
      ) {
        continue;
      }
      const obj = parsed as Record<string, unknown>;
      const subject =
        typeof obj.subject === "string" ? obj.subject.trim() : "";
      if (!subject) continue;
      const body = typeof obj.body === "string" ? obj.body.trim() : "";
      return body ? `${subject}\n\n${body}` : subject;
    }
  }
  return null;
}

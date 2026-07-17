# GitCommitDialog: AI-Generated Commit Message Design

**Date:** 2026-07-17
**Status:** Draft (pending user review)
**Author:** elecvoid243
**Related:** `F:\github\astrbot_plugin_spcode_toolkit\docs\api\v2.20-btw-frontend.md` (`POST /spcode/btw`), `docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md` (commit workflow), `docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md` (git-diff fetch)

## Goal

When the commit dialog (`GitCommitDialog.vue`) is open, the user must be able to click an **"AI generate"** button to have an LLM draft the commit message from the current **staged** changes, instead of typing it manually. The generated text is filled into the existing message textarea, where the user can edit it, regenerate it, and finally submit it through the unchanged `POST /spcode/git-commit` flow.

A small language toggle next to the button selects the language of the generated message: **中文** or **English**. The message style is always [Conventional Commits](https://www.conventionalcommits.org/) with a ≤72-character subject line, matching the dialog's existing placeholder convention (`feat: 简要描述本次改动...`).

## Background

### Current commit flow

- `GitCommitBar.vue` (sticky bar at the bottom of the diff view) emits `commit` → `GitDiffSidebar.onClickCommit()` opens `GitCommitDialog.vue`.
- `GitCommitDialog.vue` owns a `message` ref bound to a `<textarea>` (8192-char cap, warning at 7000, Ctrl+Enter submits, staged-file list, stderr block for failed commits). It emits `confirm({message})` / `cancel`.
- `GitDiffSidebar.onConfirmCommit()` calls `useSpcodeGitCommit.commit({message, worktree, umo})`, which POSTs `spcode/git-commit` via `pluginExtensionApi`.

### The btw endpoint (spcode plugin v2.20)

`POST /spcode/btw` is a one-shot, side-effect-free LLM endpoint designed exactly for "AI do X for me" buttons outside the main chat flow:

- Body: `{prompt: string, umo?: string}`.
- Always HTTP 200; business result in `success` / `reason` / `data`.
- Success: `data = {reply: string, has_context: boolean}`.
- Failure reasons: `invalid_body`, `no_provider`, `empty_response`, `llm_error` (`data` is always `null` on failure).
- **No LLM tools are mounted** (confirmed in `tools/webapi/btw.py`): the model sees only the prompt text, the chat history of the passed `umo` (if the session exists), and the persona system prompt. It **cannot** run git commands.
- It never writes to conversation history, so calling it does not pollute the chat.

**Consequence:** because the endpoint cannot see the repository, the frontend must embed the staged changes in the prompt text. Relying on chat history (`has_context`) alone is unreliable — the user may not have discussed the changes in chat. This was confirmed with the user (decision Q1 → option A).

## Decisions (confirmed with user)

| # | Question | Decision |
|---|----------|----------|
| Q1 | Where does the AI get the change content? | **A** — on button click, the frontend fetches the fresh staged diff (`GET /spcode/git-diff?scope=staged`) and embeds file stats + truncated patch text into the prompt |
| Q2 | Message language / style | **B+C** — both Chinese and English supported, chosen via an in-dialog toggle (`中文 \| EN`); style is always Conventional Commits, subject ≤72 chars. Default toggle value follows UI locale (zh-CN → 中文, otherwise EN), persisted to `localStorage` afterwards |
| Q3 | Button placement | **A** — inside `GitCommitDialog`, on the "Commit message" label row; result replaces the textarea content and can be regenerated / edited before submitting |
| Arch | Code organization | **Option 1** — generic `useSpcodeBtw` composable + pure `commitMessagePrompt` module; dialog orchestrates inline |

## Scope

The feature must:

- add a language toggle (`中文 | EN`) and an "AI generate" button to the label row of `GitCommitDialog.vue`;
- on click, fetch the current staged diff with one `GET /spcode/git-diff?scope=staged&umo=...(&worktree=...)` call, parse it with the existing `parseSpcodeGitDiff`;
- build a locale-correct prompt via a new pure module `commitMessagePrompt.ts` (instruction + full file-stat list + diff text capped at 6000 chars with a truncation marker);
- call `POST /spcode/btw` via a new generic composable `useSpcodeBtw.ts` with a 30 s timeout, passing the current `umo`;
- on success, replace the textarea content with `reply` (the user can edit or regenerate before submitting);
- on failure, show an inline error line inside the dialog (styled consistently with the existing stderr block), mapped from the backend ReasonCode;
- disable the button while a generation or a commit is in flight, when there are no staged files, or when `umo` is missing;
- abort the in-flight btw request when the dialog is cancelled (btw is side-effect-free, so closing is never blocked);
- persist the chosen language to `localStorage` key `astrbot.spcode.gitDiffSidebar.commitMsgLang` (initial default: `"zh"` when the UI locale is zh-CN, else `"en"`);
- keep every existing behavior of the dialog (char counter, staged list, stderr block, Ctrl+Enter, cancel-while-committing guard) untouched.

The feature must **not**:

- modify the spcode plugin backend in any way (the btw endpoint already exists in v2.20);
- touch `GitCommitBar.vue`, `useSpcodeGitCommit.ts`, or the `POST /spcode/git-commit` flow;
- attempt streaming (the endpoint is one-shot JSON only);
- show a `has_context` badge, generation history, or multiple candidates;
- regenerate the openapi client (`pluginExtensionApi` is a path-based passthrough; `pnpm generate:api` is not needed);
- auto-generate on dialog open (generation is always user-initiated — each call costs tokens).

## Architecture

Three new frontend files plus four modifications:

1. **`dashboard/src/composables/useSpcodeBtw.ts`** *(new)* — generic composable wrapping `POST /spcode/btw`. Lifecycle mirrors `useSpcodeGitCommit.ts`: single in-flight call, `AbortController`, `isMounted` guard, `dispose()`.
2. **`dashboard/src/composables/commitMessagePrompt.ts`** *(new)* — pure, dependency-free module exporting `buildCommitMessagePrompt()` (bilingual templates + truncation). Importable by `node --test`.
3. **`dashboard/tests/commitMessagePrompt.test.mjs`** *(new)* — unit tests for the prompt builder, mirroring `tests/parseSpcodeGitShow.test.mjs`.
4. **`dashboard/src/components/chat/message_list_comps/GitCommitDialog.vue`** *(modified)* — new props (`umo`, `worktree`), language toggle + generate button on the label row, inline generate-error line, `onGenerate()` orchestration, abort-on-cancel.
5. **`dashboard/src/components/chat/GitDiffSidebar.vue`** *(modified)* — pass `umo` / `worktree` props to `<GitCommitDialog>`.
6. **`dashboard/src/i18n/locales/{zh-CN,en-US,ru-RU}/features/chat.json`** *(modified)* — new keys under `spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.*`.

### Data flow

```
GitDiffSidebar.vue                         GitCommitDialog.vue
  │ props: umo, worktree ─────────────────► │
  │                                         │ [中文|EN] toggle + [✨ AI 生成]
  │                                         │  onGenerate():
  │                                         │   1. GET spcode/git-diff?scope=staged
  │                                         │      → parseSpcodeGitDiff()      (existing)
  │                                         │   2. buildCommitMessagePrompt()  (new, pure)
  │                                         │   3. useSpcodeBtw.ask({prompt, umo})
  │                                         │      → POST spcode/btw (30s timeout)
  │                                         │   4a. ok    → message.value = reply
  │                                         │   4b. error → inline error line (i18n by reason)
  │  ◄──────────── confirm({message}) ───── │  (existing, unchanged)
  │ onConfirmCommit() → POST git-commit     │
```

## Component design

### 4.1 `useSpcodeBtw.ts`

```typescript
export interface BtwParams {
  prompt: string;
  umo?: string | null;
}

export type BtwResult =
  | { ok: true; reply: string; hasContext: boolean }
  | { ok: false; reason: string }; // backend ReasonCode | "network" | "aborted"

export interface UseSpcodeBtw {
  isGenerating: Ref<boolean>;
  ask: (params: BtwParams) => Promise<BtwResult>;
  /** Abort the in-flight request; the composable stays usable afterwards. */
  cancel: () => void;
  /** Unmount hook: abort in-flight and stop all further state writes. */
  dispose: () => void;
}
```

- POSTs `spcode/btw` via `pluginExtensionApi.post`, `timeout: 30_000` (per the endpoint doc §4.2), abortable.
- Response parsing is intentionally shallow (this endpoint's envelope is tiny): read `resp.data`; `success === true` → take `data.reply` / `data.has_context`; otherwise take `reason` verbatim. A reply that is empty after `trim()` is mapped to `empty_response` defensively.
- Error mapping follows `useSpcodeGitCommit`: axios `CanceledError` / unmounted → `aborted`; `ERR_NETWORK`, `ECONNABORTED` (axios timeout), or `/network|timeout/i.test(message)` → `network`; anything else → the backend reason or `unknown`.
- Only one in-flight call: a new `ask()` aborts the previous one.

### 4.2 `commitMessagePrompt.ts` (pure)

```typescript
export type CommitMessageLanguage = "zh" | "en";

export interface CommitMessagePromptInput {
  language: CommitMessageLanguage;
  files: Array<{ path: string; status: string; additions: number; deletions: number }>;
  rawDiff: string | null;
}

export const DIFF_CHAR_BUDGET = 6000;

export function buildCommitMessagePrompt(input: CommitMessagePromptInput): string;
```

Output structure (language-dependent instruction wording, identical semantics):

1. **Instruction** — Conventional Commits; subject ≤72 chars; optional body bullet points for complex changes; write the message in Chinese (中文) / English; return **only** the message text — no explanations, no Markdown code fences.
2. **File stats** — always the complete list, one per line: `<path> (<status>, +<additions>/-<deletions>)`.
3. **Diff section** — `rawDiff` capped at `DIFF_CHAR_BUDGET` chars; when cut, append a truncation marker (`...(diff truncated)` / `……(diff 已截断)`). When `rawDiff` is null/empty (e.g. all-binary changes), the section is omitted entirely and the instruction notes that generation must rely on the file stats.

### 4.3 `GitCommitDialog.vue` changes

**New props:**

```typescript
umo: string | null;        // current session origin, forwarded to both endpoints
worktree: string | null;   // selected worktree (null = primary), forwarded to git-diff
```

**New state:**

- `msgLanguage: Ref<"zh" | "en">` — initialized from `localStorage["astrbot.spcode.gitDiffSidebar.commitMsgLang"]` (repo namespace convention, mirroring the sidebar's `STORAGE_KEYS`), falling back to `"zh"` when the UI locale is zh-CN else `"en"`; every change is written back to `localStorage` immediately.
- `generateErrorKey: Ref<string | null>` — i18n key suffix of the last generate failure (`no_provider` | `empty_response` | `llm_error` | `network` | `diff_fetch_failed` | `unknown`), cleared on each new attempt and on dialog open (together with the existing `message` reset watch).
- `useSpcodeBtw()` instance; `onBeforeUnmount(() => btw.dispose())` added to the existing unmount hook chain.

**`onGenerate()` (inline orchestration, single linear flow):**

1. Guard: return early when `isGenerating || isCommitting || stagedFiles.length === 0 || !umo`.
2. Clear `generateErrorKey`.
3. `GET spcode/git-diff` with `params: {umo, scope: "staged", ...(worktree ? {worktree} : {})}` — one-shot `pluginExtensionApi.get`, parsed by `parseSpcodeGitDiff`; any throw / non-ok → `generateErrorKey = "diff_fetch_failed"`, stop.
4. `prompt = buildCommitMessagePrompt({language: msgLanguage.value, files: snapshot.files, rawDiff: snapshot.rawDiff})`.
5. `result = await btw.ask({prompt, umo})`.
6. `ok` → `message.value = result.reply` (replace; user may edit / regenerate). Failure (except `aborted`, which is silent) → `generateErrorKey = result.reason`.

**Cancel behavior:** `onCancel()` additionally calls `btw.cancel()` so a late reply never overwrites a closed dialog's state. Unlike commit-in-flight, generation **never blocks** closing.

**Template (label row):**

```html
<div class="commit-message-label-row">
  <label class="commit-message-label">{{ tm("...dialog.messageLabel") }}</label>
  <v-btn-toggle v-model="msgLanguage" mandatory density="compact" variant="tonal"
                :aria-label="tm('...dialog.langToggleAria')">
    <v-btn value="zh" size="x-small">{{ tm("...dialog.langZh") }}</v-btn>
    <v-btn value="en" size="x-small">{{ tm("...dialog.langEn") }}</v-btn>
  </v-btn-toggle>
  <v-btn variant="text" size="small" prepend-icon="mdi-auto-fix"
         :loading="isGenerating" :disabled="!canGenerate"
         :aria-label="tm('...dialog.generateAria')"
         @click="onGenerate">
    {{ tm("...dialog.generate") }}
  </v-btn>
</div>
<!-- below the char counter, only when generateErrorKey: -->
<div v-if="generateErrorKey" class="commit-generate-error">
  {{ tm(`...dialog.generateError.${generateErrorKey}`) }}
</div>
```

- `canGenerate = stagedFiles.length > 0 && !!umo && !isCommitting && !isGenerating`.
- `.commit-message-label-row` is a flex row (`align-items: center; gap: 8px`); the label keeps its existing style, controls are pushed right (`margin-left: auto`).
- `.commit-generate-error` reuses the stderr block's visual language: 12 px, `rgb(var(--v-theme-error))`, `margin-top: 4px` (a plain line — not a boxed block — because generate errors carry no stderr payload).

### 4.4 `GitDiffSidebar.vue` changes

At the existing `<GitCommitDialog>` usage, add:

```html
:umo="spcodeStatus.status.value.umo"
:worktree="selectedWorktree"
```

No other sidebar logic changes.

## i18n keys

Added under `spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog` in all three locales (`zh-CN`, `en-US`, `ru-RU`):

| Key | zh-CN | en-US | ru-RU |
|-----|-------|-------|-------|
| `generate` | AI 生成 | Generate | Сгенерировать |
| `generateAria` | 用 AI 生成 commit message | Generate commit message with AI | Сгенерировать сообщение коммита с помощью ИИ |
| `langZh` | 中文 | 中文 | 中文 |
| `langEn` | EN | EN | EN |
| `langToggleAria` | 生成语言 | Message language | Язык сообщения |
| `generateError.no_provider` | AI 服务暂不可用，请稍后再试 | AI service unavailable, please try again later | Сервис ИИ недоступен, попробуйте позже |
| `generateError.empty_response` | AI 没有返回内容，请重试 | AI returned nothing, please retry | ИИ ничего не вернул, повторите попытку |
| `generateError.llm_error` | AI 服务异常，请稍后重试 | AI service error, please retry later | Ошибка сервиса ИИ, повторите позже |
| `generateError.network` | 网络错误，请稍后重试 | Network error, please retry later | Сетевая ошибка, повторите позже |
| `generateError.diff_fetch_failed` | 无法获取暂存区改动，请重试 | Failed to load staged changes, please retry | Не удалось загрузить изменения, повторите попытку |
| `generateError.unknown` | 生成失败，请重试 | Generation failed, please retry | Не удалось сгенерировать, повторите попытку |

(`invalid_body` maps to `unknown` — it indicates a frontend bug, per the endpoint doc §1.5.)

## Error handling matrix

| Situation | UX |
|-----------|----|
| `no_provider` | inline error `generateError.no_provider`; no auto-retry |
| `empty_response` | inline error; user may click again |
| `llm_error` | inline error; user may click again |
| network / timeout (>30 s abort) | inline error `network` |
| staged-diff GET fails | inline error `diff_fetch_failed` (btw is never called) |
| dialog cancelled mid-generation | request aborted silently; no error shown |
| reply longer than 8192 chars | existing `overMax` guard blocks submit until the user trims — message is still shown for editing |
| clicked with 0 staged files / no umo | button disabled (no error path needed) |

## Testing

1. **`dashboard/tests/commitMessagePrompt.test.mjs`** (`node --test`, mirrors `tests/parseSpcodeGitShow.test.mjs`):
   - zh and en templates both contain the Conventional-Commits instruction, the ≤72-char rule, and the "message text only" rule;
   - file stats list is complete and formatted (`path (M, +10/-2)`);
   - diff longer than `DIFF_CHAR_BUDGET` is cut at the budget and carries the truncation marker in the correct language;
   - `rawDiff: null` / empty → no diff section, instruction mentions stats-only generation;
   - binary-only input (files with `slice: null`) still yields a valid prompt.
2. **Manual verification** (dev dashboard against a live spcode plugin):
   - stage files → open dialog → generate in both languages → edit → submit;
   - disable the LLM provider → `no_provider` inline error;
   - cancel the dialog mid-generation → no late overwrite, no console errors;
   - reload the page → language toggle restores the persisted choice.

## Non-goals (YAGNI)

- Streaming generation (endpoint limitation).
- `has_context` badge, generation history, multiple candidates, "insert at cursor" mode.
- Auto-generate on dialog open.
- Any backend change; any openapi client regeneration; any change to the commit submission path.

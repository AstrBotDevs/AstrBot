# Tool Result Card Copyable Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable `CopyableText.vue` component and integrate it into 8 tool-result display components so users can hover to reveal a copy button on every copyable value (file paths, error messages, args, shell output, etc.) without breaking the existing "click row to expand" interaction.

**Architecture:** New SFC at `message_list_comps/__shared__/CopyableText.vue` (chat-local shared). Replaces inline `SessionIdCopy` in `IntaShellToolResultView.vue`. Replaces plain `<span>` / `<code>` / `<pre>` in 7 other files with `<CopyableText :value="..." :display-value="..." mode="..." :show-icon="..." :multiline="...">`. The component handles its own `opacity: 0 → 1` hover affordance, `position: absolute` button placement, `await copyToClipboard()`, and `@click.stop` to prevent row-toggle interference.

**Tech Stack:** Vue 3.3 + TypeScript + Vuetify 3 + vue-i18n 11. Reuses existing `@/utils/clipboard` (`copyToClipboard` async). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-28-tool-result-card-copyable-design.md`

---

## File Structure

### Files Created

| File | Purpose | LoC est. |
|------|---------|---------|
| `dashboard/src/components/chat/message_list_comps/__shared__/CopyableText.vue` | Reusable copyable text wrapper (3 modes + default slot) | ~180 |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` | + `copy.copy` / `copy.copied` | +6 |
| `dashboard/src/i18n/locales/en-US/features/chat.json` | + `copy.copy` / `copy.copied` | +6 |
| `dashboard/src/i18n/locales/ru-RU/features/chat.json` | + `copy.copy` / `copy.copied` | +6 |

### Files Modified

| File | Changes | Risk |
|------|---------|------|
| `dashboard/src/components/chat/message_list_comps/ToolCallCard.vue` | args-value → CopyableText (preserve 60-char truncation); `.args-table` overflow visible | Low |
| `dashboard/src/components/chat/message_list_comps/ToolResultView.vue` | result-header-text + grep-file + 4 big blocks → CopyableText with default slot | Medium |
| `dashboard/src/components/chat/message_list_comps/IntaShellToolResultView.vue` | Remove inline `SessionIdCopy`; add CopyableText to command/output/pid/list-cmd/initial_output/created_at/last_activity | Medium |
| `dashboard/src/components/chat/message_list_comps/IPythonToolBlock.vue` | code/result/suffix → CopyableText with default slot | Low |
| `dashboard/src/components/chat/message_list_comps/spcode_tools/CodeCheckResult.vue` | issue-loc / issue-code / issue-msg → CopyableText | Low |
| `dashboard/src/components/chat/message_list_comps/spcode_tools/CodeCheckResultList.vue` | Same as CodeCheckResult.vue (verbatim) | Low |
| `dashboard/src/components/chat/message_list_comps/spcode_tools/CodeExploreResult.vue` | symbol-name / symbol-loc / caller-chip → CopyableText | Low |
| `dashboard/src/components/chat/message_list_comps/spcode_tools/EsSearchResult.vue` | item-name / item-path → CopyableText | Low |

### Files NOT Modified

`ToolCallItem.vue`, `SpcodeToolResultView.vue`, `spcode_tools/FileRemoveResult.vue`, `spcode_tools/FileDiffResult.vue`, `spcode_tools/CodeIndexResult.vue`, `spcode_tools/TodoListResult.vue`, `spcode_tools/TodoListPanel.vue`, `spcode_tools/icons.ts` — out of scope per spec §1.3.

### Verification Commands

- `pnpm lint` — must pass
- `pnpm typecheck` — must pass
- `pnpm build` — must pass (smoke test)
- `pnpm dev` then manual hand-test in browser — per spec §7.1

---

## Chunk 1: Foundation (CopyableText + i18n)

> **Goal:** Build the reusable component and i18n keys. Pilot-test in isolation by mounting a temporary instance in `ChatMessageList.vue` (rolled back at the end of the chunk).

### Task 1.1: Add i18n keys (3 locales)

**Files:**
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json`
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json`

- [ ] **Step 1: Inspect existing `chat.json` structure**

Run in cmd.exe to locate the top-level closing brace (zero indent):
```cmd
findstr /N "^}$" "F:\github\Astrbot\dashboard\src\i18n\locales\en-US\features\chat.json"
```
Expected: a line like `  485 }` (or wherever the file ends). The file is one big JSON object. Plan to insert the new top-level `"copy"` key just before this closing brace — append `,` to the previous top-level key's closing brace, then on a new line add the `"copy": { ... }` block.

**Before editing**, identify the last existing top-level key (e.g., `"actions"`, `"intaShell"`, `"planModeChip"`) by scrolling up from the closing `}`. This is the key after which you'll append a `,` and the new block.

- [ ] **Step 2: Add keys to `zh-CN`**

Open `dashboard/src/i18n/locales/zh-CN/features/chat.json`. Find the last top-level key block (e.g., the closing `}` of `"planModeChip": { ... }`) and replace that single closing `}` with:

```json
  },
  "copy": {
    "copy": "复制",
    "copied": "已复制"
  }
```

(Add a trailing `,` to the previous key's `}`, then add the new `copy` block on the next line.)

- [ ] **Step 3: Add keys to `en-US`**

Same edit in `dashboard/src/i18n/locales/en-US/features/chat.json`:

```json
  },
  "copy": {
    "copy": "Copy",
    "copied": "Copied"
  }
```

- [ ] **Step 4: Add keys to `ru-RU`**

Same edit in `dashboard/src/i18n/locales/ru-RU/features/chat.json`:

```json
  },
  "copy": {
    "copy": "Копировать",
    "copied": "Скопировано"
  }
```

- [ ] **Step 5: Validate JSON syntax**

In cmd.exe:
```cmd
cd /d F:\github\Astrbot\dashboard && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/zh-CN/features/chat.json','utf8'));JSON.parse(require('fs').readFileSync('src/i18n/locales/en-US/features/chat.json','utf8'));JSON.parse(require('fs').readFileSync('src/i18n/locales/ru-RU/features/chat.json','utf8'));console.log('OK')"
```
Expected: `OK` (no error). If any locale fails, fix trailing commas or brace mismatch.

- [ ] **Step 6: Commit**

```cmd
cd /d F:\github\Astrbot && git add dashboard\src\i18n\locales\zh-CN\features\chat.json dashboard\src\i18n\locales\en-US\features\chat.json dashboard\src\i18n\locales\ru-RU\features\chat.json && git commit -m "feat(i18n): add copy.copy / copy.copied keys for tool-result card copyable"
```

---

### Task 1.2: Create `CopyableText.vue` component

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/__shared__/CopyableText.vue`

- [ ] **Step 1: Create the `__shared__` directory**

```cmd
mkdir F:\github\Astrbot\dashboard\src\components\chat\message_list_comps\__shared__
```

- [ ] **Step 2: Write the component SFC**

Create `dashboard/src/components/chat/message_list_comps/__shared__/CopyableText.vue` with the following content:

```vue
<!--
  CopyableText
  ─────────────────────────────────────────────────────────────────────
  Reusable copyable text wrapper for tool-call result cards.

  Three modes:
    - inline : short text in a normal paragraph; icon floats in a
               pre-reserved right padding (no layout shift on hover).
    - code   : short monospace text; icon floats top-right of a small
               chip-like container.
    - block  : multi-line content; icon floats top-right of a
               pre/wrap container; supports `default` slot for Shiki
               HTML or other rendered content.

  Author: elecvoid243 | 2026-06-28
-->
<template>
  <span
    v-if="mode === 'inline'"
    class="copyable copyable-inline"
    :class="{ 'is-empty': !displayedText }"
    :title="title || undefined"
  >
    <span class="copyable-text">{{ displayedText }}</span>
    <button
      v-if="showCopyIcon"
      type="button"
      class="copyable-btn"
      :aria-label="copied ? tm('copy.copied') : tm('copy.copy')"
      :title="copied ? tm('copy.copied') : tm('copy.copy')"
      @click.stop="handleCopy"
    >
      <v-icon size="12">{{ copied ? 'mdi-check' : 'mdi-content-copy' }}</v-icon>
    </button>
  </span>

  <span
    v-else-if="mode === 'code'"
    class="copyable copyable-code"
    :class="{ 'is-empty': !displayedText }"
    :title="title || undefined"
  >
    <span class="copyable-text">{{ displayedText }}</span>
    <button
      v-if="showCopyIcon"
      type="button"
      class="copyable-btn copyable-btn-corner"
      :aria-label="copied ? tm('copy.copied') : tm('copy.copy')"
      :title="copied ? tm('copy.copied') : tm('copy.copy')"
      @click.stop="handleCopy"
    >
      <v-icon size="12">{{ copied ? 'mdi-check' : 'mdi-content-copy' }}</v-icon>
    </button>
  </span>

  <div
    v-else
    class="copyable copyable-block"
    :class="{ 'is-empty': !displayedText, 'is-multiline': multiline, 'is-bare': bare }"
    :title="title || undefined"
  >
    <button
      v-if="showCopyIcon"
      type="button"
      class="copyable-btn copyable-btn-corner"
      :aria-label="copied ? tm('copy.copied') : tm('copy.copy')"
      :title="copied ? tm('copy.copied') : tm('copy.copy')"
      @click.stop="handleCopy"
    >
      <v-icon size="12">{{ copied ? 'mdi-check' : 'mdi-content-copy' }}</v-icon>
    </button>
    <div v-if="$slots.default" class="copyable-slot"><slot /></div>
    <span v-else class="copyable-text">{{ displayedText }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { copyToClipboard } from "@/utils/clipboard";

const props = withDefaults(
  defineProps<{
    /** Source for the clipboard; always the copy target. */
    value: string;
    /** Optional display text. Defaults to `value`. */
    displayValue?: string;
    /** Visual mode. */
    mode?: "inline" | "code" | "block";
    /** Shown when `value` is empty. */
    placeholder?: string;
    /** block mode: preserve newlines. */
    multiline?: boolean;
    /** Whether to show the copy icon. */
    showIcon?: boolean;
    /** Optional native browser tooltip on the root. */
    title?: string;
    /** block mode: drop the wrapper's own background/padding/border-radius so
     *  the slot content provides its own visual chrome. Use when wrapping
     *  existing code blocks that already have their own styling. */
    bare?: boolean;
  }>(),
  {
    mode: "inline",
    placeholder: "—",
    multiline: false,
    showIcon: true,
    title: undefined,
    bare: false,
  },
);

const { tm } = useModuleI18n("features/chat");

/** What the user actually sees. Falls back to placeholder when value is empty. */
const displayedText = computed(() => {
  if (props.value) return props.displayValue ?? props.value;
  return props.placeholder;
});

/** Show copy icon only when there is something to copy. */
const showCopyIcon = computed(() => props.showIcon && !!props.value);

const copied = ref(false);
let resetTimer: ReturnType<typeof setTimeout> | null = null;

async function handleCopy() {
  // MUST await: copyToClipboard is async; flipping copied=true before
  // the promise resolves would mislead users on failure.
  const ok = await copyToClipboard(props.value);
  if (!ok) {
    // Silent fail: leave `copied` false so the button doesn't fake success.
    // Optional: console.warn for diagnostics, but no UX feedback (avoids
    // bloating the button state machine).
    return;
  }
  copied.value = true;
  if (resetTimer) clearTimeout(resetTimer);
  resetTimer = setTimeout(() => {
    copied.value = false;
    resetTimer = null;
  }, 1200);
}
</script>

<style scoped>
.copyable {
  position: relative;
  display: inline-block;
  user-select: text;
}

/* ── inline: stays inline, reserves right padding for icon ─────── */
.copyable-inline {
  padding-right: 18px;
  cursor: text;
}
.copyable-inline .copyable-text {
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── code: monospace chip, icon top-right ─────────────────────── */
.copyable-code {
  display: inline-block;
  padding: 0 22px 0 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-radius: 3px;
  color: rgba(var(--v-theme-on-surface), 0.8);
  cursor: text;
  max-width: 100%;
  vertical-align: baseline;
}
.copyable-code .copyable-text {
  white-space: pre-wrap;
  word-break: break-all;
}

/* ── block: block-level, icon top-right, supports slot ─────────── */
.copyable-block {
  display: block;
  position: relative;
  padding: 4px 24px 4px 8px;
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), 0.8);
  cursor: text;
}
.copyable-block.is-multiline .copyable-text {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}
.copyable-block .copyable-slot {
  /* slot content is rendered as-is; consumers bring their own pre/shiki */
}
.copyable-block.is-empty {
  color: rgba(var(--v-theme-on-surface), 0.4);
  font-style: italic;
}

/* bare: drop wrapper's own chrome (background / border-radius / padding)
   so the slot content (e.g. a <pre> with its own background) shows through
   without doubled visual layers. Keeps position:relative + right padding
   for the absolute-positioned copy button. */
.copyable-block.is-bare {
  padding: 0 24px 0 0;
  background: transparent;
  border-radius: 0;
}

/* ── copy button (corner, hover-revealed) ─────────────────────── */
.copyable-btn {
  position: absolute;
  top: 2px;
  right: 2px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 3px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.45);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease, color 0.15s ease, background 0.15s ease;
  z-index: 1;
}
.copyable-btn:hover,
.copyable-btn:focus-visible {
  background: rgba(var(--v-theme-on-surface), 0.1);
  color: rgba(var(--v-theme-on-surface), 0.85);
  outline: none;
}
.copyable-btn:focus-visible {
  box-shadow: 0 0 0 1.5px rgba(var(--v-theme-primary), 0.55);
}
/* show on hover of the wrapper or when the button itself is focused */
.copyable:hover .copyable-btn,
.copyable:focus-within .copyable-btn,
.copyable-btn:focus-visible {
  opacity: 1;
}

/* inline mode: button is in-flow, no absolute positioning */
.copyable-inline .copyable-btn,
.copyable-code .copyable-btn {
  position: absolute;
  top: 50%;
  right: 0;
  transform: translateY(-50%);
}
</style>
```

- [ ] **Step 3: Verify typecheck**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm typecheck
```
Expected: exits 0, no type errors. If `copyToClipboard` type signature doesn't match (it returns `Promise<boolean>`, this should be fine).

- [ ] **Step 4: Verify lint**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm lint
```
Expected: no new errors. (Existing lint warnings/errors are fine to leave if pre-existing — verify with `git stash && pnpm lint && git stash pop` if you suspect new violations.)

- [ ] **Step 5: Commit**

```cmd
cd /d F:\github\Astrbot && git add dashboard\src\components\chat\message_list_comps\__shared__\CopyableText.vue && git commit -m "feat(dashboard): add CopyableText component for hover copy affordance"
```

---

### Task 1.3: Pilot-test the component in `ChatMessageList.vue` (temporary, rolled back)

> This step validates the component works in a real message-list context before we wire it into 8 production call sites. The temporary mount is reverted at the end of Chunk 1.

**Files:**
- Modify: `dashboard/src/components/chat/ChatMessageList.vue` (temporary)
- Modify: `dashboard/src/views/ConversationPage.vue` (verify it renders; no changes expected)

- [ ] **Step 1: Add a temporary mount in `ChatMessageList.vue`**

Open `dashboard/src/components/chat/ChatMessageList.vue`. Find the `<script setup lang="ts">` block (the marker `<script setup lang="ts">` is unique) and add an import line near the other component imports (grouped with `ToolCallCard`, `IPythonToolBlock`, etc.):

```ts
import CopyableText from "@/components/chat/message_list_comps/__shared__/CopyableText.vue";
```

Then find the `<div v-else class="unknown-part">` block (the marker `class="unknown-part"` is unique) and add a temporary debug panel just before it:

```vue
<div v-if="showCopyableDebug" class="copyable-debug-panel" style="padding: 8px; margin: 8px 0; border: 1px dashed rgba(var(--v-theme-on-surface), 0.2); border-radius: 4px;">
  <div>DEBUG: CopyableText pilot</div>
  <div>inline: <CopyableText :value="'hello inline'" mode="inline" /></div>
  <div>code: <CopyableText :value="'hello code'" mode="code" /></div>
  <div>block: <CopyableText :value="'hello\nblock\nmultiline'" mode="block" :multiline="true" /></div>
  <div>block with slot: <CopyableText :value="'raw to copy'" mode="block" :multiline="true">
    <span style="background: yellow;">SLOT CONTENT: rendered as-is</span>
  </CopyableText></div>
  <div>empty: <CopyableText :value="''" mode="code" /></div>
  <div>truncated: <CopyableText :value="'this is the full raw text'" :display-value="'this is the t…'" mode="code" /></div>
  <div>no icon: <CopyableText :value="'no icon'" mode="code" :show-icon="false" /></div>
</div>
```

Add a `const showCopyableDebug = ref(true)` near the top of the script, next to other `ref(...)` declarations like `downloadingFiles`.

- [ ] **Step 2: Run dev server and verify visually**

Start the dev server in a background shell (it runs indefinitely):
```cmd
cd /d F:\github\Astrbot\dashboard && pnpm dev
```
(Use the shell's background mode; the agent will keep the server running for Steps 2–4 and stop it in Step 5.)

Open the chat in browser. Verify each variant in the debug panel:
1. `inline` shows "hello inline" with an icon that appears on hover
2. `code` shows "hello code" in monospace with a corner icon on hover
3. `block` shows 3 lines of "hello" with a corner icon on hover
4. `block with slot` shows the yellow-highlighted slot text; the icon (top-right) should still appear on hover; clicking the icon should copy the **raw `value`** ("raw to copy"), NOT the slot text
5. `empty` shows the placeholder "—" with NO icon
6. `truncated` shows "this is the t…" (displayValue); clicking the icon copies "this is the full raw text" (value)
7. `no icon` shows "no icon" with no icon even on hover

Also test keyboard accessibility: Tab to focus one of the copy buttons (the focused button should be visible — `opacity: 1` via `:focus-within`); press Enter; clipboard should contain the value; icon should become ✓ for 1.2s.

- [ ] **Step 3: Test i18n in another locale**

In the dev app's browser console, run:
```js
localStorage.setItem('astrbot-locale', 'en-US'); location.reload();
```
After hard reload, verify the button's `title`/`aria-label` reads "Copy" and "Copied".

Repeat with `ru-RU`: verify "Копировать" / "Скопировано".

(Without the `location.reload()`, the new locale won't take effect because `setupI18n` only reads `localStorage` on app init.)

- [ ] **Step 4: Test dark mode**

Toggle dark/light mode (project uses Vuetify theme). Verify the icon color (rgba 0.45) is readable in both modes; the button's hover background (rgba 0.1) is visible.

- [ ] **Step 5: Stop the dev server, then revert the temporary mount**

Stop the background `pnpm dev` process (Ctrl+C in its shell, or kill it).

Then in `ChatMessageList.vue`, remove exactly three things:
- The `import CopyableText` line
- The `const showCopyableDebug = ref(true)` line
- The entire `<div v-if="showCopyableDebug" class="copyable-debug-panel">...</div>` block (including the opening and closing tags and all 7 inner divs)

**Verification (strict):** run `git diff dashboard/src/components/chat/ChatMessageList.vue` and confirm the output is **empty**. If any lines appear, the revert is incomplete — repeat removal and re-check.

- [ ] **Step 6: Verify typecheck and lint still pass**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm typecheck && pnpm lint
```
Expected: both exit 0. No regressions from the temporary mount.

> **Note:** `pnpm lint` runs `eslint --fix` (per `package.json` scripts). It may auto-fix unrelated files. If `git status` shows modified files outside Chunk 1's scope, revert them with `git checkout -- <file>` before proceeding.

- [ ] **Step 7: Commit (no-op; nothing changed)**

No commit needed — the temporary mount was reverted. Move on to Chunk 2.

Confirm `git log -2` shows:
1. The CopyableText component commit (Task 1.2 Step 5)
2. The i18n keys commit (Task 1.1 Step 6)

No additional commit for the reverted pilot.

---

## Chunk 2: Pilot — `IntaShellToolResultView.vue` (replace `SessionIdCopy` + add coverage)

> **Goal:** Validate `CopyableText` integration in a real component before the horizontal rollout. This chunk has a **rollback checkpoint** (Task 2.5) before committing — if the pilot reveals unforeseen issues, we revert and fix the component.

### Task 2.1: Replace inline `SessionIdCopy` with `CopyableText`

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/IntaShellToolResultView.vue`

> The `CopyableText` component (built in Task 1.2) already has the `title` prop, `bare` prop, and proper `aria-label` wiring. No additional component work is needed before this task.

- [ ] **Step 1: Add `CopyableText` import to IntaShell**

Open `IntaShellToolResultView.vue`. Find the `import` block for `SpcodeToolResultView`-style imports (the existing `import { useModuleI18n }` etc.) and add at the top of the import list (after the existing `import { computed, h, defineComponent } from "vue";`):

```ts
import CopyableText from "./__shared__/CopyableText.vue";
```

- [ ] **Step 2: Replace `<SessionIdCopy>` usages (5 places total)**

The file uses `<SessionIdCopy>` in **5 places**:
- 4 normal-session blocks (`start`, `send`, `read`, `stop`) — all have identical markup
- 1 list block (compact variant)

**Use the editor's replace-all** for the 4 identical instances (markers: `<SessionIdCopy v-if="parsed.session" :session-id="parsed.session.session_id" />`):

Find (the exact 1-line text):
```vue
<SessionIdCopy v-if="parsed.session" :session-id="parsed.session.session_id" />
```
Replace with (preserves `v-if`, adds `title` for hover-tooltip):
```vue
<CopyableText
  v-if="parsed.session"
  :value="parsed.session.session_id"
  :display-value="parsed.session.session_id.length > 12 ? `${parsed.session.session_id.slice(0, 8)}…` : parsed.session.session_id"
  :title="parsed.session.session_id"
  mode="code"
  class="session-id"
/>
```

Then handle the **list block** separately (it uses `compact` and a different binding source — `s.session_id` not `parsed.session.session_id`):

Find:
```vue
<SessionIdCopy :session-id="s.session_id" compact />
```
Replace with:
```vue
<CopyableText
  :value="s.session_id"
  :display-value="s.session_id.length > 12 ? `${s.session_id.slice(0, 8)}…` : s.session_id"
  :title="s.session_id"
  mode="code"
  class="session-id compact"
/>
```

> **Verification:** after both replacements, run `git grep "SessionIdCopy" dashboard/src/components/chat/message_list_comps/IntaShellToolResultView.vue` — expected output is **empty** (no matches). If any remain, replace them.

- [ ] **Step 3: Delete the inline `SessionIdCopy` sub-component and its unused imports**

Find the entire `const SessionIdCopy = defineComponent({ ... })` block (starts with the `// ── Inline sub-component: SessionIdCopy ─────────────────────────` comment, ends with the matching `});`). Delete it entirely.

Also delete:
- The `void INTA_SHELL_ICONS;` line below it (no longer needed)
- The `import { INTA_SHELL_ICONS, ... } from "./inta_shell_tools/icons";` line at the top of `<script setup>` (the only use of `INTA_SHELL_ICONS` in this file was inside `SessionIdCopy`'s setup)

**Verification:** after deletion, run:
```cmd
cd /d F:\github\Astrbot && git grep -n "INTA_SHELL_ICONS" dashboard\src\components\chat\message_list_comps\IntaShellToolResultView.vue
```
Expected: **empty output** (no matches). If any line remains, delete it.

- [ ] **Step 4: Verify typecheck**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm typecheck
```
Expected: exits 0. If `useModuleI18n` import is now unused, remove the import as well.

- [ ] **Step 5: Verify lint (and check for auto-fix side effects)**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm lint
```
Then:
```cmd
cd /d F:\github\Astrbot && git status --short
```
Expected: only `IntaShellToolResultView.vue` should appear as modified. If other files appear (due to eslint --fix), revert them: `git checkout -- <file>`.

---

### Task 2.2: Add `CopyableText` to remaining copy targets in `IntaShellToolResultView.vue`

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/IntaShellToolResultView.vue`

- [ ] **Step 1: Replace `<code class="meta-value">` for `parsed.session.command`**

In the `start` block, find:
```vue
<code class="meta-value">{{ parsed.session.command }}</code>
```
Replace with:
```vue
<CopyableText :value="parsed.session.command" mode="code" class="meta-value" />
```

- [ ] **Step 2: Replace `<code class="meta-value">` for `parsed.message`**

In the `send` block, find:
```vue
<span class="meta-value">{{ parsed.message }}</span>
```
Replace with:
```vue
<CopyableText :value="parsed.message" mode="code" class="meta-value" />
```

- [ ] **Step 3: Replace `<code class="meta-value">` (output) — `read` block**

In the `read` block, find:
```vue
<code class="meta-value">{{ parsed.session.command }}</code>
```
Replace with:
```vue
<CopyableText :value="parsed.session.command" mode="code" class="meta-value" />
```

- [ ] **Step 4: Replace `<pre class="output-value">` for `parsed.output` (read) and `parsed.initial_output` (start)**

In the `start` block, find:
```vue
<pre v-if="hasInitialOutput" class="output-value">{{ parsed.initial_output }}</pre>
```
Replace with:
```vue
<CopyableText
  v-if="hasInitialOutput"
  :value="parsed.initial_output"
  mode="block"
  :multiline="true"
  class="output-value"
/>
```

In the `read` block, find:
```vue
<pre v-if="hasOutput" class="output-value">{{ parsed.output }}</pre>
```
Replace with:
```vue
<CopyableText
  v-if="hasOutput"
  :value="parsed.output"
  mode="block"
  :multiline="true"
  class="output-value"
/>
```

- [ ] **Step 5: Replace `<span class="meta-value-dim">` for `pid` and `created_at`**

In the `start` block, find:
```vue
<span class="meta-value-dim">{{ parsed.session.pid }}</span>
<span v-if="parsed.session.created_at" class="meta-sep">·</span>
<span v-if="parsed.session.created_at" class="meta-value-dim">
    {{ tm('intaShell.labels.created') }}: {{ formatRelativeTime(parsed.session.created_at) }}
</span>
```

Replace the two `<span class="meta-value-dim">` (keep the `<span class="meta-sep">` as-is). **Use `mode="inline"`** (not `code`) to preserve the original `.meta-value-dim` dim color and monospace (inline mode has no background/color/font overrides):

```vue
<CopyableText :value="String(parsed.session.pid)" mode="inline" class="meta-value-dim" />
<span v-if="parsed.session.created_at" class="meta-sep">·</span>
<CopyableText
  v-if="parsed.session.created_at"
  :value="`${tm('intaShell.labels.created')}: ${formatRelativeTime(parsed.session.created_at)}`"
  mode="inline"
  class="meta-value-dim"
/>
```

- [ ] **Step 6: Replace `<code class="session-list-cmd">` and `meta-value-dim` in `list` block**

Find:
```vue
<code class="session-list-cmd">{{ s.command }}</code>
...
<span class="meta-value-dim">pid {{ s.pid }}</span>
<span v-if="s.last_activity" class="meta-sep">·</span>
<span v-if="s.last_activity" class="meta-value-dim">
    {{ formatRelativeTime(s.last_activity) }}
</span>
```

Replace with (use `mode="code"` for `.session-list-cmd` since it's a command label, `mode="inline"` for `.meta-value-dim` to preserve dim styling):

```vue
<CopyableText :value="s.command" mode="code" class="session-list-cmd" />
...
<CopyableText :value="`pid ${s.pid}`" mode="inline" class="meta-value-dim" />
<span v-if="s.last_activity" class="meta-sep">·</span>
<CopyableText
  v-if="s.last_activity"
  :value="formatRelativeTime(s.last_activity)"
  mode="inline"
  class="meta-value-dim"
/>
```

- [ ] **Step 7: Verify typecheck and lint**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm typecheck && pnpm lint
```
Expected: both pass. Check `git status --short` shows only the IntaShell file modified.

---

### Task 2.3: Hand-test the IntaShell pilot

**Files:** none

- [ ] **Step 1: Run dev server and trigger an inta_shell session**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm dev
```

In the browser, start an interactive shell session via the LLM (or any existing chat with `astrbot_inta_shell_start` / `send` / `read` / `stop` / `list` tool calls). Verify each variant:

1. `start`: session_id is displayed as 8-char-truncated; hover the session-id → copy icon appears; click → clipboard contains the **full** session_id; icon becomes ✓ for 1.2s. **Also verify** the `title` tooltip on the chip shows the full session_id (this is a regression of the original `SessionIdCopy`'s `title` attribute — add a `title` attribute to the CopyableText root if missing, see spec §6 minor).
2. `start`: `command` chip is copyable; `pid` and `created_at` are copyable.
3. `start`: `initial_output` (if present) is copyable in block mode.
4. `send`: `message` is copyable.
5. `read`: `output` is copyable in block mode (preserves newlines).
6. `stop`: `exit_code` chip is unaffected (not a CopyableText target).
7. `list`: each session row's `command` is copyable; `session_id` (compact) is copyable; `pid` and `last_activity` are copyable.

For each, verify:
- Hovering the chip reveals the copy icon
- Clicking copies the full text to clipboard
- ✓ feedback appears for 1.2s
- Tab key focuses the button (visible `:focus-visible` outline)
- Enter triggers copy

- [ ] **Step 2: Test row click-to-expand is preserved**

Verify that clicking on the row **outside** the CopyableText button still does whatever the row did before (for `IntaShellToolResultView`, the session-card is not click-to-expand — there is no row-level click handler — so this is a no-op test, but verify the chips still look right).

- [ ] **Step 3: Test scrollable parent interaction**

Open a session list with 7+ sessions (if not possible in your test, skip this step). Verify the scrollable `.session-list` container doesn't clip the copy button when the cursor is on a row near the bottom edge.

- [ ] **Step 4: Test dark mode**

Toggle theme. Verify all CopyableText instances remain readable.

- [ ] **Step 5: Stop dev server**

Stop the background `pnpm dev` process.

---

### Task 2.4: Commit the IntaShell changes

- [ ] **Step 1: Inspect the diff**

```cmd
cd /d F:\github\Astrbot && git diff dashboard\src\components\chat\message_list_comps\IntaShellToolResultView.vue
```
Expected: only the IntaShell file appears in `git status`. Verify the diff makes sense (no unrelated changes).

- [ ] **Step 2: Commit**

```cmd
cd /d F:\github\Astrbot && git add dashboard\src\components\chat\message_list_comps\IntaShellToolResultView.vue && git commit -m "refactor(dashboard): replace inline SessionIdCopy with CopyableText in inta_shell view"
```

---

### Task 2.5: Rollback checkpoint

> **Before proceeding to Chunk 3, the executor MUST validate the pilot in Task 2.3. If any of the hand-tests failed in a way that requires non-trivial component changes, ROLLBACK the IntaShell commit and fix the component first.**

- [ ] **Step 1: Decide: proceed or rollback**

Review Task 2.3 results. If all 4 sub-steps passed, mark this task complete and move to Chunk 3. If any sub-step failed with a component bug (e.g., icon clipped, i18n key not resolving, async race condition):
- [ ] **Step 2 (only if rollback needed): Revert the IntaShell commit**

```cmd
cd /d F:\github\Astrbot && git revert --no-edit HEAD
git revert --no-edit HEAD~1
```
Or, if easier:
```cmd
cd /d F:\github\Astrbot && git reset --hard HEAD~1
```
Then fix the `CopyableText` component, re-run the Chunk 1 pilot test (Task 1.3), then re-do Chunk 2.

- [ ] **Step 3: Proceed to Chunk 3**

Move on only when Task 2.3 passed.

---

## Chunk 3: Horizontal rollout (5 files, all small changes)

> **Goal:** Apply the proven `CopyableText` pattern to the remaining 5 small/medium files. These are all mechanical replacements of `<span class="...-value">` etc. with `<CopyableText :value="..." mode="..." class="..." />`.

### Task 3.1: `ToolCallCard.vue` — args value

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/ToolCallCard.vue`

- [ ] **Step 1: Add `CopyableText` import**

Open `ToolCallCard.vue`. Find the existing import block (it has `import { computed, onMounted, onUnmounted, reactive, ref } from "vue";` and `import DiffPreview from "./DiffPreview.vue";`). Add the CopyableText import next to the other local component imports:

```ts
import CopyableText from "./__shared__/CopyableText.vue";
```

- [ ] **Step 2: Replace `<span class="args-value">` for entries**

Find (inside the `v-for="(entry, i) in displayedArgEntries"` loop):
```vue
<span class="args-value">{{ entry.display }}</span>
```
Replace with:
```vue
<CopyableText
  :value="entry.raw"
  :display-value="entry.display"
  mode="code"
  class="args-value"
  :show-icon="entry.long"
/>
```

**Important:** Do NOT touch the `<span class="args-value args-more-text">` block on the `+N more` / `Show fewer` row — that's a label, not data. Find the marker `args-more-text` to confirm.

- [ ] **Step 3: Update `.args-table` CSS to `overflow: visible`**

Find the CSS block for `.args-table` (in the `<style scoped>` section, marker: `.args-table {`). It currently has:
```css
overflow: hidden;
```
Change to:
```css
overflow: visible;
```

This is the one CSS change required to prevent the hover icon from being clipped by the args table's rounded border. (See spec §4.2 "position: absolute vs overflow: hidden".)

- [ ] **Step 4: Verify typecheck and lint**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm typecheck && pnpm lint
```
Check `git status --short` — only `ToolCallCard.vue` should be modified.

- [ ] **Step 5: Commit**

```cmd
cd /d F:\github\Astrbot && git add dashboard\src\components\chat\message_list_comps\ToolCallCard.vue && git commit -m "feat(dashboard): make ToolCallCard args value copyable"
```

---

### Task 3.2: `EsSearchResult.vue` — item name & path

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/spcode_tools/EsSearchResult.vue`

- [ ] **Step 1: Add `CopyableText` import**

Find the existing `import { computed, reactive } from "vue";` block. Add after the existing component imports (this file has none yet):

```ts
import CopyableText from "../__shared__/CopyableText.vue";
```

- [ ] **Step 2: Replace item name and path spans**

Find:
```vue
<span class="item-name">{{ item.name }}</span>
<span v-if="item.path" class="item-path">{{ item.path }}</span>
```
Replace with:
```vue
<CopyableText :value="item.name" mode="inline" class="item-name" />
<CopyableText v-if="item.path" :value="item.path" mode="code" class="item-path" />
```

- [ ] **Step 3: Verify and commit**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm typecheck && pnpm lint
cd /d F:\github\Astrbot && git add dashboard\src\components\chat\message_list_comps\spcode_tools\EsSearchResult.vue && git commit -m "feat(dashboard): make es_search item name/path copyable"
```

---

### Task 3.3: `CodeExploreResult.vue` — symbol & callers

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/spcode_tools/CodeExploreResult.vue`

- [ ] **Step 1: Add `CopyableText` import**

```ts
import CopyableText from "../__shared__/CopyableText.vue";
```

- [ ] **Step 2: Replace symbol header spans**

Find:
```vue
<span class="symbol-name">{{ sym.name }}</span>
<span v-if="sym.file" class="symbol-loc">{{ sym.file }}:{{ sym.line }}</span>
```
Replace with:
```vue
<CopyableText :value="sym.name" mode="inline" class="symbol-name" />
<CopyableText v-if="sym.file" :value="`${sym.file}:${sym.line}`" mode="code" class="symbol-loc" />
```

- [ ] **Step 3: Replace caller chips**

Find:
```vue
<code v-for="c in data.callers[sym.name]" :key="c" class="caller-chip">{{ c }}</code>
```
Replace with:
```vue
<CopyableText
  v-for="c in data.callers[sym.name]"
  :key="c"
  :value="c"
  mode="code"
  class="caller-chip"
/>
```

- [ ] **Step 4: Verify and commit**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm typecheck && pnpm lint
cd /d F:\github\Astrbot && git add dashboard\src\components\chat\message_list_comps\spcode_tools\CodeExploreResult.vue && git commit -m "feat(dashboard): make code_explore symbol/callers copyable"
```

---

### Task 3.4: `CodeCheckResult.vue` & `CodeCheckResultList.vue` — issue rows

> These two files have **identical** modifications. Apply the same edits to both.

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/spcode_tools/CodeCheckResult.vue`
- Modify: `dashboard/src/components/chat/message_list_comps/spcode_tools/CodeCheckResultList.vue`

- [ ] **Step 1: Add `CopyableText` import to both files**

In each file, add:
```ts
import CopyableText from "../__shared__/CopyableText.vue";
```

- [ ] **Step 2: Replace issue three-piece in `CodeCheckResult.vue`**

Find (inside the `v-for="(iss, i) in displayedIssues"` loop):
```vue
<span class="issue-loc">{{ getLocText(iss) }}</span>
<span v-if="getCode(iss)" class="issue-code">{{ getCode(iss) }}</span>
<span class="issue-msg">{{ getMessage(iss) }}</span>
```
Replace with:
```vue
<CopyableText :value="getLocText(iss)" mode="code" class="issue-loc" />
<CopyableText v-if="getCode(iss)" :value="getCode(iss)" mode="code" class="issue-code" />
<CopyableText :value="getMessage(iss)" mode="block" :multiline="true" class="issue-msg" />
```

- [ ] **Step 3: Apply the SAME edit to `CodeCheckResultList.vue`**

The same three lines exist in `CodeCheckResultList.vue` (in its `v-for="(iss, i) in displayedIssues"` loop). Apply the exact same replacement. **Do not skip this file** — it's the most common oversight.

- [ ] **Step 4: Verify and commit (separate commits per file)**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm typecheck && pnpm lint
cd /d F:\github\Astrbot && git add dashboard\src\components\chat\message_list_comps\spcode_tools\CodeCheckResult.vue dashboard\src\components\chat\message_list_comps\spcode_tools\CodeCheckResultList.vue && git commit -m "feat(dashboard): make code_check issue rows copyable (loc/code/msg)"
```

---

### Task 3.5: Hand-test Chunk 3 changes (5 files)

**Files:** none

- [ ] **Step 1: Run dev server and trigger each tool type**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm dev
```

In the browser, trigger tool calls of each type and verify:
- `ToolCallCard` (any tool with args): long arg shows icon on hover; click copies full raw text (not the truncated 60-char display); clicking the row outside the button still toggles expand.
- `EsSearchResult`: file name and path are copyable; row click-to-expand still works.
- `CodeExploreResult`: symbol name + location are copyable; caller chips are copyable.
- `CodeCheckResult` + `CodeCheckResultList`: issue L? / code / message are copyable; row click-to-expand still shows context and JSON detail.

For each, also verify dark mode and Tab+Enter keyboard accessibility.

- [ ] **Step 2: Stop dev server**

```cmd
(Ctrl+C in the background dev server shell)
```

- [ ] **Step 3: Final verification**

```cmd
cd /d F:\github\Astrbot && git log -5 --oneline
```
Expected: at least 4 new commits (ToolCallCard, EsSearchResult, CodeExploreResult, CodeCheckResult+List). If any commit is missing, find the uncommitted changes and commit them.

---

## Chunk 4: Big block changes (ToolResultView, IPythonToolBlock)

> **Goal:** Apply `CopyableText` to the big code/result blocks that need the `default` slot (so the existing Shiki/pre rendering is preserved). Also add the two new high-value copy targets identified in spec review (file path header, grep file path).

### Task 4.1: `ToolResultView.vue` — new copy targets + block wrapping

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/ToolResultView.vue`

- [ ] **Step 1: Add `CopyableText` import**

Find the existing import block (it has `import SpcodeToolResultView` and `import IntaShellToolResultView`). Add:

```ts
import CopyableText from "./__shared__/CopyableText.vue";
```

- [ ] **Step 2: Replace `<span class="result-header-text">` for `file_read_tool`**

Find (inside the `v-if="toolName === 'astrbot_file_read_tool'"` branch):
```vue
<span class="result-header-text">{{ readFilePath }}</span>
```
Replace with:
```vue
<CopyableText :value="readFilePath" mode="code" class="result-header-text" />
```

- [ ] **Step 3: Replace `<span class="grep-file">` in grep results**

Find (inside the `v-else-if="toolName === 'astrbot_grep_tool'"` branch, in the `v-for="(line, i) in grepLines"` loop):
```vue
<span v-if="line.file" class="grep-file">{{ line.file }}</span>
```
Replace with:
```vue
<CopyableText v-if="line.file" :value="line.file" mode="code" class="grep-file" />
```

- [ ] **Step 4: Wrap `file_read_tool` code block in CopyableText with default slot (use `bare` to avoid doubled chrome)**

Find:
```vue
<div
  v-if="shikiReady && detectedLanguage !== 'text'"
  class="result-code result-code-shiki"
  v-html="highlightedCode"
></div>
<pre v-else class="result-code">{{ readFileContent }}</pre>
```
Replace with:
```vue
<CopyableText
  :value="readFileContent"
  mode="block"
  :multiline="true"
  bare
>
  <div
    v-if="shikiReady && detectedLanguage !== 'text'"
    class="result-code result-code-shiki"
    v-html="highlightedCode"
  ></div>
  <pre v-else class="result-code">{{ readFileContent }}</pre>
</CopyableText>
```

> The `bare` prop (added in Chunk 1 / Task 1.2) drops the wrapper's own background/padding/border-radius so the inner `.result-code` / `.result-code-shiki` keeps its own visual treatment without doubled layers. The 24px right padding for the copy button is preserved.

- [ ] **Step 5: Wrap shell stdout in CopyableText with default slot (use `bare`)**

Find:
```vue
<pre class="shell-value" v-text="shellStdout"></pre>
```
Replace with:
```vue
<CopyableText
  :value="shellStdout"
  mode="block"
  :multiline="true"
  bare
>
  <pre class="shell-value" v-text="shellStdout"></pre>
</CopyableText>
```

- [ ] **Step 6: Wrap shell stderr in CopyableText with default slot (use `bare`)**

Find:
```vue
<pre v-if="shellStderr" class="shell-value shell-stderr-text" v-text="shellStderr"></pre>
```
Replace with:
```vue
<CopyableText
  v-if="shellStderr"
  :value="shellStderr"
  mode="block"
  :multiline="true"
  bare
>
  <pre class="shell-value shell-stderr-text" v-text="shellStderr"></pre>
</CopyableText>
```

- [ ] **Step 7: Wrap python / ipython / fallback blocks in CopyableText with default slot (use `bare`)**

Find (in the `v-else-if="toolName === 'astrbot_execute_python' || ..."` branch):
```vue
<pre class="result-terminal" v-text="resultText"></pre>
```
Replace with:
```vue
<CopyableText
  :value="resultText"
  mode="block"
  :multiline="true"
  bare
>
  <pre class="result-terminal" v-text="resultText"></pre>
</CopyableText>
```

Find (in the `v-else` fallback branch):
```vue
<pre class="result-raw">{{ formattedResult }}</pre>
```
Replace with:
```vue
<CopyableText
  :value="formattedResult"
  mode="block"
  :multiline="true"
  bare
>
  <pre class="result-raw">{{ formattedResult }}</pre>
</CopyableText>
```

- [ ] **Step 8: Wrap `result-suffix` ([SYSTEM NOTICE] suffix) in CopyableText (use `bare`)**

Find:
```vue
<div v-if="resultSuffix && toolName !== 'astrbot_execute_shell' && !isIntaShellTool" class="result-suffix">{{ resultSuffix }}</div>
```
Replace with:
```vue
<CopyableText
  v-if="resultSuffix && toolName !== 'astrbot_execute_shell' && !isIntaShellTool"
  :value="resultSuffix"
  mode="block"
  :multiline="true"
  bare
  class="result-suffix"
/>
```

> The existing `.result-suffix` class has its own dim/italic styling (`color: rgba(..., 0.55)`, `font-style: italic`, etc.). Without `bare`, CopyableText's `.copyable-block` would override the color to 0.8 (brighter) and add its own background/padding (doubled). The `bare` prop lets `.result-suffix` keep its visual treatment intact.

- [ ] **Step 9: NO new CSS needed**

The `bare` prop handles all the visual chrome concerns. There is no `.result-code-wrap` CSS rule. (The previous draft had a no-op `:deep(.copyable-text) { padding: 0 }` rule that targeted a fallback element not used in the slot path — the `bare` prop supersedes this approach entirely.)

Skip to Step 10.

- [ ] **Step 10: Verify typecheck and lint**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm typecheck && pnpm lint
```
Check `git status --short` — only `ToolResultView.vue` modified.

- [ ] **Step 11: Commit**

```cmd
cd /d F:\github\Astrbot && git add dashboard\src\components\chat\message_list_comps\ToolResultView.vue && git commit -m "feat(dashboard): make ToolResultView code/result blocks and high-value paths copyable"
```

---

### Task 4.2: `IPythonToolBlock.vue` — code/result wrapping

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/IPythonToolBlock.vue`

- [ ] **Step 1: Add `CopyableText` import**

Find the existing import block. Add:

```ts
import CopyableText from "./__shared__/CopyableText.vue";
```

- [ ] **Step 2: Wrap code section in CopyableText (use `bare` + `show-icon` toggle for empty code)**

Find:
```vue
<div class="code-section">
  <div
    v-if="shikiReady && code"
    class="code-highlighted code-result-shiki"
    v-html="highlightedCode"
  ></div>
  <pre v-else class="code-fallback">{{ code || 'No code available' }}</pre>
</div>
```
Replace with:
```vue
<div class="code-section">
  <CopyableText
    :value="code"
    mode="block"
    :multiline="true"
    bare
    :show-icon="!!code"
  >
    <div
      v-if="shikiReady && code"
      class="code-highlighted code-result-shiki"
      v-html="highlightedCode"
    ></div>
    <pre v-else class="code-fallback">{{ code || 'No code available' }}</pre>
  </CopyableText>
</div>
```

> When `code` is empty: `:value="code"` is `""` so the button is hidden (via `:show-icon="!!code"`). No zero-width space pollution. The inner `<pre>` still shows "No code available" without a copy button. The CopyableText's `displayedText` placeholder is **bypassed** when a default slot is provided (the template renders the slot via `<div class="copyable-slot">`, not the `.copyable-text` span), so the placeholder "—" is not shown in this case. The user sees only the inner `<pre>No code available</pre>` with no surrounding chrome and no copy button.

- [ ] **Step 3: Wrap result section in CopyableText (use `bare`)**

Find:
```vue
<div v-if="result" class="result-section">
  <div class="result-label">
    {{ tm('ipython.output') }}:
  </div>
  <pre class="result-content">{{ formattedResult }}</pre>
  <div v-if="resultNotice" class="result-suffix">{{ resultNotice }}</div>
</div>
```
Replace with:
```vue
<div v-if="result" class="result-section">
  <div class="result-label">
    {{ tm('ipython.output') }}:
  </div>
  <CopyableText
    :value="formattedResult"
    mode="block"
    :multiline="true"
    bare
  >
    <pre class="result-content">{{ formattedResult }}</pre>
  </CopyableText>
  <CopyableText
    v-if="resultNotice"
    :value="resultNotice"
    mode="block"
    :multiline="true"
    bare
    class="result-suffix"
  />
</div>
```

- [ ] **Step 4: NO new CSS needed**

The `bare` prop handles all visual chrome concerns. The previous draft's `.result-code-wrap :deep(.copyable-text) { padding: 0 }` rule was a no-op (targeted the fallback span, not the slot wrapper) and is no longer needed.

Skip to Step 5.

- [ ] **Step 5: Verify typecheck and lint**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm typecheck && pnpm lint
```

- [ ] **Step 6: Commit**

```cmd
cd /d F:\github\Astrbot && git add dashboard\src\components\chat\message_list_comps\IPythonToolBlock.vue && git commit -m "feat(dashboard): make IPythonToolBlock code/result blocks copyable"
```

---

### Task 4.3: Hand-test Chunk 4 changes (2 files)

**Files:** none

- [ ] **Step 1: Run dev server and trigger each big-block tool type**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm dev
```

In the browser, trigger tool calls:
- `file_read_tool`: the file path in the header should be copyable; the code body should be copyable (preserves Shiki rendering, copies plain text on click).
- `grep_tool`: each per-line file path should be copyable.
- `shell` (`astrbot_execute_shell`): stdout, stderr, exit code are all copyable.
- `python` / `ipython` (`astrbot_execute_python` / `astrbot_execute_ipython`): the output is copyable; the source code (in ipython) is copyable.
- The `[SYSTEM NOTICE]` suffix at the bottom of any tool result is copyable.
- Fallback (any unknown tool): the raw result is copyable.

For each, also verify dark mode and Tab+Enter.

- [ ] **Step 2: Verify Shiki highlight doesn't break**

For `file_read_tool` on a `.py` or `.ts` file, confirm that:
- The code is syntax-highlighted (Shiki still works)
- The text is selectable
- The copy button is in the top-right corner and doesn't overlap with the first line of code

- [ ] **Step 3: Stop dev server**

Stop the background `pnpm dev`.

---

## Chunk 5: Final cleanup & verification

### Task 5.1: Full build smoke test

**Files:** none

- [ ] **Step 1: Run full build**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm build
```
Expected: exits 0. The build script runs `vue-tsc --noEmit && vite build`, so a successful build means typecheck + bundle both pass.

If it fails:
- Read the error output
- If it's a type error in CopyableText, fix the component
- If it's a bundler error, check that all new imports resolve
- If it's a CSS error, check the `.copyable-block.is-bare` rule in `CopyableText.vue`

- [ ] **Step 2: Verify the 8 target files all show in the diff**

```cmd
cd /d F:\github\Astrbot && git log --stat -10 --oneline
```
Expected: at least these commits, in order:
1. `i18n` keys commit
2. `CopyableText` component commit
3. `IntaShellToolResultView` commit
4. `ToolCallCard` commit
5. `EsSearchResult` commit
6. `CodeExploreResult` commit
7. `CodeCheckResult + CodeCheckResultList` commit (1 commit)
8. `ToolResultView` commit
9. `IPythonToolBlock` commit

- [ ] **Step 3: Final lint pass**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm lint
```
Expected: 0 errors. Auto-fix side effects already handled in each chunk's verify step.

---

### Task 5.2: Full hand-test matrix (spec §7.1)

> Re-verify the entire spec §7.1 matrix (18 cases). Use the dev server.

- [ ] **Step 1: Start dev server**

```cmd
cd /d F:\github\Astrbot\dashboard && pnpm dev
```

- [ ] **Step 2: Walk through spec §7.1 cases 1-18**

Open the spec file and walk through each of the 18 hand-test cases. Mark each ✓ or ✗ in your own notes.

Key cases to revisit (in case Chunk 2-4 refactoring regressed them):
- Case 9: copy session_id in inta_shell — verify 8-char truncation display is preserved AND clipboard contains the full id
- Case 11: copy Shiki-rendered code body — verify clipboard contains the original source (not HTML)
- Case 12: copy file_read_tool header path
- Case 13: copy grep result's `line.file`
- Cases 17-18: keyboard accessibility (Tab + Enter)

- [ ] **Step 3: Stop dev server**

---

### Task 5.3: Update spec status & commit

- [ ] **Step 1: Update the spec file's status line**

Open `docs/superpowers/specs/2026-06-28-tool-result-card-copyable-design.md` and change:
```markdown
| 状态 | Draft — 待用户审阅 |
```
to:
```markdown
| 状态 | Implemented — 2026-06-28 |
```

- [ ] **Step 2: Commit the status update**

```cmd
cd /d F:\github\Astrbot && git add docs\superpowers\specs\2026-06-28-tool-result-card-copyable-design.md && git commit -m "docs(spec): mark copyable design as implemented"
```

- [ ] **Step 3: Final summary**

Print a summary:
- Total commits added: (run `git log --oneline -10` and count new ones)
- Files modified: (run `git diff --stat <first-commit>~1 HEAD` and count)
- DoD checklist (from spec §10):
  - [x] 8 files transformed
  - [x] §7.1 hand-test matrix all pass
  - [x] `pnpm lint` / `pnpm typecheck` / `pnpm build` all pass
  - [x] Dark mode no regressions
  - [x] i18n 3 locales updated
  - [x] Inline `SessionIdCopy` deleted
  - [x] `pnpm dev` no console warnings
  - [x] `.args-table` overflow visible

**Implementation complete.**
---


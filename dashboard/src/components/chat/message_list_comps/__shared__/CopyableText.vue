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
    :class="['copyable', 'copyable-inline', { 'is-empty': !displayedText }]"
    :title="title || undefined"
  >
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
    <span class="copyable-text">{{ displayedText }}</span>
  </span>

  <span
    v-else-if="mode === 'code'"
    :class="['copyable', 'copyable-code', { 'is-empty': !displayedText }]"
    :title="title || undefined"
  >
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
    <span class="copyable-text">{{ displayedText }}</span>
  </span>

  <div
    v-else
    :class="[
      'copyable',
      'copyable-block',
      {
        'is-empty': !displayedText,
        'is-multiline': multiline,
        'is-bare': bare,
      },
    ]"
    :title="title || undefined"
  >
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
    <div v-if="$slots.default" class="copyable-slot">
      <slot />
    </div>
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

const displayedText = computed(() => {
  if (props.value) return props.displayValue ?? props.value;
  return props.placeholder;
});

const showCopyIcon = computed(() => props.showIcon && !!props.value);

const copied = ref(false);
let resetTimer: ReturnType<typeof setTimeout> | null = null;

async function handleCopy() {
  // MUST await: copyToClipboard is async; flipping copied=true before
  // the promise resolves would mislead users on failure.
  const ok = await copyToClipboard(props.value);
  if (!ok) {
    return; // silent fail
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

/* inline: stays inline, reserves right padding for icon */
.copyable-inline {
  padding-right: 18px;
  cursor: text;
}
.copyable-inline .copyable-text {
  white-space: pre-wrap;
  word-break: break-word;
}

/* code: monospace chip, icon top-right */
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

/* block: block-level, icon top-right, supports slot */
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

/* copy button (corner, hover-revealed) */
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
.copyable:hover .copyable-btn,
.copyable:focus-within .copyable-btn,
.copyable-btn:focus-visible {
  opacity: 1;
}

/* inline + code: button is in-flow within reserved right padding */
.copyable-inline .copyable-btn,
.copyable-code .copyable-btn {
  position: absolute;
  top: 50%;
  right: 0;
  transform: translateY(-50%);
}
</style>